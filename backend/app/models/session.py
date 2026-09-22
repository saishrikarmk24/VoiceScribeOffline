from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
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
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import (
    AudioSource,
    SessionMode,
    SessionStatus,
    SimulationType,
    SpeakerRole,
)


class Session(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A clinical encounter and the root of the provenance chain."""

    __tablename__ = "sessions"

    reference: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    patient_id: Mapped[str] = mapped_column(String(64), nullable=False)
    patient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scenario: Mapped[str | None] = mapped_column(Text, nullable=True)
    simulation_type: Mapped[SimulationType] = mapped_column(
        Enum(SimulationType, native_enum=False, length=32),
        default=SimulationType.OUTPATIENT,
        nullable=False,
    )
    doctor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    faculty_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    doctor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    faculty_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, native_enum=False, length=32),
        default=SessionStatus.CREATED,
        nullable=False,
        index=True,
    )
    mode: Mapped[SessionMode] = mapped_column(
        Enum(SessionMode, native_enum=False, length=32), default=SessionMode.DEMO, nullable=False
    )
    audio_source: Mapped[AudioSource] = mapped_column(
        Enum(AudioSource, native_enum=False, length=32), default=AudioSource.SIMULATION, nullable=False
    )
    ai_mode: Mapped[str] = mapped_column(String(32), default="gemini", nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), default="gemini-2.5-flash", nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paused_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    speakers: Mapped[list["Speaker"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="selectin"
    )
    audio_chunks: Mapped[list["AudioChunk"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Session {self.reference} {self.status}>"


class Speaker(UUIDPrimaryKeyMixin, Base):
    """A diarized voice within a session, optionally mapped to a clinical role."""

    __tablename__ = "speakers"
    __table_args__ = (UniqueConstraint("session_id", "label", name="uq_speaker_session_label"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[SpeakerRole] = mapped_column(
        Enum(SpeakerRole, native_enum=False, length=32), default=SpeakerRole.UNKNOWN, nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    role_source: Mapped[str] = mapped_column(String(16), default="SYSTEM", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    session: Mapped[Session] = relationship(back_populates="speakers")


class AudioChunk(UUIDPrimaryKeyMixin, Base):
    """Metadata for a captured audio buffer after preprocessing."""

    __tablename__ = "audio_chunks"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[AudioSource] = mapped_column(
        Enum(AudioSource, native_enum=False, length=32), default=AudioSource.SIMULATION, nullable=False
    )
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    sample_rate: Mapped[int] = mapped_column(Integer, default=16000, nullable=False)
    channels: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    speech_ratio: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rms_dbfs: Mapped[float] = mapped_column(Float, default=-90.0, nullable=False)
    storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="PROCESSED", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    session: Mapped[Session] = relationship(back_populates="audio_chunks")
