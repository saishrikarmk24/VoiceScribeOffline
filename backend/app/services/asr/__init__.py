"""ASR provider selection.

The single most important rule here: **scripted transcription is only ever used
for scripted audio.** Demo Mode synthesises speech-shaped tones that no acoustic
model could transcribe, so it is paired with the script-driven mock provider. Real
microphone or uploaded audio must reach a real speech-to-text engine, and if none
is usable the pipeline raises instead of substituting demo text - a wrong
transcript in a clinical record is worse than a visible failure.
"""

from __future__ import annotations

from app.core.config import ASRProviderName, settings
from app.core.logging import get_logger
from app.models.enums import AudioSource
from app.services.asr.base import ASRProvider, ASRUnavailable
from app.services.asr.mock_provider import MockASRProvider
from app.services.types import ASRSegment, AudioFrame

logger = get_logger(__name__)


class UnavailableASRProvider(ASRProvider):
    """Placeholder that fails loudly when real audio arrives.

    Used instead of silently degrading to the scripted provider so that a
    misconfiguration surfaces as an error in the UI rather than as a plausible
    but fabricated transcript.
    """

    name = "unavailable"
    is_mock = False

    def __init__(self, reason: str) -> None:
        self.reason = reason

    async def transcribe(self, audio_chunk: AudioFrame) -> list[ASRSegment]:
        raise ASRUnavailable(self.reason)

    def describe(self) -> dict[str, object]:
        return {"name": self.name, "mock": False, "reason": self.reason}


def build_asr_provider(script=None, audio_source: AudioSource | None = None) -> ASRProvider:
    """Return the ASR provider appropriate for ``audio_source``.

    ``audio_source`` defaults to real audio; scripted transcription has to be
    asked for explicitly so that a forgotten argument can never downgrade a real
    recording to demo content.
    """
    if audio_source is AudioSource.SIMULATION:
        return MockASRProvider(script=script)

    if settings.asr_provider is ASRProviderName.MOCK:
        return UnavailableASRProvider(
            "ASR_PROVIDER=mock replays a scripted demo conversation and cannot transcribe real "
            "audio. Set ASR_PROVIDER=faster_whisper or ASR_PROVIDER=gemini."
        )

    if settings.asr_provider is ASRProviderName.GEMINI:
        from app.services.asr.gemini_provider import GeminiASRProvider

        if not settings.gemini_configured:
            return UnavailableASRProvider(
                "ASR_PROVIDER=gemini requires GEMINI_API_KEY. Add the key to .env and restart the backend."
            )
        if not GeminiASRProvider.sdk_available():
            return UnavailableASRProvider(
                "The google-genai package is not importable by the running backend, so audio cannot be "
                "transcribed. Start the backend with the project virtualenv (backend/.venv) or run "
                "`pip install -r backend/requirements.txt`."
            )
        return GeminiASRProvider()

    if settings.asr_provider is ASRProviderName.INDIC_WHISPER:
        try:
            from app.services.asr.indic_whisper_provider import IndicWhisperASRProvider

            return IndicWhisperASRProvider()
        except Exception as exc:
            return UnavailableASRProvider(f"Failed to initialize IndicWhisper ASR: {exc}")

    if settings.asr_provider is ASRProviderName.INDIC_CONFORMER:
        try:
            from app.services.asr.indic_conformer_provider import IndicConformerASRProvider

            return IndicConformerASRProvider()
        except Exception as exc:
            return UnavailableASRProvider(f"Failed to initialize IndicConformer ASR: {exc}")

    if settings.asr_provider is ASRProviderName.FASTER_WHISPER:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return UnavailableASRProvider(
                "faster-whisper is not installed. From the backend folder run: "
                "pip install -r requirements-asr.txt"
            )
        from app.services.asr.faster_whisper_provider import FasterWhisperProvider

        return FasterWhisperProvider()

    return UnavailableASRProvider(f"Unknown ASR provider: {settings.asr_provider}")


__all__ = [
    "ASRProvider",
    "ASRUnavailable",
    "MockASRProvider",
    "UnavailableASRProvider",
    "build_asr_provider",
]
