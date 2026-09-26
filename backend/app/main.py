"""VoiceScribe AI - FastAPI application entrypoint."""

from __future__ import annotations

from pathlib import Path
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import api_router
from app.core.config import settings
from app.core.database import dispose_database, init_database
from app.core.logging import configure_logging, get_logger, metrics, request_id_var
from app.websocket.routes import router as websocket_router

configure_logging()
logger = get_logger(__name__)

DESCRIPTION = """\
AI-powered clinical documentation and meeting minutes workstation.

VoiceScribe AI converts a doctor-patient conversation or multi-speaker meeting into a
structured, evidence-linked clinical note or meeting minutes:

`audio -> diarization + ASR -> transcript -> clinical NLP -> Gemini structuring
-> evidence linking -> note state engine -> clinical workstation`

**This is a documentation assistant, not an autonomous diagnostic system.**
Every AI-generated statement is traceable to a transcript segment, and human
review is mandatory before a note can be approved.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    state = await init_database()
    settings.audio_storage_path.mkdir(parents=True, exist_ok=True)
    logger.info(
        "application_started",
        extra={
            "environment": settings.environment,
            "database_dialect": state.dialect,
            "sqlite_fallback": state.using_fallback,
            "ai_mode": settings.effective_ai_mode.value,
            "gemini_model": settings.gemini_model,
            "gemini_configured": settings.gemini_configured,
            "demo_mode": settings.enable_demo_mode,
        },
    )
    try:
        yield
    finally:
        await dispose_database()
        logger.info("application_stopped")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=r"^chrome-extension://.*$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "X-MedScribe-Note-Status", "X-MedScribe-Human-Approved"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        metrics.increment("http_errors_total", path=request.url.path)
        logger.exception("request_failed", extra={"path": request.url.path, "method": request.method})
        request_id_var.reset(token)
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "detail": "Unexpected server error", "request_id": request_id},
        )
    duration = time.perf_counter() - started
    metrics.observe("http_request_duration_seconds", duration, method=request.method)
    metrics.increment("http_requests_total", status=response.status_code)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time-ms"] = f"{duration * 1000:.2f}"
    if request.url.path.startswith(settings.api_prefix):
        logger.info(
            "request_complete",
            extra={
                "path": request.url.path,
                "method": request.method,
                "status": response.status_code,
                "duration_ms": round(duration * 1000, 2),
            },
        )
    request_id_var.reset(token)
    return response


app.include_router(api_router, prefix=settings.api_prefix)
app.include_router(websocket_router)


# Check candidate paths for built frontend dist
frontend_dist_candidates = [
    Path(__file__).resolve().parents[2] / "frontend" / "dist",
    Path("dist").resolve(),
    Path("../frontend/dist").resolve(),
    Path("/content/VoiceScribeOffline/frontend/dist").resolve(),
]
frontend_dist: Path | None = None
for candidate in frontend_dist_candidates:
    if candidate.exists() and (candidate / "index.html").exists():
        frontend_dist = candidate
        break

if frontend_dist:
    from fastapi.staticfiles import StaticFiles
    from starlette.responses import FileResponse

    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", tags=["spa"])
    async def serve_spa(full_path: str):
        if full_path.startswith("api") or full_path.startswith("ws") or full_path.startswith("docs") or full_path.startswith("openapi.json"):
            return JSONResponse(status_code=404, content={"detail": "Not Found"})
        file_path = frontend_dist / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(frontend_dist / "index.html")
else:
    @app.get("/", tags=["system"])
    async def root() -> dict:
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "purpose": "Clinical documentation assistant",
            "not_a_diagnostic_system": True,
            "docs": "/docs",
            "api": settings.api_prefix,
            "websocket": "/ws/sessions/{session_id}",
        }
