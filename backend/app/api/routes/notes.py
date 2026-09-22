"""Clinical note endpoints: read, edit, approve.

Approval is human-controlled by design: an AI update can never set APPROVED, and
the reviewer must explicitly acknowledge that they reviewed the note.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentPrincipal, DbSession, SessionDep
from app.models import NoteStatus, NoteVersion
from app.schemas.clinical import NoteApproval, NoteOut, NotePatch, NoteVersionOut
from app.schemas.events import EventType
from app.services import repository as repo
from app.services.note_engine import NoteStateEngine, NoteStateError
from app.websocket.manager import manager

router = APIRouter(tags=["notes"])
engine = NoteStateEngine()


@router.get("/sessions/{session_id}/note", response_model=NoteOut)
async def get_note(session: SessionDep, db: DbSession) -> NoteOut:
    note = await repo.get_or_create_note(db, session)
    await db.commit()
    return repo.serialize_note(note)


@router.get("/sessions/{session_id}/note/versions", response_model=list[NoteVersionOut])
async def get_note_versions(session: SessionDep, db: DbSession) -> list[NoteVersionOut]:
    note = await repo.get_note(db, session.id)
    if note is None:
        return []
    versions = await repo.list_note_versions(db, note.id)
    return [repo.serialize_note_version(version) for version in versions]


@router.patch("/notes/{note_id}", response_model=NoteOut)
async def edit_note(note_id: str, payload: NotePatch, db: DbSession, principal: CurrentPrincipal) -> NoteOut:
    note = await repo.get_note_by_id(db, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")

    changes = payload.changes()
    if not changes:
        raise HTTPException(status_code=400, detail="No section edits supplied.")

    editor = payload.editor or principal.display_name
    try:
        outcome = engine.apply_human_edit(
            current=repo.note_content(note), changes=changes, version=note.version, editor=editor
        )
    except NoteStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if outcome.changed_sections:
        note.content = outcome.content.model_dump(mode="json")
        note.version = outcome.version
        note.status = outcome.status
        note.review_flags = [
            flag for flag in (note.review_flags or []) if flag.get("section") not in outcome.changed_sections
        ]
        db.add(
            NoteVersion(
                note_id=note.id,
                session_id=note.session_id,
                version=outcome.version,
                status=outcome.status,
                content=note.content,
                change_summary=outcome.change_summary,
                changed_sections=outcome.changed_sections,
                author_type="HUMAN",
                author=editor,
                model=None,
            )
        )
        await repo.record_audit(
            db,
            action="NOTE_EDITED",
            resource_type="note",
            resource_id=str(note.id),
            session_id=note.session_id,
            actor_email=principal.email,
            actor_role=principal.role.value,
            detail={"sections": outcome.changed_sections},
        )
    await db.commit()

    serialized = repo.serialize_note(note)
    await manager.broadcast(
        str(note.session_id),
        EventType.NOTE_UPDATE,
        {
            "note": serialized.model_dump(mode="json"),
            "changed_sections": outcome.changed_sections,
            "change_summary": outcome.change_summary,
            "author_type": "HUMAN",
        },
    )
    return serialized


@router.post("/notes/{note_id}/approve", response_model=NoteOut)
async def approve_note(
    note_id: str, payload: NoteApproval, db: DbSession, principal: CurrentPrincipal
) -> NoteOut:
    if not principal.can_approve_notes():
        raise HTTPException(status_code=403, detail="This role cannot approve clinical documentation.")

    note = await repo.get_note_by_id(db, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")

    approver = payload.approved_by or principal.display_name
    try:
        outcome = engine.approve(
            content=repo.note_content(note),
            current_status=note.status,
            version=note.version,
            approver=approver,
            acknowledged=payload.acknowledgement,
        )
    except NoteStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    note.status = outcome.status
    note.version = outcome.version
    note.approved_by = approver
    note.approved_at = datetime.now(timezone.utc)
    db.add(
        NoteVersion(
            note_id=note.id,
            session_id=note.session_id,
            version=outcome.version,
            status=outcome.status,
            content=note.content,
            change_summary=outcome.change_summary,
            changed_sections=[],
            author_type="HUMAN",
            author=approver,
        )
    )

    session = await repo.get_session(db, str(note.session_id))
    if session is not None:
        from app.models import SessionStatus

        session.status = SessionStatus.APPROVED
    await repo.record_audit(
        db,
        action="NOTE_APPROVED",
        resource_type="note",
        resource_id=str(note.id),
        session_id=note.session_id,
        actor_email=principal.email,
        actor_role=principal.role.value,
        detail={"approved_by": approver, "version": outcome.version},
    )
    await db.commit()

    serialized = repo.serialize_note(note)
    await manager.broadcast(
        str(note.session_id),
        EventType.NOTE_UPDATE,
        {
            "note": serialized.model_dump(mode="json"),
            "changed_sections": [],
            "change_summary": outcome.change_summary,
            "author_type": "HUMAN",
        },
    )
    return serialized


@router.post("/notes/{note_id}/reopen", response_model=NoteOut)
async def reopen_note(note_id: str, db: DbSession, principal: CurrentPrincipal) -> NoteOut:
    """Return an approved note to DRAFT so it can be edited again."""
    note = await repo.get_note_by_id(db, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail=f"Note {note_id} not found")
    if note.status not in (NoteStatus.APPROVED, NoteStatus.EXPORTED):
        raise HTTPException(status_code=409, detail="Only approved or exported notes can be reopened.")

    note.status = NoteStatus.DRAFT
    note.approved_by = None
    note.approved_at = None
    await repo.record_audit(
        db,
        action="NOTE_REOPENED",
        resource_type="note",
        resource_id=str(note.id),
        session_id=note.session_id,
        actor_email=principal.email,
        actor_role=principal.role.value,
    )
    await db.commit()
    return repo.serialize_note(note)
