"""Speaker diarization contract."""

from __future__ import annotations

import abc

from app.services.types import AudioFrame, DiarizationTurn


class DiarizationService(abc.ABC):
    """Segments audio into speaker turns."""

    name: str = "base"
    is_mock: bool = False

    @abc.abstractmethod
    async def diarize(self, audio: AudioFrame) -> list[DiarizationTurn]:
        """Return speaker turns for the supplied frame."""

    def describe(self) -> dict[str, object]:
        return {"name": self.name, "mock": self.is_mock}
