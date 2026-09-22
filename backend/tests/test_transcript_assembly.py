"""Transcript assembly: attribution, merging, overlap and role attribution."""

from __future__ import annotations

from app.models.enums import SpeakerRole
from app.services.transcript_assembly import (
    SpeakerRoleAttributionService,
    TranscriptAssemblyService,
)
from app.services.types import ASRSegment, DiarizationTurn

assembler = TranscriptAssemblyService()


def test_asr_and_diarization_are_merged_into_speaker_attributed_segments() -> None:
    asr = [ASRSegment(id="asr_1", text="What brings you in today?", start_time=12.3, end_time=15.8, confidence=0.96)]
    turns = [DiarizationTurn(speaker_id="speaker_0", start_time=12.0, end_time=16.0, confidence=0.94)]

    segments = assembler.assemble(asr, turns, roles={"speaker_0": SpeakerRole.DOCTOR})

    assert len(segments) == 1
    segment = segments[0]
    assert segment.ref == "seg_001"
    assert segment.speaker_label == "speaker_0"
    assert segment.role is SpeakerRole.DOCTOR
    assert segment.start_time == 12.3
    assert segment.end_time == 15.8
    assert 0.9 <= segment.confidence <= 1.0


def test_segment_refs_continue_across_batches() -> None:
    asr = [ASRSegment(id="a", text="Any shortness of breath?", start_time=0.0, end_time=2.0, confidence=0.9)]
    turns = [DiarizationTurn(speaker_id="speaker_0", start_time=0.0, end_time=2.0, confidence=0.9)]
    segments = assembler.assemble(asr, turns, start_index=7)
    assert segments[0].ref == "seg_008"


def test_overlapping_speech_is_flagged_and_confidence_reduced() -> None:
    asr = [ASRSegment(id="a", text="I have chest pain doctor", start_time=1.0, end_time=4.0, confidence=0.9)]
    turns = [
        DiarizationTurn(speaker_id="speaker_1", start_time=1.0, end_time=3.6, confidence=0.9),
        DiarizationTurn(speaker_id="speaker_0", start_time=2.0, end_time=4.0, confidence=0.85),
    ]
    segment = assembler.assemble(asr, turns)[0]
    assert segment.overlapping is True
    assert segment.speaker_label == "speaker_1"


def test_fragmented_asr_output_is_merged_for_the_same_speaker() -> None:
    asr = [
        ASRSegment(id="a", text="I've been having chest discomfort", start_time=0.0, end_time=2.0, confidence=0.9),
        ASRSegment(id="b", text="since yesterday", start_time=2.2, end_time=3.0, confidence=0.88),
    ]
    turns = [DiarizationTurn(speaker_id="speaker_1", start_time=0.0, end_time=3.0, confidence=0.93)]
    segments = assembler.assemble(asr, turns)
    assert len(segments) == 1
    assert segments[0].text == "I've been having chest discomfort since yesterday"
    assert segments[0].end_time == 3.0


def test_different_speakers_are_never_merged() -> None:
    asr = [
        ASRSegment(id="a", text="Any pain?", start_time=0.0, end_time=1.0, confidence=0.95),
        ASRSegment(id="b", text="Yes a bit", start_time=1.1, end_time=2.0, confidence=0.9),
    ]
    turns = [
        DiarizationTurn(speaker_id="speaker_0", start_time=0.0, end_time=1.05, confidence=0.95),
        DiarizationTurn(speaker_id="speaker_1", start_time=1.05, end_time=2.0, confidence=0.92),
    ]
    segments = assembler.assemble(asr, turns)
    assert [segment.speaker_label for segment in segments] == ["speaker_0", "speaker_1"]


def test_missing_diarization_falls_back_to_unknown_speaker() -> None:
    asr = [ASRSegment(id="a", text="Hello there", start_time=0.0, end_time=1.0, confidence=0.9)]
    segment = assembler.assemble(asr, [])[0]
    assert segment.speaker_label == "unknown"
    assert segment.role is SpeakerRole.UNKNOWN
    assert segment.diarization_confidence == 0.0
    assert segment.confidence < 0.9


def test_segments_are_sorted_chronologically() -> None:
    asr = [
        ASRSegment(id="b", text="Second utterance here.", start_time=5.0, end_time=6.0, confidence=0.9),
        ASRSegment(id="a", text="First utterance here.", start_time=1.0, end_time=2.0, confidence=0.9),
    ]
    turns = [
        DiarizationTurn(speaker_id="speaker_0", start_time=1.0, end_time=2.0, confidence=0.9),
        DiarizationTurn(speaker_id="speaker_1", start_time=5.0, end_time=6.0, confidence=0.9),
    ]
    segments = assembler.assemble(asr, turns)
    assert [segment.start_time for segment in segments] == [1.0, 5.0]


def test_role_attribution_scores_doctor_and_patient() -> None:
    service = SpeakerRoleAttributionService()
    doctor_role, doctor_confidence = service.score(
        ["What brings you in today?", "Can you describe the discomfort?", "Any shortness of breath?"]
    )
    patient_role, patient_confidence = service.score(
        ["I've been having chest discomfort since yesterday evening.", "I'm taking metformin."]
    )
    assert doctor_role is SpeakerRole.DOCTOR
    assert patient_role is SpeakerRole.PATIENT
    assert doctor_confidence > 0.5 and patient_confidence > 0.5


def test_role_attribution_returns_unknown_without_signal() -> None:
    role, confidence = SpeakerRoleAttributionService().score(["Mmm.", "Okay."])
    assert role is SpeakerRole.UNKNOWN
    assert confidence == 0.0
