"""WebSocket endpoint for a live session."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.database import get_session_factory
from app.core.logging import get_logger
from app.schemas.events import EventType, SocketEvent
from app.services import repository as repo
from app.services.pipeline import pipeline
from app.websocket.manager import manager

logger = get_logger(__name__)
router = APIRouter()


@router.websocket("/ws/sessions/{session_id}")
async def session_socket(websocket: WebSocket, session_id: str) -> None:
    await manager.connect(session_id, websocket)
    try:
        await _send_snapshot(websocket, session_id)
        while True:
            message = await websocket.receive_json()
            kind = str(message.get("type", "")).upper()

            if kind == "PING":
                await manager.send_to(
                    websocket,
                    SocketEvent(
                        type=EventType.PONG,
                        session_id=session_id,
                        payload={"server_sequence": manager.last_sequence(session_id)},
                    ),
                )
            elif kind == "SYNC":
                last = int(message.get("last_sequence") or 0)
                missed = manager.history(session_id, after_sequence=last)
                if missed and last:
                    for event in missed:
                        await manager.send_to(websocket, event)
                else:
                    await _send_snapshot(websocket, session_id)
    except WebSocketDisconnect:
        await manager.disconnect(session_id, websocket)
    except Exception:
        logger.exception("websocket_error", extra={"session_id": session_id})
        await manager.disconnect(session_id, websocket)


async def _send_snapshot(websocket: WebSocket, session_id: str) -> None:
    factory = get_session_factory()
    async with factory() as db:
        session = await repo.get_session(db, session_id)
        if session is None:
            await manager.send_to(
                websocket,
                SocketEvent(
                    type=EventType.PROCESSING_ERROR,
                    session_id=session_id,
                    payload={"code": "SESSION_NOT_FOUND", "message": "Unknown session", "recoverable": False},
                ),
            )
            return
        payload = await pipeline.snapshot(db, session)
    await manager.send_to(
        websocket,
        SocketEvent(
            type=EventType.STATE_SNAPSHOT,
            session_id=session_id,
            payload=payload,
            sequence=manager.last_sequence(session_id),
        ),
    )
