"""Per-session WebSocket fan-out with replayable event history.

Clients that reconnect send ``{"type": "SYNC", "last_sequence": n}`` and receive
either the missed events or a full state snapshot, so a dropped socket never
leaves the workstation showing stale data.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from typing import Any, Deque

from fastapi import WebSocket

from app.core.logging import get_logger, metrics
from app.schemas.events import EventType, SocketEvent

logger = get_logger(__name__)

HISTORY_LIMIT = 400


class SessionConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._history: dict[str, Deque[SocketEvent]] = defaultdict(lambda: deque(maxlen=HISTORY_LIMIT))
        self._sequences: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------- connections
    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[session_id].add(websocket)
        metrics.set_gauge("websocket_connections", self.total_connections)
        logger.info("websocket_connected", extra={"session_id": session_id, "clients": self.client_count(session_id)})

    async def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.get(session_id, set()).discard(websocket)
            if not self._connections.get(session_id):
                self._connections.pop(session_id, None)
        metrics.set_gauge("websocket_connections", self.total_connections)
        logger.info("websocket_disconnected", extra={"session_id": session_id})

    def client_count(self, session_id: str) -> int:
        return len(self._connections.get(session_id, set()))

    @property
    def total_connections(self) -> int:
        return sum(len(clients) for clients in self._connections.values())

    def stats(self) -> dict[str, Any]:
        return {
            "connections": self.total_connections,
            "sessions": len(self._connections),
            "history_limit": HISTORY_LIMIT,
        }

    # ------------------------------------------------------------------ events
    async def broadcast(self, session_id: str, event_type: EventType, payload: dict[str, Any]) -> SocketEvent:
        self._sequences[session_id] += 1
        event = SocketEvent(
            type=event_type,
            session_id=session_id,
            payload=payload,
            sequence=self._sequences[session_id],
        )
        self._history[session_id].append(event)
        metrics.increment("websocket_events_total", type=event_type.value)

        message = event.model_dump(mode="json")
        stale: list[WebSocket] = []
        for websocket in list(self._connections.get(session_id, set())):
            try:
                await websocket.send_json(message)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            await self.disconnect(session_id, websocket)
        return event

    async def send_to(self, websocket: WebSocket, event: SocketEvent) -> None:
        await websocket.send_json(event.model_dump(mode="json"))

    def history(self, session_id: str, after_sequence: int = 0) -> list[SocketEvent]:
        return [event for event in self._history.get(session_id, ()) if event.sequence > after_sequence]

    def last_sequence(self, session_id: str) -> int:
        return self._sequences.get(session_id, 0)

    def reset(self, session_id: str) -> None:
        self._history.pop(session_id, None)
        self._sequences.pop(session_id, None)


manager = SessionConnectionManager()
