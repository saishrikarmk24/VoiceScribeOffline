"""Validation of AI output before anything reaches the database.

Pipeline: JSON -> Pydantic (done by the provider) -> evidence validation ->
business validation -> persistence. Anything that fails is either dropped with a
reason or flagged for human review; nothing is silently accepted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.core.logging import get_logger
from app.models.enums import EntityStatus, EntityType
from app.services.llm.grounding import STRICT_ENTITY_TYPES, is_grounded
from app.services.llm.schemas import ExtractedEntity, GeneratedNote, NoteUpdate

logger = get_logger(__name__)

_SEGMENT_REF_RE = re.compile(r"^seg_\d{3,6}$")

# Statements the system must never produce autonomously.
_ADVICE_MARKERS = (
    "you should take",
    "i recommend",
    "we recommend",
    "recommended dose",
    "start treatment with",
    "the diagnosis is likely",
    "most likely diagnosis",
    "differential diagnosis includes",
    "prognosis is",
)


@dataclass(slots=True)
class ValidationIssue:
    severity: str  # "ERROR" (dropped) or "WARNING" (kept, flagged)
    target: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "target": self.target, "message": self.message}


@dataclass(slots=True)
class EntityValidationResult:
    entities: list[ExtractedEntity] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)
    dropped: int = 0

    @property
    def review_required(self) -> bool:
        return any(issue.severity == "ERROR" for issue in self.issues)


@dataclass(slots=True)
class NoteValidationResult:
    note: GeneratedNote
    changed_sections: list[str] = field(default_factory=list)
    change_summary: str = ""
    issues: list[ValidationIssue] = field(default_factory=list)
    unsupported_sections: list[str] = field(default_factory=list)

    @property
    def review_required(self) -> bool:
        return bool(self.unsupported_sections) or any(issue.severity == "ERROR" for issue in self.issues)


class OutputValidator:
    """Validates extraction and note payloads against the real transcript."""

    def __init__(self, max_value_length: int = 300) -> None:
        self.max_value_length = max_value_length

    # ------------------------------------------------------------- entities
    def validate_entities(
        self,
        entities: list[ExtractedEntity],
        *,
        valid_segment_refs: set[str],
        segment_texts: dict[str, str],
        rule_statuses: dict[str, EntityStatus] | None = None,
    ) -> EntityValidationResult:
        result = EntityValidationResult()
        rule_statuses = rule_statuses or {}
        seen: set[tuple[str, str]] = set()

        for entity in entities:
            target = f"{entity.entity_type}:{entity.value}"
            value = entity.value.strip()

            if not value:
                result.issues.append(ValidationIssue("ERROR", target, "empty entity value"))
                result.dropped += 1
                continue
            if len(value) > self.max_value_length:
                result.issues.append(ValidationIssue("ERROR", target, "entity value exceeds maximum length"))
                result.dropped += 1
                continue

            refs = [ref for ref in entity.source_segment_ids if _SEGMENT_REF_RE.match(ref)]
            unknown = [ref for ref in refs if ref not in valid_segment_refs]
            malformed = [ref for ref in entity.source_segment_ids if not _SEGMENT_REF_RE.match(ref)]
            refs = [ref for ref in refs if ref in valid_segment_refs]

            if malformed:
                result.issues.append(
                    ValidationIssue("WARNING", target, f"discarded malformed segment ids: {malformed}")
                )
            if unknown:
                result.issues.append(
                    ValidationIssue("WARNING", target, f"discarded non-existent segment ids: {unknown}")
                )
            if not refs:
                result.issues.append(
                    ValidationIssue("ERROR", target, "no valid transcript evidence - entity dropped")
                )
                result.dropped += 1
                continue

            if not 0.0 <= entity.confidence <= 1.0:
                result.issues.append(ValidationIssue("WARNING", target, "confidence out of range, clamped"))
                entity.confidence = min(max(entity.confidence, 0.0), 1.0)

            grounded = self._is_grounded(value, refs, segment_texts)
            if not grounded and entity.entity_type in STRICT_ENTITY_TYPES:
                result.issues.append(
                    ValidationIssue(
                        "ERROR",
                        target,
                        "value is not supported by the cited transcript - entity dropped",
                    )
                )
                result.dropped += 1
                continue
            if not grounded:
                result.issues.append(
                    ValidationIssue(
                        "WARNING", target, "value not found verbatim in cited segments - flagged for review"
                    )
                )

            rule_status = rule_statuses.get(value.lower())
            if (
                rule_status is EntityStatus.NEGATED
                and entity.status is EntityStatus.PRESENT
                and entity.entity_type in (EntityType.SYMPTOM, EntityType.FINDING, EntityType.ALLERGY)
            ):
                result.issues.append(
                    ValidationIssue(
                        "WARNING",
                        target,
                        "rule engine detected a negation while the model reported PRESENT - status corrected",
                    )
                )
                entity.status = EntityStatus.NEGATED

            key = (entity.entity_type.value, (value.lower()))
            if key in seen:
                continue
            seen.add(key)

            entity.value = value
            entity.source_segment_ids = refs
            result.entities.append(entity)

        return result

    @staticmethod
    def _is_grounded(value: str, refs: list[str], segment_texts: dict[str, str]) -> bool:
        """Groundedness check including Indian vernacular and brand/generic synonyms."""
        cited = " ".join(segment_texts.get(ref, "") for ref in refs)
        return is_grounded(value, cited)

    # ----------------------------------------------------------------- note
    def validate_note(
        self,
        update: NoteUpdate,
        *,
        valid_segment_refs: set[str],
    ) -> NoteValidationResult:
        note = update.note
        issues: list[ValidationIssue] = []
        unsupported: list[str] = []

        for key, section in note.model_dump().items():
            text = (section.get("text") or "").strip()
            refs = [ref for ref in section.get("source_segment_ids", []) if _SEGMENT_REF_RE.match(ref)]
            unknown = [ref for ref in refs if ref not in valid_segment_refs]
            refs = [ref for ref in refs if ref in valid_segment_refs]

            if unknown:
                issues.append(ValidationIssue("WARNING", key, f"discarded non-existent segment ids: {unknown}"))

            # Strip leading "Not mentioned" placeholder prefix if actual clinical content follows
            lower_text = text.lower()
            for prefix in ("not mentioned.", "not mentioned,", "not mentioned:", "not mentioned -", "not mentioned;"):
                if lower_text.startswith(prefix):
                    text = text[len(prefix):].strip()
                    lower_text = text.lower()
                    break

            placeholder = text.lower() in ("not mentioned", "n/a", "none", "not found")
            if placeholder:
                text = ""
                issues.append(ValidationIssue("WARNING", key, "placeholder section text cleared"))

            documented = bool(text)
            if documented and not refs:
                unsupported.append(key)
                issues.append(
                    ValidationIssue("ERROR", key, "documented section has no valid transcript evidence")
                )
            if not documented and refs:
                refs = []

            advice = [marker for marker in _ADVICE_MARKERS if marker in text.lower()]
            if advice:
                issues.append(
                    ValidationIssue("ERROR", key, f"section contains advisory/diagnostic language: {advice}")
                )
                unsupported.append(key)

            section_model = getattr(note, key)
            section_model.text = text
            section_model.source_segment_ids = refs
            section_model.confidence = min(max(section_model.confidence, 0.0), 1.0)

        changed = [key for key in update.changed_sections if hasattr(note, key)]
        return NoteValidationResult(
            note=note,
            changed_sections=changed,
            change_summary=update.change_summary.strip()[:500],
            issues=issues,
            unsupported_sections=sorted(set(unsupported)),
        )
