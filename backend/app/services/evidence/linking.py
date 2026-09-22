"""Evidence linking: the provenance chain that makes the note inspectable.

    clinical statement -> evidence reference -> transcript segment
                                            -> speaker -> timestamp -> audio

A statement that cannot be linked to at least one existing transcript segment is
never presented as documentation; it is flagged REVIEW REQUIRED.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from app.core.logging import get_logger, track_duration
from app.models.enums import SpeakerRole
from app.schemas.clinical import EvidenceReference

logger = get_logger(__name__)


@dataclass(slots=True)
class SegmentIndexEntry:
    ref: str
    text: str
    speaker_label: str
    role: SpeakerRole
    start_time: float
    end_time: float
    confidence: float
    segment_id: str | None = None


@dataclass(slots=True)
class LinkedStatement:
    """A clinical statement together with its (validated) evidence."""

    target_kind: str  # "SECTION" | "ENTITY"
    target_key: str
    clinical_statement: str
    evidence: list[EvidenceReference] = field(default_factory=list)
    missing_refs: list[str] = field(default_factory=list)

    @property
    def review_required(self) -> bool:
        return not any(reference.validated for reference in self.evidence)


class EvidenceLinkingService:
    def __init__(self) -> None:
        self._index: dict[str, SegmentIndexEntry] = {}

    # ------------------------------------------------------------------- index
    def build_index(self, segments: Iterable[SegmentIndexEntry]) -> dict[str, SegmentIndexEntry]:
        self._index = {segment.ref: segment for segment in segments}
        return self._index

    @property
    def valid_refs(self) -> set[str]:
        return set(self._index)

    def segment_texts(self) -> dict[str, str]:
        return {ref: entry.text for ref, entry in self._index.items()}

    # -------------------------------------------------------------------- link
    def reference(self, ref: str) -> EvidenceReference:
        entry = self._index.get(ref)
        if entry is None:
            return EvidenceReference(
                transcript_segment_ref=ref,
                validated=False,
                validation_error="transcript segment does not exist in this session",
            )
        return EvidenceReference(
            transcript_segment_ref=entry.ref,
            speaker_label=entry.speaker_label,
            speaker_role=entry.role.value if hasattr(entry.role, "value") else str(entry.role),
            timestamp=round(entry.start_time, 3),
            confidence=round(entry.confidence, 4),
            source_text=entry.text,
            validated=True,
        )

    def link(
        self,
        *,
        target_kind: str,
        target_key: str,
        clinical_statement: str,
        refs: Iterable[str],
    ) -> LinkedStatement:
        references: list[EvidenceReference] = []
        missing: list[str] = []
        for ref in dict.fromkeys(refs):  # de-duplicate, preserve order
            reference = self.reference(ref)
            if not reference.validated:
                missing.append(ref)
            references.append(reference)
        return LinkedStatement(
            target_kind=target_kind,
            target_key=target_key,
            clinical_statement=clinical_statement,
            evidence=references,
            missing_refs=missing,
        )

    def link_many(
        self, items: Iterable[tuple[str, str, str, Iterable[str]]], *, session_id: str = "-"
    ) -> list[LinkedStatement]:
        with track_duration("evidence_linking", logger, session_id=session_id):
            return [
                self.link(target_kind=kind, target_key=key, clinical_statement=statement, refs=refs)
                for kind, key, statement, refs in items
            ]

    def segment_id_for(self, ref: str) -> str | None:
        entry = self._index.get(ref)
        return entry.segment_id if entry else None
