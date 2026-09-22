"""Negation and uncertainty detection is mandatory - these tests guard it."""

from __future__ import annotations

import pytest

from app.models.enums import EntityStatus
from app.services.nlp.negation import NegationDetector

detector = NegationDetector()


@pytest.mark.parametrize(
    ("sentence", "target", "expected"),
    [
        ("The patient has fever.", "fever", EntityStatus.PRESENT),
        ("Patient denies fever.", "fever", EntityStatus.NEGATED),
        ("No, I don't have any shortness of breath.", "shortness of breath", EntityStatus.NEGATED),
        ("There is no evidence of chest pain.", "chest pain", EntityStatus.NEGATED),
        ("No known drug allergies.", "drug allergies", EntityStatus.NEGATED),
        ("Possible fever.", "fever", EntityStatus.UNCERTAIN),
        ("I possibly had some blurred vision once, but I am not sure.", "blurred vision", EntityStatus.UNCERTAIN),
        ("He might have pneumonia.", "pneumonia", EntityStatus.UNCERTAIN),
        ("History of asthma as a child.", "asthma", EntityStatus.HISTORICAL),
        ("I had appendicitis three years ago.", "appendicitis", EntityStatus.HISTORICAL),
    ],
)
def test_status_detection(sentence: str, target: str, expected: EntityStatus) -> None:
    assert detector.detect(sentence, target).status is expected


def test_termination_term_limits_negation_scope() -> None:
    sentence = "No cough, but he does report chest discomfort."
    assert detector.detect(sentence, "cough").status is EntityStatus.NEGATED
    assert detector.detect(sentence, "chest discomfort").status is EntityStatus.PRESENT


def test_pseudo_negation_is_not_a_negation() -> None:
    sentence = "There is no change in the chest discomfort."
    assert detector.detect(sentence, "chest discomfort").status is not EntityStatus.NEGATED


def test_negation_result_explains_itself() -> None:
    result = detector.detect("Patient denies fever.", "fever")
    assert result.trigger == "denies"
    assert "denies" in (result.rationale or "")
