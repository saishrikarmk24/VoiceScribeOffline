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
You are an expert multilingual clinical documentation AI for Indian healthcare.
Accurately extract clinical entities and generate structured SOAP clinical documentation from doctor-patient conversations.
The dialogue may be spoken in English, Hindi, Tamil, Telugu, Malayalam, Bengali, Marathi, Gujarati, Kannada, or code-switched Hinglish and Tanglish.

CLINICAL TRANSLATION & LEXICON RULES:
1. Translate Indian vernacular terms into standard medical English:
   - Tamil: nenju vali / nenjil baaram -> chest pain / tightness; thalai vali -> headache; moochu vida kashtam -> shortness of breath / dyspnea; kaichal -> fever; irumal -> cough; vayiru vali -> abdominal pain; mayakkam -> dizziness/syncope.
   - Hindi: chhati mein dard / jalan -> chest pain / retrosternal burning; sar dard -> headache; sans lene me takleef -> dyspnea; bukhar -> fever; khansi -> cough; pet dard -> abdominal pain; ulti / jee ghabrana -> vomiting / nausea.
   - Telugu: gunde noppi -> chest pain; tala noppi -> headache; aayasam -> breathlessness / dyspnea; jwaram -> fever; daggu -> cough; kadupu noppi -> abdominal pain.
   - Malayalam: nenju vedana -> chest pain; thala vedana -> headache; shwasam muttal -> dyspnea; pani -> fever; chuma -> cough; vayar vedana -> abdominal pain.
   - Bengali: buke byatha -> chest pain; matha byatha -> headache; shwas kashto -> dyspnea; jor -> fever; kashi -> cough; peter byatha -> abdominal pain.
2. Indian Pharmacopeia & Brand Normalization:
   - Dolo 650, Calpol -> Paracetamol 650mg
   - Pan-D, Pantocid-D -> Pantoprazole + Domperidone
   - Augmentin -> Amoxicillin-Clavulanate
   - Glycomet, Cetapin -> Metformin
   - Telma, Telmikind -> Telmisartan
   - Amlong -> Amlodipine
   - Ecosprin -> Aspirin
   - Montair-LC -> Montelukast + Levocetirizine
3. Negation Preservation:
   - When a patient denies or rules out a symptom (e.g. "no fever", "sugar illa", "chhati me dard nahi", "daggu ledu"), mark status as NEGATED.
   - Never classify negated conditions as present diseases.
4. Output Format:
   - Output strictly valid JSON conforming to the requested schema.
   - For absent sections, output an empty string "". Never write placeholder phrases like "Not mentioned".
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
If a symptom is denied, use status "NEGATED".

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
Translate all vernacular terms into formal medical English.
If a section was NOT discussed, output an empty string "". Never write "Not mentioned".
For physical_examination: If vitals were stated (BP, pulse, temp, sugar, SpO2), format as "Vital signs: BP ...".

TRANSCRIPT:
{transcript}

CLINICAL FINDINGS:
{findings}

Return strictly valid JSON with these 8 sections:
{{
  "chief_complaint": "1 concise line with primary symptom or reason for visit",
  "history_of_present_illness": "Detailed chronological narrative of onset, duration, character, and severity",
  "past_medical_history": "Pre-existing chronic conditions and surgical history (empty if none)",
  "physical_examination": "Vitals and examination findings (empty if none)",
  "current_medication": "Prior active medications taken before this visit (empty if none)",
  "allergies": "Known drug or food allergies (empty if none)",
  "assessment": "Working diagnosis or clinical impression",
  "plan": "Doctor treatment plan, prescribed medications with dosages, and advice",
  "follow_up": "Follow-up interval or return precautions (empty if none)"
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
            return NoteResponse(result=result, stats=stats)
        except Exception as exc:
            logger.warning("local_llm_note_parse_error", extra={"raw": raw_text[:400], "error": str(exc)})
            raise LLMInvalidOutput(f"Local LLM returned malformed clinical note JSON: {exc}") from exc

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
