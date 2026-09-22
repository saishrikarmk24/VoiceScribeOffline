"""Diarization provider selection.

Demo Mode uses the script-hinted mock diarizer. Real recordings default to local
two-speaker clustering so audio never has to go to Gemini for speaker labels.
pyannote remains an optional upgrade; Gemini diarization is only used when
explicitly configured (paired with Gemini ASR).
"""

from __future__ import annotations

from app.core.config import DiarizationProviderName, settings
from app.core.logging import get_logger
from app.models.enums import AudioSource
from app.services.diarization.base import DiarizationService
from app.services.diarization.local_provider import LocalDiarizationProvider
from app.services.diarization.mock_provider import MockDiarizationProvider

logger = get_logger(__name__)


def build_diarization_provider(audio_source: AudioSource | None = None) -> DiarizationService:
    """Instantiate the diarizer appropriate for ``audio_source``."""
    if audio_source is AudioSource.SIMULATION:
        return MockDiarizationProvider()

    if settings.diarization_provider is DiarizationProviderName.PYANNOTE:
        from app.services.diarization.pyannote_provider import (
            PyannoteDiarizationProvider,
            PyannoteUnavailable,
        )

        try:
            provider = PyannoteDiarizationProvider()
            provider._load()
            return provider
        except PyannoteUnavailable as exc:  # pragma: no cover - optional dependency
            logger.warning(
                "pyannote_unavailable_falling_back_to_local", 
                extra={"error": str(exc), "message": "Pyannote is not available. Using local diarization fallback."}
            )
            return LocalDiarizationProvider()

    if settings.diarization_provider is DiarizationProviderName.CONVERSATIONAL:
        from app.services.diarization.conversational_provider import ConversationalDiarizationProvider

        return ConversationalDiarizationProvider()

    if settings.diarization_provider is DiarizationProviderName.GEMINI:
        from app.services.diarization.gemini_provider import GeminiDiarizationProvider

        return GeminiDiarizationProvider()

    if settings.diarization_provider is DiarizationProviderName.MOCK:
        return MockDiarizationProvider()

    return LocalDiarizationProvider()


__all__ = [
    "DiarizationService",
    "LocalDiarizationProvider",
    "MockDiarizationProvider",
    "build_diarization_provider",
]
