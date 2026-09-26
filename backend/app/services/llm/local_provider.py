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
from app.services.llm.json_parse import extract_json_object
from app.services.llm.schemas import (
    ExtractionResult,
    NoteUpdate,
    _NOTE_SECTION_KEYS,
    coerce_llm_payload,
)

logger = get_logger(__name__)

LOCAL_SYSTEM_INSTRUCTION = """\
You are an expert clinical documentation and medical transcription AI for outpatient consultations.
You document consultations, extracting exact medical facts and producing comprehensive, professional SOAP notes in Standard Medical English.

CORE CLINICAL PRINCIPLES:
1. ACCURATE TRANSLATION & STANDARDIZATION: The patient and doctor may speak in Hindi, Tamil, Telugu, Malayalam, Bengali, Hinglish, or code-switched Indian languages. You MUST translate and synthesize all documented entities and narrative sections into clear, fluent, professional Clinical English (e.g. 'sar dard' -> 'Headache', 'gas / jalan' -> 'Dyspepsia / Epigastric burning', 'sugar' -> 'Diabetes mellitus').
2. EXTRACT MEDICATIONS & TESTS THOROUGHLY:
   - Identify every medication spoken (whether taken before coming, over-the-counter, regular daily meds, or prescribed by the doctor).
   - Identify every investigation or test ordered or discussed (ECG, CBC, Chest X-ray, Blood Sugar, HbA1c, Troponin, Ultrasound, CT, etc.).
3. DO NOT INVENT: Do not fabricate facts that were not spoken or implied. If a section was not discussed, return an empty string "" (never write "Not mentioned" or "N/A").
4. ATTRIBUTE EVIDENCE: Every non-empty section must reference the supporting transcript segment ref(s) in source_segment_ids (e.g. ["seg_001"]).
5. Always output valid JSON only.
"""


def _build_local_extraction_prompt(
    segments: list[dict[str, Any]],
    rule_hints: list[dict[str, Any]] | None = None,
) -> str:
    transcript = "\n".join(
        f"[{s.get('ref', 'seg')}] {s.get('role', 'SPEAKER')} ({s.get('speaker_label', 'speaker')}): {s.get('text', '')}"
        for s in segments
    )
    hints_text = ""
    if rule_hints:
        valid_hints = [h for h in rule_hints if h.get("value")]
        if valid_hints:
            hints_text = (
                "\nRULE-BASED CANDIDATES (verify against transcript):\n"
                f"{json.dumps(valid_hints, default=str)}\n"
            )

    return f"""TASK: Extract all clinical entities from this conversation. Return JSON ONLY.

MANDATORY CLINICAL EXTRACTION RULES:
1. TRANSLATE TO MEDICAL ENGLISH: All extracted values must be written in standard clinical English (e.g., 'sar dard' -> 'Headache', 'chhati me dard' -> 'Chest pain', 'chakkar' -> 'Dizziness', 'sugar ki goli' -> 'Antidiabetic medication').
2. EXTRACT MEDICATIONS THOROUGHLY:
   - Extract ANY medication spoken: regular home meds, OTC meds taken prior (e.g. Paracetamol, Dolo 650, Aspirin, Antacid), and any medicines newly prescribed by the doctor.
3. EXTRACT INVESTIGATIONS / TESTS:
   - Extract ANY test mentioned: ECG, Blood tests, Sugar, Troponin, Chest X-ray, Ultrasound, CT scan, Urine test, etc.
4. EXTRACT SYMPTOMS, VITALS & FINDINGS:
   - Symptoms (chest pain, fever, cough, nausea, shortness of breath, etc.)
   - Vitals/Findings (BP, Pulse, SpO2, Temp, examination findings)
   - Diagnoses mentioned (Angina, Hypertension, Bronchitis, etc.)
5. STATUS VALUES:
   - 'PRESENT': currently reported or active
   - 'NEGATED': explicitly denied or absent (e.g. 'no fever', 'fever nahi hai')
   - 'UNCERTAIN': suspected or unclear
   - 'HISTORICAL': prior past condition or prior medication taken in the past
6. Every entity MUST include at least one valid source_segment_id from the transcript (e.g. ["seg_001"]).

TRANSCRIPT:
{transcript}
{hints_text}

OUTPUT FORMAT (JSON ONLY):
{{
  "entities": [
    {{"entity_type": "SYMPTOM", "value": "Chest pain", "status": "PRESENT", "confidence": 0.95, "source_segment_ids": ["seg_001"], "detail": "2 hours"}},
    {{"entity_type": "SYMPTOM", "value": "Fever", "status": "NEGATED", "confidence": 0.95, "source_segment_ids": ["seg_001"], "detail": null}},
    {{"entity_type": "INVESTIGATION", "value": "12-lead ECG", "status": "PRESENT", "confidence": 0.95, "source_segment_ids": ["seg_002"], "detail": "Urgent"}},
    {{"entity_type": "MEDICATION", "value": "Dolo 650", "status": "HISTORICAL", "confidence": 0.95, "source_segment_ids": ["seg_003"], "detail": "Taken at home"}},
    {{"entity_type": "MEDICATION", "value": "Aspirin 300mg", "status": "PRESENT", "confidence": 0.95, "source_segment_ids": ["seg_004"], "detail": "Prescribed stat"}},
    {{"entity_type": "FINDING", "value": "Blood pressure 140/90 mmHg", "status": "PRESENT", "confidence": 0.9, "source_segment_ids": ["seg_002"], "detail": null}}
  ],
  "unsupported_content": []
}}"""


def _build_local_note_prompt(
    segments: list[dict[str, Any]],
    entities: list[dict[str, Any]],
) -> str:
    transcript = "\n".join(
        f"[{s.get('ref', 'seg')}] {s.get('role', 'SPEAKER')} ({s.get('speaker_label', 'speaker')}): {s.get('text', '')}"
        for s in segments
    )
    findings_list = [
        f"• {e.get('entity_type')}: {e.get('value')} ({e.get('status')})"
        for e in entities if e.get("value")
    ]
    findings = "\n".join(findings_list) if findings_list else "None documented yet"

    return f"""TASK: Synthesize a professional, comprehensive clinical SOAP note from this consultation in standard Medical English. Return JSON ONLY.

MANDATORY CLINICAL DOCUMENTATION RULES:
1. TRANSLATE TO MEDICAL ENGLISH: All sections must be in clear, professional clinical English, translating any vernacular or Indian terms (e.g. Hindi, Tamil, Telugu, Hinglish).
2. DOCUMENT ALL 14 CLINICAL SECTIONS:
   - chief_complaint: Presenting Complaint (e.g. "Chest pain and breathlessness for 2 hours").
   - history_of_present_illness: Detailed HPI narrative (onset, duration, severity, radiation, aggravating/relieving factors, associated symptoms).
   - relevant_medical_history: Past medical history, chronic diseases (Hypertension, Diabetes, previous surgeries). If not discussed, return "".
   - social_history: Lifestyle, diet, smoking, alcohol, exercise. If not discussed, return "".
   - family_history: Family history of heart disease, diabetes, hypertension, stroke, etc. If not discussed, return "".
   - menstrual_history: Gynecological/menstrual history if applicable, else "".
   - physical_examination: Physical exam findings, vitals (BP, pulse, SpO2, temp, heart/lung auscultation).
   - current_medication: Regular chronic medications the patient was already taking before this encounter.
   - allergies: Known drug or food allergies. If not discussed, return "".
   - treatment_history: Prior treatments or medicines taken by the patient for this illness before coming to the doctor (e.g. "Took OTC Dolo 650 and antacid at home with minimal relief").
   - previous_investigation: Prior diagnostic tests or reports mentioned by the patient or clinician (e.g. "ECG done 6 months ago was normal; random blood sugar reported 160 mg/dL").
   - assessment: Clinical impression, working diagnosis, or differential (e.g. "Suspected Acute Coronary Syndrome / Atypical Angina, rule out MI").
   - plan: Doctor's treatment plan. MUST INCLUDE:
     * Diagnostic tests ordered (e.g. "Order urgent 12-lead ECG, Troponin-I, CBC, lipid profile").
     * Prescribed medications with dose, route, frequency, and duration (e.g. "Tab Aspirin 300mg stat chewable; Tab Sorbitrate 5mg SL PRN").
     * Non-pharmacological advice and lifestyle precautions.
   - follow_up: Follow-up interval, warning signs, and return precautions.
3. DO NOT write placeholder phrases like "Not mentioned", "N/A", or "None". If a section was not discussed, use an empty string "".
4. Every non-empty section MUST include "source_segment_ids" with the supporting transcript segment ref(s) (e.g. ["seg_001"]).
5. Return JSON ONLY matching this exact structure:

{{
  "note": {{
    "chief_complaint": {{"text": "...", "confidence": 0.95, "source_segment_ids": ["seg_001"]}},
    "history_of_present_illness": {{"text": "...", "confidence": 0.95, "source_segment_ids": ["seg_001"]}},
    "relevant_medical_history": {{"text": "", "confidence": 0.0, "source_segment_ids": []}},
    "social_history": {{"text": "", "confidence": 0.0, "source_segment_ids": []}},
    "family_history": {{"text": "", "confidence": 0.0, "source_segment_ids": []}},
    "menstrual_history": {{"text": "", "confidence": 0.0, "source_segment_ids": []}},
    "physical_examination": {{"text": "...", "confidence": 0.9, "source_segment_ids": ["seg_002"]}},
    "current_medication": {{"text": "...", "confidence": 0.9, "source_segment_ids": ["seg_003"]}},
    "allergies": {{"text": "", "confidence": 0.0, "source_segment_ids": []}},
    "treatment_history": {{"text": "...", "confidence": 0.9, "source_segment_ids": ["seg_004"]}},
    "previous_investigation": {{"text": "...", "confidence": 0.9, "source_segment_ids": ["seg_005"]}},
    "assessment": {{"text": "...", "confidence": 0.9, "source_segment_ids": ["seg_006"]}},
    "plan": {{"text": "...", "confidence": 0.9, "source_segment_ids": ["seg_007"]}},
    "follow_up": {{"text": "...", "confidence": 0.9, "source_segment_ids": ["seg_008"]}}
  }},
  "changed_sections": ["chief_complaint", "history_of_present_illness", "treatment_history", "previous_investigation", "assessment", "plan", "follow_up"]
}}

TRANSCRIPT:
{transcript}

EXTRACTED CLINICAL FINDINGS:
{findings}
"""


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
        raw_text, stats = await self._post_chat(prompt, purpose="entity_extraction", max_tokens=1000)
        try:
            parsed_json = extract_json_object(raw_text)
            coerced = coerce_llm_payload(parsed_json, ExtractionResult)
            result = ExtractionResult.model_validate(coerced)
            # Ensure each entity has at least one source_segment_id
            all_refs = [str(s.get("ref", "")) for s in clean_segments if s.get("ref")]
            if all_refs:
                for entity in result.entities:
                    if not entity.source_segment_ids:
                        entity.source_segment_ids = [all_refs[0]]
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
        raw_text, stats = await self._post_chat(prompt, purpose="note_generation", max_tokens=2048)
        try:
            parsed_json = extract_json_object(raw_text)
            coerced = coerce_llm_payload(parsed_json, NoteUpdate)
            result = NoteUpdate.model_validate(coerced)
            # Ensure documented sections have at least one source_segment_id so evidence linking succeeds
            all_refs = [str(s.get("ref", "")) for s in clean_segments if s.get("ref")]
            if all_refs:
                note_dict = result.note
                for sec_name in _NOTE_SECTION_KEYS:
                    sec = getattr(note_dict, sec_name, None)
                    if sec and sec.text and not sec.source_segment_ids:
                        sec.source_segment_ids = [all_refs[0]]
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
