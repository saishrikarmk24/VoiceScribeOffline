"""Deterministic ASR provider used for Demo Mode.

The provider is driven by a *script*: the text of the demo encounter is
known in advance, and the provider emits the next utterance whenever voice
activity is detected in the incoming audio frame. Timestamps, confidence and
word offsets are produced exactly as a real engine would, so nothing downstream
knows or cares that the text did not come from an acoustic model.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.core.logging import get_logger, track_duration
from app.services.asr.base import ASRProvider
from app.services.demo.conversations import ScriptedUtterance, SimulationScript, get_script
from app.services.types import ASRSegment, AudioFrame

logger = get_logger(__name__)


@dataclass(slots=True)
class _Cursor:
    index: int = 0


class MockASRProvider(ASRProvider):
    name = "mock"
    is_mock = True

    def __init__(self, script: SimulationScript | None = None, latency_seconds: float = 0.05) -> None:
        self.script = script or get_script(None)
        self.latency_seconds = latency_seconds
        self._cursors: dict[str, _Cursor] = {}

    def reset(self, session_id: str) -> None:
        self._cursors.pop(session_id, None)

    def peek(self, session_id: str) -> ScriptedUtterance | None:
        cursor = self._cursors.setdefault(session_id, _Cursor())
        if cursor.index >= len(self.script.utterances):
            return None
        return self.script.utterances[cursor.index]

    async def transcribe(self, audio_chunk: AudioFrame) -> list[ASRSegment]:
        with track_duration("asr", logger, provider=self.name, session_id=audio_chunk.session_id):
            await asyncio.sleep(self.latency_seconds)

            forced_text = audio_chunk.hints.get("script_text")
            forced_confidence = float(audio_chunk.hints.get("script_confidence", 0.94))

            if forced_text:
                text, confidence = str(forced_text), forced_confidence
            else:
                if audio_chunk.speech_ratio < 0.08:
                    return []  # silence in, nothing out
                cursor = self._cursors.setdefault(audio_chunk.session_id, _Cursor())
                if cursor.index >= len(self.script.utterances):
                    return []
                utterance = self.script.utterances[cursor.index]
                cursor.index += 1
                text, confidence = utterance.text, utterance.confidence

            start = audio_chunk.start_time
            end = max(audio_chunk.end_time, start + 0.4)
            return [
                ASRSegment(
                    id=f"asr_{audio_chunk.sequence:04d}",
                    text=text,
                    start_time=round(start, 3),
                    end_time=round(end, 3),
                    confidence=round(min(max(confidence, 0.0), 1.0), 4),
                    words=self._word_offsets(text, start, end),
                )
            ]

    @staticmethod
    def _word_offsets(text: str, start: float, end: float) -> list[dict[str, object]]:
        words = text.split()
        if not words:
            return []
        step = (end - start) / len(words)
        return [
            {
                "word": word,
                "start": round(start + index * step, 3),
                "end": round(start + (index + 1) * step, 3),
            }
            for index, word in enumerate(words)
        ]
