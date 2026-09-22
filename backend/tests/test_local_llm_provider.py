"""Unit tests for LocalLLMProvider (offline Ollama / llama.cpp integration)."""

from __future__ import annotations

import json
import pytest
import httpx

from app.core.config import AIMode, settings
from app.services.llm import build_llm_provider
from app.services.llm.base import LLMUnavailable
from app.services.llm.local_provider import LocalLLMProvider


@pytest.mark.asyncio
async def test_build_llm_provider_returns_local(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ai_mode", AIMode.LOCAL)
    provider = build_llm_provider()
    assert isinstance(provider, LocalLLMProvider)
    assert provider.name == "local"
    assert provider.is_mock is False


@pytest.mark.asyncio
async def test_local_llm_extract_entities_success(monkeypatch) -> None:
    provider = LocalLLMProvider(base_url="http://mock-ollama:11434/v1", model="qwen2.5:7b")

    mock_llm_payload = {
        "entities": [
            {
                "entity_type": "SYMPTOM",
                "value": "Persistent cough",
                "status": "PRESENT",
                "confidence": 0.95,
                "source_segment_ids": ["seg_001"],
                "detail": "3 days duration",
            }
        ],
        "unsupported_content": [],
    }

    mock_response = httpx.Response(
        status_code=200,
        json={
            "choices": [{"message": {"content": json.dumps(mock_llm_payload)}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 45},
        },
        request=httpx.Request("POST", "http://mock-ollama:11434/v1/chat/completions"),
    )

    async def mock_post(*args, **kwargs):
        return mock_response

    client = provider._get_client()
    monkeypatch.setattr(client, "post", mock_post)

    response = await provider.extract_entities(
        session_context={"reference": "TEST-01"},
        segments=[{"ref": "seg_001", "role": "PATIENT", "text": "I have had a cough for 3 days."}],
    )

    assert len(response.result.entities) == 1
    assert response.result.entities[0].value == "Persistent cough"
    assert response.result.entities[0].confidence == 0.95
    assert response.stats.model == "qwen2.5:7b"
    assert response.stats.provider == "local"
    await provider.aclose()


@pytest.mark.asyncio
async def test_local_llm_generate_note_success(monkeypatch) -> None:
    provider = LocalLLMProvider(base_url="http://mock-ollama:11434/v1", model="qwen2.5:7b")

    mock_note_payload = {
        "note": {
            "chief_complaint": {"text": "Dry cough", "source_segment_ids": ["seg_001"]},
            "history_of_present_illness": {"text": "Patient has had a dry cough for 3 days.", "source_segment_ids": ["seg_001"]},
            "relevant_medical_history": {"text": "", "source_segment_ids": []},
            "assessment": {"text": "Upper respiratory tract infection", "source_segment_ids": ["seg_002"]},
            "plan": {"text": "Prescribed hydration and rest.", "source_segment_ids": ["seg_002"]},
            "follow_up": {"text": "Review in 1 week if not resolved.", "source_segment_ids": ["seg_002"]},
        },
        "changed_sections": ["chief_complaint", "history_of_present_illness", "assessment", "plan", "follow_up"],
    }

    mock_response = httpx.Response(
        status_code=200,
        json={
            "choices": [{"message": {"content": json.dumps(mock_note_payload)}}],
            "usage": {"prompt_tokens": 250, "completion_tokens": 110},
        },
        request=httpx.Request("POST", "http://mock-ollama:11434/v1/chat/completions"),
    )

    async def mock_post(*args, **kwargs):
        return mock_response

    client = provider._get_client()
    monkeypatch.setattr(client, "post", mock_post)

    response = await provider.generate_note(
        session_context={"reference": "TEST-01"},
        segments=[
            {"ref": "seg_001", "role": "PATIENT", "text": "I have had a dry cough for 3 days."},
            {"ref": "seg_002", "role": "DOCTOR", "text": "It seems like a mild upper respiratory infection. Rest and drink fluids."},
        ],
        entities=[],
    )

    assert response.result.note.chief_complaint.text == "Dry cough"
    assert response.result.note.assessment.text == "Upper respiratory tract infection"
    assert "chief_complaint" in response.result.changed_sections
    await provider.aclose()


@pytest.mark.asyncio
async def test_local_llm_connect_error(monkeypatch) -> None:
    provider = LocalLLMProvider(base_url="http://mock-ollama:11434/v1", max_retries=1)

    async def mock_post(*args, **kwargs):
        raise httpx.ConnectError("Connection refused")

    client = provider._get_client()
    monkeypatch.setattr(client, "post", mock_post)

    with pytest.raises(LLMUnavailable) as exc_info:
        await provider.extract_entities(
            session_context={"reference": "TEST-01"},
            segments=[{"ref": "seg_001", "role": "PATIENT", "text": "I feel dizzy."}],
        )
    assert "Could not connect to local LLM" in str(exc_info.value)
    await provider.aclose()


@pytest.mark.asyncio
async def test_local_llm_check_connection(monkeypatch) -> None:
    provider = LocalLLMProvider(base_url="http://mock-ollama:11434/v1", model="qwen2.5:7b")

    mock_models_response = httpx.Response(
        status_code=200,
        json={"data": [{"id": "qwen2.5:7b"}, {"id": "llama3.1:8b"}]},
        request=httpx.Request("GET", "http://mock-ollama:11434/v1/models"),
    )

    async def mock_get(*args, **kwargs):
        return mock_models_response

    client = provider._get_client()
    monkeypatch.setattr(client, "get", mock_get)

    result = await provider.check_connection()
    assert result["ok"] is True
    assert result["provider"] == "local"
    assert result["model_available"] is True
    await provider.aclose()
