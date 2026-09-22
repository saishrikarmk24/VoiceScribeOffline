"""Lenient JSON extraction for LLM replies (fences, preamble, truncated objects)."""

from __future__ import annotations

import json
from typing import Any


def extract_json_object(text: str) -> Any:
    cleaned = _strip_fences(text)
    decoder = json.JSONDecoder()
    candidates: list[dict[str, Any]] = []
    for index, char in enumerate(cleaned):
        if char != "{":
            continue
        try:
            obj, _end = decoder.raw_decode(cleaned[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            candidates.append(obj)
    for obj in reversed(candidates):
        if "entities" in obj or "note" in obj:
            return obj
    for obj in reversed(candidates):
        if "chief_complaint" in obj:
            return obj
    if candidates:
        return candidates[-1]
    repaired = _close_truncated_json(cleaned)
    if repaired:
        try:
            parsed = json.loads(repaired)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    raise ValueError("malformed JSON")


def _strip_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```", 2)[1]
        if cleaned.lstrip().lower().startswith("json"):
            cleaned = cleaned.lstrip()[4:]
    return cleaned.strip()


def _close_truncated_json(fragment: str) -> str | None:
    start = fragment.find("{")
    if start < 0:
        return None
    text = fragment[start:].rstrip()
    in_string = False
    escape = False
    stack: list[str] = []
    for char in text:
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            stack.append("}")
        elif char == "[":
            stack.append("]")
        elif char in "}]" and stack and stack[-1] == char:
            stack.pop()
    if in_string:
        text += '"'
    text = text.rstrip().rstrip(",")
    text += "".join(reversed(stack))
    return text
