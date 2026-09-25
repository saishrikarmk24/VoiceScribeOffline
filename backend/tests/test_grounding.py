"""Grounding: invented meds/diagnoses must not reach the note."""

from __future__ import annotations

from app.models.enums import EntityStatus, EntityType
from app.services.llm.grounding import (
    filter_ungrounded_entities,
    is_grounded,
    purge_note_hallucinations,
)
from app.services.llm.schemas import ExtractedEntity, GeneratedNote, GeneratedSection, NoteUpdate


def test_fever_is_grounded_by_bukhar() -> None:
    assert is_grounded("fever", "Do din se bukhar hai")


def test_headache_is_grounded_by_sar_dard() -> None:
    assert is_grounded("headache", "severe sar dard")


def test_paracetamol_is_grounded_by_dolo() -> None:
    assert is_grounded("paracetamol", "Take Dolo 650 twice daily")


def test_invented_drug_is_not_grounded() -> None:
    assert not is_grounded("azithromycin", "Patient has fever for two days")


def test_filter_drops_invented_medication() -> None:
    entities = [
        ExtractedEntity(
            entity_type=EntityType.SYMPTOM,
            value="fever",
            status=EntityStatus.PRESENT,
            source_segment_ids=["seg_001"],
        ),
        ExtractedEntity(
            entity_type=EntityType.MEDICATION,
            value="Ondem 4 mg",
            status=EntityStatus.PRESENT,
            source_segment_ids=["seg_001"],
        ),
    ]
    kept, dropped = filter_ungrounded_entities(
        entities,
        segment_texts={"seg_001": "Do din se bukhar hai, cough nahi hai."},
    )
    assert dropped == 1
    assert [e.value for e in kept] == ["fever"]


def test_purge_strips_invented_plan_drugs() -> None:
    update = NoteUpdate(
        note=GeneratedNote(
            chief_complaint=GeneratedSection(text="Fever", source_segment_ids=["seg_001"]),
            plan=GeneratedSection(
                text="Tab Paracetamol 650 mg TDS. Rest and fluids.",
                source_segment_ids=["seg_002"],
            ),
            assessment=GeneratedSection(
                text="Viral fever with likely typhoid.",
                source_segment_ids=["seg_002"],
            ),
        )
    )
    purge_note_hallucinations(
        update,
        segments=[
            {"ref": "seg_001", "text": "Do din se bukhar hai."},
            {"ref": "seg_002", "text": "Take rest and drink plenty of fluids."},
        ],
        entities=[{"value": "fever", "status": "PRESENT"}],
    )
    assert "Paracetamol" not in (update.note.plan.text or "")
    assert "typhoid" not in (update.note.assessment.text or "").lower()
    assert "rest" in (update.note.plan.text or "").lower() or update.note.plan.text == ""
