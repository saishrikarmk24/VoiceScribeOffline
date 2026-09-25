"""AI4Bharat IndicWhisper & Code-Switched Speech Recognition Provider.

Specifically designed for Indian multilingual healthcare dialogues with code-switching
between English and Indian regional languages (Hinglish, Tanglish, Telugish, etc.).
Fine-tuned on the AI4Bharat Vistaar benchmark (10,700+ hours across 12 Indian languages).

Supports:
1. Native AI4Bharat IndicWhisper models via HuggingFace Transformers pipeline.
2. Fast CTranslate2 Multilingual Whisper with Code-Switching Prompt Conditioning.
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
from app.services.asr.medical_normalizer import normalize_medical_transcript
from app.services.types import ASRSegment, AudioFrame

logger = get_logger(__name__)

# Language hint only. Never list drug names — Whisper copies prompt words into output.
DEFAULT_CODE_SWITCH_PROMPT = ""


class IndicWhisperUnavailable(RuntimeError):
    pass


class IndicWhisperASRProvider(ASRProvider):
    """AI4Bharat IndicWhisper & Multilingual Code-Switching ASR Provider."""

    name = "indic_whisper"
    is_mock = False

    def __init__(
        self,
        model_name: str | None = None,
        language: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
        initial_prompt: str | None = None,
    ) -> None:
        self.model_name = model_name or getattr(settings, "indic_whisper_model", "ai4bharat/whisper-medium-hi_alldata_multigpu")
        self.fallback_whisper_model = settings.faster_whisper_model
        self.language = (language or settings.indic_asr_language).lower().strip()
        if self.language in ("auto", "none", "", "code_switching", "indic"):
            self.target_language = None
        else:
            self.target_language = self.language

        self.device = device or getattr(settings, "asr_device", "auto")
        self.compute_type = compute_type or getattr(settings, "asr_compute_type", "int8")
        self.use_transformers = bool(getattr(settings, "indic_whisper_use_transformers", False))
        self.initial_prompt = (
            initial_prompt
            if initial_prompt is not None
            else (getattr(settings, "indic_asr_prompt_biasing", "") or DEFAULT_CODE_SWITCH_PROMPT)
        )
        self._engine: Any | None = None
        self._engine_type: str = "unknown"

    def _load(self) -> Any:
        if self._engine is not None:
            return self._engine

        # HuggingFace Transformers + whisper-medium-hi is the 4050 VRAM bomb.
        # Only load it when explicitly enabled.
        if self.use_transformers:
            try:
                import torch  # type: ignore
                from transformers import pipeline  # type: ignore

                device_str = "cuda:0" if torch.cuda.is_available() else "cpu"
                logger.info("loading_indic_whisper_transformers", extra={"model": self.model_name, "device": device_str})
                self._engine = pipeline(
                    "automatic-speech-recognition",
                    model=self.model_name,
                    device=device_str,
                )
                if self.target_language and hasattr(self._engine.tokenizer, "get_decoder_prompt_ids"):
                    forced_ids = self._engine.tokenizer.get_decoder_prompt_ids(
                        language=self.target_language,
                        task="transcribe",
                    )
                    self._engine.model.config.forced_decoder_ids = forced_ids

                self._engine_type = "transformers"
                return self._engine
            except (ImportError, Exception) as hf_err:
                logger.debug("transformers_indic_whisper_not_available", extra={"error": str(hf_err)})

        # Default: multilingual Faster-Whisper (CTranslate2 int8). Fits an RTX 4050.
        try:
            from faster_whisper import WhisperModel  # type: ignore

            model_id = self.fallback_whisper_model
            try:
                logger.info(
                    "loading_faster_whisper_indic",
                    extra={"model": model_id, "device": self.device, "compute": self.compute_type},
                )
                self._engine = WhisperModel(
                    model_id,
                    device=self.device,
                    compute_type=self.compute_type,
                )
            except Exception:
                model_id = self.fallback_whisper_model
                if model_id.endswith(".en"):
                    model_id = model_id[:-3]
                logger.info(
                    "loading_fallback_whisper_multilingual",
                    extra={"model": model_id, "device": self.device, "compute": self.compute_type},
                )
                self._engine = WhisperModel(
                    model_id,
                    device=self.device,
                    compute_type=self.compute_type,
                )

            self._engine_type = "faster_whisper"
            return self._engine
        except ImportError as fw_err:
            raise IndicWhisperUnavailable(
                "Neither transformers nor faster-whisper is installed for Indic speech recognition. "
                "Run 'pip install faster-whisper numpy'."
            ) from fw_err

    async def transcribe(self, audio_chunk: AudioFrame) -> list[ASRSegment]:
        wav_bytes = self._to_wav(audio_chunk)
        engine = self._load()

        with track_duration("asr_indic_whisper_transcribe"):
            if self._engine_type == "transformers":
                return await asyncio.to_thread(self._transcribe_transformers, engine, wav_bytes, audio_chunk)
            else:
                return await asyncio.to_thread(self._transcribe_faster_whisper, engine, wav_bytes, audio_chunk)

    def _transcribe_faster_whisper(self, model: Any, wav_bytes: bytes, audio_chunk: AudioFrame) -> list[ASRSegment]:
        segments, info = model.transcribe(
            io.BytesIO(wav_bytes),
            language=self.target_language,
            task="transcribe",
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            word_timestamps=True,
            condition_on_previous_text=False,
            temperature=0.0,
        )

        detected_lang = getattr(info, "language", self.target_language or "unknown")
        detected_prob = getattr(info, "language_probability", 1.0)
        logger.debug(
            "indic_whisper_detected",
            extra={
                "detected_lang": detected_lang,
                "confidence": round(detected_prob, 3),
                "session_id": audio_chunk.session_id,
            },
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
        return [s for s in results if s.text]

    def _transcribe_transformers(self, pipeline_fn: Any, wav_bytes: bytes, audio_chunk: AudioFrame) -> list[ASRSegment]:
        import numpy as np  # type: ignore

        # Convert 16-bit PCM bytes to float32 audio array normalized to [-1.0, 1.0]
        audio_arr = np.frombuffer(audio_chunk.pcm, dtype=np.int16).astype(np.float32) / 32768.0
        generate_kwargs: dict[str, Any] = {"task": "transcribe"}
        if self.target_language:
            generate_kwargs["language"] = self.target_language

        output = pipeline_fn(
            audio_arr,
            generate_kwargs=generate_kwargs,
            return_timestamps=True,
        )
        text = normalize_medical_transcript((output.get("text") or "").strip())
        if not text:
            return []

        duration = len(audio_arr) / float(audio_chunk.sample_rate)
        return [
            ASRSegment(
                id=f"asr_{audio_chunk.sequence:04d}_00",
                text=text,
                start_time=round(audio_chunk.start_time, 3),
                end_time=round(audio_chunk.start_time + duration, 3),
                confidence=0.92,
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
            "engine": self._engine_type,
            "model": self.model_name,
            "target_language": self.target_language or "auto (code-switching)",
            "device": self.device,
        }
