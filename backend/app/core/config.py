"""Central configuration for MedScribe Live.

Every tunable value lives here so that business logic never hard-codes a model
name, provider or connection string.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent


class AIMode(str, Enum):
    GEMINI = "gemini"
    LOCAL = "local"
    OLLAMA = "ollama"
    MOCK = "mock"


class ASRProviderName(str, Enum):
    GEMINI = "gemini"
    FASTER_WHISPER = "faster_whisper"
    INDIC_WHISPER = "indic_whisper"
    INDIC_CONFORMER = "indic_conformer"
    MOCK = "mock"


class DiarizationProviderName(str, Enum):
    GEMINI = "gemini"
    LOCAL = "local"
    PYANNOTE = "pyannote"
    CONVERSATIONAL = "conversational"
    MOCK = "mock"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- application -------------------------------------------------------
    app_name: str = "VoiceScribe AI"
    app_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"
    api_prefix: str = "/api"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173"

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.7-flash"
    ai_mode: AIMode = AIMode.LOCAL
    gemini_verify_ssl: bool = True
    gemini_http_proxy: str | None = None
    gemini_update_interval_seconds: float = 10.0
    gemini_min_segments_per_update: int = 3
    gemini_timeout_seconds: float = 45.0
    gemini_max_retries: int = 3
    gemini_temperature: float = 0.1

    # --- Local / Offline LLM (Ollama / llama.cpp) --------------------------
    # RTX 4050 (6 GB): Qwen 2.5 7B Q4 ~4.7 GB on GPU. Keep Whisper on CPU.
    local_llm_base_url: str = "http://localhost:11434/v1"
    local_llm_model: str = "qwen2.5:7b"
    local_llm_timeout_seconds: float = 180.0
    local_llm_max_retries: int = 2
    local_llm_temperature: float = 0.0
    local_llm_num_ctx: int = 8192
    local_llm_max_tokens: int = 2048

    # --- database ----------------------------------------------------------
    database_url: str = "postgresql+asyncpg://medscribe:medscribe@localhost:5432/medscribe"
    allow_sqlite_fallback: bool = True
    sqlite_fallback_url: str = "sqlite+aiosqlite:///./medscribe_dev.db"
    db_echo: bool = False
    auto_create_schema: bool = True

    # --- demo mode ---------------------------------------------------------
    enable_demo_mode: bool = True
    demo_segment_interval_seconds: float = 2.5

    # --- pipeline providers ------------------------------------------------
    # RTX 4050 (6 GB): Whisper on CPU so Qwen 7B can use the GPU.
    asr_provider: ASRProviderName = ASRProviderName.FASTER_WHISPER
    diarization_provider: DiarizationProviderName = DiarizationProviderName.LOCAL
    faster_whisper_model: str = "large-v3-turbo"
    asr_device: str = "auto"
    asr_compute_type: str = "auto"
    indic_whisper_model: str = "ai4bharat/whisper-medium-hi_alldata_multigpu"
    indic_whisper_use_transformers: bool = False
    indic_conformer_model: str = "ai4bharat/indicconformer_stt_multi_hybrid_rnnt_600m"
    indic_asr_language: str = "auto"
    # Never list drug names here — Whisper copies initial_prompt into the transcript.
    indic_asr_prompt_biasing: str = ""
    pyannote_model: str = "pyannote/speaker-diarization-3.1"
    huggingface_token: str | None = None

    # Gemini audio transcription. The ASR model is configurable separately from
    # the structuring model because transcription is the more latency-sensitive
    # call and may warrant a cheaper/faster model.
    gemini_asr_model: str | None = None
    gemini_asr_timeout_seconds: float = 180.0
    gemini_asr_max_retries: int = 2
    asr_max_audio_bytes: int = 48 * 1024 * 1024

    # --- audio -------------------------------------------------------------
    audio_sample_rate: int = 16000
    audio_channels: int = 1
    audio_storage_dir: str = "./storage/audio"

    # --- security ----------------------------------------------------------
    dev_auth_enabled: bool = True
    dev_user_email: str = "dev.clinician@medscribe.local"
    dev_user_role: str = "DOCTOR"
    secret_key: str = "change-me-in-production"
    data_retention_days: int = 30

    # --- monitoring --------------------------------------------------------
    enable_metrics: bool = True

    @field_validator("ai_mode", mode="before")
    @classmethod
    def _retired_groq_mode(cls, value: object) -> object:
        if isinstance(value, str) and value.strip().lower() == "groq":
            return AIMode.GEMINI.value
        return value

    @field_validator("gemini_api_key", "huggingface_token", mode="before")
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def effective_gemini_asr_model(self) -> str:
        return self.gemini_asr_model or self.gemini_model

    @property
    def effective_ai_mode(self) -> AIMode:
        if self.ai_mode is AIMode.MOCK:
            return AIMode.MOCK
        if self.ai_mode in (AIMode.LOCAL, AIMode.OLLAMA):
            return self.ai_mode
        if self.gemini_configured:
            return AIMode.GEMINI
        return AIMode.LOCAL

    @property
    def audio_storage_path(self) -> Path:
        path = Path(self.audio_storage_dir)
        if not path.is_absolute():
            path = BACKEND_ROOT / path
        return path

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def pipeline_summary(self) -> dict[str, str]:
        """Single source of truth for the offline stack shown in Settings."""
        asr = self.asr_provider.value
        asr_model = (
            self.faster_whisper_model
            if asr in ("faster_whisper", "indic_whisper")
            else self.indic_whisper_model
        )
        return {
            "target_gpu": "NVIDIA RTX 4050 laptop (6 GB VRAM)",
            "audio": "Browser 16 kHz mono WAV → local preprocess (VAD)",
            "asr": f"{asr} / {asr_model} ({self.asr_compute_type} on {self.asr_device})",
            "diarization": self.diarization_provider.value,
            "llm": f"{self.effective_ai_mode.value} / {self.local_llm_model if self.effective_ai_mode.value in ('local', 'ollama') else self.gemini_model}",
            "grounding": "Entities and plan/assessment must match the transcript or they are dropped",
            "vram_budget": "Qwen 2.5 7B Q4 ~4.7 GB on GPU; Faster-Whisper turbo int8 on CPU",
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
