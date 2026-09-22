"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import CurrentPrincipal, Principal  # re-exported for routes
from app.models import Session as SessionModel
from app.services import repository as repo

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_session_or_404(
    session_id: Annotated[str, Path(description="Session UUID or reference (SIM-YYYY-NNN)")],
    db: DbSession,
) -> SessionModel:
    session = await repo.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session {session_id} not found")
    return session


SessionDep = Annotated[SessionModel, Depends(get_session_or_404)]

__all__ = ["CurrentPrincipal", "DbSession", "Principal", "SessionDep", "get_session_or_404"]
