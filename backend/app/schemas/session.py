from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    AudioSource,
    SessionMode,
    SessionStatus,
    SimulationType,
    SpeakerRole,
)


class SessionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    patient_id: str = Field(min_length=1, max_length=64, description="Patient identifier")
    patient_name: str | None = Field(default=None, max_length=255, description="Patient full name")
    scenario: str | None = None
    simulation_type: SimulationType = Field(default=SimulationType.OUTPATIENT, description="Encounter type")
    doctor_name: str | None = None
    faculty_name: str | None = None
    mode: SessionMode = SessionMode.DEMO
    audio_source: AudioSource | None = None


class SpeakerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    label: str
    display_name: str | None = None
    role: SpeakerRole
    confidence: float
    role_source: str


class SpeakerRoleUpdate(BaseModel):
    role: SpeakerRole
    display_name: str | None = None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    reference: str
    name: str
    patient_id: str
    patient_name: str | None = None
    scenario: str | None = None
    simulation_type: SimulationType
    doctor_name: str | None = None
    faculty_name: str | None = None
    status: SessionStatus
    mode: SessionMode
    audio_source: AudioSource
    ai_mode: str
    model_name: str
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    last_error: str | None = None
    duration_seconds: float = 0.0
    segment_count: int = 0
    entity_count: int = 0
    note_status: str | None = None
    note_version: int = 0
    speakers: list[SpeakerOut] = Field(default_factory=list)


class SessionSummary(BaseModel):
    """Lighter payload for lists and the dashboard."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    reference: str
    name: str
    patient_id: str
    patient_name: str | None = None
    status: SessionStatus
    mode: SessionMode
    simulation_type: SimulationType
    created_at: datetime
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: float = 0.0
    segment_count: int = 0
    entity_count: int = 0
    note_status: str | None = None


class DashboardStats(BaseModel):
    active_sessions: int
    completed_sessions: int
    total_sessions: int
    notes_generated: int
    notes_approved: int
    total_segments: int
    total_entities: int
    average_note_latency_ms: float
    average_gemini_latency_ms: float
    review_required_count: int
    recent_sessions: list[SessionSummary]
    sessions_by_day: list[dict[str, float | str]]
    entity_distribution: list[dict[str, float | str]]


class SystemStatus(BaseModel):
    environment: str
    version: str
    database: dict
    ai: dict
    providers: dict
    websocket: dict
    demo_mode_enabled: bool
