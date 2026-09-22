"""Session pipeline orchestrator.

    audio -> preprocessing -> diarization + ASR -> transcript assembly
          -> clinical NLP -> LLM structuring -> validation -> evidence linking
          -> note state engine -> WebSocket broadcast

One :class:`SessionRuntime` exists per live session and owns that session's
providers, timeline cursor and batching state. Every stage is individually
failure-tolerant: a broken subsystem degrades its own output and reports status
instead of ending the session.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session_factory
from app.core.logging import get_logger, metrics, session_id_var
from app.models import (
    AudioChunk,
    AudioSource,
    ClinicalEntity,
    EntityStatus,
    EntityType,
    EvidenceLink,
    NoteStatus,
    NoteVersion,
    Session as SessionModel,
    SessionMode,
    SessionStatus,
    SpeakerRole,
    TranscriptSegment,
)
from app.schemas.clinical import ENTITY_KEYS, ClinicalEntityOut, ClinicalNoteContent
from app.schemas.events import EventType, ProcessingStage
from app.services import repository as repo
from app.services.asr import ASRProvider, ASRUnavailable, build_asr_provider
from app.services.audio import AudioPreprocessingService, RawAudio, SimulationAudioProvider
from app.services.diarization import DiarizationService, build_diarization_provider
from app.services.evidence import EvidenceLinkingService
from app.services.llm import (
    LLMAuthError,
    LLMError,
    LLMProvider,
    OutputValidator,
    get_fallback_provider,
    get_llm_provider,
)
from app.services.nlp import ClinicalNLPService
from app.services.note_engine import NoteStateEngine
from app.services.transcript_assembly import (
    SpeakerRoleAttributionService,
    TranscriptAssemblyService,
)
from app.services.types import AssembledSegment, AudioFrame
from app.websocket.manager import manager

logger = get_logger(__name__)

ENTITY_GROUP_BY_TYPE: dict[EntityType, str] = {
    EntityType.MEDICATION: "medications",
    EntityType.SYMPTOM: "symptoms",
    EntityType.FINDING: "findings",
    EntityType.INVESTIGATION: "investigations",
}


def _public_llm_message(provider: str, exc: LLMError) -> str:
    label = {"gemini": "Gemini", "local": "Local LLM", "ollama": "Ollama"}.get(provider, provider)
    err_str = str(exc).lower()
    if "blocked by your local network firewall" in err_str or "fortiguard" in err_str:
        return f"{label} was blocked by your local network firewall (FortiGuard AI filter). Connect to a mobile hotspot or VPN to use Gemini."
    if "ssl certificate verification failed" in err_str:
        return f"{label} SSL verification failed. Set GEMINI_VERIFY_SSL=false in .env if on an inspected network."
    if exc.code == "LLM_INVALID_OUTPUT":
        return (
            f"{label} replied, but the JSON was incomplete so it could not be used. "
            "A draft note was filled from the transcript instead."
        )
    if exc.code == "LLM_UNAVAILABLE":
        return f"{label} could not complete this request. A draft note was filled from the transcript instead."
    if exc.code == "LLM_RATE_LIMIT":
        return (
            f"{label} hit its free-tier quota. This draft was filled from the transcript on this PC; "
            "retry later when the quota resets."
        )
    return str(exc)[:240]


@dataclass
class SessionRuntime:
    session_id: str
    reference: str
    mode: SessionMode
    audio_source: AudioSource
    script_key: str | None = None

    asr: ASRProvider = field(default_factory=build_asr_provider)
    diarizer: DiarizationService = field(default_factory=build_diarization_provider)
    nlp: ClinicalNLPService = field(default_factory=ClinicalNLPService)
    assembler: TranscriptAssemblyService = field(default_factory=TranscriptAssemblyService)
    role_attribution: SpeakerRoleAttributionService = field(default_factory=SpeakerRoleAttributionService)
    evidence: EvidenceLinkingService = field(default_factory=EvidenceLinkingService)
    note_engine: NoteStateEngine = field(default_factory=NoteStateEngine)
    validator: OutputValidator = field(default_factory=OutputValidator)
    preprocessor: AudioPreprocessingService = field(default_factory=AudioPreprocessingService)
    simulator: SimulationAudioProvider = field(default_factory=SimulationAudioProvider)

    llm: LLMProvider = field(default_factory=get_llm_provider)

    timeline: float = 0.0
    chunk_sequence: int = 0
    segment_sequence: int = 0
    pending_segments: int = 0
    entity_sequence: int = 0
    last_ai_run: float = 0.0
    ai_degraded: bool = False
    last_ai_error: dict[str, Any] | None = None
    stage: ProcessingStage = ProcessingStage.IDLE
    utterances_by_speaker: dict[str, list[str]] = field(default_factory=dict)
    stopped: bool = False
    task: asyncio.Task | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    resume_event: asyncio.Event = field(default_factory=asyncio.Event)
    latencies: dict[str, list[float]] = field(default_factory=lambda: {"note": [], "extraction": []})

    def __post_init__(self) -> None:
        self.resume_event.set()

    @property
    def ai_status(self) -> dict[str, Any]:
        active = self.llm if not self.ai_degraded else get_fallback_provider()
        return {
            "provider": active.name,
            "model": active.model,
            "mock": active.is_mock,
            "degraded": self.ai_degraded,
            "configured": settings.gemini_configured,
            "last_error": self.last_ai_error,
        }


class SessionPipeline:
    """Owns the live runtimes and drives every processing stage."""

    def __init__(self) -> None:
        self._runtimes: dict[str, SessionRuntime] = {}

    # ---------------------------------------------------------------- lifecycle
    def runtime(self, session_id: str) -> SessionRuntime | None:
        return self._runtimes.get(str(session_id))

    def active_sessions(self) -> list[str]:
        return list(self._runtimes)

    async def ensure_runtime(self, session: SessionModel) -> SessionRuntime:
        key = str(session.id)
        runtime = self._runtimes.get(key)
        if runtime is None:
            from app.services.demo.conversations import get_script

            is_simulation = session.audio_source is AudioSource.SIMULATION
            script = get_script(session.scenario) if session.mode is SessionMode.DEMO else None
            runtime = SessionRuntime(
                session_id=key,
                reference=session.reference,
                mode=session.mode,
                audio_source=session.audio_source,
                script_key=script.key if script else None,
                # The script is only handed to the ASR provider for Demo Mode
                # audio; real recordings must go to a real speech engine.
                asr=build_asr_provider(
                    script=script if is_simulation else None,
                    audio_source=session.audio_source,
                ),
                diarizer=build_diarization_provider(audio_source=session.audio_source),
            )
            self._runtimes[key] = runtime
        return runtime

    async def start(self, db: AsyncSession, session: SessionModel) -> SessionRuntime:
        runtime = await self.ensure_runtime(session)
        runtime.stopped = False
        runtime.resume_event.set()
        session.status = SessionStatus.LIVE
        session.started_at = session.started_at or datetime.now(timezone.utc)
        session.last_error = None
        await repo.get_or_create_note(db, session)
        await db.commit()

        await manager.broadcast(
            runtime.session_id,
            EventType.SESSION_STARTED,
            {
                "session_id": runtime.session_id,
                "reference": session.reference,
                "mode": session.mode.value,
                "audio_source": session.audio_source.value,
                "started_at": session.started_at.isoformat(),
                "ai": runtime.ai_status,
                "providers": self.provider_status(runtime),
            },
        )
        await self._emit_stage(runtime, ProcessingStage.AUDIO_CAPTURE, "Audio capture active")

        if session.mode is SessionMode.DEMO and settings.enable_demo_mode:
            from app.services.demo.runner import DemoSimulationRunner

            runner = DemoSimulationRunner(self, runtime)
            runtime.task = asyncio.create_task(runner.run(), name=f"demo-{runtime.reference}")
        return runtime

    async def pause(self, db: AsyncSession, session: SessionModel) -> None:
        runtime = await self.ensure_runtime(session)
        runtime.resume_event.clear()
        session.status = SessionStatus.PAUSED
        await db.commit()
        await self._emit_session_status(runtime, session)
        await self._emit_stage(runtime, ProcessingStage.IDLE, "Session paused")

    async def resume(self, db: AsyncSession, session: SessionModel) -> None:
        runtime = await self.ensure_runtime(session)
        runtime.resume_event.set()
        session.status = SessionStatus.LIVE
        await db.commit()
        await self._emit_session_status(runtime, session)
        await self._emit_stage(runtime, ProcessingStage.AUDIO_CAPTURE, "Audio capture resumed")

    async def stop(self, db: AsyncSession, session: SessionModel) -> None:
        runtime = await self.ensure_runtime(session)
        runtime.stopped = True
        runtime.resume_event.set()
        if runtime.task and not runtime.task.done():
            runtime.task.cancel()
            try:
                await runtime.task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - task teardown
                pass

        session.status = SessionStatus.PROCESSING
        await db.commit()
        await self._emit_session_status(runtime, session)

        # Final structuring pass over the complete transcript.
        await self.run_ai_update(runtime, force=True, final=True)

        factory = get_session_factory()
        async with factory() as final_db:
            refreshed = await repo.get_session(final_db, runtime.session_id)
            if refreshed is not None:
                note = await repo.get_note(final_db, refreshed.id)
                refreshed.status = SessionStatus.REVIEW
                refreshed.ended_at = refreshed.ended_at or datetime.now(timezone.utc)
                await final_db.commit()
                await manager.broadcast(
                    runtime.session_id,
                    EventType.SESSION_COMPLETED,
                    {
                        "status": refreshed.status.value,
                        "note_status": note.status.value if note else None,
                        "duration_seconds": round(repo.session_duration(refreshed), 2),
                        "segments": await repo.segment_count(final_db, refreshed.id),
                    },
                )
        await self._emit_stage(runtime, ProcessingStage.IDLE, "Session ended - ready for review")

    def discard(self, session_id: str) -> None:
        self._runtimes.pop(str(session_id), None)

    # ------------------------------------------------------------------ ingest
    async def ingest_audio(
        self,
        runtime: SessionRuntime,
        raw: RawAudio,
        *,
        hints: dict[str, Any] | None = None,
    ) -> list[AssembledSegment]:
        """Run one audio buffer through the full pipeline."""
        session_id_var.set(runtime.session_id)
        async with runtime.lock:
            runtime.chunk_sequence += 1
            sequence = runtime.chunk_sequence
            start_time = runtime.timeline

        try:
            await self._emit_stage(runtime, ProcessingStage.AUDIO_PREPROCESSING, "Preprocessing audio")
            frame = runtime.preprocessor.process(
                raw,
                session_id=runtime.session_id,
                sequence=sequence,
                start_time=start_time,
                source=runtime.audio_source,
            )
        except Exception as exc:
            logger.exception("audio_preprocessing_failed", extra={"session_id": runtime.session_id})
            await self._emit_error(runtime, "AUDIO_PREPROCESSING_FAILED", str(exc), ProcessingStage.AUDIO_PREPROCESSING)
            return []

        frame.hints.update(hints or {})
        runtime.timeline = max(runtime.timeline, frame.end_time)

        factory = get_session_factory()
        async with factory() as db:
            session = await repo.get_session(db, runtime.session_id)
            if session is None:
                return []
            chunk = AudioChunk(
                session_id=session.id,
                sequence=sequence,
                source=frame.source,
                start_time=frame.start_time,
                end_time=frame.end_time,
                sample_rate=frame.sample_rate,
                channels=frame.channels,
                size_bytes=len(frame.pcm),
                speech_ratio=frame.speech_ratio,
                rms_dbfs=frame.rms_dbfs,
                status="PROCESSED" if frame.decoded else "FORWARDED_UNDECODED",
            )
            db.add(chunk)
            await db.commit()
            chunk_id = chunk.id
            chunk_payload = repo.serialize_chunk(chunk)

        await manager.broadcast(
            runtime.session_id,
            EventType.AUDIO_STATUS,
            {
                "chunk": chunk_payload.model_dump(mode="json"),
                "timeline_seconds": round(runtime.timeline, 2),
                "voice_activity": frame.speech_ratio > 0.05,
                "decoded": frame.decoded,
            },
        )

        # ASR runs before diarization: providers that transcribe and attribute
        # speakers in one pass (Gemini) publish their turns onto the frame for
        # the diarization stage to consume.
        asr_segments = await self._transcribe(runtime, frame)
        if not asr_segments:
            return []

        # Publish ASR segments as hints for text-based diarization providers
        frame.hints['asr_segments'] = [
            {'text': seg.text, 'start_time': seg.start_time, 'end_time': seg.end_time, 'confidence': seg.confidence}
            for seg in asr_segments
        ]

        turns = await self._diarize(runtime, frame)

        return await self._assemble_and_store(runtime, frame, asr_segments, turns, chunk_id)

    async def _diarize(self, runtime: SessionRuntime, frame: AudioFrame) -> list:
        await self._emit_stage(runtime, ProcessingStage.DIARIZATION, "Detecting speakers")
        try:
            return await runtime.diarizer.diarize(frame)
        except Exception as exc:
            logger.exception("diarization_failed", extra={"session_id": runtime.session_id})
            await self._emit_error(
                runtime, "DIARIZATION_FAILED", str(exc), ProcessingStage.DIARIZATION, recoverable=True
            )
            return []  # speaker becomes UNKNOWN downstream

    async def _transcribe(self, runtime: SessionRuntime, frame: AudioFrame) -> list:
        """Transcribe one frame.

        A failure here produces no transcript at all - deliberately. Falling back
        to any other source of text would put words a clinician never said into a
        clinical record, so the error is surfaced instead.
        """
        await self._emit_stage(runtime, ProcessingStage.ASR, "Transcribing audio")
        try:
            return await runtime.asr.transcribe(frame)
        except ASRUnavailable as exc:
            logger.error("asr_unavailable", extra={"session_id": runtime.session_id, "error": str(exc)})
            await self._emit_error(
                runtime, "ASR_UNAVAILABLE", str(exc), ProcessingStage.ASR, recoverable=False
            )
            raise
        except Exception as exc:
            logger.exception("asr_failed", extra={"session_id": runtime.session_id})
            await self._emit_error(
                runtime,
                "ASR_FAILED",
                f"Transcription failed, so no transcript was produced for this audio: {exc}",
                ProcessingStage.ASR,
                recoverable=True,
            )
            raise

    async def _assemble_and_store(
        self,
        runtime: SessionRuntime,
        frame: AudioFrame,
        asr_segments: list,
        turns: list,
        chunk_id: uuid.UUID,
    ) -> list[AssembledSegment]:
        await self._emit_stage(runtime, ProcessingStage.TRANSCRIPT_ASSEMBLY, "Assembling transcript")
        factory = get_session_factory()
        async with factory() as db:
            session = await repo.get_session(db, runtime.session_id)
            if session is None:
                return []

            roles = await repo.speaker_roles(db, session.id)
            assembled = runtime.assembler.assemble(
                asr_segments,
                turns,
                roles=roles,
                start_index=runtime.segment_sequence,
                audio_sequence=frame.sequence,
                session_id=runtime.session_id,
            )
            if not assembled:
                return []

            # Fallback: if audio diarization detected only 1 speaker,
            # use Gemini text analysis to split by conversational role.
            unique_speakers = {seg.speaker_label for seg in assembled}
            if len(unique_speakers) <= 1 and len(assembled) >= 2 and settings.gemini_configured:
                await self._emit_stage(
                    runtime, ProcessingStage.ROLE_ATTRIBUTION, "Splitting speakers by conversation",
                )
                from app.services.diarization.text_splitter import GeminiTextSplitter  # noqa: PLC0415
                splitter = GeminiTextSplitter()
                splits = await splitter.split([
                    {"ref": seg.ref, "text": seg.text} for seg in assembled
                ])
                if splits:
                    for seg in assembled:
                        role = splits.get(seg.ref)
                        if role == "doctor":
                            seg.speaker_label = "speaker_0"
                        elif role == "patient":
                            seg.speaker_label = "speaker_1"

            stored: list[TranscriptSegment] = []
            speaker_updates: list[dict[str, Any]] = []

            for segment in assembled:
                label = segment.speaker_label or "unknown"
                speaker = await repo.get_or_create_speaker(
                    db, session.id, label, confidence=segment.diarization_confidence
                )

                # Utterance-level conversational role check (Doctor vs Patient)
                utt_role, utt_conf = runtime.role_attribution.score_utterance(segment.text)
                if (label in ("speaker_0", "unknown") or speaker.role_source != "HUMAN") and utt_role is not SpeakerRole.UNKNOWN and utt_conf >= 0.65:
                    target_label = "speaker_0" if utt_role is SpeakerRole.DOCTOR else ("speaker_1" if utt_role is SpeakerRole.PATIENT else label)
                    if target_label != label:
                        label = target_label
                        segment.speaker_label = label
                        speaker = await repo.get_or_create_speaker(
                            db, session.id, label, confidence=utt_conf
                        )
                        if speaker.role_source != "HUMAN":
                            speaker.role = utt_role
                            speaker.confidence = utt_conf
                            speaker_updates.append(
                                {"id": str(speaker.id), "label": label, "role": utt_role.value, "confidence": utt_conf}
                            )

                runtime.utterances_by_speaker.setdefault(label, []).append(segment.text)

                if speaker.role_source != "HUMAN":
                    await self._emit_stage(
                        runtime, ProcessingStage.ROLE_ATTRIBUTION, f"Attributing role for {label}"
                    )
                    role, confidence = runtime.role_attribution.score(runtime.utterances_by_speaker[label])
                    if role is not SpeakerRole.UNKNOWN and (
                        speaker.role is SpeakerRole.UNKNOWN or confidence >= speaker.confidence
                    ):
                        speaker.role = role
                        speaker.confidence = confidence
                        speaker_updates.append(
                            {"id": str(speaker.id), "label": label, "role": role.value, "confidence": confidence}
                        )
                segment.role = speaker.role

                runtime.segment_sequence += 1
                record = TranscriptSegment(
                    session_id=session.id,
                    speaker_id=speaker.id,
                    # Assigned as an object as well as an id so serialisation
                    # after commit never triggers a lazy load from sync context.
                    speaker=speaker,
                    audio_chunk_id=chunk_id,
                    ref=segment.ref,
                    sequence=runtime.segment_sequence,
                    text=segment.text,
                    start_time=segment.start_time,
                    end_time=segment.end_time,
                    confidence=segment.confidence,
                    asr_confidence=segment.asr_confidence,
                    diarization_confidence=segment.diarization_confidence,
                    overlapping=segment.overlapping,
                )
                db.add(record)
                stored.append(record)

            await db.commit()
            payloads = [repo.serialize_segment(record).model_dump(mode="json") for record in stored]
            speakers = [repo.serialize_speaker(s).model_dump(mode="json") for s in await repo.list_speakers(db, session.id)]

        runtime.pending_segments += len(assembled)
        metrics.increment("transcript_segments_total", value=len(assembled))

        await manager.broadcast(runtime.session_id, EventType.TRANSCRIPT_UPDATE, {"segments": payloads})
        if speaker_updates or turns:
            await manager.broadcast(
                runtime.session_id,
                EventType.DIARIZATION_UPDATE,
                {
                    "speakers": speakers,
                    "turns": [
                        {
                            "speaker_id": turn.speaker_id,
                            "start_time": turn.start_time,
                            "end_time": turn.end_time,
                            "confidence": turn.confidence,
                        }
                        for turn in turns
                    ],
                    "role_updates": speaker_updates,
                },
            )

        ai_ran = await self.maybe_run_ai_update(runtime)
        if not ai_ran:
            await self._emit_stage(
                runtime,
                ProcessingStage.AUDIO_CAPTURE if not runtime.stopped else ProcessingStage.IDLE,
                "Ready",
            )
        return assembled

    # ------------------------------------------------------------------- the AI
    async def maybe_run_ai_update(self, runtime: SessionRuntime) -> bool:
        """Batching gate: never one call per word."""
        elapsed = time.monotonic() - runtime.last_ai_run
        enough_segments = runtime.pending_segments >= max(1, settings.gemini_min_segments_per_update)
        interval_passed = elapsed >= settings.gemini_update_interval_seconds and runtime.pending_segments > 0
        if not (enough_segments or interval_passed):
            return False
        return await self.run_ai_update(runtime)

    async def run_ai_update(
        self, runtime: SessionRuntime, *, force: bool = False, final: bool = False
    ) -> bool:
        async with runtime.lock:
            if runtime.pending_segments == 0 and not force:
                return False
            runtime.pending_segments = 0
            runtime.last_ai_run = time.monotonic()

        factory = get_session_factory()
        async with factory() as db:
            session = await repo.get_session(db, runtime.session_id)
            if session is None:
                return False
            segments = await repo.list_segments(db, session.id)
            if not segments:
                return False

            index = runtime.evidence.build_index(repo.segment_index(segments))
            prompt_segments = repo.segments_as_prompt_dicts(segments)
            existing_entities = await repo.list_entities(db, session.id)
            speakers = await repo.list_speakers(db, session.id)
            note = await repo.get_or_create_note(db, session)
            note_id = note.id
            note_version = note.version
            note_status = note.status
            current_content = repo.note_content(note)
            session_context = {
                "reference": session.reference,
                "simulation_type": session.simulation_type.value,
                "scenario": session.scenario,
                "patient_id": session.patient_id,
                "speakers": [
                    {"label": speaker.label, "role": speaker.role.value, "confidence": speaker.confidence}
                    for speaker in speakers
                ],
                "elapsed_seconds": round(repo.session_duration(session), 1),
            }
            await db.commit()

        assembled = [
            AssembledSegment(
                ref=item["ref"],
                speaker_label=item["speaker_label"],
                role=SpeakerRole(item["role"]),
                text=item["text"],
                start_time=item["start_time"],
                end_time=item["end_time"],
                confidence=item["confidence"],
                asr_confidence=item["confidence"],
                diarization_confidence=item["confidence"],
            )
            for item in prompt_segments
        ]

        await self._emit_stage(runtime, ProcessingStage.CLINICAL_NLP, "Extracting clinical information")
        rule_candidates = runtime.nlp.extract(assembled)
        rule_hints = [
            {
                "entity_type": candidate.entity_type.value,
                "value": candidate.value,
                "status": candidate.status.value,
                "source_segment_ids": candidate.source_segment_refs,
            }
            for candidate in rule_candidates
        ]
        rule_statuses = {
            (candidate.normalized_value or candidate.value).lower(): candidate.status
            for candidate in rule_candidates
        }

        existing_payload = [
            {
                "entity_type": entity.entity_type.value,
                "value": entity.value,
                "status": entity.status.value,
                "source_segment_ids": list(entity.source_segment_refs or []),
            }
            for entity in existing_entities
        ]

        await self._emit_stage(runtime, ProcessingStage.LLM_STRUCTURING, "Clinical structuring")
        provider, extraction = await self._call_provider(
            runtime,
            "extraction",
            lambda active: active.extract_entities(
                session_context=session_context,
                segments=prompt_segments,
                rule_based_candidates=rule_hints,
                existing_entities=existing_payload,
            ),
        )
        if extraction is None:
            await self._flag_review(runtime, "Clinical extraction unavailable")
            await self._emit_stage(
                runtime,
                ProcessingStage.AUDIO_CAPTURE if not runtime.stopped else ProcessingStage.IDLE,
                "Ready",
            )
            return False
        runtime.latencies["extraction"].append(extraction.stats.duration_ms)

        validated_entities = runtime.validator.validate_entities(
            extraction.result.entities,
            valid_segment_refs=set(index),
            segment_texts=runtime.evidence.segment_texts(),
            rule_statuses=rule_statuses,
        )

        entity_records = await self._persist_entities(
            runtime, validated_entities.entities, provider_model=provider.model
        )

        note_provider, note_response = await self._call_provider(
            runtime,
            "note",
            lambda active: active.generate_note(
                session_context=session_context,
                segments=prompt_segments,
                entities=[
                    {
                        "entity_type": entity.entity_type.value,
                        "value": entity.value,
                        "normalized_value": entity.normalized_value,
                        "status": entity.status.value,
                        "confidence": entity.confidence,
                        "source_segment_refs": entity.source_segment_refs,
                        "detail": entity.detail,
                    }
                    for entity in entity_records
                ],
                current_note=current_content.model_dump(mode="json"),
            ),
        )
        if note_response is None:
            await self._flag_review(runtime, "Note generation unavailable")
            await self._emit_stage(
                runtime,
                ProcessingStage.AUDIO_CAPTURE if not runtime.stopped else ProcessingStage.IDLE,
                "Ready",
            )
            return False
        runtime.latencies["note"].append(note_response.stats.duration_ms)

        validated_note = runtime.validator.validate_note(
            note_response.result, valid_segment_refs=set(index)
        )

        await self._emit_stage(runtime, ProcessingStage.EVIDENCE_LINKING, "Linking evidence")
        grouped = self._group_entities(entity_records)
        outcome = runtime.note_engine.apply_ai_update(
            current=current_content,
            validated=validated_note,
            entities=grouped,
            evidence=runtime.evidence,
            current_status=note_status,
            version=note_version,
            model=note_provider.model,
        )

        await self._emit_stage(runtime, ProcessingStage.NOTE_STATE, "Updating clinical note")
        await self._persist_note(runtime, note_id, outcome, note_provider, final=final)
        await self._emit_stage(
            runtime,
            ProcessingStage.AUDIO_CAPTURE if not runtime.stopped else ProcessingStage.IDLE,
            "Ready",
        )
        return True

    async def _call_provider(self, runtime: SessionRuntime, purpose: str, call) -> tuple[LLMProvider, Any]:
        """Gemini first; rule-based mock if Gemini is unavailable."""
        provider = runtime.llm if not runtime.ai_degraded else get_fallback_provider()
        try:
            result = await call(provider)
            if not runtime.ai_degraded:
                runtime.last_ai_error = None
            return provider, result
        except LLMError as exc:
            runtime.last_ai_error = {"code": exc.code, "message": str(exc)[:300], "purpose": purpose}
            runtime.ai_degraded = True
            metrics.increment("ai_degraded_total", code=exc.code)
            logger.warning(
                "llm_call_degraded",
                extra={"session_id": runtime.session_id, "purpose": purpose, "code": exc.code},
            )
            await self._emit_error(
                runtime,
                exc.code,
                _public_llm_message(provider.name, exc),
                ProcessingStage.LLM_STRUCTURING,
                recoverable=not isinstance(exc, LLMAuthError),
            )
            fallback = get_fallback_provider()
            try:
                return fallback, await call(fallback)
            except Exception as inner:  # pragma: no cover - deterministic provider is offline-safe
                logger.exception("fallback_provider_failed", extra={"session_id": runtime.session_id})
                runtime.last_ai_error = {"code": "FALLBACK_FAILED", "message": str(inner)[:300]}
                return fallback, None
        except Exception as exc:
            logger.exception("llm_call_failed", extra={"session_id": runtime.session_id, "purpose": purpose})
            runtime.last_ai_error = {"code": "LLM_UNEXPECTED", "message": str(exc)[:300]}
            await self._emit_error(
                runtime,
                "LLM_UNEXPECTED",
                f"{provider.name} failed before a usable note could be written. A draft was filled from the transcript instead.",
                ProcessingStage.LLM_STRUCTURING,
            )
            fallback = get_fallback_provider()
            try:
                return fallback, await call(fallback)
            except Exception as inner:  # pragma: no cover
                logger.exception("fallback_provider_failed", extra={"session_id": runtime.session_id})
                runtime.last_ai_error = {"code": "FALLBACK_FAILED", "message": str(inner)[:300]}
                return fallback, None

    async def _persist_entities(
        self, runtime: SessionRuntime, entities: list, *, provider_model: str
    ) -> list[ClinicalEntityOut]:
        factory = get_session_factory()
        async with factory() as db:
            session = await repo.get_session(db, runtime.session_id)
            if session is None:
                return []
            existing = {
                (entity.entity_type, (entity.normalized_value or entity.value).lower()): entity
                for entity in await repo.list_entities(db, session.id)
            }
            runtime.entity_sequence = max(runtime.entity_sequence, len(existing))
            touched: list[ClinicalEntity] = []
            evidence_rows: list[tuple[str, str, list[str]]] = []

            for extracted in entities:
                normalization = runtime.nlp.terminology.normalize(extracted.value, extracted.entity_type)
                normalized = (normalization.normalized_value or extracted.value).lower()
                key = (extracted.entity_type, normalized)
                record = existing.get(key)
                if record is None:
                    runtime.entity_sequence += 1
                    record = ClinicalEntity(
                        session_id=session.id,
                        ref=f"ent_{runtime.entity_sequence:03d}",
                        entity_type=extracted.entity_type,
                        value=extracted.value,
                        normalized_value=normalization.normalized_value,
                        normalized_code=normalization.normalized_code,
                        terminology_system=normalization.system,
                        status=extracted.status,
                        confidence=extracted.confidence,
                        source_segment_refs=list(extracted.source_segment_ids),
                        detail=extracted.detail,
                        extraction_model=provider_model,
                    )
                    db.add(record)
                    existing[key] = record
                else:
                    record.status = extracted.status
                    record.confidence = max(record.confidence, extracted.confidence)
                    record.source_segment_refs = repo.dedupe(
                        list(record.source_segment_refs or []) + list(extracted.source_segment_ids)
                    )
                    record.detail = extracted.detail or record.detail
                    record.extraction_model = provider_model

                statement = self._entity_statement(record)
                unresolved = [
                    ref for ref in record.source_segment_refs if ref not in runtime.evidence.valid_refs
                ]
                record.review_required = bool(unresolved) or not record.source_segment_refs
                record.review_reason = (
                    "Evidence references could not be resolved" if record.review_required else None
                )
                touched.append(record)
                evidence_rows.append((record.ref, statement, list(record.source_segment_refs or [])))

            await db.flush()

            # Rebuild entity evidence so it always matches the current refs.
            refs = [row[0] for row in evidence_rows]
            if refs:
                for link in await repo.list_evidence(db, session.id):
                    if link.target_kind == "ENTITY" and link.target_key in refs:
                        await db.delete(link)
                await db.flush()

            for entity_ref, statement, segment_refs in evidence_rows:
                linked = runtime.evidence.link(
                    target_kind="ENTITY", target_key=entity_ref, clinical_statement=statement, refs=segment_refs
                )
                for reference in linked.evidence:
                    db.add(
                        EvidenceLink(
                            session_id=session.id,
                            transcript_segment_id=(
                                repo.as_uuid(runtime.evidence.segment_id_for(reference.transcript_segment_ref))
                                if runtime.evidence.segment_id_for(reference.transcript_segment_ref)
                                else None
                            ),
                            clinical_entity_id=next(
                                (record.id for record in touched if record.ref == entity_ref), None
                            ),
                            target_kind="ENTITY",
                            target_key=entity_ref,
                            clinical_statement=statement,
                            segment_ref=reference.transcript_segment_ref,
                            speaker_label=reference.speaker_label,
                            speaker_role=reference.speaker_role,
                            source_text=reference.source_text,
                            timestamp=reference.timestamp,
                            confidence=reference.confidence,
                            validated=reference.validated,
                            validation_error=reference.validation_error,
                        )
                    )
            await db.commit()

            all_entities = await repo.list_entities(db, session.id)
            evidence_map = await repo.entity_evidence_map(db, session.id)
            payload = [repo.serialize_entity(entity, evidence_map) for entity in all_entities]

        metrics.increment("clinical_entities_total", value=len(entities))
        await manager.broadcast(
            runtime.session_id,
            EventType.ENTITY_UPDATE,
            {
                "entities": [entity.model_dump(mode="json") for entity in payload],
                "counts": self._entity_counts(payload),
            },
        )
        return payload

    async def _persist_note(
        self,
        runtime: SessionRuntime,
        note_id: uuid.UUID,
        outcome,
        provider: LLMProvider,
        *,
        final: bool = False,
    ) -> None:
        factory = get_session_factory()
        async with factory() as db:
            note = await repo.get_note_by_id(db, note_id)
            if note is None:
                return
            note.content = outcome.content.model_dump(mode="json")
            note.status = outcome.status
            note.version = outcome.version
            note.review_flags = outcome.review_flags
            note.model = provider.model

            version_row: NoteVersion | None = None
            if outcome.changed_sections or final:
                version_row = NoteVersion(
                    note_id=note.id,
                    session_id=note.session_id,
                    version=outcome.version,
                    status=outcome.status,
                    content=note.content,
                    change_summary=outcome.change_summary,
                    changed_sections=outcome.changed_sections,
                    author_type="AI",
                    author=provider.name,
                    model=provider.model,
                )
                db.add(version_row)
                await db.flush()

                for statement in outcome.linked_statements:
                    for reference in statement.evidence:
                        segment_id = runtime.evidence.segment_id_for(reference.transcript_segment_ref)
                        db.add(
                            EvidenceLink(
                                session_id=note.session_id,
                                transcript_segment_id=repo.as_uuid(segment_id) if segment_id else None,
                                note_version_id=version_row.id,
                                target_kind="SECTION",
                                target_key=statement.target_key,
                                clinical_statement=statement.clinical_statement,
                                segment_ref=reference.transcript_segment_ref,
                                speaker_label=reference.speaker_label,
                                speaker_role=reference.speaker_role,
                                source_text=reference.source_text,
                                timestamp=reference.timestamp,
                                confidence=reference.confidence,
                                validated=reference.validated,
                                validation_error=reference.validation_error,
                            )
                        )
            await db.commit()

            note_payload = repo.serialize_note(note).model_dump(mode="json")
            evidence_payload = [
                repo.serialize_evidence(link).model_dump(mode="json")
                for link in await repo.list_evidence(db, note.session_id)
            ]

        metrics.increment("note_updates_total")
        await manager.broadcast(
            runtime.session_id,
            EventType.NOTE_UPDATE,
            {
                "note": note_payload,
                "changed_sections": outcome.changed_sections,
                "change_summary": outcome.change_summary,
                "review_flags": outcome.review_flags,
                "ai": runtime.ai_status,
            },
        )
        await manager.broadcast(
            runtime.session_id, EventType.EVIDENCE_UPDATE, {"evidence": evidence_payload}
        )

    # ------------------------------------------------------------------ helpers
    @staticmethod
    def _entity_statement(entity: ClinicalEntity) -> str:
        label = entity.entity_type.value.replace("_", " ").lower()
        if entity.status is EntityStatus.NEGATED:
            return f"Explicitly denied {label}: {entity.value}"
        if entity.status is EntityStatus.UNCERTAIN:
            return f"Uncertain {label}: {entity.value}"
        if entity.status is EntityStatus.HISTORICAL:
            return f"Historical {label}: {entity.value}"
        return f"Documented {label}: {entity.value}"

    @staticmethod
    def _group_entities(entities: list[ClinicalEntityOut]) -> dict[str, list[ClinicalEntityOut]]:
        grouped: dict[str, list[ClinicalEntityOut]] = {key: [] for key in ENTITY_KEYS}
        for entity in entities:
            group = ENTITY_GROUP_BY_TYPE.get(entity.entity_type)
            if group:
                grouped[group].append(entity)
        return grouped

    @staticmethod
    def _entity_counts(entities: list[ClinicalEntityOut]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for entity in entities:
            counts[entity.entity_type.value] = counts.get(entity.entity_type.value, 0) + 1
        counts["TOTAL"] = len(entities)
        counts["REVIEW_REQUIRED"] = sum(1 for entity in entities if entity.review_required)
        return counts

    def provider_status(self, runtime: SessionRuntime) -> dict[str, Any]:
        return {
            "asr": runtime.asr.describe(),
            "diarization": runtime.diarizer.describe(),
            "terminology": runtime.nlp.terminology.describe(),
            "llm": runtime.llm.describe(),
        }

    async def _emit_stage(self, runtime: SessionRuntime, stage: ProcessingStage, detail: str) -> None:
        runtime.stage = stage
        await manager.broadcast(
            runtime.session_id,
            EventType.PROCESSING_STATUS,
            {"stage": stage.value, "detail": detail, "ai": runtime.ai_status},
        )

    async def _emit_error(
        self,
        runtime: SessionRuntime,
        code: str,
        message: str,
        stage: ProcessingStage,
        *,
        recoverable: bool = True,
    ) -> None:
        await manager.broadcast(
            runtime.session_id,
            EventType.PROCESSING_ERROR,
            {
                "code": code,
                "message": message,
                "stage": stage.value,
                "recoverable": recoverable,
                "ai": runtime.ai_status,
            },
        )

    async def _emit_session_status(self, runtime: SessionRuntime, session: SessionModel) -> None:
        await manager.broadcast(
            runtime.session_id,
            EventType.SESSION_STATUS,
            {
                "status": session.status.value,
                "duration_seconds": round(repo.session_duration(session), 2),
                "ai": runtime.ai_status,
            },
        )

    async def _flag_review(self, runtime: SessionRuntime, reason: str) -> None:
        factory = get_session_factory()
        async with factory() as db:
            session = await repo.get_session(db, runtime.session_id)
            if session is None:
                return
            note = await repo.get_or_create_note(db, session)
            flags = list(note.review_flags or [])
            flags.append({"section": "note", "label": "Note", "reason": reason, "severity": "ERROR"})
            note.review_flags = flags
            if note.status in (NoteStatus.PROCESSING, NoteStatus.DRAFT):
                note.status = NoteStatus.REVIEW_REQUIRED
            session.last_error = reason
            await db.commit()
            payload = repo.serialize_note(note).model_dump(mode="json")
        await manager.broadcast(
            runtime.session_id,
            EventType.NOTE_UPDATE,
            {"note": payload, "changed_sections": [], "change_summary": reason, "ai": runtime.ai_status},
        )

    # ----------------------------------------------------------------- snapshot
    async def snapshot(self, db: AsyncSession, session: SessionModel) -> dict[str, Any]:
        """Full session state, used for WebSocket resynchronisation."""
        runtime = self.runtime(str(session.id))
        segments = await repo.list_segments(db, session.id)
        entities = await repo.list_entities(db, session.id)
        evidence_map = await repo.entity_evidence_map(db, session.id)
        note = await repo.get_note(db, session.id)
        evidence = await repo.list_evidence(db, session.id)
        return {
            "session": (await repo.serialize_session(db, session)).model_dump(mode="json"),
            "segments": [repo.serialize_segment(segment).model_dump(mode="json") for segment in segments],
            "speakers": [
                repo.serialize_speaker(speaker).model_dump(mode="json")
                for speaker in await repo.list_speakers(db, session.id)
            ],
            "entities": [
                repo.serialize_entity(entity, evidence_map).model_dump(mode="json") for entity in entities
            ],
            "note": repo.serialize_note(note).model_dump(mode="json") if note else None,
            "evidence": [repo.serialize_evidence(link).model_dump(mode="json") for link in evidence],
            "ai": runtime.ai_status
            if runtime
            else {
                "provider": get_llm_provider().name,
                "model": get_llm_provider().model,
                "mock": get_llm_provider().is_mock,
                "degraded": False,
                "configured": settings.gemini_configured,
            },
            "stage": runtime.stage.value if runtime else ProcessingStage.IDLE.value,
            "providers": self.provider_status(runtime) if runtime else None,
        }


pipeline = SessionPipeline()
