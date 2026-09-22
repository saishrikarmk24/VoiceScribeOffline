"""Audio ingestion endpoints (browser microphone and uploaded recordings)."""

from __future__ import annotations

import base64

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.api.deps import DbSession, SessionDep
from app.core.config import settings
from app.core.logging import get_logger
from app.models import SessionStatus
from app.schemas.common import Acknowledgement
from app.schemas.transcript import AudioChunkIngest
from app.services.asr import ASRUnavailable
from app.services.audio import RawAudio, UploadedAudioProvider
from app.services.pipeline import pipeline

logger = get_logger(__name__)
router = APIRouter(prefix="/sessions", tags=["audio"])

MAX_CHUNK_BYTES = 8 * 1024 * 1024


@router.post("/{session_id}/audio/chunk", response_model=Acknowledgement)
async def ingest_chunk(session: SessionDep, payload: AudioChunkIngest, db: DbSession) -> Acknowledgement:
    """Accept a live microphone buffer captured by the browser."""
    if session.status not in (SessionStatus.LIVE, SessionStatus.PROCESSING):
        raise HTTPException(status_code=409, detail=f"Session is {session.status.value}; audio is not being captured.")

    try:
        data = base64.b64decode(payload.audio_base64, validate=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="audio_base64 is not valid base64.") from exc
    if not data:
        raise HTTPException(status_code=400, detail="Empty audio payload.")
    if len(data) > MAX_CHUNK_BYTES:
        raise HTTPException(status_code=413, detail="Audio chunk exceeds the 8 MB limit.")

    runtime = await pipeline.ensure_runtime(session)
    raw = RawAudio(
        data=data,
        mime_type=payload.mime_type,
        sample_rate=payload.sample_rate or settings.audio_sample_rate,
        channels=payload.channels or settings.audio_channels,
        duration_seconds=payload.duration_seconds,
    )
    segments = await _ingest(runtime, raw)
    return Acknowledgement(
        ok=True,
        message=f"Processed {len(data)} bytes.",
        detail={
            "segments": [segment.ref for segment in segments],
            "timeline_seconds": round(runtime.timeline, 2),
            "asr_provider": runtime.asr.name,
        },
    )


@router.post("/{session_id}/audio/upload", response_model=Acknowledgement)
async def upload_recording(
    session: SessionDep, db: DbSession, file: UploadFile = File(...)
) -> Acknowledgement:
    """Ingest a complete recording (WAV is decoded locally; other containers are forwarded)."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(data) > 64 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Uploaded recording exceeds the 64 MB limit.")

    runtime = await pipeline.ensure_runtime(session)
    provider = UploadedAudioProvider(data=data, mime_type=file.content_type or "audio/wav")
    raw = await provider.next_chunk()
    if raw is None:  # pragma: no cover - provider always yields once
        raise HTTPException(status_code=400, detail="Could not read the uploaded recording.")

    segments = await _ingest(runtime, raw)
    if not segments:
        # An empty transcript is reported honestly rather than as a success, so
        # the UI never implies speech was captured when none was recognised.
        return Acknowledgement(
            ok=False,
            message=(
                "No speech was recognised in this recording. Check the microphone input level "
                "and try again."
            ),
            detail={"segments": [], "asr_provider": runtime.asr.name, "bytes": len(data)},
        )

    # Trigger clinical extraction & note synthesis immediately for the uploaded take
    await pipeline.run_ai_update(runtime, force=True)

    return Acknowledgement(
        ok=True,
        message=f"Transcribed {file.filename or 'recording'} and generated clinical note.",
        detail={
            "segments": [segment.ref for segment in segments],
            "asr_provider": runtime.asr.name,
            "bytes": len(data),
        },
    )


async def _ingest(runtime, raw: RawAudio):
    """Run one buffer through the pipeline, mapping failures to clear HTTP errors.

    Transcription failures must never degrade to demo or placeholder content, so
    they surface as an error the clinician can act on.
    """
    try:
        return await pipeline.ingest_audio(runtime, raw)
    except ASRUnavailable as exc:
        logger.error("audio_ingest_asr_unavailable", extra={"error": str(exc)})
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("audio_ingest_failed")
        raise HTTPException(
            status_code=502, detail=f"Audio could not be transcribed: {exc}"
        ) from exc


@router.post("/transcribe_clip", response_model=Acknowledgement)
async def transcribe_clip(file: UploadFile = File(...)) -> Acknowledgement:
    """Transcribe a standalone voice dictation clip directly using the active ASR provider."""
    data = await file.read()
    if not data:
        return Acknowledgement(ok=False, message="Audio clip was empty.", detail={"text": ""})
    try:
        from app.models.enums import AudioSource
        from app.services.asr import build_asr_provider
        from app.services.audio import AudioPreprocessingService, UploadedAudioProvider

        provider = UploadedAudioProvider(data=data, mime_type=file.content_type or "audio/wav")
        raw = await provider.next_chunk()
        if raw is None:
            return Acknowledgement(ok=False, message="Could not decode audio.", detail={"text": ""})

        preprocessor = AudioPreprocessingService()
        frame = preprocessor.process(
            raw,
            session_id="clip",
            sequence=1,
            start_time=0.0,
            source=AudioSource.MICROPHONE,
        )
        asr = build_asr_provider()
        segments = await asr.transcribe(frame)
        text = " ".join(s.text.strip() for s in segments if s.text.strip())
        return Acknowledgement(
            ok=bool(text),
            message="Transcription complete" if text else "No speech recognised in audio clip.",
            detail={"text": text},
        )
    except Exception as exc:
        logger.exception("clip_transcription_failed")
        return Acknowledgement(ok=False, message=str(exc), detail={"text": ""})

