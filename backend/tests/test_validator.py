"""AI output validation: nothing unsupported reaches the database."""

from __future__ import annotations

from app.models.enums import EntityStatus, EntityType
from app.services.llm.schemas import (
    ExtractedEntity,
    GeneratedNote,
    GeneratedSection,
    NoteUpdate,
)
from app.services.llm.validator import OutputValidator

validator = OutputValidator()

VALID_REFS = {"seg_001", "seg_002", "seg_003"}
SEGMENT_TEXTS = {
    "seg_001": "Good morning. What brings you in today?",
    "seg_002": "I've been having chest discomfort since yesterday evening.",
    "seg_003": "No, I don't have any shortness of breath.",
}


def entity(**overrides) -> ExtractedEntity:
    payload = {
        "entity_type": EntityType.SYMPTOM,
        "value": "chest discomfort",
        "status": EntityStatus.PRESENT,
        "confidence": 0.9,
        "source_segment_ids": ["seg_002"],
    }
    payload.update(overrides)
    return ExtractedEntity(**payload)


def validate(entities: list[ExtractedEntity], rule_statuses=None):
    return validator.validate_entities(
        entities,
        valid_segment_refs=VALID_REFS,
        segment_texts=SEGMENT_TEXTS,
        rule_statuses=rule_statuses or {},
    )


def test_entity_with_valid_evidence_is_accepted() -> None:
    result = validate([entity()])
    assert len(result.entities) == 1
    assert result.dropped == 0


def test_entity_with_nonexistent_segment_id_is_dropped() -> None:
    result = validate([entity(source_segment_ids=["seg_999"])])
    assert result.entities == []
    assert result.dropped == 1
    assert result.review_required is True


def test_malformed_segment_ids_are_discarded() -> None:
    result = validate([entity(source_segment_ids=["not-a-ref", "seg_002"])])
    assert result.entities[0].source_segment_ids == ["seg_002"]
    assert any("malformed" in issue.message for issue in result.issues)


def test_confidence_outside_range_is_clamped() -> None:
    result = validate([entity(confidence=1.0)])
    assert result.entities[0].confidence == 1.0

    unchecked = ExtractedEntity.model_construct(
        entity_type=EntityType.SYMPTOM,
        value="fever",
        status=EntityStatus.PRESENT,
        confidence=4.2,
        source_segment_ids=["seg_002"],
        detail=None,
    )
    clamped = validate([unchecked])
    assert clamped.entities[0].confidence == 1.0


def test_rule_engine_negation_overrides_a_present_status() -> None:
    result = validate(
        [entity(value="shortness of breath", source_segment_ids=["seg_003"])],
        rule_statuses={"shortness of breath": EntityStatus.NEGATED},
    )
    assert result.entities[0].status is EntityStatus.NEGATED
    assert any("negation" in issue.message for issue in result.issues)


def test_ungrounded_value_is_flagged_but_kept() -> None:
    result = validate([entity(value="haemoptysis", source_segment_ids=["seg_001"])])
    assert len(result.entities) == 1
    assert any("verbatim" in issue.message for issue in result.issues)


def test_duplicate_entities_are_collapsed() -> None:
    result = validate([entity(), entity(value="Chest Discomfort")])
    assert len(result.entities) == 1


def note(**sections) -> NoteUpdate:
    def section(text: str, refs: list[str], confidence: float = 0.9) -> GeneratedSection:
        return GeneratedSection(text=text, confidence=confidence, source_segment_ids=refs)

    defaults = {
        "chief_complaint": section("Patient reports chest discomfort.", ["seg_002"]),
        "history_of_present_illness": section("Denies shortness of breath.", ["seg_003"]),
        "relevant_medical_history": section("Not mentioned", []),
        "assessment": section("Not mentioned", []),
        "plan": section("Not mentioned", []),
        "follow_up": section("Not mentioned", []),
    }
    defaults.update(sections)
    return NoteUpdate(note=GeneratedNote(**defaults), changed_sections=list(defaults), change_summary="test")


def test_documented_section_without_evidence_is_unsupported() -> None:
    result = validator.validate_note(
        note(assessment=GeneratedSection(text="Likely angina.", confidence=0.8, source_segment_ids=[])),
        valid_segment_refs=VALID_REFS,
    )
    assert "assessment" in result.unsupported_sections
    assert result.review_required is True


def test_section_with_nonexistent_evidence_is_unsupported() -> None:
    result = validator.validate_note(
        note(plan=GeneratedSection(text="Start aspirin.", confidence=0.8, source_segment_ids=["seg_777"])),
        valid_segment_refs=VALID_REFS,
    )
    assert "plan" in result.unsupported_sections


def test_advisory_language_is_rejected() -> None:
    result = validator.validate_note(
        note(
            assessment=GeneratedSection(
                text="I recommend starting aspirin.", confidence=0.9, source_segment_ids=["seg_002"]
            )
        ),
        valid_segment_refs=VALID_REFS,
    )
    assert "assessment" in result.unsupported_sections
    assert any("advisory" in issue.message for issue in result.issues)


def test_valid_note_passes_without_review() -> None:
    result = validator.validate_note(note(), valid_segment_refs=VALID_REFS)
    assert result.unsupported_sections == []
    assert result.review_required is False


def test_not_mentioned_sections_have_no_evidence() -> None:
    result = validator.validate_note(
        note(follow_up=GeneratedSection(text="Not mentioned", confidence=0.0, source_segment_ids=["seg_001"])),
        valid_segment_refs=VALID_REFS,
    )
    assert result.note.follow_up.source_segment_ids == []
