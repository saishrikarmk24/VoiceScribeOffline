"""ASR provider contract."""

from __future__ import annotations

import abc

from app.services.types import ASRSegment, AudioFrame


class ASRUnavailable(RuntimeError):
    """No usable speech-to-text engine for real audio.

    Raised rather than returning substitute text, so a misconfiguration surfaces
    as a visible error instead of a fabricated transcript.
    """


class ASRProvider(abc.ABC):
    """Speech-to-text over a preprocessed audio frame."""

    name: str = "base"
    is_mock: bool = False

    @abc.abstractmethod
    async def transcribe(self, audio_chunk: AudioFrame) -> list[ASRSegment]:
        """Return zero or more hypotheses for the supplied frame."""

    async def warmup(self) -> None:
        """Optional model preload hook."""

    def describe(self) -> dict[str, object]:
        return {"name": self.name, "mock": self.is_mock}
