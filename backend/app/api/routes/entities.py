"""Clinical entity endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import DbSession, SessionDep
from app.models.enums import EntityStatus, EntityType
from app.schemas.clinical import ClinicalEntityOut
from app.services import repository as repo

router = APIRouter(prefix="/sessions", tags=["clinical"])


@router.get("/{session_id}/entities", response_model=list[ClinicalEntityOut])
async def get_entities(
    session: SessionDep,
    db: DbSession,
    entity_type: EntityType | None = Query(default=None),
    entity_status: EntityStatus | None = Query(default=None, alias="status"),
) -> list[ClinicalEntityOut]:
    entities = await repo.list_entities(db, session.id)
    evidence = await repo.entity_evidence_map(db, session.id)
    payload = [repo.serialize_entity(entity, evidence) for entity in entities]
    if entity_type:
        payload = [entity for entity in payload if entity.entity_type is entity_type]
    if entity_status:
        payload = [entity for entity in payload if entity.status is entity_status]
    return payload


@router.get("/{session_id}/entities/summary")
async def entity_summary(session: SessionDep, db: DbSession) -> dict:
    entities = await repo.list_entities(db, session.id)
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for entity in entities:
        by_type[entity.entity_type.value] = by_type.get(entity.entity_type.value, 0) + 1
        by_status[entity.status.value] = by_status.get(entity.status.value, 0) + 1
    return {
        "total": len(entities),
        "by_type": by_type,
        "by_status": by_status,
        "review_required": sum(1 for entity in entities if entity.review_required),
    }
