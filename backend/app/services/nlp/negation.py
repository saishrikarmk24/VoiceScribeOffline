"""Negation and uncertainty detection (NegEx-style, scoped by trigger windows).

Negation is mandatory in clinical documentation: "denies fever" must never be
recorded as fever. This module also detects hedging ("possible", "not sure") and
historical framing ("a few years ago"), because an uncertain finding must not be
promoted to a confirmed one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.models.enums import EntityStatus

PRE_NEGATION_TRIGGERS = (
    "no",
    "not",
    "never",
    "denies",
    "denied",
    "deny",
    "without",
    "absent",
    "negative for",
    "no evidence of",
    "no complaints of",
    "no known",
    "free of",
    "rules out",
    "ruled out",
    "doesn't have",
    "does not have",
    "don't have",
    "do not have",
    "didn't have",
    "did not have",
    "hasn't had",
    "has not had",
    "haven't had",
    "have not had",
    "no longer",
)

POST_NEGATION_TRIGGERS = ("is absent", "was absent", "not present", "ruled out", "declined")

PSEUDO_NEGATION = (
    "no change",
    "no increase",
    "no further",
    "not only",
    "no doubt",
    "not necessarily",
)

UNCERTAINTY_TRIGGERS = (
    "possible",
    "possibly",
    "probable",
    "probably",
    "may have",
    "might have",
    "might be",
    "could be",
    "suspect",
    "suspected",
    "suspicion of",
    "cannot exclude",
    "can't exclude",
    "not sure",
    "unsure",
    "unclear",
    "questionable",
    "perhaps",
    "maybe",
    "i think",
    "seems",
    "appears to",
    "rule out",
)

HISTORICAL_TRIGGERS = (
    "history of",
    "past medical history",
    "previously",
    "in the past",
    "years ago",
    "year ago",
    "months ago",
    "as a child",
    "childhood",
    "used to",
    "formerly",
)

TERMINATION_TRIGGERS = (
    "but",
    "however",
    "although",
    "though",
    "except",
    "aside from",
    "apart from",
    "still",
    "yet",
    "otherwise",
)

_WORD_RE = re.compile(r"[a-z0-9']+")


@dataclass(slots=True)
class NegationResult:
    status: EntityStatus
    trigger: str | None = None
    rationale: str | None = None


class NegationDetector:
    def __init__(self, scope_words: int = 6) -> None:
        self.scope_words = scope_words

    def detect(self, sentence: str, target: str) -> NegationResult:
        text = sentence.lower()
        target_lower = target.lower()

        position = text.find(target_lower)
        if position < 0:
            # The entity value may be a normalisation of the surface form.
            head = _WORD_RE.findall(target_lower)
            position = text.find(head[0]) if head else -1
        if position < 0:
            position = 0

        left = text[:position]
        right = text[position + len(target_lower) :]

        for pseudo in PSEUDO_NEGATION:
            if pseudo in left[-40:]:
                left = left.replace(pseudo, " ")

        left_window = self._window(left, from_end=True)
        right_window = self._window(right, from_end=False)

        trigger = self._match(left_window, PRE_NEGATION_TRIGGERS) or self._match(
            right_window, POST_NEGATION_TRIGGERS
        )
        if trigger:
            return NegationResult(EntityStatus.NEGATED, trigger, f"negation trigger '{trigger}' in scope")

        hedge = self._match(left_window, UNCERTAINTY_TRIGGERS) or self._match(right_window, UNCERTAINTY_TRIGGERS)
        if hedge:
            return NegationResult(EntityStatus.UNCERTAIN, hedge, f"uncertainty trigger '{hedge}' in scope")

        historical = self._match(left_window, HISTORICAL_TRIGGERS) or self._match(
            right_window, HISTORICAL_TRIGGERS
        )
        if historical:
            return NegationResult(EntityStatus.HISTORICAL, historical, f"historical trigger '{historical}' in scope")

        return NegationResult(EntityStatus.PRESENT, None, "no negation or hedging found in scope")

    def _window(self, fragment: str, *, from_end: bool) -> str:
        """Clip the scope at the nearest termination term or clause boundary."""
        for terminator in TERMINATION_TRIGGERS:
            pattern = rf"\b{re.escape(terminator)}\b"
            matches = list(re.finditer(pattern, fragment))
            if not matches:
                continue
            if from_end:
                fragment = fragment[matches[-1].end() :]
            else:
                fragment = fragment[: matches[0].start()]
        words = _WORD_RE.findall(fragment)
        selected = words[-self.scope_words :] if from_end else words[: self.scope_words]
        return " " + " ".join(selected) + " "

    @staticmethod
    def _match(window: str, triggers: tuple[str, ...]) -> str | None:
        best: str | None = None
        for trigger in triggers:
            if re.search(rf"(?<![a-z]){re.escape(trigger)}(?![a-z])", window):
                if best is None or len(trigger) > len(best):
                    best = trigger
        return best
