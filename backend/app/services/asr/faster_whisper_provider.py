"""Faster-Whisper adapter.

Installed via ``pip install -r requirements-asr.txt``. The import is lazy so the
prototype runs (and Demo Mode works) without the ML stack present.
"""

from __future__ import annotations

import asyncio
import io
import wave
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger, track_duration
from app.services.asr.base import ASRProvider
from app.services.asr.medical_normalizer import normalize_medical_transcript
from app.services.types import ASRSegment, AudioFrame

logger = get_logger(__name__)


class FasterWhisperUnavailable(RuntimeError):
    pass


class FasterWhisperProvider(ASRProvider):
    name = "faster_whisper"
    is_mock = False

    def __init__(
        self,
        model_name: str | None = None,
        device: str = "auto",
        compute_type: str = "int8",
        initial_prompt: str | None = None,
    ) -> None:
        self.model_name = model_name or settings.faster_whisper_model
        self.device = device
        self.compute_type = compute_type
        self.initial_prompt = initial_prompt or getattr(settings, "indic_asr_prompt_biasing", None)
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel  # type: ignore import-not-found
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise FasterWhisperUnavailable(
                "faster-whisper is not installed. Install requirements-asr.txt and set ASR_PROVIDER=faster_whisper."
            ) from exc
        logger.info("loading_asr_model", extra={"model": self.model_name, "device": self.device})
        self._model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)
        return self._model

    async def warmup(self) -> None:  # pragma: no cover - requires model download
        await asyncio.to_thread(self._load)

    async def transcribe(self, audio_chunk: AudioFrame) -> list[ASRSegment]:  # pragma: no cover - optional dependency
        if not audio_chunk.decoded or not audio_chunk.pcm:
            return []
        with track_duration("asr", logger, provider=self.name, session_id=audio_chunk.session_id):
            model = await asyncio.to_thread(self._load)
            wav_bytes = self._to_wav(audio_chunk)
            transcribe_kwargs: dict[str, Any] = {
                "beam_size": 5,
                "vad_filter": True,
                "word_timestamps": True,
            }
            if self.initial_prompt:
                transcribe_kwargs["initial_prompt"] = self.initial_prompt
            segments, _info = await asyncio.to_thread(
                model.transcribe,
                io.BytesIO(wav_bytes),
                **transcribe_kwargs,
            )
            results: list[ASRSegment] = []
            for index, segment in enumerate(segments):
                confidence = self._confidence(segment)
                cleaned_text = normalize_medical_transcript(segment.text.strip())
                results.append(
                    ASRSegment(
                        id=f"asr_{audio_chunk.sequence:04d}_{index:02d}",
                        text=cleaned_text,
                        start_time=round(audio_chunk.start_time + segment.start, 3),
                        end_time=round(audio_chunk.start_time + segment.end, 3),
                        confidence=confidence,
                        words=[
                            {
                                "word": word.word,
                                "start": round(audio_chunk.start_time + word.start, 3),
                                "end": round(audio_chunk.start_time + word.end, 3),
                            }
                            for word in (getattr(segment, "words", None) or [])
                        ],
                    )
                )
            return [segment for segment in results if segment.text]

    @staticmethod
    def _confidence(segment: Any) -> float:  # pragma: no cover - optional dependency
        logprob = getattr(segment, "avg_logprob", None)
        if logprob is None:
            return 0.8
        import math

        return round(min(max(math.exp(logprob), 0.0), 1.0), 4)

    @staticmethod
    def _to_wav(frame: AudioFrame) -> bytes:  # pragma: no cover - optional dependency
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(frame.sample_rate)
            handle.writeframes(frame.pcm)
        return buffer.getvalue()
