"""Demo Mode driver.

Plays a synthetic encounter through the *real* pipeline: synthesised audio is
preprocessed, diarized, transcribed, assembled, extracted and structured exactly
as microphone input would be. Nothing is pre-computed and no transcript is
dumped at once - the timeline unfolds so the workstation behaves like a live
system.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.logging import get_logger
from app.services.demo.conversations import get_script

if TYPE_CHECKING:  # pragma: no cover
    from app.services.pipeline import SessionPipeline, SessionRuntime

logger = get_logger(__name__)


class DemoSimulationRunner:
    def __init__(self, pipeline: "SessionPipeline", runtime: "SessionRuntime") -> None:
        self.pipeline = pipeline
        self.runtime = runtime
        self.script = get_script(runtime.script_key)

    async def run(self) -> None:
        interval = max(0.2, settings.demo_segment_interval_seconds)
        logger.info(
            "demo_runner_started",
            extra={
                "session_id": self.runtime.session_id,
                "script": self.script.key,
                "utterances": len(self.script.utterances),
            },
        )
        try:
            await asyncio.sleep(min(1.5, interval))
            for utterance in self.script.utterances:
                if self.runtime.stopped:
                    return
                await self.runtime.resume_event.wait()

                raw = await self.runtime.simulator.next_chunk(
                    duration_seconds=utterance.duration, fundamental_hz=utterance.pitch_hz
                )
                await self.pipeline.ingest_audio(
                    self.runtime,
                    raw,
                    hints={
                        "speaker_label": utterance.speaker_label,
                        "script_text": utterance.text,
                        "script_confidence": utterance.confidence,
                        "diarization_confidence": min(0.97, utterance.confidence + 0.01),
                        "demo": True,
                    },
                )
                await asyncio.sleep(interval)

            if not self.runtime.stopped:
                await self.pipeline.run_ai_update(self.runtime, force=True, final=True)
        except asyncio.CancelledError:  # session stopped by the user
            raise
        except Exception:
            logger.exception("demo_runner_failed", extra={"session_id": self.runtime.session_id})
            await self.pipeline._emit_error(  # noqa: SLF001 - intentional internal notification
                self.runtime,
                "DEMO_RUNNER_FAILED",
                "The session driver stopped unexpectedly. Transcript and note remain available.",
                self.runtime.stage,
            )
