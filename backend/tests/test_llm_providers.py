"""LLM layer: deterministic provider behaviour and Gemini error handling.

The Gemini tests never hit the network; they exercise parsing, schema
validation, error mapping and the retry policy against fakes. Live connectivity
is covered by ``scripts/test_gemini.py``.
"""

from __future__ import annotations

import asyncio

import pytest

from app.models.enums import EntityStatus, EntityType
from app.services.llm import DeterministicLLMProvider
from app.services.llm.base import (
    LLMAuthError,
    LLMInvalidOutput,
    LLMRateLimited,
    LLMSafetyBlocked,
    LLMTimeout,
    LLMUnavailable,
)
from app.services.llm.gemini_provider import GeminiProvider
from app.services.llm.schemas import ExtractionResult, NoteUpdate

SEGMENTS = [
    {
        "ref": "seg_001",
        "speaker_label": "speaker_0",
        "role": "DOCTOR",
        "text": "Good morning. What brings you in today?",
        "start_time": 0.0,
        "end_time": 3.4,
        "confidence": 0.97,
    },
    {
        "ref": "seg_002",
        "speaker_label": "speaker_1",
        "role": "PATIENT",
        "text": "I've been having chest discomfort since yesterday evening.",
        "start_time": 3.4,
        "end_time": 7.6,
        "confidence": 0.94,
    },
    {
        "ref": "seg_003",
        "speaker_label": "speaker_1",
        "role": "PATIENT",
        "text": "No, I don't have any shortness of breath.",
        "start_time": 7.6,
        "end_time": 11.0,
        "confidence": 0.95,
    },
    {
        "ref": "seg_004",
        "speaker_label": "speaker_1",
        "role": "PATIENT",
        "text": "I'm taking metformin.",
        "start_time": 11.0,
        "end_time": 13.2,
        "confidence": 0.92,
    },
]

CONTEXT = {"reference": "SIM-TEST-001", "simulation_type": "OSCE", "patient_id": "SIM-PT-1"}


async def test_deterministic_provider_extracts_with_evidence() -> None:
    provider = DeterministicLLMProvider()
    response = await provider.extract_entities(session_context=CONTEXT, segments=SEGMENTS)
    values = {(entity.entity_type, entity.value.lower()): entity for entity in response.result.entities}

    assert (EntityType.SYMPTOM, "chest discomfort") in values
    assert values[(EntityType.SYMPTOM, "shortness of breath")].status is EntityStatus.NEGATED
    assert (EntityType.MEDICATION, "metformin") in values
    for entity in response.result.entities:
        assert entity.source_segment_ids
    assert response.stats.fallback_used is True


async def test_deterministic_provider_generates_note_without_diagnosing() -> None:
    provider = DeterministicLLMProvider()
    extraction = await provider.extract_entities(session_context=CONTEXT, segments=SEGMENTS)
    entities = [
        {
            "entity_type": entity.entity_type,
            "value": entity.value,
            "status": entity.status,
            "confidence": entity.confidence,
            "source_segment_refs": entity.source_segment_ids,
        }
        for entity in extraction.result.entities
    ]
    response = await provider.generate_note(session_context=CONTEXT, segments=SEGMENTS, entities=entities)
    note = response.result.note

    assert "chest discomfort" in note.chief_complaint.text.lower()
    assert note.chief_complaint.source_segment_ids
    assert "shortness of breath" in note.history_of_present_illness.text.lower()
    assert note.assessment.text == "Not mentioned"  # nothing was diagnosed in the conversation


async def test_deterministic_provider_reports_changed_sections() -> None:
    provider = DeterministicLLMProvider()
    first = await provider.generate_note(session_context=CONTEXT, segments=SEGMENTS, entities=[])
    current = {key: value for key, value in first.result.note.model_dump().items()}
    second = await provider.generate_note(
        session_context=CONTEXT, segments=SEGMENTS, entities=[], current_note=current
    )
    assert second.result.changed_sections == []


async def test_deterministic_provider_connection_check() -> None:
    result = await DeterministicLLMProvider().check_connection()
    assert result["connected"] is True
    assert result["mock"] is True


# ------------------------------------------------------------------ Gemini
class FakeResponse:
    def __init__(self, text: str | None = None, parsed=None, block_reason: str | None = None) -> None:
        self.text = text
        self.parsed = parsed
        self.prompt_feedback = type("Feedback", (), {"block_reason": block_reason})()
        self.candidates = []
        self.usage_metadata = type("Usage", (), {"prompt_token_count": 10, "candidates_token_count": 20})()


def test_gemini_requires_an_api_key() -> None:
    provider = GeminiProvider(api_key=None)
    with pytest.raises(LLMAuthError):
        provider._ensure_client()


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("API key not valid. Please pass a valid API key.", LLMAuthError),
        ("429 RESOURCE_EXHAUSTED: quota exceeded", LLMRateLimited),
        ("503 UNAVAILABLE: service temporarily unavailable", LLMUnavailable),
        ("404 model not found", LLMUnavailable),
        ("connection timed out", LLMTimeout),
    ],
)
def test_gemini_error_mapping(message: str, expected: type[Exception]) -> None:
    mapped = GeminiProvider(api_key="k")._map_exception(RuntimeError(message))
    assert isinstance(mapped, expected)


def test_authentication_failures_are_not_retried() -> None:
    mapped = GeminiProvider(api_key="k")._map_exception(RuntimeError("permission_denied"))
    assert mapped.retryable is False


def test_model_not_found_is_not_retried() -> None:
    mapped = GeminiProvider(api_key="k")._map_exception(RuntimeError("404 model not found"))
    assert mapped.retryable is False


def test_gemini_parses_json_wrapped_in_code_fences() -> None:
    provider = GeminiProvider(api_key="k")
    text = """```json
{"entities": [{"entity_type": "SYMPTOM", "value": "fever", "status": "PRESENT", "confidence": 0.9, "source_segment_ids": ["seg_001"], "detail": null}], "unsupported_content": []}
```"""
    result = provider._parse(FakeResponse(text=text), ExtractionResult)
    assert result.entities[0].value == "fever"


def test_gemini_rejects_empty_output() -> None:
    provider = GeminiProvider(api_key="k")
    with pytest.raises(LLMInvalidOutput):
        provider._parse(FakeResponse(text="   "), ExtractionResult)


def test_gemini_rejects_malformed_json() -> None:
    provider = GeminiProvider(api_key="k")
    with pytest.raises(LLMInvalidOutput):
        provider._parse(FakeResponse(text="entities: not json at all"), ExtractionResult)


def test_gemini_drops_unknown_entity_types() -> None:
    provider = GeminiProvider(api_key="k")
    result = provider._parse(
        FakeResponse(text='{"entities": [{"entity_type": "NOT_A_TYPE", "value": "x"}]}'), ExtractionResult
    )
    assert result.entities == []


def test_gemini_detects_safety_blocks() -> None:
    provider = GeminiProvider(api_key="k")
    with pytest.raises(LLMSafetyBlocked):
        provider._parse(FakeResponse(text="{}", block_reason="SAFETY"), ExtractionResult)


def test_gemini_prefers_the_sdk_parsed_object() -> None:
    provider = GeminiProvider(api_key="k")
    parsed = ExtractionResult(entities=[])
    assert provider._parse(FakeResponse(parsed=parsed), ExtractionResult) is parsed


async def test_gemini_retries_then_raises_after_the_bound() -> None:
    provider = GeminiProvider(api_key="k", max_retries=3, timeout_seconds=1)
    attempts = {"count": 0}

    class FailingClient:
        class aio:  # noqa: N801 - mirrors the SDK surface
            class models:
                @staticmethod
                async def generate_content(**_kwargs):
                    attempts["count"] += 1
                    raise RuntimeError("503 UNAVAILABLE")

    provider._client = FailingClient()
    with pytest.raises(LLMUnavailable):
        await provider._generate("prompt", ExtractionResult, purpose="test")
    assert attempts["count"] == 3


async def test_gemini_does_not_retry_auth_failures() -> None:
    provider = GeminiProvider(api_key="k", max_retries=3, timeout_seconds=1)
    attempts = {"count": 0}

    class AuthFailingClient:
        class aio:  # noqa: N801
            class models:
                @staticmethod
                async def generate_content(**_kwargs):
                    attempts["count"] += 1
                    raise RuntimeError("API key not valid")

    provider._client = AuthFailingClient()
    with pytest.raises(LLMAuthError):
        await provider._generate("prompt", ExtractionResult, purpose="test")
    assert attempts["count"] == 1


async def test_gemini_succeeds_after_a_transient_failure() -> None:
    provider = GeminiProvider(api_key="k", max_retries=3, timeout_seconds=2)
    state = {"calls": 0}
    payload = ExtractionResult(entities=[])

    class FlakyClient:
        class aio:  # noqa: N801
            class models:
                @staticmethod
                async def generate_content(**_kwargs):
                    state["calls"] += 1
                    if state["calls"] == 1:
                        raise RuntimeError("503 UNAVAILABLE")
                    return FakeResponse(parsed=payload)

    provider._client = FlakyClient()
    result, stats = await provider._generate("prompt", ExtractionResult, purpose="test")
    assert result is payload
    assert stats.attempts == 2


async def test_gemini_timeout_is_mapped() -> None:
    provider = GeminiProvider(api_key="k", max_retries=1, timeout_seconds=0.01)

    class HangingClient:
        class aio:  # noqa: N801
            class models:
                @staticmethod
                async def generate_content(**_kwargs):
                    await asyncio.sleep(1.0)

    provider._client = HangingClient()
    with pytest.raises(LLMTimeout):
        await provider._generate("prompt", ExtractionResult, purpose="test")


async def test_gemini_note_call_uses_the_note_schema() -> None:
    provider = GeminiProvider(api_key="k", max_retries=1, timeout_seconds=2)
    captured: dict = {}
    note_payload = NoteUpdate.model_validate(
        {
            "note": {
                key: {"text": "Not mentioned", "confidence": 0.0, "source_segment_ids": []}
                for key in (
                    "chief_complaint",
                    "history_of_present_illness",
                    "relevant_medical_history",
                    "assessment",
                    "plan",
                    "follow_up",
                )
            },
            "changed_sections": [],
            "change_summary": "",
        }
    )

    class CapturingClient:
        class aio:  # noqa: N801
            class models:
                @staticmethod
                async def generate_content(**kwargs):
                    captured.update(kwargs)
                    return FakeResponse(parsed=note_payload)

    provider._client = CapturingClient()
    response = await provider.generate_note(session_context=CONTEXT, segments=SEGMENTS, entities=[])
    assert response.result is note_payload
    assert "SPEAKER-ATTRIBUTED TRANSCRIPT" in captured["contents"]
    assert "seg_002" in captured["contents"]


async def test_connection_check_reports_missing_key() -> None:
    result = await GeminiProvider(api_key=None).check_connection()
    assert result["connected"] is False
    assert "GEMINI_API_KEY" in result["error"]
