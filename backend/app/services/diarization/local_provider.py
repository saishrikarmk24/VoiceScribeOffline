"""Local two-speaker clustering for real microphone / upload audio.

This is not pyannote. It splits the recording into short voiced windows, measures
pitch (zero-crossings) and loudness, and clusters them into at most two voices —
the usual clinician / patient pair. Same-gender overlapping speech will often
collapse to one speaker; the roster still lets a human fix the role.

Demo Mode keeps using the script-hinted mock diarizer.
"""

from __future__ import annotations

import array

from app.core.logging import get_logger, track_duration
from app.services.diarization.base import DiarizationService
from app.services.types import AudioFrame, DiarizationTurn

logger = get_logger(__name__)

_WINDOW_SECONDS = 0.45
_HOP_SECONDS = 0.20
_PITCH_JOIN = 16.0
_MAX_SPEAKERS = 2


class LocalDiarizationProvider(DiarizationService):
    name = "local"
    is_mock = False

    def __init__(self, max_speakers: int = _MAX_SPEAKERS) -> None:
        self.max_speakers = max(1, min(max_speakers, 4))
        self._centroids: dict[str, list[tuple[str, float]]] = {}

    def reset(self, session_id: str) -> None:
        self._centroids.pop(session_id, None)

    async def diarize(self, audio: AudioFrame) -> list[DiarizationTurn]:
        with track_duration("diarization", logger, provider=self.name, session_id=audio.session_id):
            if audio.speech_ratio < 0.04 or not audio.pcm:
                return []

            windows = self._windows(audio)
            if not windows:
                return []

            labelled: list[tuple[float, float, str, float]] = []
            for start, end, pitch in windows:
                label, confidence = self._assign(audio.session_id, pitch)
                labelled.append((start, end, label, confidence))
            return _merge_turns(labelled)

    def _windows(self, audio: AudioFrame) -> list[tuple[float, float, float]]:
        regions = audio.speech_regions or [(0.0, audio.duration)]
        samples = _pcm16(audio.pcm)
        if len(samples) < 32:
            return []
        rate = max(audio.sample_rate, 1)
        out: list[tuple[float, float, float]] = []
        win = max(int(_WINDOW_SECONDS * rate), 64)
        hop = max(int(_HOP_SECONDS * rate), 32)
        for rel_start, rel_end in regions:
            if rel_end - rel_start < 0.12:
                continue
            i0 = max(0, int(rel_start * rate))
            i1 = min(len(samples), int(rel_end * rate))
            index = i0
            while index + win <= i1:
                chunk = samples[index : index + win]
                pitch = _pitch_hz(chunk, rate)
                abs_start = audio.start_time + index / rate
                abs_end = audio.start_time + (index + win) / rate
                out.append((round(abs_start, 3), round(abs_end, 3), pitch))
                index += hop
        return out

    def _assign(self, session_id: str, pitch: float) -> tuple[str, float]:
        clusters = self._centroids.setdefault(session_id, [])
        best_label: str | None = None
        best_distance = float("inf")
        for label, centroid in clusters:
            distance = abs(centroid - pitch)
            if distance < best_distance:
                best_label, best_distance = label, distance

        if best_label is not None and best_distance < _PITCH_JOIN:
            updated = []
            for label, centroid in clusters:
                if label == best_label:
                    updated.append((label, centroid * 0.92 + pitch * 0.08))
                else:
                    updated.append((label, centroid))
            self._centroids[session_id] = updated
            confidence = max(0.60, 0.95 - best_distance / 80.0)
            return best_label, round(confidence, 4)

        if len(clusters) >= self.max_speakers:
            fallback = min(clusters, key=lambda item: abs(item[1] - pitch))
            return fallback[0], 0.55

        label = f"speaker_{len(clusters)}"
        clusters.append((label, pitch))
        return label, 0.75


def _merge_turns(labelled: list[tuple[float, float, str, float]]) -> list[DiarizationTurn]:
    if not labelled:
        return []
    turns: list[DiarizationTurn] = []
    start, end, label, confidence = labelled[0]
    confidences = [confidence]
    for next_start, next_end, next_label, next_confidence in labelled[1:]:
        if next_label == label and next_start - end <= 0.45:
            end = next_end
            confidences.append(next_confidence)
            continue
        turns.append(
            DiarizationTurn(
                speaker_id=label,
                start_time=round(start, 3),
                end_time=round(end, 3),
                confidence=round(sum(confidences) / len(confidences), 4),
            )
        )
        start, end, label = next_start, next_end, next_label
        confidences = [next_confidence]
    turns.append(
        DiarizationTurn(
            speaker_id=label,
            start_time=round(start, 3),
            end_time=round(end, 3),
            confidence=round(sum(confidences) / len(confidences), 4),
        )
    )
    return turns


def _pcm16(pcm: bytes) -> array.array:
    samples = array.array("h")
    usable = len(pcm) - (len(pcm) % 2)
    samples.frombytes(pcm[:usable])
    return samples


def _pitch_hz(samples: array.array, sample_rate: int) -> float:
    """Autocorrelation-based pitch detector for human speech (70Hz - 350Hz)."""
    n = len(samples)
    if n < 128:
        return 130.0
    min_lag = max(1, int(sample_rate / 350))
    max_lag = min(n - 1, int(sample_rate / 70))
    if min_lag >= max_lag:
        return 130.0

    energy = sum(s * s for s in samples)
    if energy < 1000:
        return 130.0

    best_lag = min_lag
    best_corr = -float("inf")
    step = 1 if n < 1024 else 2

    for lag in range(min_lag, max_lag, step):
        corr = sum(samples[i] * samples[i + lag] for i in range(0, n - lag, 2))
        if corr > best_corr:
            best_corr = corr
            best_lag = lag

    if best_lag > 0:
        pitch = float(sample_rate) / float(best_lag)
        return max(70.0, min(360.0, pitch))
    return 130.0
