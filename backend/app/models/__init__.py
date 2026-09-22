"""ORM models. Importing this package registers every mapper."""

from app.models.audit import AuditLog
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, utcnow
from app.models.clinical import ClinicalEntity, ClinicalNote, EvidenceLink, NoteVersion
from app.models.enums import (
    AudioSource,
    EntityStatus,
    EntityType,
    ExportFormat,
    NoteSectionKey,
    NoteStatus,
    SessionMode,
    SessionStatus,
    SimulationType,
    SpeakerRole,
    UserRole,
)
from app.models.session import AudioChunk, Session, Speaker
from app.models.transcript import TranscriptSegment
from app.models.user import User

__all__ = [
    "AuditLog",
    "AudioChunk",
    "AudioSource",
    "ClinicalEntity",
    "ClinicalNote",
    "EntityStatus",
    "EntityType",
    "EvidenceLink",
    "ExportFormat",
    "NoteSectionKey",
    "NoteStatus",
    "NoteVersion",
    "Session",
    "SessionMode",
    "SessionStatus",
    "SimulationType",
    "Speaker",
    "SpeakerRole",
    "TimestampMixin",
    "TranscriptSegment",
    "User",
    "UserRole",
    "UUIDPrimaryKeyMixin",
    "utcnow",
]
