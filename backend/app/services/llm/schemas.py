"""Structured-output schemas handed to the LLM.

These are intentionally *flat and small*: response schemas constrain generation,
and every extra nested optional field costs tokens and increases the chance of a
malformed response. Provenance is expressed as lists of short segment refs
(``seg_004``), which the evidence layer expands into full references after
validating that each ref actually exists.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import EntityStatus, EntityType, NoteSectionKey

DEFAULT_CONFIDENCE = 0.75
_NOTE_SECTION_KEYS = [key.value.lower() for key in NoteSectionKey]


class ExtractedEntity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    entity_type: EntityType = Field(description="Clinical category of the extracted item")
    value: str = Field(description="Exact clinical concept as stated in the conversation")
    status: EntityStatus = Field(
        default=EntityStatus.PRESENT,
        description="PRESENT, NEGATED (explicitly denied), UNCERTAIN (hedged), HISTORICAL or UNKNOWN",
    )
    confidence: float = Field(
        default=DEFAULT_CONFIDENCE,
        ge=0.0,
        le=1.0,
        description="Extraction confidence between 0 and 1",
    )
    source_segment_ids: list[str] = Field(
        default_factory=list, description="Transcript segment ids that state this item, e.g. ['seg_002']"
    )
    detail: str | None = Field(
        default=None, description="Short qualifier such as dose, laterality or context. Null if absent."
    )


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    entities: list[ExtractedEntity] = Field(default_factory=list)
    unsupported_content: list[str] = Field(
        default_factory=list,
        description="Anything you could not attribute to a transcript segment id",
    )


class GeneratedSection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str = Field(
        default="",
        description="Documentation text, or an empty string when the conversation does not cover this section",
    )
    confidence: float = Field(default=DEFAULT_CONFIDENCE, ge=0.0, le=1.0)
    source_segment_ids: list[str] = Field(default_factory=list)


class GeneratedNote(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chief_complaint: GeneratedSection = Field(default_factory=GeneratedSection)
    history_of_present_illness: GeneratedSection = Field(default_factory=GeneratedSection)
    relevant_medical_history: GeneratedSection = Field(default_factory=GeneratedSection)
    social_history: GeneratedSection = Field(default_factory=GeneratedSection)
    family_history: GeneratedSection = Field(default_factory=GeneratedSection)
    menstrual_history: GeneratedSection = Field(default_factory=GeneratedSection)
    physical_examination: GeneratedSection = Field(default_factory=GeneratedSection)
    current_medication: GeneratedSection = Field(default_factory=GeneratedSection)
    allergies: GeneratedSection = Field(default_factory=GeneratedSection)
    treatment_history: GeneratedSection = Field(default_factory=GeneratedSection)
    previous_investigation: GeneratedSection = Field(default_factory=GeneratedSection)
    assessment: GeneratedSection = Field(default_factory=GeneratedSection)
    plan: GeneratedSection = Field(default_factory=GeneratedSection)
    follow_up: GeneratedSection = Field(default_factory=GeneratedSection)


class NoteUpdate(BaseModel):
    """Incremental result: the generated note plus which sections changed."""

    model_config = ConfigDict(extra="ignore")

    note: GeneratedNote = Field(default_factory=GeneratedNote)
    changed_sections: list[str] = Field(default_factory=list)
    change_summary: str = ""


def coerce_llm_payload(payload: Any, schema: type[BaseModel]) -> Any:
    """Fill fields smaller models often omit (confidence, status, note wrapper)."""
    if isinstance(payload, list) and schema is ExtractionResult:
        payload = {"entities": payload}
    if not isinstance(payload, dict):
        return payload
    if schema is ExtractionResult:
        return _coerce_extraction(payload)
    if schema is NoteUpdate:
        return _coerce_note_update(payload)
    return payload


_TYPE_ALIASES = {
    "SYMPTOMS": "SYMPTOM",
    "SIGN": "FINDING",
    "SIGNS": "FINDING",
    "DRUG": "MEDICATION",
    "MEDS": "MEDICATION",
    "MEDICINE": "MEDICATION",
    "HISTORY": "MEDICAL_HISTORY",
}


def _enum_value(raw: Any, choices: type[EntityType] | type[EntityStatus], default: str | None) -> str | None:
    text = str(raw or "").strip().upper().replace(" ", "_").replace("-", "_")
    if not text:
        return default
    if choices is EntityType:
        text = _TYPE_ALIASES.get(text, text)
    try:
        return choices(text).value
    except ValueError:
        return default


def _confidence(raw: Any) -> float:
    if raw is None or raw == "":
        return DEFAULT_CONFIDENCE
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_CONFIDENCE
    if value > 1:
        value = value / 100.0
    return min(max(value, 0.0), 1.0)


def _coerce_extraction(payload: dict[str, Any]) -> dict[str, Any]:
    raw_entities = payload.get("entities")
    if raw_entities is None:
        raw_entities = payload.get("items") or []
    entities: list[dict[str, Any]] = []
    for item in raw_entities:
        if not isinstance(item, dict):
            continue
        entity = dict(item)
        if "entity_type" not in entity and "type" in entity:
            entity["entity_type"] = entity["type"]
        entity_type = _enum_value(entity.get("entity_type"), EntityType, None)
        value = str(entity.get("value") or "").strip()
        if not entity_type or not value:
            continue
        if "source_segment_ids" not in entity:
            entity["source_segment_ids"] = entity.get("segment_ids") or entity.get("source_segments") or []
        entity["entity_type"] = entity_type
        entity["status"] = _enum_value(entity.get("status"), EntityStatus, EntityStatus.PRESENT.value)
        entity["confidence"] = _confidence(entity.get("confidence"))
        entity["value"] = value
        entities.append(entity)
    return {
        "entities": entities,
        "unsupported_content": payload.get("unsupported_content") or [],
    }


def _coerce_section(section: Any) -> dict[str, Any]:
    if isinstance(section, str):
        text = section
        refs: list[str] = []
    elif isinstance(section, dict):
        text = str(section.get("text") or section.get("content") or "")
        refs = list(section.get("source_segment_ids") or section.get("segment_ids") or [])
        confidence = section.get("confidence")
        return {
            "text": text,
            "confidence": _confidence(confidence) if str(text).strip() else 0.0,
            "source_segment_ids": refs,
        }
    else:
        text = ""
        refs = []
    return {
        "text": text,
        "confidence": DEFAULT_CONFIDENCE if text.strip() else 0.0,
        "source_segment_ids": refs,
    }


def _coerce_note_update(payload: dict[str, Any]) -> dict[str, Any]:
    note = payload.get("note")
    if not isinstance(note, dict):
        if any(key in payload for key in _NOTE_SECTION_KEYS):
            note = {key: payload.get(key) for key in _NOTE_SECTION_KEYS}
        else:
            note = {}
    return {
        "note": {key: _coerce_section(note.get(key)) for key in _NOTE_SECTION_KEYS},
        "changed_sections": payload.get("changed_sections") or [],
        "change_summary": payload.get("change_summary") or "",
    }
