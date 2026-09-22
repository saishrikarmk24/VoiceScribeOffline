"""WebSocket layer.

``routes`` is not imported here on purpose: it depends on the pipeline, which
depends on this package's connection manager.
"""

from app.websocket.manager import SessionConnectionManager, manager

__all__ = ["SessionConnectionManager", "manager"]
