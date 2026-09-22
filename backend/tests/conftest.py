"""Test configuration.

The environment is configured *before* importing anything from ``app`` so the
settings singleton picks up the test database and the offline AI mode.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path or sys.path[0] != str(BACKEND_DIR):
    sys.path.insert(0, str(BACKEND_DIR))

TEST_DB = Path(__file__).resolve().parent / "medscribe_test.db"

os.environ.update(
    {
        "DATABASE_URL": f"sqlite+aiosqlite:///{TEST_DB.as_posix()}",
        "ALLOW_SQLITE_FALLBACK": "false",
        "AI_MODE": "mock",
        "GEMINI_API_KEY": "",
        "ENVIRONMENT": "test",
        "LOG_LEVEL": "WARNING",
        "ENABLE_DEMO_MODE": "true",
        "DEMO_SEGMENT_INTERVAL_SECONDS": "0.05",
        "GEMINI_MIN_SEGMENTS_PER_UPDATE": "2",
        "GEMINI_UPDATE_INTERVAL_SECONDS": "1",
    }
)

import asyncio  # noqa: E402
from contextlib import suppress  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.core.database import Base, db_state, dispose_database, init_database  # noqa: E402
from app.main import app  # noqa: E402
from app.models.enums import SessionMode  # noqa: E402
from app.services.pipeline import pipeline  # noqa: E402
from app.websocket.manager import manager  # noqa: E402


@pytest_asyncio.fixture
async def database():
    await init_database(create_schema=False)
    assert db_state.engine is not None
    async with db_state.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield db_state
    # Stop demo drivers before the loop closes, otherwise their database
    # connections outlive it and surface as unrelated teardown warnings.
    for session_id in list(pipeline.active_sessions()):
        runtime = pipeline.runtime(session_id)
        if runtime is not None:
            runtime.stopped = True
            runtime.resume_event.set()
            if runtime.task and not runtime.task.done():
                runtime.task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await runtime.task
        pipeline.discard(session_id)
        manager.reset(session_id)
    await asyncio.sleep(0)
    await dispose_database()


@pytest_asyncio.fixture
async def client(database) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as async_client:
        yield async_client


@pytest_asyncio.fixture
async def db_session(database):
    factory = db_state.session_factory
    assert factory is not None
    async with factory() as session:
        yield session


@pytest.fixture
def session_payload() -> dict:
    return {
        "name": "Chest discomfort OSCE",
        "patient_id": "SIM-PT-014",
        "scenario": "chest_discomfort",
        "simulation_type": "OSCE",
        "doctor_name": "Dr. Demo",
        "faculty_name": "Prof. Faculty",
        "mode": SessionMode.DEMO.value,
    }


@pytest_asyncio.fixture
async def created_session(client, session_payload) -> dict:
    response = await client.post("/api/sessions", json=session_payload)
    assert response.status_code == 201, response.text
    return response.json()
