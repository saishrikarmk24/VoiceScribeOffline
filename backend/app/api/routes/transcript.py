"""Transcript and speaker endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentPrincipal, DbSession, SessionDep
from app.models.enums import SpeakerRole
from app.schemas.session import SpeakerOut, SpeakerRoleUpdate
from app.schemas.transcript import TranscriptSegmentOut
from app.services import repository as repo
from app.services.pipeline import pipeline
from app.schemas.events import EventType
from app.websocket.manager import manager

router = APIRouter(tags=["transcript"])


@router.get("/sessions/{session_id}/transcript", response_model=list[TranscriptSegmentOut])
async def get_transcript(session: SessionDep, db: DbSession) -> list[TranscriptSegmentOut]:
    segments = await repo.list_segments(db, session.id)
    return [repo.serialize_segment(segment) for segment in segments]


@router.get("/sessions/{session_id}/speakers", response_model=list[SpeakerOut])
async def get_speakers(session: SessionDep, db: DbSession) -> list[SpeakerOut]:
    return [repo.serialize_speaker(speaker) for speaker in await repo.list_speakers(db, session.id)]


@router.get("/sessions/{session_id}/audio-chunks")
async def get_audio_chunks(session: SessionDep, db: DbSession) -> dict:
    chunks = await repo.list_audio_chunks(db, session.id)
    return {"chunks": [repo.serialize_chunk(chunk).model_dump(mode="json") for chunk in chunks]}


@router.patch("/speakers/{speaker_id}", response_model=SpeakerOut)
async def update_speaker_role(
    speaker_id: str, payload: SpeakerRoleUpdate, db: DbSession, principal: CurrentPrincipal
) -> SpeakerOut:
    """Human role assignment. It wins over any heuristic attribution."""
    speaker = await repo.get_speaker(db, speaker_id)
    if speaker is None:
        raise HTTPException(status_code=404, detail=f"Speaker {speaker_id} not found")

    previous = speaker.role
    speaker.role = payload.role
    speaker.role_source = "HUMAN"
    speaker.confidence = 1.0
    if payload.display_name is not None:
        speaker.display_name = payload.display_name.strip() or speaker.display_name

    await repo.record_audit(
        db,
        action="SPEAKER_ROLE_UPDATED",
        resource_type="speaker",
        resource_id=str(speaker.id),
        session_id=speaker.session_id,
        actor_email=principal.email,
        actor_role=principal.role.value,
        detail={"from": previous.value, "to": payload.role.value},
    )
    await db.commit()

    session = await repo.get_session(db, str(speaker.session_id))
    payload_speakers = [
        repo.serialize_speaker(item).model_dump(mode="json")
        for item in await repo.list_speakers(db, speaker.session_id)
    ]
    segments = [
        repo.serialize_segment(segment).model_dump(mode="json")
        for segment in await repo.list_segments(db, speaker.session_id)
    ]
    await manager.broadcast(
        str(speaker.session_id),
        EventType.DIARIZATION_UPDATE,
        {"speakers": payload_speakers, "turns": [], "role_updates": [{"id": str(speaker.id), "role": speaker.role.value}]},
    )
    await manager.broadcast(str(speaker.session_id), EventType.TRANSCRIPT_UPDATE, {"segments": segments, "replace": True})

    # Re-run structuring so role-sensitive rules (plan, assessment) are reapplied.
    if session is not None and speaker.role in (SpeakerRole.DOCTOR, SpeakerRole.NURSE, SpeakerRole.PATIENT):
        runtime = await pipeline.ensure_runtime(session)
        await pipeline.run_ai_update(runtime, force=True)

    return repo.serialize_speaker(speaker)
