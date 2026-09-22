"""Deterministic diarization for Demo Mode.

Two strategies are used, in priority order:

1. If the audio frame carries a script hint (Demo Mode), that speaker is used.
2. Otherwise the frame's pitch estimate is compared against previously observed
   voices, and the closest cluster wins - a miniature version of what an
   embedding-based diarizer does.
"""

from __future__ import annotations

import array
import asyncio

from app.core.logging import get_logger, track_duration
from app.services.diarization.base import DiarizationService
from app.services.types import AudioFrame, DiarizationTurn

logger = get_logger(__name__)


class MockDiarizationProvider(DiarizationService):
    name = "mock"
    is_mock = True

    def __init__(self, max_speakers: int = 4, latency_seconds: float = 0.03) -> None:
        self.max_speakers = max_speakers
        self.latency_seconds = latency_seconds
        self._clusters: dict[str, list[tuple[str, float]]] = {}

    def reset(self, session_id: str) -> None:
        self._clusters.pop(session_id, None)

    async def diarize(self, audio: AudioFrame) -> list[DiarizationTurn]:
        with track_duration("diarization", logger, provider=self.name, session_id=audio.session_id):
            await asyncio.sleep(self.latency_seconds)

            hinted = audio.hints.get("speaker_label")
            if hinted:
                confidence = float(audio.hints.get("diarization_confidence", 0.94))
                return [
                    DiarizationTurn(
                        speaker_id=str(hinted),
                        start_time=round(audio.start_time, 3),
                        end_time=round(audio.end_time, 3),
                        confidence=round(confidence, 4),
                    )
                ]

            if audio.speech_ratio < 0.05:
                return []

            pitch = self._estimate_pitch(audio)
            label, confidence = self._assign_cluster(audio.session_id, pitch)
            regions = audio.speech_regions or [(0.0, audio.duration)]
            return [
                DiarizationTurn(
                    speaker_id=label,
                    start_time=round(audio.start_time + start, 3),
                    end_time=round(audio.start_time + end, 3),
                    confidence=round(confidence, 4),
                )
                for start, end in regions
                if end > start
            ]

    def _assign_cluster(self, session_id: str, pitch: float) -> tuple[str, float]:
        clusters = self._clusters.setdefault(session_id, [])
        best_label: str | None = None
        best_distance = float("inf")
        for label, centroid in clusters:
            distance = abs(centroid - pitch)
            if distance < best_distance:
                best_label, best_distance = label, distance

        if best_label is not None and best_distance < 28.0:
            updated = []
            for label, centroid in clusters:
                if label == best_label:
                    updated.append((label, centroid * 0.8 + pitch * 0.2))
                else:
                    updated.append((label, centroid))
            self._clusters[session_id] = updated
            confidence = max(0.62, 0.96 - best_distance / 100.0)
            return best_label, confidence

        if len(clusters) >= self.max_speakers:
            fallback = min(clusters, key=lambda item: abs(item[1] - pitch))
            return fallback[0], 0.6

        label = f"speaker_{len(clusters)}"
        clusters.append((label, pitch))
        return label, 0.72 if clusters else 0.8

    @staticmethod
    def _estimate_pitch(audio: AudioFrame) -> float:
        """Zero-crossing based pitch proxy - cheap and good enough to cluster."""
        if not audio.pcm or not audio.decoded:
            return 130.0
        samples = array.array("h")
        usable = len(audio.pcm) - (len(audio.pcm) % 2)
        samples.frombytes(audio.pcm[:usable])
        if len(samples) < 2:
            return 130.0
        crossings = 0
        previous = samples[0]
        for value in samples[1:]:
            if (previous >= 0 > value) or (previous < 0 <= value):
                crossings += 1
            previous = value
        seconds = len(samples) / audio.sample_rate
        if seconds <= 0:
            return 130.0
        return max(60.0, min(400.0, crossings / (2 * seconds)))
