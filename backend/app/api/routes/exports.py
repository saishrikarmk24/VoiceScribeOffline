"""Export endpoints: JSON, PDF and FHIR-compatible bundle."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Response

from app.api.deps import CurrentPrincipal, DbSession, SessionDep
from app.models.enums import ExportFormat, NoteStatus
from app.services import repository as repo
from app.services.export import FHIRAdapter, build_export_payload, export_json, export_pdf
from app.services.note_engine import NoteStateEngine

router = APIRouter(prefix="/sessions", tags=["export"])
engine = NoteStateEngine()
fhir = FHIRAdapter()


async def _gather(session, db) -> dict:
    note = await repo.get_or_create_note(db, session)
    segments = await repo.list_segments(db, session.id)
    entities = await repo.list_entities(db, session.id)
    evidence_map = await repo.entity_evidence_map(db, session.id)
    evidence = await repo.list_evidence(db, session.id)
    versions = await repo.list_note_versions(db, note.id)
    await db.commit()
    return {
        "note": note,
        "session_payload": (await repo.serialize_session(db, session)).model_dump(mode="json"),
        "note_payload": repo.serialize_note(note).model_dump(mode="json"),
        "segments": [repo.serialize_segment(segment).model_dump(mode="json") for segment in segments],
        "entities": [repo.serialize_entity(entity, evidence_map).model_dump(mode="json") for entity in entities],
        "evidence": [repo.serialize_evidence(link).model_dump(mode="json") for link in evidence],
        "versions": [repo.serialize_note_version(version).model_dump(mode="json") for version in versions],
    }


@router.post("/{session_id}/export")
async def export_session(
    session: SessionDep,
    db: DbSession,
    principal: CurrentPrincipal,
    export_format: ExportFormat = Query(default=ExportFormat.JSON, alias="format"),
) -> Response:
    data = await _gather(session, db)
    note = data["note"]

    payload = build_export_payload(
        session=data["session_payload"],
        note=data["note_payload"],
        segments=data["segments"],
        entities=data["entities"],
        evidence=data["evidence"],
        versions=data["versions"],
    )
    stem = f"medscribe-{session.reference}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    if export_format is ExportFormat.JSON:
        body, media_type, filename = export_json(payload), "application/json", f"{stem}.json"
    elif export_format is ExportFormat.PDF:
        try:
            body = export_pdf(payload)
        except Exception as exc:  # pragma: no cover - reportlab is a hard dependency
            raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}") from exc
        media_type, filename = "application/pdf", f"{stem}.pdf"
    else:
        bundle = fhir.build_bundle(
            session=data["session_payload"],
            note=data["note_payload"],
            entities=data["entities"],
            segments=data["segments"],
        )
        body, media_type, filename = (
            export_json(bundle),
            "application/fhir+json",
            f"{stem}-fhir.json",
        )

    outcome = engine.mark_exported(
        content=repo.note_content(note), current_status=note.status, version=note.version, fmt=export_format.value
    )
    note.status = outcome.status
    note.exported_at = datetime.now(timezone.utc)
    await repo.record_audit(
        db,
        action="SESSION_EXPORTED",
        resource_type="session",
        resource_id=str(session.id),
        session_id=session.id,
        actor_email=principal.email,
        actor_role=principal.role.value,
        detail={"format": export_format.value, "note_version": note.version},
    )
    await db.commit()

    return Response(
        content=body,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-MedScribe-Note-Status": note.status.value,
            "X-MedScribe-Human-Approved": "true" if note.status in (NoteStatus.APPROVED, NoteStatus.EXPORTED) else "false",
        },
    )


@router.get("/{session_id}/export/preview")
async def export_preview(session: SessionDep, db: DbSession) -> dict:
    """Inspect the export payload (and the FHIR bundle) without downloading."""
    data = await _gather(session, db)
    payload = build_export_payload(
        session=data["session_payload"],
        note=data["note_payload"],
        segments=data["segments"],
        entities=data["entities"],
        evidence=data["evidence"],
        versions=data["versions"],
    )
    bundle = fhir.build_bundle(
        session=data["session_payload"],
        note=data["note_payload"],
        entities=data["entities"],
        segments=data["segments"],
    )
    return {
        "json_export": payload,
        "fhir_bundle": bundle,
        "fhir_resource_counts": _count_resources(bundle),
    }


def _count_resources(bundle: dict) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in bundle.get("entry", []):
        resource_type = entry.get("resource", {}).get("resourceType", "Unknown")
        counts[resource_type] = counts.get(resource_type, 0) + 1
    return counts
