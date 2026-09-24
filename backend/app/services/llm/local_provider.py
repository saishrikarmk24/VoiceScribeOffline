"""Local LLM provider connecting to Ollama, llama.cpp, or any OpenAI-compatible local server.

Operates 100% offline with zero external network connectivity or subscription fees.
Compatible with Qwen 2.5, Llama 3.1, Llama 3.2, Mistral, and MedGemma models.
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger, metrics
from app.services.llm.base import (
    ExtractionResponse,
    LLMCallStats,
    LLMError,
    LLMInvalidOutput,
    LLMNotConfigured,
    LLMProvider,
    LLMTimeout,
    LLMUnavailable,
    NoteResponse,
)
from app.services.llm.json_parse import extract_json_object
from app.services.llm.prompts import CONNECTION_TEST_PROMPT
from app.services.llm.schemas import ExtractionResult, NoteUpdate, coerce_llm_payload

logger = get_logger(__name__)

LOCAL_SYSTEM_INSTRUCTION = """\
You are an ambient clinical scribe AI for Indian healthcare.
Your job is to ACCURATELY DOCUMENT what was spoken in the doctor-patient dialogue.
You are a PASSIVE RECORDER, NOT A TREATING DOCTOR.

CRITICAL SAFETY & ZERO-HALLUCINATION RULES:
1. NEVER invent, recommend, or prescribe any medication, treatment, diagnostic test, or lifestyle advice.
2. In "plan": Record ONLY medications and advice explicitly prescribed by the doctor in the transcript. If the doctor did not prescribe anything or gave no treatment plan, "plan" MUST BE "" (empty string).
3. In "current_medication": Record ONLY medications the patient explicitly reported taking prior to the visit. If none were mentioned, "current_medication" MUST BE "" (empty string).
4. If a section was not discussed (e.g. past history, allergies, physical exam), return "" (empty string). NEVER write placeholder text like "Not mentioned".
5. Translate vernacular terms into medical English accurately:
   - nenju vali / chhati dard / gunde noppi / buke byatha -> chest pain
   - thalai vali / sar dard / tala noppi / matha byatha -> headache
   - kaichal / bukhar / jwaram / pani / jor -> fever
   - irumal / khansi / daggu / chuma / kashi -> cough
   - moochu vida kashtam / sans takleef / aayasam -> dyspnea / shortness of breath
   - ulti -> vomiting; chakkar / mayakkam -> dizziness
6. Preserved Negation: If a symptom is denied (e.g. "no fever", "kaichal illa", "ulti nahi"), mark status as "NEGATED".
7. Every single clinical fact MUST be grounded directly in the transcript. Never extrapolate, guess, or assume.
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
            hints_text = f"CANDIDATES: {json.dumps(valid_hints, default=str)}\n"

    return f"""TASK: Extract clinical entities from the transcript below into valid JSON.
Translate vernacular terms (Hindi, Tamil, Telugu, Malayalam, Bengali, Hinglish, Tanglish) into standard medical English.
If a symptom is denied or ruled out, set status to "NEGATED".
STRICT RULE: Extract ONLY entities that were explicitly spoken in the transcript. Do NOT invent medications.

TRANSCRIPT:
{transcript}
{hints_text}
Output strictly valid JSON:
{{
  "entities": [
    {{
      "entity_type": "SYMPTOM",
      "value": "chest pain",
      "status": "PRESENT",
      "confidence": 0.95,
      "source_segment_ids": ["seg_001"],
      "detail": null
    }}
  ],
  "unsupported_content": []
}}
Allowed entity types: SYMPTOM, DIAGNOSIS, MEDICATION, DOSAGE, EXAMINATION_FINDING, ALLERGY, MEDICAL_HISTORY.
Allowed status values: PRESENT, NEGATED, UNCERTAIN, HISTORICAL."""


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

    return f"""TASK: Synthesize a professional clinical SOAP note from the transcript.
STRICT SCRIBE SAFETY DIRECTIVE:
- DO NOT invent, recommend, or prescribe any medications, tests, or treatments.
- In "plan": Document ONLY what the doctor explicitly prescribed or advised in the dialogue. If the doctor did not give a treatment plan or prescribe medication, leave "plan" as "" (empty string).
- In "current_medication": Document ONLY prior medications the patient reported taking. If none mentioned, leave as "".
- If a section was NOT discussed, leave it as "" (empty string). Never output "Not mentioned".
- For physical_examination: If vitals were stated (BP, pulse, temp, sugar, SpO2), format as "Vital signs: BP ...".

TRANSCRIPT:
{transcript}

CLINICAL FINDINGS FROM TRANSCRIPT:
{findings}

Return strictly valid JSON with these 8 sections:
{{
  "chief_complaint": "primary symptom or reason for visit",
  "history_of_present_illness": "chronological narrative of onset, duration, character, and severity",
  "past_medical_history": "pre-existing chronic conditions mentioned (empty string if none)",
  "physical_examination": "vitals and examination findings mentioned (empty string if none)",
  "current_medication": "prior active medications taken before this visit (empty string if none)",
  "allergies": "known drug or food allergies mentioned (empty string if none)",
  "assessment": "working diagnosis or clinical impression stated by doctor",
  "plan": "doctor's stated plan and prescribed medications (empty string if none prescribed)",
  "follow_up": "follow-up instruction stated by doctor (empty string if none)"
}}"""


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

    async def _post_chat(self, prompt: str, *, purpose: str) -> tuple[str, LLMCallStats]:
        client = self._get_client()
        num_ctx = getattr(settings, "local_llm_num_ctx", 1536)
        max_tokens = getattr(settings, "local_llm_max_tokens", 500)

        is_ollama = "11434" in self.base_url
        if is_ollama:
            ollama_base = self.base_url[:-3] if self.base_url.endswith("/v1") else self.base_url
            url = f"{ollama_base}/api/chat"
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": LOCAL_SYSTEM_INSTRUCTION},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "format": "json",
                "options": {
                    "num_thread": 8,
                    "num_ctx": num_ctx,
                    "num_predict": max_tokens,
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
                "max_tokens": max_tokens,
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
                logger.warning("local_llm_connect_failed", extra={"purpose": purpose, "attempt": attempts, "error": str(exc)})
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
        prompt = _build_local_extraction_prompt(
            segments=segments,
            rule_hints=rule_based_candidates,
        )
        raw_text, stats = await self._post_chat(prompt, purpose="entity_extraction")
        try:
            parsed_json = extract_json_object(raw_text)
            coerced = coerce_llm_payload(parsed_json, ExtractionResult)
            result = ExtractionResult.model_validate(coerced)
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
        prompt = _build_local_note_prompt(
            segments=segments,
            entities=entities,
        )
        raw_text, stats = await self._post_chat(prompt, purpose="note_generation")
        try:
            parsed_json = extract_json_object(raw_text)
            coerced = coerce_llm_payload(parsed_json, NoteUpdate)
            result = NoteUpdate.model_validate(coerced)
            self._purge_hallucinations(result, segments, entities)
            return NoteResponse(result=result, stats=stats)
        except Exception as exc:
            logger.warning("local_llm_note_parse_error", extra={"raw": raw_text[:400], "error": str(exc)})
            raise LLMInvalidOutput(f"Local LLM returned malformed clinical note JSON: {exc}") from exc

    @staticmethod
    def _purge_hallucinations(
        update: NoteUpdate,
        segments: list[dict[str, Any]],
        entities: list[dict[str, Any]],
    ) -> None:
        """Strip medications or instructions in plan and current_medication that have zero transcript support."""
        transcript_text = " ".join(s.get("text", "") for s in segments).lower()

        # 1. Purge current_medication if transcript never mentioned taking prior medications
        curr_med_sec = update.note.current_medication
        if curr_med_sec and curr_med_sec.text:
            med_signals = (
                "tab", "cap", "mg", "syrup", "daily", "dose", "medicine", "medication",
                "taking", "dolo", "metformin", "glycomet", "telma", "pan", "pantocid",
                "aspirin", "insulin", "sugar medicine", "bp medicine"
            )
            has_transcript_meds = any(sig in transcript_text for sig in med_signals)
            if not has_transcript_meds:
                curr_med_sec.text = ""

        # 2. Purge plan if doctor never prescribed or instructed treatments
        plan_sec = update.note.plan
        if plan_sec and plan_sec.text:
            doctor_segments = [
                s.get("text", "").lower()
                for s in segments
                if s.get("speaker_label", "").lower() in ("doctor", "clinician", "physician")
                or s.get("role", "") == "DOCTOR"
            ]
            doc_text = " ".join(doctor_segments) if doctor_segments else transcript_text
            rx_signals = (
                "prescrib", "take", "tab", "cap", "syrup", "daily", "mg", "dose",
                "start", "continue", "advice", "advise", "meal", "food", "drink",
                "test", "scan", "x-ray", "ecg", "blood", "ointment", "drops", "injection"
            )
            has_doctor_plan = any(sig in doc_text for sig in rx_signals)
            if not has_doctor_plan:
                plan_sec.text = ""

    async def check_connection(self) -> dict[str, Any]:
        """Verify local LLM server accessibility and model readiness."""
        client = self._get_client()
        try:
            # Query /models endpoint supported by Ollama, vLLM, and llama.cpp
            resp = await client.get("/models")
            resp.raise_for_status()
            models_data = resp.json()
            available_models = [
                m.get("id", "") for m in (models_data.get("data") or [])
            ]
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
