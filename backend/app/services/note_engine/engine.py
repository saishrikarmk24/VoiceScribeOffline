"""Note state engine: incremental updates, versioning and review gating.

The engine is deliberately database-free so its state transitions can be unit
tested. Persistence is handled by :mod:`app.services.pipeline`.

    PROCESSING -> DRAFT -> (REVIEW_REQUIRED) -> APPROVED -> EXPORTED

Only a human can move a note to APPROVED.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger
from app.models.enums import NoteStatus
from app.schemas.clinical import (
    ENTITY_KEYS,
    SECTION_KEYS,
    SECTION_LABELS,
    ClinicalEntityOut,
    ClinicalNoteContent,
    ClinicalSection,
)
from app.services.evidence.linking import EvidenceLinkingService, LinkedStatement
from app.services.llm.validator import NoteValidationResult

logger = get_logger(__name__)

NOT_MENTIONED = "Not mentioned"

_ALLOWED_TRANSITIONS: dict[NoteStatus, set[NoteStatus]] = {
    NoteStatus.PROCESSING: {NoteStatus.PROCESSING, NoteStatus.DRAFT, NoteStatus.REVIEW_REQUIRED},
    NoteStatus.DRAFT: {NoteStatus.PROCESSING, NoteStatus.DRAFT, NoteStatus.REVIEW_REQUIRED, NoteStatus.APPROVED},
    NoteStatus.REVIEW_REQUIRED: {
        NoteStatus.PROCESSING,
        NoteStatus.DRAFT,
        NoteStatus.REVIEW_REQUIRED,
        NoteStatus.APPROVED,
    },
    NoteStatus.APPROVED: {NoteStatus.APPROVED, NoteStatus.EXPORTED, NoteStatus.DRAFT},
    NoteStatus.EXPORTED: {NoteStatus.EXPORTED, NoteStatus.DRAFT},
}


class NoteStateError(RuntimeError):
    pass


@dataclass(slots=True)
class NoteUpdateOutcome:
    content: ClinicalNoteContent
    status: NoteStatus
    version: int
    changed_sections: list[str] = field(default_factory=list)
    change_summary: str = ""
    review_flags: list[dict[str, Any]] = field(default_factory=list)
    linked_statements: list[LinkedStatement] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.changed_sections)


class NoteStateEngine:
    def can_transition(self, current: NoteStatus, target: NoteStatus) -> bool:
        return target in _ALLOWED_TRANSITIONS.get(current, set())

    def transition(self, current: NoteStatus, target: NoteStatus) -> NoteStatus:
        if not self.can_transition(current, target):
            raise NoteStateError(f"Illegal note transition: {current.value} -> {target.value}")
        return target

    # --------------------------------------------------------------- AI update
    def apply_ai_update(
        self,
        *,
        current: ClinicalNoteContent,
        validated: NoteValidationResult,
        entities: dict[str, list[ClinicalEntityOut]],
        evidence: EvidenceLinkingService,
        current_status: NoteStatus,
        version: int,
        model: str | None,
    ) -> NoteUpdateOutcome:
        """Merge a validated AI note into the current state, section by section."""
        content = current.model_copy(deep=True)
        changed: list[str] = []
        review_flags: list[dict[str, Any]] = []
        linked: list[LinkedStatement] = []

        generated = validated.note.model_dump()
        for key in SECTION_KEYS:
            incoming = generated[key]
            existing: ClinicalSection = getattr(content, key)

            if existing.edited_by_human:
                review_flags.append(
                    {
                        "section": key,
                        "label": SECTION_LABELS[key],
                        "reason": "AI update skipped: section was edited by a human reviewer",
                        "severity": "INFO",
                    }
                )
                continue

            text = (incoming.get("text") or NOT_MENTIONED).strip()
            refs = list(incoming.get("source_segment_ids") or [])

            # Never replace documented content with an empty section.
            if text == NOT_MENTIONED and existing.text not in ("", NOT_MENTIONED):
                continue

            statement = evidence.link(
                target_kind="SECTION", target_key=key, clinical_statement=text, refs=refs
            )
            linked.append(statement)

            unsupported = key in validated.unsupported_sections
            needs_review = text != NOT_MENTIONED and (unsupported or statement.review_required)

            if needs_review:
                review_flags.append(
                    {
                        "section": key,
                        "label": SECTION_LABELS[key],
                        "reason": "REVIEW REQUIRED: statement could not be linked to transcript evidence",
                        "severity": "ERROR",
                    }
                )

            new_section = ClinicalSection(
                text=text,
                confidence=float(incoming.get("confidence") or 0.0),
                evidence=[reference for reference in statement.evidence if reference.validated],
                review_required=needs_review,
                review_reason="No validated transcript evidence" if needs_review else None,
                edited_by_human=False,
            )

            if self._section_differs(existing, new_section):
                setattr(content, key, new_section)
                changed.append(key)

        for group_key in ENTITY_KEYS:
            if hasattr(content, group_key) and group_key in entities:
                setattr(content, group_key, entities[group_key])

        for issue in validated.issues:
            if issue.severity == "ERROR":
                review_flags.append(
                    {
                        "section": issue.target,
                        "label": SECTION_LABELS.get(issue.target, issue.target),
                        "reason": issue.message,
                        "severity": "ERROR",
                    }
                )

        flagged_entities = [
            entity for group in entities.values() for entity in group if entity.review_required
        ]
        for entity in flagged_entities:
            review_flags.append(
                {
                    "section": "entities",
                    "label": entity.value,
                    "reason": entity.review_reason or "Entity flagged for review",
                    "severity": "WARNING",
                }
            )

        next_version = version + 1 if changed else version
        content.version = next_version
        content.model = model
        content.generated_at = datetime.now(timezone.utc).isoformat()

        has_errors = any(flag["severity"] == "ERROR" for flag in review_flags)
        if current_status in (NoteStatus.APPROVED, NoteStatus.EXPORTED):
            # New AI content after approval reopens the note as a draft.
            status = NoteStatus.DRAFT if changed else current_status
        elif has_errors:
            status = NoteStatus.REVIEW_REQUIRED
        else:
            status = NoteStatus.DRAFT

        return NoteUpdateOutcome(
            content=content,
            status=status,
            version=next_version,
            changed_sections=changed,
            change_summary=validated.change_summary or self._summarise(changed),
            review_flags=review_flags,
            linked_statements=linked,
        )

    # ------------------------------------------------------------- human edits
    def apply_human_edit(
        self,
        *,
        current: ClinicalNoteContent,
        changes: dict[str, str],
        version: int,
        editor: str | None,
    ) -> NoteUpdateOutcome:
        content = current.model_copy(deep=True)
        changed: list[str] = []

        for key, text in changes.items():
            if key not in SECTION_KEYS:
                raise NoteStateError(f"Unknown note section: {key}")
            section: ClinicalSection = getattr(content, key)
            cleaned = text.strip() or NOT_MENTIONED
            if cleaned == section.text:
                continue
            section.text = cleaned
            section.edited_by_human = True
            section.review_required = False
            section.review_reason = None
            changed.append(key)

        version = version + 1 if changed else version
        content.version = version
        return NoteUpdateOutcome(
            content=content,
            status=NoteStatus.DRAFT,
            version=version,
            changed_sections=changed,
            change_summary=f"Human edit by {editor or 'reviewer'}: {', '.join(changed) or 'no changes'}",
            review_flags=[],
        )

    # ---------------------------------------------------------------- approval
    def approve(
        self,
        *,
        content: ClinicalNoteContent,
        current_status: NoteStatus,
        version: int,
        approver: str,
        acknowledged: bool,
    ) -> NoteUpdateOutcome:
        """Human-controlled approval. AI output is never auto-approved."""
        if not approver:
            raise NoteStateError("An approver identity is required.")
        if not acknowledged:
            raise NoteStateError("The reviewer must acknowledge they reviewed the note and its evidence.")
        if current_status is NoteStatus.PROCESSING:
            raise NoteStateError("The note is still being generated and cannot be approved yet.")

        blocking = [
            key for key in SECTION_KEYS if getattr(content, key).review_required
        ]
        if blocking:
            raise NoteStateError(
                "Resolve the flagged sections before approval: " + ", ".join(SECTION_LABELS[k] for k in blocking)
            )

        status = self.transition(current_status, NoteStatus.APPROVED)
        return NoteUpdateOutcome(
            content=content,
            status=status,
            version=version + 1,
            changed_sections=[],
            change_summary=f"Approved by {approver}",
        )

    def mark_exported(
        self, *, content: ClinicalNoteContent, current_status: NoteStatus, version: int, fmt: str
    ) -> NoteUpdateOutcome:
        status = current_status
        if current_status is NoteStatus.APPROVED:
            status = self.transition(current_status, NoteStatus.EXPORTED)
        return NoteUpdateOutcome(
            content=content,
            status=status,
            version=version,
            change_summary=f"Exported as {fmt}",
        )

    # ----------------------------------------------------------------- helpers
    @staticmethod
    def _section_differs(existing: ClinicalSection, incoming: ClinicalSection) -> bool:
        if existing.text != incoming.text:
            return True
        existing_refs = [reference.transcript_segment_ref for reference in existing.evidence]
        incoming_refs = [reference.transcript_segment_ref for reference in incoming.evidence]
        return existing_refs != incoming_refs

    @staticmethod
    def _summarise(changed: list[str]) -> str:
        if not changed:
            return "No section changes"
        labels = ", ".join(SECTION_LABELS.get(key, key) for key in changed)
        return f"Updated: {labels}"
