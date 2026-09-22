from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import SpeakerRole


class TranscriptSegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ref: str
    sequence: int
    speaker_id: str | None = None
    speaker_label: str | None = None
    role: SpeakerRole = SpeakerRole.UNKNOWN
    text: str
    start_time: float
    end_time: float
    confidence: float
    asr_confidence: float = 0.0
    diarization_confidence: float = 0.0
    overlapping: bool = False
    is_final: bool = True


class DiarizationTurnOut(BaseModel):
    speaker_id: str
    start_time: float
    end_time: float
    confidence: float


class AudioChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    sequence: int
    source: str
    start_time: float
    end_time: float
    sample_rate: int
    channels: int
    size_bytes: int
    speech_ratio: float
    rms_dbfs: float
    status: str


class AudioChunkIngest(BaseModel):
    """Browser-captured audio, sent as base64 so it survives JSON transport."""

    audio_base64: str = Field(description="Raw PCM16, WAV or WebM payload, base64 encoded")
    mime_type: str = "audio/wav"
    sample_rate: int | None = None
    channels: int | None = None
    duration_seconds: float | None = None
    sequence: int | None = None
