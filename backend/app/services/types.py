"""Transport objects passed between pipeline stages.

Plain dataclasses (not ORM rows, not Pydantic models) keep the ASR, diarization
and assembly stages independent of both the database and the API layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.enums import AudioSource, SpeakerRole


@dataclass(slots=True)
class AudioFrame:
    """A preprocessed mono 16 kHz PCM16 buffer with its analysis metadata."""

    session_id: str
    sequence: int
    pcm: bytes
    sample_rate: int
    channels: int
    start_time: float
    end_time: float
    source: AudioSource = AudioSource.SIMULATION
    speech_ratio: float = 0.0
    rms_dbfs: float = -90.0
    decoded: bool = True
    speech_regions: list[tuple[float, float]] = field(default_factory=list)
    hints: dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return max(self.end_time - self.start_time, 0.0)


@dataclass(slots=True)
class ASRSegment:
    """Raw ASR hypothesis, before speaker attribution."""

    id: str
    text: str
    start_time: float
    end_time: float
    confidence: float
    language: str = "en"
    words: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class DiarizationTurn:
    """A contiguous region of audio attributed to one voice."""

    speaker_id: str
    start_time: float
    end_time: float
    confidence: float

    def overlaps(self, start: float, end: float) -> float:
        return max(0.0, min(self.end_time, end) - max(self.start_time, start))


@dataclass(slots=True)
class AssembledSegment:
    """ASR + diarization merged into a speaker-attributed utterance."""

    ref: str
    speaker_label: str
    role: SpeakerRole
    text: str
    start_time: float
    end_time: float
    confidence: float
    asr_confidence: float
    diarization_confidence: float
    overlapping: bool = False
    audio_sequence: int | None = None
