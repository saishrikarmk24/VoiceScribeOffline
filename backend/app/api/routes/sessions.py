"""Session lifecycle endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentPrincipal, DbSession, SessionDep
from app.core.config import settings
from app.core.logging import get_logger, metrics
from app.models import (
    AudioSource,
    ClinicalEntity,
    ClinicalNote,
    NoteStatus,
    Session as SessionModel,
    SessionMode,
    SessionStatus,
    TranscriptSegment,
)
from app.schemas.common import Acknowledgement, Page
from app.schemas.session import DashboardStats, SessionCreate, SessionOut, SessionSummary
from app.services import repository as repo
from app.services.demo.conversations import list_scripts
from app.services.pipeline import pipeline

logger = get_logger(__name__)
router = APIRouter(prefix="/sessions", tags=["sessions"])

_DEFAULT_AUDIO_SOURCE = {
    SessionMode.DEMO: AudioSource.SIMULATION,
    SessionMode.MICROPHONE: AudioSource.MICROPHONE,
    SessionMode.UPLOAD: AudioSource.UPLOAD,
}


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(payload: SessionCreate, db: DbSession, principal: CurrentPrincipal) -> SessionOut:
    if payload.mode is SessionMode.DEMO and not settings.enable_demo_mode:
        raise HTTPException(status_code=400, detail="Demo mode is disabled (ENABLE_DEMO_MODE=false).")

    user = await repo.get_or_create_user(db, principal.email, role=principal.role.value)
    session = SessionModel(
        reference=await repo.next_session_reference(db),
        name=payload.name.strip(),
        patient_id=payload.patient_id.strip(),
        patient_name=payload.patient_name.strip() if payload.patient_name else None,
        scenario=payload.scenario,
        simulation_type=payload.simulation_type,
        doctor_id=user.id,
        doctor_name=payload.doctor_name or principal.display_name,
        faculty_name=payload.faculty_name,
        status=SessionStatus.CREATED,
        mode=payload.mode,
        audio_source=payload.audio_source or _DEFAULT_AUDIO_SOURCE[payload.mode],
        ai_mode=settings.effective_ai_mode.value,
        model_name=settings.gemini_model if settings.gemini_configured else "medscribe-rules-v1",
    )
    db.add(session)
    await db.flush()
    await repo.get_or_create_note(db, session)
    await repo.record_audit(
        db,
        action="SESSION_CREATED",
        resource_type="session",
        resource_id=str(session.id),
        session_id=session.id,
        actor_email=principal.email,
        actor_role=principal.role.value,
        user_id=user.id,
        detail={"mode": session.mode.value, "reference": session.reference},
    )
    await db.commit()
    metrics.increment("sessions_created_total", mode=session.mode.value)
    logger.info("session_created", extra={"session_id": str(session.id), "reference": session.reference})
    return await repo.serialize_session(db, session)


@router.get("", response_model=Page[SessionSummary])
async def list_sessions(
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    session_status: Annotated[SessionStatus | None, Query(alias="status")] = None,
) -> Page[SessionSummary]:
    sessions, total = await repo.list_sessions(
        db, limit=limit, offset=offset, status=session_status.value if session_status else None
    )
    items = [await repo.serialize_summary(db, session) for session in sessions]
    return Page[SessionSummary](items=items, total=total, limit=limit, offset=offset)


@router.get("/scripts", tags=["demo"])
async def available_scripts() -> dict:
    """Synthetic conversation scripts available for Demo Mode."""
    return {"scripts": list_scripts(), "demo_mode_enabled": settings.enable_demo_mode}


@router.get("/dashboard", response_model=DashboardStats)
async def dashboard(db: DbSession) -> DashboardStats:
    total = int((await db.execute(select(func.count()).select_from(SessionModel))).scalar() or 0)
    active = int(
        (
            await db.execute(
                select(func.count())
                .select_from(SessionModel)
                .where(SessionModel.status.in_([SessionStatus.LIVE, SessionStatus.PAUSED, SessionStatus.PROCESSING]))
            )
        ).scalar()
        or 0
    )
    completed = int(
        (
            await db.execute(
                select(func.count())
                .select_from(SessionModel)
                .where(SessionModel.status.in_([SessionStatus.COMPLETED, SessionStatus.APPROVED]))
            )
        ).scalar()
        or 0
    )
    notes_generated = int(
        (
            await db.execute(select(func.count()).select_from(ClinicalNote).where(ClinicalNote.version > 0))
        ).scalar()
        or 0
    )
    notes_approved = int(
        (
            await db.execute(
                select(func.count())
                .select_from(ClinicalNote)
                .where(ClinicalNote.status.in_([NoteStatus.APPROVED, NoteStatus.EXPORTED]))
            )
        ).scalar()
        or 0
    )
    review_required = int(
        (
            await db.execute(
                select(func.count()).select_from(ClinicalNote).where(ClinicalNote.status == NoteStatus.REVIEW_REQUIRED)
            )
        ).scalar()
        or 0
    )
    total_segments = int((await db.execute(select(func.count()).select_from(TranscriptSegment))).scalar() or 0)
    total_entities = int((await db.execute(select(func.count()).select_from(ClinicalEntity))).scalar() or 0)

    entity_rows = await db.execute(
        select(ClinicalEntity.entity_type, func.count()).group_by(ClinicalEntity.entity_type)
    )
    entity_distribution = [
        {"type": row[0].value if hasattr(row[0], "value") else str(row[0]), "count": int(row[1])}
        for row in entity_rows.all()
    ]

    recent_models, _ = await repo.list_sessions(db, limit=8, offset=0)
    recent = [await repo.serialize_summary(db, session) for session in recent_models]

    today = datetime.now(timezone.utc).date()
    buckets: dict[str, int] = {
        (today - timedelta(days=offset)).isoformat(): 0 for offset in range(6, -1, -1)
    }
    all_sessions, _ = await repo.list_sessions(db, limit=500, offset=0)
    for session in all_sessions:
        key = session.created_at.date().isoformat()
        if key in buckets:
            buckets[key] += 1
    sessions_by_day = [{"date": key, "sessions": value} for key, value in buckets.items()]

    snapshot = metrics.snapshot()["durations"]
    note_latency = next(
        (stats["avg_ms"] for name, stats in snapshot.items() if name.startswith("gemini_request_duration_seconds")),
        0.0,
    )
    nlp_latency = next(
        (stats["avg_ms"] for name, stats in snapshot.items() if name.startswith("clinical_nlp_duration_seconds")),
        0.0,
    )

    return DashboardStats(
        active_sessions=active,
        completed_sessions=completed,
        total_sessions=total,
        notes_generated=notes_generated,
        notes_approved=notes_approved,
        total_segments=total_segments,
        total_entities=total_entities,
        average_note_latency_ms=round(note_latency or nlp_latency, 2),
        average_gemini_latency_ms=round(note_latency, 2),
        review_required_count=review_required,
        recent_sessions=recent,
        sessions_by_day=sessions_by_day,
        entity_distribution=entity_distribution,
    )


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(session: SessionDep, db: DbSession) -> SessionOut:
    return await repo.serialize_session(db, session)


@router.post("/{session_id}/start", response_model=SessionOut)
async def start_session(session: SessionDep, db: DbSession, principal: CurrentPrincipal) -> SessionOut:
    if session.status in (SessionStatus.LIVE, SessionStatus.PROCESSING):
        raise HTTPException(status_code=409, detail=f"Session is already {session.status.value}.")
    if session.status in (SessionStatus.APPROVED, SessionStatus.COMPLETED):
        raise HTTPException(status_code=409, detail="An approved or completed session cannot be restarted.")
    if not principal.can_manage_sessions():
        raise HTTPException(status_code=403, detail="This role cannot start sessions.")

    await repo.record_audit(
        db,
        action="SESSION_STARTED",
        resource_type="session",
        resource_id=str(session.id),
        session_id=session.id,
        actor_email=principal.email,
        actor_role=principal.role.value,
    )
    await pipeline.start(db, session)
    await db.refresh(session)
    return await repo.serialize_session(db, session)


@router.post("/{session_id}/pause", response_model=SessionOut)
async def pause_session(session: SessionDep, db: DbSession, principal: CurrentPrincipal) -> SessionOut:
    if session.status is not SessionStatus.LIVE:
        raise HTTPException(status_code=409, detail="Only a live session can be paused.")
    await pipeline.pause(db, session)
    await repo.record_audit(
        db,
        action="SESSION_PAUSED",
        resource_type="session",
        resource_id=str(session.id),
        session_id=session.id,
        actor_email=principal.email,
        actor_role=principal.role.value,
    )
    await db.commit()
    return await repo.serialize_session(db, session)


@router.post("/{session_id}/resume", response_model=SessionOut)
async def resume_session(session: SessionDep, db: DbSession, principal: CurrentPrincipal) -> SessionOut:
    if session.status is not SessionStatus.PAUSED:
        raise HTTPException(status_code=409, detail="Only a paused session can be resumed.")
    await pipeline.resume(db, session)
    await repo.record_audit(
        db,
        action="SESSION_RESUMED",
        resource_type="session",
        resource_id=str(session.id),
        session_id=session.id,
        actor_email=principal.email,
        actor_role=principal.role.value,
    )
    await db.commit()
    return await repo.serialize_session(db, session)


@router.post("/{session_id}/stop", response_model=SessionOut)
async def stop_session(session: SessionDep, db: DbSession, principal: CurrentPrincipal) -> SessionOut:
    if session.status in (SessionStatus.CREATED,):
        raise HTTPException(status_code=409, detail="Session has not started yet.")
    await repo.record_audit(
        db,
        action="SESSION_STOPPED",
        resource_type="session",
        resource_id=str(session.id),
        session_id=session.id,
        actor_email=principal.email,
        actor_role=principal.role.value,
    )
    await db.commit()
    session_id = str(session.id)
    await pipeline.stop(db, session)
    # The final structuring pass writes through its own sessions, so re-read the
    # row instead of trusting this request's identity map.
    db.expunge(session)
    refreshed = await repo.get_session(db, session_id)
    return await repo.serialize_session(db, refreshed or session)


@router.post("/{session_id}/process", response_model=Acknowledgement)
async def force_ai_update(session: SessionDep, db: DbSession) -> Acknowledgement:
    """Retry / force a clinical structuring pass (used by the Retry AI action)."""
    runtime = await pipeline.ensure_runtime(session)
    runtime.ai_degraded = False
    runtime.last_ai_error = None
    updated = await pipeline.run_ai_update(runtime, force=True)
    return Acknowledgement(
        ok=updated,
        message="Clinical structuring completed." if updated else "Nothing to process yet.",
        detail={"ai": runtime.ai_status},
    )


@router.delete("/{session_id}", response_model=Acknowledgement)
async def delete_session(session: SessionDep, db: DbSession, principal: CurrentPrincipal) -> Acknowledgement:
    if not principal.is_admin and principal.role.value not in ("DOCTOR", "FACULTY"):
        raise HTTPException(status_code=403, detail="This role cannot delete sessions.")
    pipeline.discard(str(session.id))
    await db.delete(session)
    await db.commit()
    return Acknowledgement(ok=True, message=f"Session {session.reference} deleted.")
