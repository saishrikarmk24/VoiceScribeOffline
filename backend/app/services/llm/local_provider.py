"""Local LLM provider connecting to Ollama, llama.cpp, or any OpenAI-compatible local server.

Default stack for an RTX 4050 laptop (6 GB): Qwen 2.5 7B via Ollama on GPU,
Faster-Whisper on CPU so the two models do not share VRAM.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.asr.medical_normalizer import normalize_segments
from app.services.llm.base import (
    ExtractionResponse,
    LLMCallStats,
    LLMError,
    LLMInvalidOutput,
    LLMProvider,
    LLMTimeout,
    LLMUnavailable,
    NoteResponse,
)
from app.services.llm.grounding import filter_ungrounded_entities, purge_note_hallucinations
from app.services.llm.json_parse import extract_json_object
from app.services.llm.schemas import ExtractionResult, NoteUpdate, coerce_llm_payload

logger = get_logger(__name__)

LOCAL_SYSTEM_INSTRUCTION = """\
You are an ambient clinical scribe for Indian outpatient care.
You DOCUMENT what was spoken. You are not a doctor.

HARD RULES:
- Extract and write ONLY facts that appear in the transcript.
- NEVER invent medications, doses, tests, diagnoses, or advice.
- If the doctor did not prescribe anything, plan must be "".
- If the patient did not name a current medicine, current_medication must be "".
- If a section was not discussed, return "".
- Translate vernacular (Hindi/Tamil/Telugu/Malayalam/Bengali/Hinglish) into clinical English.
- Denied symptoms (nahi, illa, no fever) have status NEGATED.
- Output valid JSON only.
"""


def _build_local_extraction_prompt(
    segments: list[dict[str, Any]],
    rule_hints: list[dict[str, Any]] | None = None,
) -> str:
    transcript = "\n".join(
        f"[{s.get('ref', 'seg')}] {s.get('speaker_label', 'speaker')}: {s.get('text', '')}"
        for s in segments
    )
    hints_text = ""
    if rule_hints:
        valid_hints = [h for h in rule_hints if h.get("value")]
        if valid_hints:
            hints_text = (
                "HINTS (verify against transcript, discard if not spoken): "
                f"{json.dumps(valid_hints, default=str)}\n"
            )

    return f"""Extract clinical entities spoken in this transcript. JSON only.

Example — transcript:
[seg_1] PATIENT: 2 days se sar dard, bukhar nahi hai.
Correct JSON:
{{"entities":[
  {{"entity_type":"SYMPTOM","value":"headache","status":"PRESENT","confidence":0.9,"source_segment_ids":["seg_1"],"detail":"2 days"}},
  {{"entity_type":"SYMPTOM","value":"fever","status":"NEGATED","confidence":0.9,"source_segment_ids":["seg_1"],"detail":null}}
],"unsupported_content":[]}}

Do NOT add medications unless a named drug was spoken. This example has none — do not copy drugs into the answer.

TRANSCRIPT:
{transcript}
{hints_text}
Return JSON with entities of types SYMPTOM, DIAGNOSIS_MENTIONED, MEDICATION, FINDING, ALLERGY, MEDICAL_HISTORY.
status: PRESENT, NEGATED, UNCERTAIN, HISTORICAL."""


def _build_local_note_prompt(
    segments: list[dict[str, Any]],
    entities: list[dict[str, Any]],
) -> str:
    transcript = "\n".join(
        f"[{s.get('ref', 'seg')}] {s.get('speaker_label', 'speaker')}: {s.get('text', '')}"
        for s in segments
    )
    findings = ", ".join(
        f"{e.get('value')} ({e.get('status')})" for e in entities if e.get("value")
    ) or "None documented"

    return f"""Write a SOAP note from this dialogue. JSON only. Empty string if not discussed.

Example — fever and body pain; doctor says rest and fluids; no named drug:
{{"chief_complaint":"Fever and body pain","history_of_present_illness":"Patient reports fever and body pain.","past_medical_history":"","physical_examination":"","current_medication":"","allergies":"","assessment":"","plan":"Rest and oral fluids as advised.","follow_up":""}}

NEVER invent a tablet, syrup, or diagnosis. If the doctor did not name a drug, plan must not contain one.

TRANSCRIPT:
{transcript}

EXTRACTED FINDINGS (already checked against the transcript):
{findings}

Return JSON with keys: chief_complaint, history_of_present_illness, past_medical_history, physical_examination, current_medication, allergies, assessment, plan, follow_up."""


class LocalLLMProvider(LLMProvider):
    """Local offline LLM provider running via Ollama / llama.cpp / vLLM."""

    name = "local"
    is_mock = False

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        temperature: float | None = None,
    ) -> None:
        self.base_url = (base_url or settings.local_llm_base_url).rstrip("/")
        self.model = model or settings.local_llm_model
        self.timeout_seconds = timeout_seconds or settings.local_llm_timeout_seconds
        self.max_retries = max_retries or settings.local_llm_max_retries
        self.temperature = settings.local_llm_temperature if temperature is None else temperature
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout_seconds, connect=10.0),
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def _post_chat(
        self, prompt: str, *, purpose: str, max_tokens: int | None = None
    ) -> tuple[str, LLMCallStats]:
        client = self._get_client()
        num_ctx = getattr(settings, "local_llm_num_ctx", 2048)
        limit_tokens = max_tokens or getattr(settings, "local_llm_max_tokens", 600)

        is_ollama = "11434" in self.base_url
        if is_ollama:
            ollama_base = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
            url = f"{ollama_base}/api/chat"
            model_l = self.model.lower()
            if "gemma" in model_l:
                chat_messages = [
                    {"role": "user", "content": f"{LOCAL_SYSTEM_INSTRUCTION}\n\n{prompt}"}
                ]
            else:
                chat_messages = [
                    {"role": "system", "content": LOCAL_SYSTEM_INSTRUCTION},
                    {"role": "user", "content": prompt},
                ]
            payload = {
                "model": self.model,
                "messages": chat_messages,
                "stream": False,
                "format": "json",
                "keep_alive": "24h",
                "options": {
                    "num_thread": 8,
                    "num_ctx": num_ctx,
                    "num_predict": limit_tokens,
                    "temperature": self.temperature,
                },
            }
        else:
            url = f"{self.base_url}/chat/completions"
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": LOCAL_SYSTEM_INSTRUCTION},
                    {"role": "user", "content": prompt},
                ],
                "temperature": self.temperature,
                "max_tokens": limit_tokens,
                "response_format": {"type": "json_object"},
                "stream": False,
            }

        attempts = 0
        started = time.perf_counter()
        last_error: LLMError | None = None

        while attempts < max(1, self.max_retries):
            attempts += 1
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
            except httpx.ConnectError as exc:
                last_error = LLMUnavailable(
                    f"Could not connect to local LLM at {self.base_url}. "
                    "Ensure Ollama or local LLM server is running (e.g. 'ollama serve')."
                )
                logger.warning(
                    "local_llm_connect_failed",
                    extra={"purpose": purpose, "attempt": attempts, "error": str(exc)},
                )
            except httpx.TimeoutException as exc:
                last_error = LLMTimeout(f"Local LLM call timed out after {self.timeout_seconds:.0f}s")
                logger.warning("local_llm_timeout", extra={"purpose": purpose, "attempt": attempts})
                _ = exc
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                error_body = exc.response.text[:300]
                if status == 404:
                    last_error = LLMUnavailable(
                        f"Model '{self.model}' not found on local LLM server. "
                        f"Run 'ollama pull {self.model}' to download it."
                    )
                else:
                    last_error = LLMUnavailable(f"Local LLM returned HTTP {status}: {error_body}")
                logger.warning(
                    "local_llm_http_error",
                    extra={"purpose": purpose, "attempt": attempts, "status": status, "body": error_body},
                )
            except Exception as exc:
                last_error = LLMError(f"Unexpected local LLM error: {exc}")
                logger.warning("local_llm_error", extra={"purpose": purpose, "attempt": attempts, "error": str(exc)})
            else:
                if is_ollama and "message" in data:
                    raw_content = data.get("message", {}).get("content", "") or ""
                    duration_ms = (time.perf_counter() - started) * 1000
                    stats = LLMCallStats(
                        provider=self.name,
                        model=self.model,
                        duration_ms=round(duration_ms, 2),
                        attempts=attempts,
                        prompt_tokens=data.get("prompt_eval_count"),
                        output_tokens=data.get("eval_count"),
                    )
                    return raw_content, stats

                choices = data.get("choices") or []
                if not choices:
                    last_error = LLMInvalidOutput("Local LLM returned no choices.")
                else:
                    raw_content = choices[0].get("message", {}).get("content", "") or ""
                    if not raw_content.strip():
                        last_error = LLMInvalidOutput("Local LLM returned empty message content.")
                    else:
                        duration_ms = (time.perf_counter() - started) * 1000
                        usage = data.get("usage") or {}
                        stats = LLMCallStats(
                            provider=self.name,
                            model=self.model,
                            duration_ms=round(duration_ms, 2),
                            attempts=attempts,
                            prompt_tokens=usage.get("prompt_tokens"),
                            output_tokens=usage.get("completion_tokens"),
                        )
                        return raw_content, stats

            if attempts < self.max_retries:
                await asyncio.sleep(min(4.0, 0.5 * (2 ** (attempts - 1))) + random.uniform(0, 0.2))

        raise last_error or LLMUnavailable("Local LLM call failed")

    async def extract_entities(
        self,
        *,
        session_context: dict[str, Any],
        segments: list[dict[str, Any]],
        rule_based_candidates: list[dict[str, Any]] | None = None,
        existing_entities: list[dict[str, Any]] | None = None,
    ) -> ExtractionResponse:
        clean_segments = normalize_segments(segments)
        prompt = _build_local_extraction_prompt(
            segments=clean_segments,
            rule_hints=rule_based_candidates,
        )
        raw_text, stats = await self._post_chat(prompt, purpose="entity_extraction", max_tokens=350)
        try:
            parsed_json = extract_json_object(raw_text)
            coerced = coerce_llm_payload(parsed_json, ExtractionResult)
            result = ExtractionResult.model_validate(coerced)
            segment_texts = {
                str(s.get("ref", "")): str(s.get("text", "")) for s in clean_segments
            }
            kept, dropped = filter_ungrounded_entities(
                result.entities,
                segment_texts=segment_texts,
                full_transcript=" ".join(segment_texts.values()),
            )
            if dropped:
                logger.info("local_llm_dropped_ungrounded_entities", extra={"dropped": dropped})
            result.entities = kept
            return ExtractionResponse(result=result, stats=stats)
        except Exception as exc:
            logger.warning("local_llm_extraction_parse_error", extra={"raw": raw_text[:400], "error": str(exc)})
            raise LLMInvalidOutput(f"Local LLM returned malformed extraction JSON: {exc}") from exc

    async def generate_note(
        self,
        *,
        session_context: dict[str, Any],
        segments: list[dict[str, Any]],
        entities: list[dict[str, Any]],
        current_note: dict[str, Any] | None = None,
    ) -> NoteResponse:
        clean_segments = normalize_segments(segments)
        prompt = _build_local_note_prompt(
            segments=clean_segments,
            entities=entities,
        )
        raw_text, stats = await self._post_chat(prompt, purpose="note_generation", max_tokens=550)
        try:
            parsed_json = extract_json_object(raw_text)
            coerced = coerce_llm_payload(parsed_json, NoteUpdate)
            result = NoteUpdate.model_validate(coerced)
            purge_note_hallucinations(result, clean_segments, entities)
            return NoteResponse(result=result, stats=stats)
        except Exception as exc:
            logger.warning("local_llm_note_parse_error", extra={"raw": raw_text[:400], "error": str(exc)})
            raise LLMInvalidOutput(f"Local LLM returned malformed clinical note JSON: {exc}") from exc

    async def check_connection(self) -> dict[str, Any]:
        """Verify local LLM server accessibility and model readiness."""
        client = self._get_client()
        try:
            resp = await client.get("/models")
            resp.raise_for_status()
            models_data = resp.json()
            available_models = [m.get("id", "") for m in (models_data.get("data") or [])]
            has_target = any(self.model in m for m in available_models)
            return {
                "ok": True,
                "provider": self.name,
                "model": self.model,
                "base_url": self.base_url,
                "model_available": has_target,
                "installed_models": available_models[:10],
            }
        except httpx.ConnectError:
            return {
                "ok": False,
                "provider": self.name,
                "error": f"Connection refused at {self.base_url}. Ensure Ollama or local LLM server is running.",
            }
        except Exception as exc:
            return {
                "ok": False,
                "provider": self.name,
                "error": str(exc),
            }

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
