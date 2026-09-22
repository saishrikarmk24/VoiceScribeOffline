"""Evidence linking: every statement must resolve to a real transcript segment."""

from __future__ import annotations

from app.models.enums import SpeakerRole
from app.services.evidence import EvidenceLinkingService, SegmentIndexEntry


def build_service() -> EvidenceLinkingService:
    service = EvidenceLinkingService()
    service.build_index(
        [
            SegmentIndexEntry(
                ref="seg_001",
                text="Good morning. What brings you in today?",
                speaker_label="speaker_0",
                role=SpeakerRole.DOCTOR,
                start_time=0.0,
                end_time=3.4,
                confidence=0.97,
                segment_id="11111111-1111-1111-1111-111111111111",
            ),
            SegmentIndexEntry(
                ref="seg_002",
                text="I've been having chest discomfort since yesterday evening.",
                speaker_label="speaker_1",
                role=SpeakerRole.PATIENT,
                start_time=78.4,
                end_time=82.6,
                confidence=0.94,
                segment_id="22222222-2222-2222-2222-222222222222",
            ),
        ]
    )
    return service


def test_reference_expands_the_full_provenance_chain() -> None:
    reference = build_service().reference("seg_002")
    assert reference.validated is True
    assert reference.speaker_label == "speaker_1"
    assert reference.speaker_role == "PATIENT"
    assert reference.timestamp == 78.4
    assert reference.confidence == 0.94
    assert reference.source_text.startswith("I've been having chest discomfort")


def test_unknown_reference_is_rejected_with_a_reason() -> None:
    reference = build_service().reference("seg_099")
    assert reference.validated is False
    assert "does not exist" in (reference.validation_error or "")


def test_statement_without_valid_evidence_requires_review() -> None:
    service = build_service()
    linked = service.link(
        target_kind="SECTION",
        target_key="assessment",
        clinical_statement="Patient has an acute coronary syndrome.",
        refs=["seg_404"],
    )
    assert linked.review_required is True
    assert linked.missing_refs == ["seg_404"]


def test_statement_with_valid_evidence_does_not_require_review() -> None:
    service = build_service()
    linked = service.link(
        target_kind="SECTION",
        target_key="chief_complaint",
        clinical_statement="Patient reports chest discomfort since yesterday evening.",
        refs=["seg_002", "seg_002"],
    )
    assert linked.review_required is False
    assert len(linked.evidence) == 1  # duplicates collapsed
    assert service.segment_id_for("seg_002") == "22222222-2222-2222-2222-222222222222"


def test_valid_refs_and_segment_texts_feed_the_validator() -> None:
    service = build_service()
    assert service.valid_refs == {"seg_001", "seg_002"}
    assert "chest discomfort" in service.segment_texts()["seg_002"]
