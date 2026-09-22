"""API route registration."""

from fastapi import APIRouter

from app.api.routes import audio, auth, entities, evidence, exports, notes, sessions, system, transcript

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(system.router)
api_router.include_router(sessions.router)
api_router.include_router(audio.router)
api_router.include_router(transcript.router)
api_router.include_router(entities.router)
api_router.include_router(notes.router)
api_router.include_router(evidence.router)
api_router.include_router(exports.router)

__all__ = ["api_router"]
