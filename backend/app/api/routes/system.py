"""Health, status, configuration and metrics endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.api.deps import DbSession, SessionDep
from app.core import database
from app.core.config import settings
from app.core.logging import metrics
from app.core.security import storage_protection
from app.schemas.session import SystemStatus
from app.services.asr import build_asr_provider
from app.services.diarization import build_diarization_provider
from app.services.llm import get_llm_provider
from app.services.nlp import TerminologyService
from app.services.pipeline import pipeline
from app.websocket.manager import manager

router = APIRouter(tags=["system"])


@router.get("/health")
async def health() -> dict:
    db_health = await database.health()
    provider = get_llm_provider()
    return {
        "status": "ok" if db_health.get("connected") else "degraded",
        "environment": settings.environment,
        "version": settings.app_version,
        "database": db_health,
        "ai": {
            "mode": settings.effective_ai_mode.value,
            "provider": provider.name,
            "model": provider.model,
            "gemini_configured": settings.gemini_configured,
        },
        "websocket": manager.stats(),
        "active_sessions": len(pipeline.active_sessions()),
    }


@router.get("/status", response_model=SystemStatus)
async def system_status() -> SystemStatus:
    provider = get_llm_provider()
    return SystemStatus(
        environment=settings.environment,
        version=settings.app_version,
        database=await database.health(),
        ai={
            "mode": settings.effective_ai_mode.value,
            "configured_mode": settings.ai_mode.value,
            "provider": provider.name,
            "model": provider.model,
            "mock": provider.is_mock,
            "gemini_configured": settings.gemini_configured,
            "update_interval_seconds": settings.gemini_update_interval_seconds,
            "min_segments_per_update": settings.gemini_min_segments_per_update,
            "max_retries": settings.gemini_max_retries,
        },
        providers={
            "asr": build_asr_provider().describe(),
            "diarization": build_diarization_provider().describe(),
            "terminology": TerminologyService().describe(),
            "security": storage_protection.describe(),
        },
        websocket=manager.stats(),
        demo_mode_enabled=settings.enable_demo_mode,
        pipeline=settings.pipeline_summary,
    )


@router.get("/ai/check")
async def check_ai() -> dict:
    """Live connectivity probe for the configured AI provider."""
    provider = get_llm_provider(refresh=True)
    result = await provider.check_connection()
    ok = bool(result.get("connected") or result.get("ok"))
    detail = result.get("error") or result.get("sample") or ("Reachable" if ok else "Unavailable")
    return {"provider": provider.name, "mock": provider.is_mock, "ok": ok, "detail": detail, **result}


@router.get("/metrics", response_model=None)
async def get_metrics(prometheus: bool = False):
    if prometheus:
        return Response(content=metrics.prometheus_text(), media_type="text/plain; version=0.0.4")
    return metrics.snapshot()


@router.get("/sessions/{session_id}/audit")
async def session_audit(session: SessionDep, db: DbSession) -> dict:
    entries = await repo_list_audit(db, session)
    return {"session_id": str(session.id), "entries": entries}


async def repo_list_audit(db, session) -> list[dict]:
    from app.services import repository as repo

    return [
        {
            "id": str(entry.id),
            "action": entry.action,
            "resource_type": entry.resource_type,
            "resource_id": entry.resource_id,
            "actor_email": entry.actor_email,
            "actor_role": entry.actor_role,
            "detail": entry.detail,
            "created_at": entry.created_at.isoformat(),
        }
        for entry in await repo.list_audit(db, session.id)
    ]
