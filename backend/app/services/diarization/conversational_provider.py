"""Conversational diarization provider using Gemini to split text."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.services.diarization.base import DiarizationService
from app.services.types import AudioFrame, DiarizationTurn

logger = get_logger(__name__)

_PROMPT = """You are a medical conversation analyst. Given numbered transcript segments from a clinical encounter, determine which are spoken by the DOCTOR (speaker_0) and which by the PATIENT (speaker_1).

Rules:
- Doctors: ask questions, examine, diagnose, prescribe, plan treatment, use clinical language
- Patients: describe symptoms, report history, answer questions, express concerns
- Use conversational flow: typically the doctor asks and the patient responds
- Questions (ending in ?) are more likely from the doctor
- First-person symptom reports ("I feel", "I have", "it hurts") are from the patient
- If uncertain, use the conversational context (alternating turns)

Return JSON only: {"labels": [{"index": 0, "speaker": "speaker_0"}, {"index": 1, "speaker": "speaker_1"}]}
"""


class ConversationalDiarizationProvider(DiarizationService):
    name = "conversational"
    is_mock = False

    def __init__(self) -> None:
        self._client: Any | None = None

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google import genai
            from google.genai import types
        except ImportError:
            raise RuntimeError("google-genai is not installed.")

        http_options = None
        client_args: dict[str, Any] = {}
        async_client_args: dict[str, Any] = {}
        if not settings.gemini_verify_ssl:
            client_args["verify"] = False
            async_client_args["verify"] = False
        proxy = settings.gemini_http_proxy or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
        if proxy:
            client_args["proxy"] = proxy
            async_client_args["proxy"] = proxy
        if client_args or async_client_args:
            http_options = types.HttpOptions(
                client_args=client_args or None,
                async_client_args=async_client_args or None,
            )

        self._client = genai.Client(api_key=settings.gemini_api_key, http_options=http_options)
        return self._client

    async def diarize(self, audio: AudioFrame) -> list[DiarizationTurn]:
        segments = audio.hints.get("asr_segments")
        if not segments:
            return []

        numbered_lines = []
        for i, seg in enumerate(segments):
            start = f"{seg['start_time']:05.2f}"
            end = f"{seg['end_time']:05.2f}"
            numbered_lines.append(f"{i}. [{start}-{end}] \"{seg['text']}\"")
        transcript_text = "\n".join(numbered_lines)

        try:
            client = self._ensure_client()
            from google.genai import types

            response = await asyncio.to_thread(
                client.models.generate_content,
                model=settings.gemini_model,
                contents=[
                    types.Part.from_text(text=_PROMPT),
                    types.Part.from_text(text=transcript_text),
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.0,
                ),
            )
            text = (response.text or "").strip()
            if text.startswith("```"):
                text = text.strip("`")
                if text.lower().startswith("json"):
                    text = text[4:]
                text = text.strip()
            
            data = json.loads(text)
            labels = data.get("labels", [])
            
            turns: list[DiarizationTurn] = []
            for label in labels:
                idx = label.get("index")
                speaker = label.get("speaker")
                if idx is not None and 0 <= idx < len(segments):
                    seg = segments[idx]
                    turns.append(
                        DiarizationTurn(
                            speaker_id=speaker,
                            start_time=seg["start_time"],
                            end_time=seg["end_time"],
                            confidence=seg.get("confidence", 0.9),
                        )
                    )
            return turns
        except Exception as exc:
            logger.warning(
                "conversational_diarization_failed",
                extra={"error": str(exc)}
            )
            return []
