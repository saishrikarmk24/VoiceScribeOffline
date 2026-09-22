"""WebSocket event contract shared with the frontend."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EventType(str, Enum):
    SESSION_STARTED = "SESSION_STARTED"
    SESSION_STATUS = "SESSION_STATUS"
    AUDIO_STATUS = "AUDIO_STATUS"
    DIARIZATION_UPDATE = "DIARIZATION_UPDATE"
    TRANSCRIPT_UPDATE = "TRANSCRIPT_UPDATE"
    ENTITY_UPDATE = "ENTITY_UPDATE"
    NOTE_UPDATE = "NOTE_UPDATE"
    EVIDENCE_UPDATE = "EVIDENCE_UPDATE"
    PROCESSING_STATUS = "PROCESSING_STATUS"
    PROCESSING_ERROR = "PROCESSING_ERROR"
    SESSION_COMPLETED = "SESSION_COMPLETED"
    STATE_SNAPSHOT = "STATE_SNAPSHOT"
    PONG = "PONG"


class SocketEvent(BaseModel):
    type: EventType
    session_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    emitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sequence: int = 0


class ProcessingStage(str, Enum):
    AUDIO_CAPTURE = "AUDIO_CAPTURE"
    AUDIO_PREPROCESSING = "AUDIO_PREPROCESSING"
    DIARIZATION = "DIARIZATION"
    ROLE_ATTRIBUTION = "ROLE_ATTRIBUTION"
    ASR = "ASR"
    TRANSCRIPT_ASSEMBLY = "TRANSCRIPT_ASSEMBLY"
    CLINICAL_NLP = "CLINICAL_NLP"
    LLM_STRUCTURING = "LLM_STRUCTURING"
    EVIDENCE_LINKING = "EVIDENCE_LINKING"
    NOTE_STATE = "NOTE_STATE"
    IDLE = "IDLE"
