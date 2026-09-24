"""Medical Terminology & Phonetic Normalizer for Indian Clinical Dialogues.

Corrects common acoustic and phonetic transcription errors produced by Whisper models
when transcribing Indian English, Hinglish, Tanglish, and regional medical encounters.
"""

from __future__ import annotations

import re
from typing import Sequence

# Regex replacement rules: (pattern, replacement)
# Carefully bounded with \b to avoid replacing substrings inside longer words
_PHONETIC_RULES: list[tuple[re.Pattern[str], str]] = [
    # --- Common Indian Pharmaceutical Brands ---
    (re.compile(r"\b(?:tell\s*my|tel\s*my|tell\s*me|tel\s*me)\s*(\d+)\b", re.IGNORECASE), r"Telma \1"),
    (re.compile(r"\b(?:tell\s*ma|tel\s*ma)\b", re.IGNORECASE), "Telma"),
    (re.compile(r"\b(?:pan\s*[- ]?d|penn\s*[- ]?d|pen\s*[- ]?d)\b", re.IGNORECASE), "Pan-D"),
    (re.compile(r"\b(?:panto\s*sid|pantocid)\b", re.IGNORECASE), "Pantocid"),
    (re.compile(r"\b(?:pantodac|panto\s*dac)\b", re.IGNORECASE), "Pantodac"),
    (re.compile(r"\b(?:dolo\s*[- ]?650|dollo\s*[- ]?650|dolo\s*six\s*fifty)\b", re.IGNORECASE), "Dolo 650"),
    (re.compile(r"\b(?:dolo)\b", re.IGNORECASE), "Dolo"),
    (re.compile(r"\b(?:cross\s*in|crossin)\b", re.IGNORECASE), "Crocin"),
    (re.compile(r"\b(?:glyco\s*met|glycomet)\b", re.IGNORECASE), "Glycomet"),
    (re.compile(r"\b(?:met\s*formin|metformin)\b", re.IGNORECASE), "Metformin"),
    (re.compile(r"\b(?:am\s*long|amlong)\b", re.IGNORECASE), "Amlong"),
    (re.compile(r"\b(?:ogmentin|aug\s*mentin|augmentin)\b", re.IGNORECASE), "Augmentin"),
    (re.compile(r"\b(?:azithro|azithral|azithromycin)\b", re.IGNORECASE), "Azithral"),
    (re.compile(r"\b(?:call\s*pol|calpol)\b", re.IGNORECASE), "Calpol"),
    (re.compile(r"\b(?:combi\s*flam|combiflam)\b", re.IGNORECASE), "Combiflam"),
    (re.compile(r"\b(?:sef\s*tum|ceftum)\b", re.IGNORECASE), "Ceftum"),
    (re.compile(r"\b(?:claw\s*vam|clavam)\b", re.IGNORECASE), "Clavam"),
    (re.compile(r"\b(?:eco\s*sprin|eco\s*spring|ecosprin)\b", re.IGNORECASE), "Ecosprin"),
    (re.compile(r"\b(?:a\s*torva|atorva|atorvastatin)\b", re.IGNORECASE), "Atorva"),
    (re.compile(r"\b(?:ro\s*suvas|rosuvas|rosuvastatin)\b", re.IGNORECASE), "Rosuvas"),
    (re.compile(r"\b(?:montek\s*[- ]?lc|montair\s*[- ]?lc)\b", re.IGNORECASE), "Montair-LC"),
    (re.compile(r"\b(?:vomi\s*kind|vomikind)\b", re.IGNORECASE), "Vomikind"),
    (re.compile(r"\b(?:on\s*dem|ondem)\b", re.IGNORECASE), "Ondem"),
    (re.compile(r"\b(?:a\s*legra|allegra)\b", re.IGNORECASE), "Allegra"),
    (re.compile(r"\b(?:meftal\s*[- ]?spas)\b", re.IGNORECASE), "Meftal-Spas"),
    (re.compile(r"\b(?:zifi|zi\s*fi)\b", re.IGNORECASE), "Zifi"),
    (re.compile(r"\b(?:supradyn|supra\s*dyn)\b", re.IGNORECASE), "Supradyn"),
    (re.compile(r"\b(?:shelcal|shel\s*cal)\b", re.IGNORECASE), "Shelcal"),
    (re.compile(r"\b(?:becosules|beco\s*sules)\b", re.IGNORECASE), "Becosules"),

    # --- Dosages & Frequencies ---
    (re.compile(r"\b(\d+)\s*(?:mili\s*gram|milli\s*gram|mili\s*grams|milli\s*grams)\b", re.IGNORECASE), r"\1 mg"),
    (re.compile(r"\b(?:once\s*a\s*day|once\s*daily|one\s*time\s*daily)\b", re.IGNORECASE), "OD (once daily)"),
    (re.compile(r"\b(?:twice\s*a\s*day|twice\s*daily|two\s*times\s*a\s*day)\b", re.IGNORECASE), "BD (twice daily)"),
    (re.compile(r"\b(?:thrice\s*a\s*day|thrice\s*daily|three\s*times\s*a\s*day)\b", re.IGNORECASE), "TDS (thrice daily)"),
    (re.compile(r"\b(?:when\s*needed|as\s*needed|if\s*pain|jarurat\s*padne\s*par)\b", re.IGNORECASE), "SOS (as needed)"),

    # --- Clinical Abbreviations & Vitals ---
    (re.compile(r"\b(?:blood\s*pressure|b\s*\.?\s*p\.?)\b", re.IGNORECASE), "BP"),
    (re.compile(r"\b(?:sugar\s*level|sugar\s*test|blood\s*sugar)\b", re.IGNORECASE), "blood sugar"),
    (re.compile(r"\b(?:sp\s*o2|spo2|oxygen\s*saturation)\b", re.IGNORECASE), "SpO2"),
    (re.compile(r"\b(?:ecg|e\s*\.?\s*c\s*\.?\s*g\.?)\b", re.IGNORECASE), "ECG"),
    (re.compile(r"\b(?:x\s*ray|x-ray)\b", re.IGNORECASE), "X-Ray"),
]


def normalize_medical_transcript(text: str) -> str:
    """Normalize common acoustic and phonetic transcription errors in medical text."""
    if not text:
        return text

    normalized = text
    for pattern, replacement in _PHONETIC_RULES:
        normalized = pattern.sub(replacement, normalized)

    return normalized.strip()


def normalize_segments(segments: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    """Normalize a list of transcript segment dicts in-place or as copies."""
    results: list[dict[str, object]] = []
    for s in segments:
        copy_s = dict(s)
        raw_text = str(copy_s.get("text", ""))
        copy_s["text"] = normalize_medical_transcript(raw_text)
        results.append(copy_s)
    return results
