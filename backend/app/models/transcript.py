from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import UUIDPrimaryKeyMixin, utcnow
from app.models.session import Speaker


class TranscriptSegment(UUIDPrimaryKeyMixin, Base):
    """A speaker-attributed utterance produced by transcript assembly.

    ``ref`` is the short, stable identifier (``seg_001``) used in prompts and in
    every evidence reference, so the AI layer never sees database UUIDs.
    """

    __tablename__ = "transcript_segments"
    __table_args__ = (UniqueConstraint("session_id", "ref", name="uq_segment_session_ref"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    speaker_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("speakers.id", ondelete="SET NULL"), nullable=True
    )
    audio_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("audio_chunks.id", ondelete="SET NULL"), nullable=True
    )
    ref: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    asr_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    diarization_confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    overlapping: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    speaker: Mapped[Speaker | None] = relationship(lazy="joined")
