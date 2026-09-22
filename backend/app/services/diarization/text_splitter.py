"""Gemini text-based speaker splitting.

Sends assembled transcript text (not audio) to a cheap Gemini model to
determine which segments were spoken by the Doctor and which by the Patient.

At ~200 text tokens per chunk vs ~25,000 audio tokens for Gemini ASR, this is
roughly **100× cheaper** and is used as a fallback when audio-based diarization
detects only a single speaker.
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Cheap, fast model – only doing text classification, not generation.
_DEFAULT_MODEL = "gemini-2.0-flash-lite"


class GeminiTextSplitter:
    """Splits transcript segments into Doctor/Patient turns using Gemini text analysis.

    Much cheaper than audio-based Gemini ASR (~200 text tokens per chunk vs
    ~25,000 audio tokens).  Used as a fallback when audio-based diarization
    detects only one speaker.
    """

    PROMPT = (
        "Given these medical consultation transcript segments, determine which "
        "were spoken by the DOCTOR and which by the PATIENT.\n\n"
        "Rules:\n"
        "- The DOCTOR asks questions, examines, prescribes, uses clinical "
        "language, directs the conversation\n"
        "- The PATIENT reports symptoms, answers questions, describes their "
        "condition, provides history\n"
        "- Return ONLY valid JSON\n\n"
        "Segments:\n{segments}\n\n"
        'Return: {{"splits": {{"seg_001": "doctor", "seg_002": "patient", ...}}}}'
    )

    def __init__(self, *, model: str | None = None) -> None:
        self._model = model or _DEFAULT_MODEL
        self._client: Any | None = None

    # ------------------------------------------------------------------ client

    def _ensure_client(self) -> Any:
        """Lazily initialise the ``google.genai.Client``.

        Mirrors the SSL / proxy setup in
        :pymod:`app.services.llm.gemini_provider`.
        """
        if self._client is not None:
            return self._client

        try:
            from google import genai  # noqa: PLC0415
            from google.genai import types  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover
            logger.error("google-genai not installed – text splitter unavailable")
            raise RuntimeError(
                "google-genai is not installed. Run: pip install -U google-genai"
            ) from exc

        http_options = None
        client_args: dict[str, Any] = {}
        async_client_args: dict[str, Any] = {}
        if not settings.gemini_verify_ssl:
            client_args["verify"] = False
            async_client_args["verify"] = False
        proxy = (
            settings.gemini_http_proxy
            or os.environ.get("HTTPS_PROXY")
            or os.environ.get("HTTP_PROXY")
        )
        if proxy:
            client_args["proxy"] = proxy
            async_client_args["proxy"] = proxy
        if client_args or async_client_args:
            http_options = types.HttpOptions(
                client_args=client_args or None,
                async_client_args=async_client_args or None,
            )

        self._client = genai.Client(
            api_key=settings.gemini_api_key, http_options=http_options
        )
        logger.info(
            "text_splitter_client_initialised",
            extra={"model": self._model, "verify_ssl": settings.gemini_verify_ssl},
        )
        return self._client

    # ------------------------------------------------------------------ public

    async def split(self, segments: list[dict]) -> dict[str, str]:
        """Classify each segment as ``'doctor'`` or ``'patient'``.

        Parameters
        ----------
        segments:
            List of ``{"ref": str, "text": str}`` dicts.

        Returns
        -------
        dict[str, str]
            Mapping of *ref* → ``"doctor"`` | ``"patient"``.
            Returns an **empty dict** on any error so the caller can fall back
            to the default behaviour.
        """
        if not segments:
            return {}
        if not settings.gemini_configured:
            logger.warning("text_splitter_skipped: GEMINI_API_KEY not configured")
            return {}

        numbered = "\n".join(
            f"{seg['ref']}: {seg['text']}" for seg in segments
        )
        prompt = self.PROMPT.format(segments=numbered)

        try:
            client = self._ensure_client()
            response = await client.aio.models.generate_content(
                model=self._model,
                contents=prompt,
            )
            raw = response.text.strip()

            # Strip markdown fences if the model wraps its reply.
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()

            data = json.loads(raw)
            splits: dict[str, str] = data.get("splits", {})

            # Normalise values to lowercase and validate.
            result: dict[str, str] = {}
            for ref, role in splits.items():
                role_lower = str(role).lower()
                if role_lower in ("doctor", "patient"):
                    result[ref] = role_lower

            logger.info(
                "text_splitter_done",
                extra={
                    "total_segments": len(segments),
                    "attributed": len(result),
                },
            )
            return result

        except Exception:
            logger.exception("text_splitter_failed")
            return {}
