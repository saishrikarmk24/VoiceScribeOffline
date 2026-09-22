"""Transcript assembly: ASR hypotheses + diarization turns -> utterances.

Handles the messy parts of a real pipeline: fragmented ASR output, overlapping
speech, turns with no matching transcript, and confidence aggregation.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.logging import get_logger, track_duration
from app.models.enums import SpeakerRole
from app.services.types import ASRSegment, AssembledSegment, DiarizationTurn

logger = get_logger(__name__)


@dataclass(slots=True)
class SpeakerAttribution:
    speaker_label: str
    confidence: float
    overlapping: bool


class TranscriptAssemblyService:
    def __init__(self, merge_gap_seconds: float = 0.8, min_words_to_merge: int = 4) -> None:
        self.merge_gap_seconds = merge_gap_seconds
        self.min_words_to_merge = min_words_to_merge

    # ------------------------------------------------------------- attribution
    @staticmethod
    def attribute(segment: ASRSegment, turns: list[DiarizationTurn]) -> SpeakerAttribution:
        """Pick the speaker whose turn overlaps the ASR segment the most."""
        if not turns:
            return SpeakerAttribution("unknown", 0.0, False)

        scored = [(turn, turn.overlaps(segment.start_time, segment.end_time)) for turn in turns]
        scored.sort(key=lambda item: item[1], reverse=True)
        best_turn, best_overlap = scored[0]

        if best_overlap <= 0:
            # No temporal overlap: fall back to the nearest turn by midpoint.
            midpoint = (segment.start_time + segment.end_time) / 2
            nearest = min(turns, key=lambda turn: abs((turn.start_time + turn.end_time) / 2 - midpoint))
            return SpeakerAttribution(nearest.speaker_id, round(nearest.confidence * 0.5, 4), False)

        duration = max(segment.end_time - segment.start_time, 1e-6)
        coverage = min(best_overlap / duration, 1.0)
        competing = [turn for turn, overlap in scored[1:] if overlap > 0.25 * duration]
        overlapping = bool(competing)
        confidence = best_turn.confidence * coverage
        if overlapping:
            confidence *= 0.8
        return SpeakerAttribution(best_turn.speaker_id, round(min(confidence, 1.0), 4), overlapping)

    # ---------------------------------------------------------------- assembly
    def assemble(
        self,
        asr_segments: list[ASRSegment],
        turns: list[DiarizationTurn],
        *,
        roles: dict[str, SpeakerRole] | None = None,
        start_index: int = 0,
        audio_sequence: int | None = None,
        session_id: str = "-",
    ) -> list[AssembledSegment]:
        with track_duration("transcript_assembly", logger, session_id=session_id):
            roles = roles or {}
            ordered = sorted(asr_segments, key=lambda item: (item.start_time, item.end_time))
            assembled: list[AssembledSegment] = []

            for segment in ordered:
                text = segment.text.strip()
                if not text:
                    continue
                attribution = self.attribute(segment, turns)
                combined = round(self._aggregate_confidence(segment.confidence, attribution.confidence), 4)

                if assembled and self._should_merge(assembled[-1], segment, attribution):
                    previous = assembled[-1]
                    previous.text = f"{previous.text} {text}".strip()
                    previous.end_time = max(previous.end_time, round(segment.end_time, 3))
                    previous.asr_confidence = round((previous.asr_confidence + segment.confidence) / 2, 4)
                    previous.diarization_confidence = round(
                        (previous.diarization_confidence + attribution.confidence) / 2, 4
                    )
                    previous.confidence = round(
                        self._aggregate_confidence(previous.asr_confidence, previous.diarization_confidence), 4
                    )
                    previous.overlapping = previous.overlapping or attribution.overlapping
                    continue

                index = start_index + len(assembled)
                assembled.append(
                    AssembledSegment(
                        ref=f"seg_{index + 1:03d}",
                        speaker_label=attribution.speaker_label,
                        role=roles.get(attribution.speaker_label, SpeakerRole.UNKNOWN),
                        text=text,
                        start_time=round(segment.start_time, 3),
                        end_time=round(max(segment.end_time, segment.start_time + 0.2), 3),
                        confidence=combined,
                        asr_confidence=round(segment.confidence, 4),
                        diarization_confidence=attribution.confidence,
                        overlapping=attribution.overlapping,
                        audio_sequence=audio_sequence,
                    )
                )
            return assembled

    def _should_merge(
        self, previous: AssembledSegment, segment: ASRSegment, attribution: SpeakerAttribution
    ) -> bool:
        """Merge consecutive fragments from the same speaker into one utterance."""
        if previous.speaker_label != attribution.speaker_label:
            return False
        if segment.start_time - previous.end_time > self.merge_gap_seconds:
            return False
        fragment_is_short = len(segment.text.split()) < self.min_words_to_merge
        previous_is_unterminated = not previous.text.rstrip().endswith((".", "?", "!"))
        return fragment_is_short or previous_is_unterminated

    @staticmethod
    def _aggregate_confidence(asr_confidence: float, diarization_confidence: float) -> float:
        """Weighted blend: transcription quality dominates, attribution modulates."""
        asr_confidence = min(max(asr_confidence, 0.0), 1.0)
        diarization_confidence = min(max(diarization_confidence, 0.0), 1.0)
        if diarization_confidence == 0.0:
            return asr_confidence * 0.75
        return 0.65 * asr_confidence + 0.35 * diarization_confidence


class SpeakerRoleAttributionService:
    """Heuristic role attribution, always overridable by a human.

    Clinicians ask questions and use examination/plan language; patients report
    symptoms in the first person. Role assignment is scored across a speaker's
    utterances so a single ambiguous line cannot flip a role.
    """

    DOCTOR_MARKERS = (
        "what brings you",
        "what problem",
        "what is your",
        "what are your",
        "what brings",
        "can you describe",
        "describe the",
        "any shortness",
        "any chest",
        "any pain",
        "any other",
        "any ",
        "do you have",
        "are you taking",
        "are you currently",
        "have you been",
        "have you not",
        "how long",
        "how often",
        "how are you",
        "where does it",
        "when did it",
        "let me examine",
        "i will",
        "we will",
        "tell me about",
        "how has",
        "please arrange",
        "i would like to",
        "i am going to",
        "we should",
        "let's check",
        "take a deep breath",
        "prescribe",
        "follow up",
        "schedule",
    )
    PATIENT_MARKERS = (
        "i've been",
        "i have been",
        "i'm having",
        "i have a",
        "i had",
        "i feel",
        "it feels",
        "i am taking",
        "i'm taking",
        "i take",
        "i took",
        "my ",
        "it hurts",
        "i don't",
        "i do not",
        "no known",
        "it started",
        "they started",
        "i slept",
        "i woke up",
        "i am allergic",
        "since last",
        "yesterday",
        "last night",
        "headache",
        "chest discomfort",
        "stomach",
        "i couldn't",
        "i can't",
        "makes me feel",
        "it comes and goes",
    )
    NURSE_MARKERS = (
        "his temperature",
        "her temperature",
        "observations",
        "the dressing",
        "wound dressing",
        "he slept",
        "she slept",
        "handover",
        "i administered",
        "vitals",
    )

    def score_utterance(self, text: str) -> tuple[SpeakerRole, float]:
        clean = text.lower().strip()
        if not clean:
            return SpeakerRole.UNKNOWN, 0.0
        doc_count = self._count(clean, self.DOCTOR_MARKERS) + clean.count("?") * 1.2
        pat_count = self._count(clean, self.PATIENT_MARKERS)
        nurse_count = self._count(clean, self.NURSE_MARKERS) * 1.4
        scores = {
            SpeakerRole.DOCTOR: doc_count,
            SpeakerRole.PATIENT: pat_count,
            SpeakerRole.NURSE: nurse_count,
        }
        best_role = max(scores, key=lambda role: scores[role])
        best_score = scores[best_role]
        if best_score <= 0:
            return SpeakerRole.UNKNOWN, 0.0
        total = sum(scores.values()) or 1.0
        confidence = round(min(0.55 + 0.45 * (best_score / total), 0.98), 4)
        return best_role, confidence

    def score(self, utterances: list[str]) -> tuple[SpeakerRole, float]:
        text = " ".join(utterances).lower()
        if not text.strip():
            return SpeakerRole.UNKNOWN, 0.0

        scores = {
            SpeakerRole.DOCTOR: self._count(text, self.DOCTOR_MARKERS) + text.count("?") * 1.0,
            SpeakerRole.PATIENT: self._count(text, self.PATIENT_MARKERS),
            SpeakerRole.NURSE: self._count(text, self.NURSE_MARKERS) * 1.4,
        }
        best_role = max(scores, key=lambda role: scores[role])
        best_score = scores[best_role]
        if best_score <= 0:
            return SpeakerRole.UNKNOWN, 0.0
        total = sum(scores.values()) or 1.0
        confidence = round(min(0.5 + 0.5 * (best_score / total), 0.97), 4)
        return best_role, confidence

    @staticmethod
    def _count(text: str, markers: tuple[str, ...]) -> float:
        return float(sum(text.count(marker) for marker in markers))
