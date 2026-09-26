"""Faster-Whisper adapter.

Installed via ``pip install -r requirements-asr.txt``. The import is lazy so the
prototype runs (and Demo Mode works) without the ML stack present.
"""

from __future__ import annotations

import asyncio
import io
import wave
from typing import Any

from app.core.config import BACKEND_ROOT, settings
from app.core.logging import get_logger, track_duration
from app.services.asr.base import ASRProvider
from app.services.asr.medical_normalizer import normalize_medical_transcript
from app.services.types import ASRSegment, AudioFrame

logger = get_logger(__name__)

LOCAL_MODELS_DIR = BACKEND_ROOT / "models"


def resolve_local_model(model_name: str) -> str:
    """Prefer ``backend/models/faster-whisper-<name>`` downloaded by the installer.

    The Hugging Face client can stall on some Windows networks, so the installer
    fetches the files with curl into this folder and the app never needs the hub.
    """
    local = LOCAL_MODELS_DIR / f"faster-whisper-{model_name}"
    if (local / "model.bin").is_file():
        return str(local)
    return model_name


def _setup_cuda_libs() -> None:
    """Ensure Linux dynamic linker can find nvidia-cublas and nvidia-cudnn wheels if installed."""
    import os
    import sys
    if sys.platform != "win32":
        try:
            import nvidia.cublas.lib as cublas_lib
            import nvidia.cudnn.lib as cudnn_lib
            extra_paths = [cublas_lib.__path__[0], cudnn_lib.__path__[0]]
            current = os.environ.get("LD_LIBRARY_PATH", "")
            for p in extra_paths:
                if p not in current:
                    current = f"{p}:{current}" if current else p
            os.environ["LD_LIBRARY_PATH"] = current
        except Exception:
            pass


def _detect_device_and_compute(requested_device: str | None, requested_compute: str | None) -> tuple[str, str]:
    device = requested_device or getattr(settings, "asr_device", "auto")
    compute = requested_compute or getattr(settings, "asr_compute_type", "auto")

    if device == "auto":
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            device = "cpu"

    if compute == "auto":
        compute = "float16" if device == "cuda" else "int8"

    return device, compute


class FasterWhisperUnavailable(RuntimeError):
    pass


class FasterWhisperProvider(ASRProvider):
    name = "faster_whisper"
    is_mock = False

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
        initial_prompt: str | None = None,
    ) -> None:
        self.model_name = resolve_local_model(model_name or settings.faster_whisper_model)
        self.device = device or getattr(settings, "asr_device", "auto")
        self.compute_type = compute_type or getattr(settings, "asr_compute_type", "auto")
        # Drug names in initial_prompt leak into the transcript. Keep this empty.
        self.initial_prompt = initial_prompt if initial_prompt is not None else ""
        self._model: Any | None = None

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        _setup_cuda_libs()
        try:
            from faster_whisper import WhisperModel  # type: ignore import-not-found
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise FasterWhisperUnavailable(
                "faster-whisper is not installed. Install requirements-asr.txt and set ASR_PROVIDER=faster_whisper."
            ) from exc

        device, compute = _detect_device_and_compute(self.device, self.compute_type)
        logger.info("loading_asr_model", extra={"model": self.model_name, "device": device, "compute": compute})
        try:
            self._model = WhisperModel(self.model_name, device=device, compute_type=compute)
            self.device = device
            self.compute_type = compute
        except Exception as exc:
            logger.warning(
                "asr_gpu_or_device_failed_using_cpu",
                extra={"requested_device": device, "error": str(exc)},
            )
            self.device = "cpu"
            self.compute_type = "int8"
            self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
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
                "beam_size": 1,
                "best_of": 1,
                "vad_filter": True,
                "vad_parameters": {"min_silence_duration_ms": 300},
                "word_timestamps": True,
                "condition_on_previous_text": False,
                "temperature": 0.0,
                "task": "transcribe",
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

    def describe(self) -> dict[str, object]:
        return {
            "name": self.name,
            "mock": self.is_mock,
            "model": self.model_name,
            "device": self.device,
            "compute_type": self.compute_type,
        }

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
