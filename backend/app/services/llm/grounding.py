"""Transcript grounding: drop clinical claims the conversation never made.

Small local models copy drugs and diagnoses from few-shot prompts.
few-shot prompts. This module is the last line of defence: an entity or note
clause is kept only when the transcript (including Indian vernacular synonyms)
actually supports it.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from app.models.enums import EntityType
from app.services.llm.schemas import ExtractedEntity, GeneratedNote, NoteUpdate
from app.services.nlp.terminology import _SYNONYMS

# Extra brand/generic pairs used only for grounding, not for rewriting speech.
_BRAND_GENERIC: dict[str, str] = {
    "dolo": "paracetamol",
    "crocin": "paracetamol",
    "calpol": "paracetamol",
    "glycomet": "metformin",
    "telma": "telmisartan",
    "pan-d": "pantoprazole",
    "pantocid": "pantoprazole",
    "ondem": "ondansetron",
    "vomikind": "ondansetron",
    "augmentin": "amoxicillin",
    "azithral": "azithromycin",
    "combiflam": "ibuprofen",
}

# Spoken Indian terms that terminology.py does not always list as full phrases.
_VERNACULAR_EXTRA: dict[str, str] = {
    "sar dard": "headache",
    "sir dard": "headache",
    "thalai vali": "headache",
    "chhati dard": "chest pain",
    "chhati me dard": "chest pain",
    "nenju vali": "chest pain",
    "ulti": "vomiting",
    "khansi": "cough",
    "jor": "fever",
    "pani": "fever",
    "jwaram": "fever",
}

# Types that must never appear unless the transcript supports them.
STRICT_ENTITY_TYPES = {
    EntityType.MEDICATION,
    EntityType.DIAGNOSIS_MENTIONED,
    EntityType.ALLERGY,
    EntityType.SYMPTOM,
    EntityType.FINDING,
    EntityType.PROCEDURE,
    EntityType.INVESTIGATION,
}

_TOKEN_RE = re.compile(r"[\w]{3,}", re.UNICODE)
_CLAUSE_SPLIT = re.compile(r"(?:\n+|;\s+|\.\s+|\d+\.\s*)")
_DRUG_HINT = re.compile(
    r"\b(?:tab|tablet|cap|capsule|syrup|inj|injection|mg|mcg|iu|drops|ointment|"
    r"dolo|crocin|paracetamol|metformin|telma|pantocid|ondem|azithral|augmentin|"
    r"amoxicillin|ibuprofen|aspirin|insulin|antibiotic)\b",
    re.IGNORECASE,
)

_INVENTED_DIAGNOSIS_MARKERS = (
    "viral fever",
    "upper respiratory",
    "urti",
    "uti",
    "gastroenteritis",
    "typhoid",
    "dengue",
    "malaria",
    "pneumonia",
    "bronchitis",
    "sinusitis",
    "migraine",
    "gerd",
    "acid reflux",
    "hypertension",
    "diabetes mellitus",
    "anemia",
    "anaemia",
)


def _synonym_pairs() -> dict[str, str]:
    pairs = dict(_SYNONYMS)
    pairs.update(_BRAND_GENERIC)
    pairs.update(_VERNACULAR_EXTRA)
    return pairs


def expand_clinical_text(text: str) -> str:
    """Lowercased text plus English/vernacular/brand expansions."""
    raw = (text or "").lower()
    extras: list[str] = []
    for phrase, english in _synonym_pairs().items():
        if phrase in raw:
            extras.append(english)
        if english in raw:
            extras.append(phrase)
    return f"{raw} {' '.join(extras)}".strip()


def is_grounded(value: str, cited_text: str) -> bool:
    """True when ``value`` is supported by ``cited_text`` (verbatim, synonym, or token overlap).

    Only the transcript is synonym-expanded. Expanding the claim as well would
    let "viral fever / typhoid" match a transcript that only said "bukhar".
    """
    value = (value or "").strip()
    cited = cited_text or ""
    if not value:
        return False
    haystack = expand_clinical_text(cited)
    value_l = value.lower()
    if not haystack:
        return False
    if value_l in haystack:
        return True
    for phrase, english in _synonym_pairs().items():
        if value_l in (phrase, english) and (phrase in haystack or english in haystack):
            return True
        if phrase in value_l and (phrase in haystack or english in haystack):
            return True
    tokens = [tok for tok in _TOKEN_RE.findall(value_l) if len(tok) >= 4]
    if not tokens:
        short = [tok for tok in _TOKEN_RE.findall(value_l) if len(tok) >= 3]
        return bool(short) and all(tok in haystack for tok in short)
    matched = sum(1 for tok in tokens if tok in haystack)
    return matched / len(tokens) >= 0.5


def transcript_blob(segments: Iterable[dict[str, Any]]) -> str:
    return " ".join(str(s.get("text", "")) for s in segments)


def filter_ungrounded_entities(
    entities: list[ExtractedEntity],
    *,
    segment_texts: dict[str, str],
    full_transcript: str | None = None,
) -> tuple[list[ExtractedEntity], int]:
    """Drop strictly-clinical entities that are not supported by the transcript."""
    blob = full_transcript or " ".join(segment_texts.values())
    kept: list[ExtractedEntity] = []
    dropped = 0
    for entity in entities:
        cited = " ".join(segment_texts.get(ref, "") for ref in entity.source_segment_ids)
        support = cited or blob
        if entity.entity_type in STRICT_ENTITY_TYPES and not is_grounded(entity.value, support):
            dropped += 1
            continue
        kept.append(entity)
    return kept, dropped


def _clause_supported(clause: str, transcript: str) -> bool:
    text = clause.strip()
    if not text:
        return False
    lowered = text.lower()
    haystack = expand_clinical_text(transcript)
    for marker in _INVENTED_DIAGNOSIS_MARKERS:
        if marker in lowered and marker not in haystack:
            return False
    if is_grounded(text, transcript):
        return True
    if _DRUG_HINT.search(text):
        return False
    tokens = [tok for tok in _TOKEN_RE.findall(lowered) if len(tok) >= 4]
    if not tokens:
        return True
    matched = sum(1 for tok in tokens if tok in haystack)
    return matched / len(tokens) >= 0.35


def _filter_section_text(text: str, transcript: str, *, medication_section: bool) -> str:
    if not (text or "").strip():
        return ""
    clauses = [part.strip(" -•\t") for part in _CLAUSE_SPLIT.split(text) if part.strip(" -•\t")]
    if len(clauses) <= 1 and not medication_section:
        return text if _clause_supported(text, transcript) else ""
    kept = [clause for clause in clauses if _clause_supported(clause, transcript)]
    if not kept:
        return ""
    if "\n" in text:
        return "\n".join(kept)
    return ". ".join(kept) + ("." if text.rstrip().endswith(".") else "")


def purge_note_hallucinations(
    update: NoteUpdate,
    segments: list[dict[str, Any]],
    entities: list[dict[str, Any]] | None = None,
) -> None:
    """Strip invented medications, diagnoses, and unsupported plan/assessment text."""
    transcript = transcript_blob(segments)
    entity_blob = " ".join(
        str(e.get("value", "")) for e in (entities or []) if e.get("value")
    )
    support = f"{transcript} {entity_blob}"

    note: GeneratedNote = update.note
    med_sections = ("current_medication", "plan", "treatment_history")
    strict_sections = ("assessment", "allergies", "past_medical_history", "relevant_medical_history")

    for key in med_sections:
        section = getattr(note, key, None)
        if section is None or not section.text:
            continue
        section.text = _filter_section_text(section.text, support, medication_section=True)
        if not section.text.strip():
            section.source_segment_ids = []
            section.confidence = 0.0

    for key in strict_sections:
        section = getattr(note, key, None)
        if section is None or not section.text:
            continue
        if not _clause_supported(section.text, support):
            section.text = ""
            section.source_segment_ids = []
            section.confidence = 0.0
        else:
            section.text = _filter_section_text(section.text, support, medication_section=False)
            if not section.text.strip():
                section.source_segment_ids = []
                section.confidence = 0.0
