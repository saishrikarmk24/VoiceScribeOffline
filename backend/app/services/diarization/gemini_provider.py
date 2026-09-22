"""Diarization derived from Gemini's speaker-attributed transcription.

Gemini returns speaker labels alongside the transcript, so re-sending the audio
to a second model would cost latency and money for no gain. The ASR stage
publishes its turns onto the frame hints and this provider consumes them.

The pipeline runs ASR before diarization specifically so this handoff works.
When no turns are present (silence, or a different ASR provider), an empty list
is returned and the speaker becomes UNKNOWN downstream - never a guess.
"""

from __future__ import annotations

from app.core.logging import get_logger
from app.services.asr.gemini_provider import DIARIZATION_HINT_KEY
from app.services.diarization.base import DiarizationService
from app.services.types import AudioFrame, DiarizationTurn

logger = get_logger(__name__)


class GeminiDiarizationProvider(DiarizationService):
    name = "gemini_diarization"
    is_mock = False

    async def diarize(self, audio: AudioFrame) -> list[DiarizationTurn]:
        turns = audio.hints.get(DIARIZATION_HINT_KEY)
        if not turns:
            return []
        return [turn for turn in turns if isinstance(turn, DiarizationTurn)]
