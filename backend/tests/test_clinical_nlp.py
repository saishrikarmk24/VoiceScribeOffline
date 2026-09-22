"""Rule-based extraction over the reference demo conversation."""

from __future__ import annotations

from app.models.enums import EntityStatus, EntityType, SpeakerRole
from app.services.demo.conversations import CHEST_DISCOMFORT_SCRIPT
from app.services.nlp import ClinicalNLPService
from app.services.types import AssembledSegment


def build_segments() -> list[AssembledSegment]:
    segments: list[AssembledSegment] = []
    cursor = 0.0
    for index, utterance in enumerate(CHEST_DISCOMFORT_SCRIPT.utterances, start=1):
        segments.append(
            AssembledSegment(
                ref=f"seg_{index:03d}",
                speaker_label=utterance.speaker_label,
                role=utterance.role,
                text=utterance.text,
                start_time=cursor,
                end_time=cursor + utterance.duration,
                confidence=utterance.confidence,
                asr_confidence=utterance.confidence,
                diarization_confidence=0.94,
            )
        )
        cursor += utterance.duration
    return segments


def extract() -> dict[tuple[EntityType, str], EntityStatus]:
    candidates = ClinicalNLPService().extract(build_segments())
    return {
        (candidate.entity_type, (candidate.normalized_value or candidate.value).lower()): candidate.status
        for candidate in candidates
    }


def test_expected_entities_from_reference_conversation() -> None:
    found = extract()
    assert found.get((EntityType.SYMPTOM, "chest discomfort")) is EntityStatus.PRESENT
    assert found.get((EntityType.SYMPTOM, "shortness of breath")) is EntityStatus.NEGATED
    assert found.get((EntityType.MEDICATION, "metformin")) is EntityStatus.PRESENT
    assert found.get((EntityType.ALLERGY, "no known drug allergies")) is EntityStatus.NEGATED
    assert (EntityType.CHARACTER, "pressure") in found
    assert any(key[0] is EntityType.DURATION and "yesterday evening" in key[1] for key in found)
    assert any(key[0] is EntityType.FREQUENCY and "comes and goes" in key[1] for key in found)


def test_no_diagnosis_is_invented() -> None:
    """The reference conversation contains no clinician-stated diagnosis."""
    found = extract()
    assert not [key for key in found if key[0] is EntityType.DIAGNOSIS_MENTIONED]


def test_every_candidate_carries_evidence() -> None:
    for candidate in ClinicalNLPService().extract(build_segments()):
        assert candidate.source_segment_refs, f"{candidate.value} has no evidence"
        assert all(ref.startswith("seg_") for ref in candidate.source_segment_refs)


def test_terminology_does_not_fabricate_codes() -> None:
    for candidate in ClinicalNLPService().extract(build_segments()):
        assert candidate.normalized_code is None


def test_plan_only_extracted_from_clinician_speech() -> None:
    nlp = ClinicalNLPService()
    patient_claim = AssembledSegment(
        ref="seg_001",
        speaker_label="speaker_1",
        role=SpeakerRole.PATIENT,
        text="I will start taking ibuprofen twice a day.",
        start_time=0.0,
        end_time=3.0,
        confidence=0.9,
        asr_confidence=0.9,
        diarization_confidence=0.9,
    )
    types = {candidate.entity_type for candidate in nlp.extract([patient_claim])}
    assert EntityType.PLAN not in types

    clinician = AssembledSegment(
        ref="seg_002",
        speaker_label="speaker_0",
        role=SpeakerRole.DOCTOR,
        text="I will arrange an ECG this afternoon.",
        start_time=3.0,
        end_time=6.0,
        confidence=0.95,
        asr_confidence=0.95,
        diarization_confidence=0.95,
    )
    types = {candidate.entity_type for candidate in nlp.extract([clinician])}
    assert EntityType.PLAN in types
    assert EntityType.INVESTIGATION in types
