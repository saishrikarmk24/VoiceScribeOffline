"""AI4Bharat IndicConformer & Indic Multilingual Speech Recognition Provider.

Provides 100% offline speech-to-text with specialized optimization for Indian languages:
- Hindi (hi), Tamil (ta), Telugu (te), Malayalam (ml), Bengali (bn)
- Marathi (mr), Gujarati (gu), Kannada (kn), Punjabi (pa), Odia (or)
- Code-mixed Indian English, Hinglish, and Tanglish

Supports AI4Bharat IndicConformer checkpoints (via NeMo/Transformers) and
high-performance CTranslate2 Indic-tuned multilingual models with domain-specific
clinical vocabulary prompt biasing.
"""

from __future__ import annotations

import asyncio
import io
import math
import wave
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger, track_duration
from app.services.asr.base import ASRProvider
from app.services.types import ASRSegment, AudioFrame

logger = get_logger(__name__)


class IndicConformerUnavailable(RuntimeError):
    pass


class IndicConformerASRProvider(ASRProvider):
    """Offline Multilingual Indic Speech-to-Text Provider."""

    name = "indic_conformer"
    is_mock = False

    def __init__(
        self,
        model_name: str | None = None,
        language: str | None = None,
        device: str = "auto",
        compute_type: str = "int8",
        prompt_biasing: str | None = None,
    ) -> None:
        self.model_name = model_name or settings.indic_conformer_model
        self.fallback_whisper_model = settings.faster_whisper_model
        self.language = (language or settings.indic_asr_language).lower().strip()
        if self.language in ("auto", "none", ""):
            self.target_language = None
        else:
            self.target_language = self.language
        self.device = device
        self.compute_type = compute_type
        self.prompt_biasing = prompt_biasing or settings.indic_asr_prompt_biasing
        self._engine: Any | None = None
        self._engine_type: str = "unknown"

    def _load(self) -> Any:
        if self._engine is not None:
            return self._engine

        # Strategy 1: Check for native NeMo IndicConformer if installed
        try:
            import nemo.collections.asr as nemo_asr  # type: ignore

            logger.info("loading_indic_conformer_nemo", extra={"model": self.model_name})
            self._engine = nemo_asr.models.ASRModel.from_pretrained(model_name=self.model_name)
            self._engine_type = "nemo"
            return self._engine
        except (ImportError, Exception) as nemo_err:
            logger.debug("nemo_indic_conformer_not_available", extra={"error": str(nemo_err)})

        # Strategy 2: Check for HuggingFace Transformers pipeline for IndicConformer
        try:
            import torch  # type: ignore
            from transformers import pipeline  # type: ignore

            logger.info("loading_indic_conformer_transformers", extra={"model": self.model_name})
            self._engine = pipeline(
                "automatic-speech-recognition",
                model=self.model_name,
                device="cuda" if torch.cuda.is_available() else "cpu",
            )
            self._engine_type = "transformers"
            return self._engine
        except (ImportError, Exception) as hf_err:
            logger.debug("transformers_indic_conformer_not_available", extra={"error": str(hf_err)})

        # Strategy 3: Fast CTranslate2 Multilingual Indic Whisper Engine with Clinical Prompt Biasing
        try:
            from faster_whisper import WhisperModel  # type: ignore

            model_id = self.fallback_whisper_model
            # Ensure we use multilingual weights, not English-only
            if model_id.endswith(".en"):
                model_id = model_id[:-3]

            logger.info(
                "loading_indic_multilingual_asr",
                extra={
                    "model": model_id,
                    "device": self.device,
                    "compute_type": self.compute_type,
                    "language": self.target_language or "auto-detect",
                },
            )
            self._engine = WhisperModel(model_id, device=self.device, compute_type=self.compute_type)
            self._engine_type = "faster_whisper_indic"
            return self._engine
        except ImportError as exc:
            raise IndicConformerUnavailable(
                "No offline ASR engine could be loaded. Install faster-whisper or IndicConformer requirements."
            ) from exc

    async def warmup(self) -> None:
        await asyncio.to_thread(self._load)

    async def transcribe(self, audio_chunk: AudioFrame) -> list[ASRSegment]:
        if not audio_chunk.decoded or not audio_chunk.pcm:
            return []

        with track_duration("asr", logger, provider=self.name, session_id=audio_chunk.session_id):
            engine = await asyncio.to_thread(self._load)
            wav_bytes = self._to_wav(audio_chunk)

            if self._engine_type == "faster_whisper_indic":
                return await asyncio.to_thread(self._transcribe_whisper, engine, wav_bytes, audio_chunk)
            elif self._engine_type == "transformers":
                return await asyncio.to_thread(self._transcribe_transformers, engine, wav_bytes, audio_chunk)
            else:
                return await asyncio.to_thread(self._transcribe_whisper, engine, wav_bytes, audio_chunk)

    def _transcribe_whisper(self, model: Any, wav_bytes: bytes, audio_chunk: AudioFrame) -> list[ASRSegment]:
        segments, info = model.transcribe(
            io.BytesIO(wav_bytes),
            language=self.target_language,
            initial_prompt=self.prompt_biasing,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            word_timestamps=True,
        )

        detected_lang = getattr(info, "language", self.target_language or "unknown")
        detected_prob = getattr(info, "language_probability", 1.0)
        logger.debug(
            "indic_asr_detection",
            extra={
                "detected_lang": detected_lang,
                "confidence": round(detected_prob, 3),
                "session_id": audio_chunk.session_id,
            },
        )

        results: list[ASRSegment] = []
        for index, segment in enumerate(segments):
            confidence = self._confidence(segment)
            results.append(
                ASRSegment(
                    id=f"asr_{audio_chunk.sequence:04d}_{index:02d}",
                    text=segment.text.strip(),
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
        return [s for s in results if s.text]

    def _transcribe_transformers(self, pipeline_fn: Any, wav_bytes: bytes, audio_chunk: AudioFrame) -> list[ASRSegment]:
        import numpy as np  # type: ignore

        # Convert 16-bit PCM bytes to float32 audio array
        audio_arr = np.frombuffer(audio_chunk.pcm, dtype=np.int16).astype(np.float32) / 32768.0
        output = pipeline_fn(audio_arr, return_timestamps=True)
        text = (output.get("text") or "").strip()
        if not text:
            return []
        duration = len(audio_arr) / float(audio_chunk.sample_rate)
        return [
            ASRSegment(
                id=f"asr_{audio_chunk.sequence:04d}_00",
                text=text,
                start_time=round(audio_chunk.start_time, 3),
                end_time=round(audio_chunk.start_time + duration, 3),
                confidence=0.90,
                words=[],
            )
        ]

    @staticmethod
    def _confidence(segment: Any) -> float:
        logprob = getattr(segment, "avg_logprob", None)
        if logprob is None:
            return 0.85
        return round(min(max(math.exp(logprob), 0.0), 1.0), 4)

    @staticmethod
    def _to_wav(frame: AudioFrame) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(frame.sample_rate)
            handle.writeframes(frame.pcm)
        return buffer.getvalue()

    def describe(self) -> dict[str, object]:
        return {
            "name": self.name,
            "mock": self.is_mock,
            "engine_type": self._engine_type,
            "language": self.target_language or "auto",
            "model": self.model_name,
        }
