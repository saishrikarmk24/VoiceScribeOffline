from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import EntityStatus, EntityType, NoteStatus


class ClinicalEntity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A discrete clinical fact extracted from the transcript."""

    __tablename__ = "clinical_entities"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ref: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[EntityType] = mapped_column(
        Enum(EntityType, native_enum=False, length=32), nullable=False, index=True
    )
    value: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_value: Mapped[str | None] = mapped_column(String(512), nullable=True)
    normalized_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    terminology_system: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[EntityStatus] = mapped_column(
        Enum(EntityStatus, native_enum=False, length=32), default=EntityStatus.UNKNOWN, nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    source_segment_refs: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    review_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    review_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ClinicalNote(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The current state of a session's clinical note."""

    __tablename__ = "clinical_notes"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[NoteStatus] = mapped_column(
        Enum(NoteStatus, native_enum=False, length=32), default=NoteStatus.PROCESSING, nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    review_flags: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    versions: Mapped[list["NoteVersion"]] = relationship(
        back_populates="note", cascade="all, delete-orphan", order_by="NoteVersion.version"
    )


class NoteVersion(UUIDPrimaryKeyMixin, Base):
    """Immutable snapshot of the note after each AI update or human edit."""

    __tablename__ = "note_versions"

    note_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clinical_notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[NoteStatus] = mapped_column(
        Enum(NoteStatus, native_enum=False, length=32), default=NoteStatus.DRAFT, nullable=False
    )
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_sections: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    author_type: Mapped[str] = mapped_column(String(16), default="AI", nullable=False)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    note: Mapped[ClinicalNote] = relationship(back_populates="versions")


class EvidenceLink(UUIDPrimaryKeyMixin, Base):
    """Provenance edge: clinical statement -> transcript segment -> speaker/time."""

    __tablename__ = "evidence_links"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transcript_segment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("transcript_segments.id", ondelete="CASCADE"), nullable=True
    )
    clinical_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clinical_entities.id", ondelete="CASCADE"), nullable=True
    )
    note_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("note_versions.id", ondelete="CASCADE"), nullable=True
    )
    target_kind: Mapped[str] = mapped_column(String(16), default="SECTION", nullable=False)
    target_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    clinical_statement: Mapped[str] = mapped_column(Text, nullable=False)
    segment_ref: Mapped[str | None] = mapped_column(String(32), nullable=True)
    speaker_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    speaker_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    validated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    validation_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
