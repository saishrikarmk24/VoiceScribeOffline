"""Database access helpers and ORM -> schema serialisers.

Keeping queries here means the pipeline, the REST routes and the exporters all
read the session state the same way.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import (
    AuditLog,
    AudioChunk,
    ClinicalEntity,
    ClinicalNote,
    EvidenceLink,
    NoteStatus,
    NoteVersion,
    Session as SessionModel,
    Speaker,
    SpeakerRole,
    TranscriptSegment,
    User,
)
from app.schemas.clinical import (
    ClinicalEntityOut,
    ClinicalNoteContent,
    EvidenceOut,
    EvidenceReference,
    NoteOut,
    NoteVersionOut,
)
from app.schemas.session import SessionOut, SessionSummary, SpeakerOut
from app.schemas.transcript import AudioChunkOut, TranscriptSegmentOut
from app.services.evidence.linking import SegmentIndexEntry

logger = get_logger(__name__)


def as_uuid(value: str | uuid.UUID) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


# --------------------------------------------------------------------- sessions
async def get_session(db: AsyncSession, session_id: str | uuid.UUID) -> SessionModel | None:
    try:
        identifier = as_uuid(session_id)
    except (ValueError, AttributeError, TypeError):
        result = await db.execute(select(SessionModel).where(SessionModel.reference == str(session_id)))
        return result.scalar_one_or_none()
    result = await db.execute(select(SessionModel).where(SessionModel.id == identifier))
    return result.scalar_one_or_none()


async def next_session_reference(db: AsyncSession) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"SIM-{year}-"
    result = await db.execute(
        select(func.count()).select_from(SessionModel).where(SessionModel.reference.like(f"{prefix}%"))
    )
    count = int(result.scalar() or 0)
    while True:
        candidate = f"{prefix}{count + 1:03d}"
        exists = await db.execute(select(SessionModel.id).where(SessionModel.reference == candidate))
        if exists.scalar_one_or_none() is None:
            return candidate
        count += 1


async def list_sessions(
    db: AsyncSession, *, limit: int = 50, offset: int = 0, status: str | None = None
) -> tuple[list[SessionModel], int]:
    query = select(SessionModel).order_by(SessionModel.created_at.desc())
    count_query = select(func.count()).select_from(SessionModel)
    if status:
        query = query.where(SessionModel.status == status)
        count_query = count_query.where(SessionModel.status == status)
    total = int((await db.execute(count_query)).scalar() or 0)
    result = await db.execute(query.limit(limit).offset(offset))
    return list(result.scalars().all()), total


async def session_counts(db: AsyncSession, session_id: uuid.UUID) -> tuple[int, int, float]:
    segments = int(
        (
            await db.execute(
                select(func.count()).select_from(TranscriptSegment).where(TranscriptSegment.session_id == session_id)
            )
        ).scalar()
        or 0
    )
    entities = int(
        (
            await db.execute(
                select(func.count()).select_from(ClinicalEntity).where(ClinicalEntity.session_id == session_id)
            )
        ).scalar()
        or 0
    )
    max_duration = float(
        (
            await db.execute(
                select(func.max(TranscriptSegment.end_time)).where(TranscriptSegment.session_id == session_id)
            )
        ).scalar()
        or 0.0
    )
    return segments, entities, max_duration


def session_duration(session: SessionModel) -> float:
    if not session.started_at:
        return 0.0
    end = session.ended_at or datetime.now(timezone.utc)
    started = session.started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return max(0.0, (end - started).total_seconds() - (session.paused_seconds or 0.0))


async def serialize_session(db: AsyncSession, session: SessionModel) -> SessionOut:
    segments, entities, max_duration = await session_counts(db, session.id)
    note = await get_note(db, session.id)
    speakers = await list_speakers(db, session.id)
    duration = max_duration if max_duration > 0 else session_duration(session)
    return SessionOut(
        id=str(session.id),
        reference=session.reference,
        name=session.name,
        patient_id=session.patient_id,
        scenario=session.scenario,
        simulation_type=session.simulation_type,
        doctor_name=session.doctor_name,
        faculty_name=session.faculty_name,
        status=session.status,
        mode=session.mode,
        audio_source=session.audio_source,
        ai_mode=session.ai_mode,
        model_name=session.model_name,
        started_at=session.started_at,
        ended_at=session.ended_at,
        created_at=session.created_at,
        updated_at=session.updated_at,
        last_error=session.last_error,
        duration_seconds=round(duration, 2),
        segment_count=segments,
        entity_count=entities,
        note_status=note.status.value if note else None,
        note_version=note.version if note else 0,
        speakers=[serialize_speaker(speaker) for speaker in speakers],
    )


async def serialize_summary(db: AsyncSession, session: SessionModel) -> SessionSummary:
    segments, entities, max_duration = await session_counts(db, session.id)
    note = await get_note(db, session.id)
    duration = max_duration if max_duration > 0 else session_duration(session)
    return SessionSummary(
        id=str(session.id),
        reference=session.reference,
        name=session.name,
        patient_id=session.patient_id,
        status=session.status,
        mode=session.mode,
        simulation_type=session.simulation_type,
        created_at=session.created_at,
        started_at=session.started_at,
        ended_at=session.ended_at,
        duration_seconds=round(duration, 2),
        segment_count=segments,
        entity_count=entities,
        note_status=note.status.value if note else None,
    )


# --------------------------------------------------------------------- speakers
async def list_speakers(db: AsyncSession, session_id: uuid.UUID) -> list[Speaker]:
    result = await db.execute(select(Speaker).where(Speaker.session_id == session_id).order_by(Speaker.label))
    return list(result.scalars().all())


async def get_speaker(db: AsyncSession, speaker_id: str | uuid.UUID) -> Speaker | None:
    result = await db.execute(select(Speaker).where(Speaker.id == as_uuid(speaker_id)))
    return result.scalar_one_or_none()


async def get_or_create_speaker(
    db: AsyncSession,
    session_id: uuid.UUID,
    label: str,
    *,
    role: SpeakerRole = SpeakerRole.UNKNOWN,
    confidence: float = 0.0,
) -> Speaker:
    result = await db.execute(
        select(Speaker).where(Speaker.session_id == session_id, Speaker.label == label)
    )
    speaker = result.scalar_one_or_none()
    if speaker is not None:
        return speaker
    speaker = Speaker(
        session_id=session_id,
        label=label,
        role=role,
        confidence=confidence,
        display_name=label.replace("_", " ").title(),
    )
    db.add(speaker)
    await db.flush()
    return speaker


def serialize_speaker(speaker: Speaker) -> SpeakerOut:
    return SpeakerOut(
        id=str(speaker.id),
        label=speaker.label,
        display_name=speaker.display_name,
        role=speaker.role,
        confidence=round(speaker.confidence, 4),
        role_source=speaker.role_source,
    )


async def speaker_roles(db: AsyncSession, session_id: uuid.UUID) -> dict[str, SpeakerRole]:
    return {speaker.label: speaker.role for speaker in await list_speakers(db, session_id)}


# ------------------------------------------------------------------- transcript
async def list_segments(db: AsyncSession, session_id: uuid.UUID) -> list[TranscriptSegment]:
    result = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.session_id == session_id)
        .order_by(TranscriptSegment.sequence)
    )
    return list(result.scalars().all())


async def segment_count(db: AsyncSession, session_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count()).select_from(TranscriptSegment).where(TranscriptSegment.session_id == session_id)
    )
    return int(result.scalar() or 0)


def serialize_segment(segment: TranscriptSegment) -> TranscriptSegmentOut:
    speaker = segment.speaker
    return TranscriptSegmentOut(
        id=str(segment.id),
        ref=segment.ref,
        sequence=segment.sequence,
        speaker_id=str(segment.speaker_id) if segment.speaker_id else None,
        speaker_label=speaker.label if speaker else None,
        role=speaker.role if speaker else SpeakerRole.UNKNOWN,
        text=segment.text,
        start_time=round(segment.start_time, 3),
        end_time=round(segment.end_time, 3),
        confidence=round(segment.confidence, 4),
        asr_confidence=round(segment.asr_confidence, 4),
        diarization_confidence=round(segment.diarization_confidence, 4),
        overlapping=segment.overlapping,
        is_final=segment.is_final,
    )


def segment_index(segments: Sequence[TranscriptSegment]) -> list[SegmentIndexEntry]:
    entries: list[SegmentIndexEntry] = []
    for segment in segments:
        speaker = segment.speaker
        entries.append(
            SegmentIndexEntry(
                ref=segment.ref,
                text=segment.text,
                speaker_label=speaker.label if speaker else "unknown",
                role=speaker.role if speaker else SpeakerRole.UNKNOWN,
                start_time=segment.start_time,
                end_time=segment.end_time,
                confidence=segment.confidence,
                segment_id=str(segment.id),
            )
        )
    return entries


def segments_as_prompt_dicts(segments: Sequence[TranscriptSegment]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for segment in segments:
        speaker = segment.speaker
        payload.append(
            {
                "ref": segment.ref,
                "speaker_label": speaker.label if speaker else "unknown",
                "role": (speaker.role.value if speaker else SpeakerRole.UNKNOWN.value),
                "text": segment.text,
                "start_time": segment.start_time,
                "end_time": segment.end_time,
                "confidence": segment.confidence,
            }
        )
    return payload


# ----------------------------------------------------------------- audio chunks
async def list_audio_chunks(db: AsyncSession, session_id: uuid.UUID) -> list[AudioChunk]:
    result = await db.execute(
        select(AudioChunk).where(AudioChunk.session_id == session_id).order_by(AudioChunk.sequence)
    )
    return list(result.scalars().all())


def serialize_chunk(chunk: AudioChunk) -> AudioChunkOut:
    return AudioChunkOut(
        id=str(chunk.id),
        sequence=chunk.sequence,
        source=chunk.source.value,
        start_time=round(chunk.start_time, 3),
        end_time=round(chunk.end_time, 3),
        sample_rate=chunk.sample_rate,
        channels=chunk.channels,
        size_bytes=chunk.size_bytes,
        speech_ratio=round(chunk.speech_ratio, 4),
        rms_dbfs=round(chunk.rms_dbfs, 2),
        status=chunk.status,
    )


# --------------------------------------------------------------------- entities
async def list_entities(db: AsyncSession, session_id: uuid.UUID) -> list[ClinicalEntity]:
    result = await db.execute(
        select(ClinicalEntity)
        .where(ClinicalEntity.session_id == session_id)
        .order_by(ClinicalEntity.created_at, ClinicalEntity.ref)
    )
    return list(result.scalars().all())


async def entity_evidence_map(
    db: AsyncSession, session_id: uuid.UUID
) -> dict[str, list[EvidenceReference]]:
    result = await db.execute(
        select(EvidenceLink).where(
            EvidenceLink.session_id == session_id, EvidenceLink.target_kind == "ENTITY"
        )
    )
    mapping: dict[str, list[EvidenceReference]] = {}
    for link in result.scalars().all():
        mapping.setdefault(link.target_key, []).append(
            EvidenceReference(
                transcript_segment_ref=link.segment_ref or "",
                speaker_label=link.speaker_label,
                speaker_role=link.speaker_role,
                timestamp=link.timestamp,
                confidence=link.confidence,
                source_text=link.source_text,
                validated=link.validated,
                validation_error=link.validation_error,
            )
        )
    return mapping


def serialize_entity(
    entity: ClinicalEntity, evidence: dict[str, list[EvidenceReference]] | None = None
) -> ClinicalEntityOut:
    return ClinicalEntityOut(
        id=str(entity.id),
        ref=entity.ref,
        entity_type=entity.entity_type,
        value=entity.value,
        normalized_value=entity.normalized_value,
        normalized_code=entity.normalized_code,
        terminology_system=entity.terminology_system,
        status=entity.status,
        confidence=round(entity.confidence, 4),
        source_segment_refs=list(entity.source_segment_refs or []),
        detail=entity.detail,
        review_required=entity.review_required,
        review_reason=entity.review_reason,
        evidence=(evidence or {}).get(entity.ref, []),
    )


# ------------------------------------------------------------------------ notes
async def get_note(db: AsyncSession, session_id: uuid.UUID) -> ClinicalNote | None:
    result = await db.execute(select(ClinicalNote).where(ClinicalNote.session_id == session_id))
    return result.scalars().first()


async def get_note_by_id(db: AsyncSession, note_id: str | uuid.UUID) -> ClinicalNote | None:
    result = await db.execute(select(ClinicalNote).where(ClinicalNote.id == as_uuid(note_id)))
    return result.scalar_one_or_none()


async def get_or_create_note(db: AsyncSession, session: SessionModel) -> ClinicalNote:
    note = await get_note(db, session.id)
    if note is not None:
        return note
    note = ClinicalNote(
        session_id=session.id,
        status=NoteStatus.PROCESSING,
        version=0,
        content=ClinicalNoteContent().model_dump(mode="json"),
        review_flags=[],
        model=session.model_name,
    )
    db.add(note)
    await db.flush()
    return note


def note_content(note: ClinicalNote | None) -> ClinicalNoteContent:
    if note is None or not note.content:
        return ClinicalNoteContent()
    try:
        return ClinicalNoteContent.model_validate(note.content)
    except Exception:  # pragma: no cover - defensive against manual DB edits
        logger.warning("note_content_invalid", extra={"note_id": str(note.id) if note else None})
        return ClinicalNoteContent()


def serialize_note(note: ClinicalNote) -> NoteOut:
    return NoteOut(
        id=str(note.id),
        session_id=str(note.session_id),
        status=note.status,
        version=note.version,
        content=note_content(note),
        review_flags=list(note.review_flags or []),
        model=note.model,
        approved_by=note.approved_by,
        approved_at=_iso(note.approved_at),
        exported_at=_iso(note.exported_at),
        updated_at=_iso(note.updated_at),
    )


async def list_note_versions(db: AsyncSession, note_id: uuid.UUID) -> list[NoteVersion]:
    result = await db.execute(
        select(NoteVersion).where(NoteVersion.note_id == note_id).order_by(NoteVersion.version)
    )
    return list(result.scalars().all())


def serialize_note_version(version: NoteVersion) -> NoteVersionOut:
    return NoteVersionOut(
        id=str(version.id),
        version=version.version,
        status=version.status,
        change_summary=version.change_summary,
        changed_sections=list(version.changed_sections or []),
        author_type=version.author_type,
        author=version.author,
        model=version.model,
        created_at=_iso(version.created_at),
    )


# --------------------------------------------------------------------- evidence
async def list_evidence(
    db: AsyncSession, session_id: uuid.UUID, *, target_key: str | None = None
) -> list[EvidenceLink]:
    query = select(EvidenceLink).where(EvidenceLink.session_id == session_id)
    if target_key:
        query = query.where(EvidenceLink.target_key == target_key)
    result = await db.execute(query.order_by(EvidenceLink.created_at))
    return list(result.scalars().all())


def serialize_evidence(link: EvidenceLink) -> EvidenceOut:
    return EvidenceOut(
        id=str(link.id),
        target_kind=link.target_kind,
        target_key=link.target_key,
        clinical_statement=link.clinical_statement,
        segment_ref=link.segment_ref,
        speaker_label=link.speaker_label,
        speaker_role=link.speaker_role,
        source_text=link.source_text,
        timestamp=link.timestamp,
        confidence=round(link.confidence, 4),
        validated=link.validated,
        validation_error=link.validation_error,
    )


# ------------------------------------------------------------------------ users
async def get_or_create_user(
    db: AsyncSession, email: str, *, full_name: str | None = None, role: str = "DOCTOR"
) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None:
        return user
    user = User(email=email, full_name=full_name or email.split("@")[0].replace(".", " ").title(), role=role, password_hash="")
    db.add(user)
    await db.flush()
    return user


# ------------------------------------------------------------------ audit trail
async def record_audit(
    db: AsyncSession,
    *,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    session_id: uuid.UUID | None = None,
    actor_email: str | None = None,
    actor_role: str | None = None,
    user_id: uuid.UUID | None = None,
    detail: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        session_id=session_id,
        user_id=user_id,
        actor_email=actor_email,
        actor_role=actor_role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail or {},
    )
    db.add(entry)
    return entry


async def list_audit(db: AsyncSession, session_id: uuid.UUID, limit: int = 200) -> list[AuditLog]:
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.session_id == session_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


def dedupe(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))
