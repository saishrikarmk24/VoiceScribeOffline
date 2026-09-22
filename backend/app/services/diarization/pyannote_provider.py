"""pyannote.audio adapter.

Requires ``requirements-asr.txt`` plus a Hugging Face token accepted for the
pretrained pipeline. Imports are lazy so Demo Mode never needs the ML stack.
"""

from __future__ import annotations

import asyncio
import io
import wave
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger, track_duration
from app.services.diarization.base import DiarizationService
from app.services.types import AudioFrame, DiarizationTurn

logger = get_logger(__name__)


class PyannoteUnavailable(RuntimeError):
    pass


class PyannoteDiarizationProvider(DiarizationService):
    name = "pyannote"
    is_mock = False

    def __init__(self, model_name: str | None = None, token: str | None = None) -> None:
        self.model_name = model_name or settings.pyannote_model
        self.token = token or settings.huggingface_token
        self._pipeline: Any | None = None

    def _load(self) -> Any:
        if self._pipeline is not None:
            return self._pipeline
        try:
            from pyannote.audio import Pipeline  # type: ignore import-not-found
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise PyannoteUnavailable(
                "pyannote.audio is not installed. Install requirements-asr.txt and set DIARIZATION_PROVIDER=pyannote."
            ) from exc
        if not self.token:
            raise PyannoteUnavailable("HUGGINGFACE_TOKEN is required for the pyannote pretrained pipeline.")
        logger.info("loading_diarization_model", extra={"model": self.model_name})
        try:
            self._pipeline = Pipeline.from_pretrained(self.model_name, token=self.token)
        except TypeError:
            self._pipeline = Pipeline.from_pretrained(self.model_name, use_auth_token=self.token)
        return self._pipeline

    async def diarize(self, audio: AudioFrame) -> list[DiarizationTurn]:  # pragma: no cover - optional dependency
        if not audio.decoded or not audio.pcm:
            return []
        with track_duration("diarization", logger, provider=self.name, session_id=audio.session_id):
            pipeline = await asyncio.to_thread(self._load)
            annotation = await asyncio.to_thread(pipeline, io.BytesIO(self._to_wav(audio)))
            turns: list[DiarizationTurn] = []
            for turn, _track, speaker in annotation.itertracks(yield_label=True):
                turns.append(
                    DiarizationTurn(
                        speaker_id=str(speaker).lower().replace(" ", "_"),
                        start_time=round(audio.start_time + turn.start, 3),
                        end_time=round(audio.start_time + turn.end, 3),
                        confidence=0.85,
                    )
                )
            return turns

    @staticmethod
    def _to_wav(frame: AudioFrame) -> bytes:  # pragma: no cover - optional dependency
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(frame.sample_rate)
            handle.writeframes(frame.pcm)
        return buffer.getvalue()
