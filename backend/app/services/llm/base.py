"""LLM provider contract and error taxonomy."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any

from app.services.llm.schemas import ExtractionResult, NoteUpdate


class LLMError(RuntimeError):
    """Base class for AI layer failures."""

    retryable = True
    code = "LLM_ERROR"


class LLMAuthError(LLMError):
    """Invalid or missing credentials - retrying cannot help."""

    retryable = False
    code = "LLM_AUTH"


class LLMNotConfigured(LLMAuthError):
    code = "LLM_NOT_CONFIGURED"


class LLMRateLimited(LLMError):
    code = "LLM_RATE_LIMIT"


class LLMTimeout(LLMError):
    code = "LLM_TIMEOUT"


class LLMUnavailable(LLMError):
    code = "LLM_UNAVAILABLE"


class LLMInvalidOutput(LLMError):
    """Empty, malformed or schema-invalid response."""

    code = "LLM_INVALID_OUTPUT"


class LLMSafetyBlocked(LLMError):
    retryable = False
    code = "LLM_SAFETY_BLOCKED"


@dataclass(slots=True)
class LLMCallStats:
    provider: str
    model: str
    duration_ms: float = 0.0
    attempts: int = 1
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    fallback_used: bool = False
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExtractionResponse:
    result: ExtractionResult
    stats: LLMCallStats


@dataclass(slots=True)
class NoteResponse:
    result: NoteUpdate
    stats: LLMCallStats


class LLMProvider(abc.ABC):
    """Clinical structuring backend."""

    name: str = "base"
    model: str = "unknown"
    is_mock: bool = False

    @abc.abstractmethod
    async def extract_entities(
        self,
        *,
        session_context: dict[str, Any],
        segments: list[dict[str, Any]],
        rule_based_candidates: list[dict[str, Any]] | None = None,
        existing_entities: list[dict[str, Any]] | None = None,
    ) -> ExtractionResponse: ...

    @abc.abstractmethod
    async def generate_note(
        self,
        *,
        session_context: dict[str, Any],
        segments: list[dict[str, Any]],
        entities: list[dict[str, Any]],
        current_note: dict[str, Any] | None = None,
    ) -> NoteResponse: ...

    @abc.abstractmethod
    async def check_connection(self) -> dict[str, Any]: ...

    def describe(self) -> dict[str, Any]:
        return {"provider": self.name, "model": self.model, "mock": self.is_mock}
