"""Audio capture provider interfaces.

Three sources feed the same preprocessing pipeline:

``BrowserMicrophoneProvider``  chunks pushed from the browser over HTTP
``UploadedAudioProvider``      a whole recording split into chunks
``SimulationAudioProvider``    synthesised speech-shaped audio for Demo Mode
"""

from __future__ import annotations

import abc
import math
import random
import struct
from dataclasses import dataclass

from app.models.enums import AudioSource


@dataclass(slots=True)
class RawAudio:
    """Undecoded bytes as they arrive from a capture source."""

    data: bytes
    mime_type: str = "audio/wav"
    sample_rate: int | None = None
    channels: int | None = None
    duration_seconds: float | None = None


class AudioCaptureProvider(abc.ABC):
    """Produces raw audio buffers for a session."""

    source: AudioSource

    @abc.abstractmethod
    async def next_chunk(self) -> RawAudio | None:
        """Return the next buffer, or ``None`` when the source is exhausted."""


class BrowserMicrophoneProvider(AudioCaptureProvider):
    """Push-based provider: the browser POSTs chunks, we just wrap them."""

    source = AudioSource.MICROPHONE

    def __init__(self) -> None:
        self._pending: list[RawAudio] = []

    def push(self, raw: RawAudio) -> None:
        self._pending.append(raw)

    async def next_chunk(self) -> RawAudio | None:
        if not self._pending:
            return None
        return self._pending.pop(0)


class UploadedAudioProvider(AudioCaptureProvider):
    """Splits an uploaded recording into fixed-length buffers."""

    source = AudioSource.UPLOAD

    def __init__(self, data: bytes, mime_type: str, chunk_seconds: float = 5.0, sample_rate: int = 16000) -> None:
        self._raw = RawAudio(data=data, mime_type=mime_type, sample_rate=sample_rate)
        self._chunk_seconds = chunk_seconds
        self._consumed = False

    async def next_chunk(self) -> RawAudio | None:
        if self._consumed:
            return None
        self._consumed = True
        return self._raw


class SimulationAudioProvider(AudioCaptureProvider):
    """Synthesises speech-shaped PCM16 so Demo Mode exercises the real pipeline.

    The waveform is not intelligible speech - it is an amplitude-modulated
    harmonic stack plus noise, which gives the preprocessing stage realistic
    energy envelopes for voice activity detection.
    """

    source = AudioSource.SIMULATION

    def __init__(self, sample_rate: int = 16000, seed: int = 7) -> None:
        self.sample_rate = sample_rate
        self._random = random.Random(seed)

    def synthesise(self, duration_seconds: float, fundamental_hz: float = 120.0) -> bytes:
        total = int(duration_seconds * self.sample_rate)
        samples = bytearray()
        syllable_rate = 4.0  # syllables per second
        for index in range(total):
            t = index / self.sample_rate
            envelope = 0.5 * (1.0 + math.sin(2 * math.pi * syllable_rate * t - math.pi / 2))
            envelope *= 0.85 + 0.15 * math.sin(2 * math.pi * 0.7 * t)
            voiced = (
                math.sin(2 * math.pi * fundamental_hz * t)
                + 0.45 * math.sin(2 * math.pi * fundamental_hz * 2 * t)
                + 0.22 * math.sin(2 * math.pi * fundamental_hz * 3 * t)
            ) / 1.67
            noise = self._random.uniform(-0.06, 0.06)
            value = max(-1.0, min(1.0, 0.72 * envelope * voiced + noise))
            samples += struct.pack("<h", int(value * 27000))
        return bytes(samples)

    async def next_chunk(self, duration_seconds: float = 3.0, fundamental_hz: float = 120.0) -> RawAudio:
        return RawAudio(
            data=self.synthesise(duration_seconds, fundamental_hz),
            mime_type="audio/pcm16",
            sample_rate=self.sample_rate,
            channels=1,
            duration_seconds=duration_seconds,
        )
