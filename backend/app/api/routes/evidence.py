"""Evidence endpoints backing the "Show Source" feature."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import DbSession, SessionDep
from app.schemas.clinical import EvidenceOut
from app.services import repository as repo

router = APIRouter(prefix="/sessions", tags=["evidence"])


@router.get("/{session_id}/evidence", response_model=list[EvidenceOut])
async def get_evidence(
    session: SessionDep,
    db: DbSession,
    target_key: str | None = Query(default=None, description="Section key or entity ref"),
) -> list[EvidenceOut]:
    links = await repo.list_evidence(db, session.id, target_key=target_key)
    return [repo.serialize_evidence(link) for link in links]


@router.get("/{session_id}/evidence/{target_key}/detail")
async def evidence_detail(session: SessionDep, target_key: str, db: DbSession) -> dict:
    """Full provenance chain for one clinical statement."""
    links = await repo.list_evidence(db, session.id, target_key=target_key)
    segments = {segment.ref: segment for segment in await repo.list_segments(db, session.id)}
    chain = []
    for link in links:
        segment = segments.get(link.segment_ref or "")
        chain.append(
            {
                "evidence": repo.serialize_evidence(link).model_dump(mode="json"),
                "segment": repo.serialize_segment(segment).model_dump(mode="json") if segment else None,
                "audio_chunk_id": str(segment.audio_chunk_id) if segment and segment.audio_chunk_id else None,
            }
        )
    return {
        "target_key": target_key,
        "clinical_statement": links[0].clinical_statement if links else None,
        "chain": chain,
        "validated_count": sum(1 for link in links if link.validated),
        "total_count": len(links),
    }
