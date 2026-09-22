"""Note state engine: incremental merge, versioning, review gating, approval."""

from __future__ import annotations

import pytest

from app.models.enums import EntityStatus, EntityType, NoteStatus, SpeakerRole
from app.schemas.clinical import ClinicalEntityOut, ClinicalNoteContent
from app.services.evidence import EvidenceLinkingService, SegmentIndexEntry
from app.services.llm.schemas import GeneratedNote, GeneratedSection, NoteUpdate
from app.services.llm.validator import OutputValidator
from app.services.note_engine import NoteStateEngine, NoteStateError

engine = NoteStateEngine()
validator = OutputValidator()


def evidence_service() -> EvidenceLinkingService:
    service = EvidenceLinkingService()
    service.build_index(
        [
            SegmentIndexEntry(
                ref="seg_001",
                text="I've been having chest discomfort since yesterday evening.",
                speaker_label="speaker_1",
                role=SpeakerRole.PATIENT,
                start_time=4.2,
                end_time=8.4,
                confidence=0.94,
                segment_id="00000000-0000-0000-0000-000000000001",
            ),
            SegmentIndexEntry(
                ref="seg_002",
                text="No, I don't have any shortness of breath.",
                speaker_label="speaker_1",
                role=SpeakerRole.PATIENT,
                start_time=20.0,
                end_time=23.4,
                confidence=0.95,
                segment_id="00000000-0000-0000-0000-000000000002",
            ),
        ]
    )
    return service


def build_update(chief: str = "Patient reports chest discomfort since yesterday evening.", refs=("seg_001",)):
    def section(text: str, section_refs: list[str], confidence: float = 0.88) -> GeneratedSection:
        return GeneratedSection(text=text, confidence=confidence, source_segment_ids=section_refs)

    return NoteUpdate(
        note=GeneratedNote(
            chief_complaint=section(chief, list(refs)),
            history_of_present_illness=section("Denies shortness of breath.", ["seg_002"]),
            relevant_medical_history=section("Not mentioned", []),
            assessment=section("Not mentioned", []),
            plan=section("Not mentioned", []),
            follow_up=section("Not mentioned", []),
        ),
        changed_sections=["chief_complaint", "history_of_present_illness"],
        change_summary="initial",
    )


def entities() -> dict[str, list[ClinicalEntityOut]]:
    symptom = ClinicalEntityOut(
        id="1",
        ref="ent_001",
        entity_type=EntityType.SYMPTOM,
        value="chest discomfort",
        status=EntityStatus.PRESENT,
        confidence=0.9,
        source_segment_refs=["seg_001"],
    )
    return {"symptoms": [symptom], "medications": [], "allergies": [], "findings": [], "investigations": []}


def apply(current: ClinicalNoteContent, update: NoteUpdate, *, status=NoteStatus.PROCESSING, version=0):
    service = evidence_service()
    validated = validator.validate_note(update, valid_segment_refs=service.valid_refs)
    return engine.apply_ai_update(
        current=current,
        validated=validated,
        entities=entities(),
        evidence=service,
        current_status=status,
        version=version,
        model="test-model",
    )


def test_first_ai_update_produces_draft_with_evidence() -> None:
    outcome = apply(ClinicalNoteContent(), build_update())
    assert outcome.status is NoteStatus.DRAFT
    assert outcome.version == 1
    assert "chief_complaint" in outcome.changed_sections
    assert outcome.content.chief_complaint.evidence[0].transcript_segment_ref == "seg_001"
    assert outcome.content.symptoms[0].value == "chest discomfort"


def test_unchanged_content_does_not_create_a_new_version() -> None:
    first = apply(ClinicalNoteContent(), build_update())
    second = apply(first.content, build_update(), status=first.status, version=first.version)
    assert second.changed_sections == []
    assert second.version == first.version


def test_new_information_updates_only_affected_sections() -> None:
    first = apply(ClinicalNoteContent(), build_update())
    changed = build_update(chief="Patient reports intermittent chest pressure since yesterday evening.")
    second = apply(first.content, changed, status=first.status, version=first.version)
    assert second.changed_sections == ["chief_complaint"]
    assert second.version == first.version + 1


def test_unsupported_statement_forces_review_required() -> None:
    outcome = apply(ClinicalNoteContent(), build_update(chief="Patient has myocardial infarction.", refs=("seg_999",)))
    assert outcome.status is NoteStatus.REVIEW_REQUIRED
    assert outcome.content.chief_complaint.review_required is True
    assert any(flag["severity"] == "ERROR" for flag in outcome.review_flags)


def test_human_edited_section_is_not_overwritten_by_ai() -> None:
    first = apply(ClinicalNoteContent(), build_update())
    edited = engine.apply_human_edit(
        current=first.content,
        changes={"chief_complaint": "Intermittent central chest pressure since yesterday evening."},
        version=first.version,
        editor="Dr. Reviewer",
    )
    assert edited.content.chief_complaint.edited_by_human is True

    after_ai = apply(
        edited.content,
        build_update(chief="Patient reports chest discomfort."),
        status=edited.status,
        version=edited.version,
    )
    assert after_ai.content.chief_complaint.text.startswith("Intermittent central chest pressure")
    assert any(flag["reason"].startswith("AI update skipped") for flag in after_ai.review_flags)


def test_documented_section_is_not_replaced_by_not_mentioned() -> None:
    first = apply(ClinicalNoteContent(), build_update())
    blanked = build_update()
    blanked.note.chief_complaint = GeneratedSection(text="Not mentioned", confidence=0.0, source_segment_ids=[])
    second = apply(first.content, blanked, status=first.status, version=first.version)
    assert second.content.chief_complaint.text.startswith("Patient reports chest discomfort")


def test_approval_requires_acknowledgement_and_a_reviewer() -> None:
    first = apply(ClinicalNoteContent(), build_update())
    with pytest.raises(NoteStateError):
        engine.approve(
            content=first.content, current_status=first.status, version=first.version, approver="Dr. A", acknowledged=False
        )
    with pytest.raises(NoteStateError):
        engine.approve(
            content=first.content, current_status=first.status, version=first.version, approver="", acknowledged=True
        )

    approved = engine.approve(
        content=first.content,
        current_status=first.status,
        version=first.version,
        approver="Dr. A",
        acknowledged=True,
    )
    assert approved.status is NoteStatus.APPROVED


def test_processing_note_cannot_be_approved() -> None:
    with pytest.raises(NoteStateError):
        engine.approve(
            content=ClinicalNoteContent(),
            current_status=NoteStatus.PROCESSING,
            version=0,
            approver="Dr. A",
            acknowledged=True,
        )


def test_flagged_sections_block_approval() -> None:
    flagged = apply(ClinicalNoteContent(), build_update(chief="Unsupported claim.", refs=("seg_999",)))
    with pytest.raises(NoteStateError) as excinfo:
        engine.approve(
            content=flagged.content,
            current_status=flagged.status,
            version=flagged.version,
            approver="Dr. A",
            acknowledged=True,
        )
    assert "flagged" in str(excinfo.value)


def test_illegal_transition_is_rejected() -> None:
    assert engine.can_transition(NoteStatus.DRAFT, NoteStatus.APPROVED) is True
    assert engine.can_transition(NoteStatus.PROCESSING, NoteStatus.APPROVED) is False
    with pytest.raises(NoteStateError):
        engine.transition(NoteStatus.PROCESSING, NoteStatus.EXPORTED)


def test_export_marks_approved_note_as_exported() -> None:
    outcome = engine.mark_exported(
        content=ClinicalNoteContent(), current_status=NoteStatus.APPROVED, version=3, fmt="JSON"
    )
    assert outcome.status is NoteStatus.EXPORTED


def test_ai_update_after_approval_reopens_the_note() -> None:
    first = apply(ClinicalNoteContent(), build_update())
    approved = engine.approve(
        content=first.content, current_status=first.status, version=first.version, approver="Dr. A", acknowledged=True
    )
    reopened = apply(
        approved.content,
        build_update(chief="Patient reports chest pressure since yesterday evening."),
        status=approved.status,
        version=approved.version,
    )
    assert reopened.status is NoteStatus.DRAFT
