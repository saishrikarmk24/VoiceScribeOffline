# MedScribe Live — Architecture

This document describes how MedScribe Live is built, why each boundary exists, and where real models plug in.

---

## 1. Design principles

1. **Evidence first.** No clinical statement exists without a link to the transcript that produced it. Unlinked statements are flagged, never silently displayed as fact.
2. **The model is not the product.** Every AI capability sits behind an interface (`LLMProvider`, `ASRProvider`, `DiarizationService`, `TerminologyProvider`). Swapping Gemini for another model, or the mock ASR for Faster-Whisper, does not touch business logic.
3. **No subsystem may end a session.** Each pipeline stage degrades independently and reports status. If Gemini fails, the transcript keeps flowing and the note is flagged for review.
4. **Humans own approval.** The note state machine has no transition from an AI update to `APPROVED`.
5. **Deterministic where it matters.** Demo Mode, negation detection and evidence validation are rule-based and reproducible, so a demonstration behaves the same every time.

---

## 2. Repository layout

```
frontend/   React + TypeScript workstation UI
backend/    FastAPI application, pipeline services, migrations, tests
scripts/    test_gemini.py — standalone Gemini verification
docs/       ARCHITECTURE.md, API.md
```

The frontend never holds credentials and never calls an AI provider. It is a pure consumer of the backend's REST + WebSocket surface.

---

## 3. Request and data flow

```
Browser ──REST──▶ FastAPI routes ──▶ SessionPipeline ──▶ providers (ASR/diarization/NLP/LLM)
   ▲                                       │
   └────────────WebSocket◀─── SessionConnectionManager ◀──┘
```

- **REST** is used for commands and reads: create/start/pause/resume/stop, fetch transcript/entities/note/evidence, edit and approve the note, export.
- **WebSocket** (`/ws/sessions/{session_id}`) is used for live push: transcript, entity, note, evidence, stage and error events.
- The pipeline writes to PostgreSQL and broadcasts in the same step, so a reconnecting client can always rebuild state from either source.

---

## 4. Pipeline stages

### 4.1 Audio capture (`services/audio/base.py`)

Three providers behind one interface:

| Provider | Source |
| --- | --- |
| `BrowserMicrophoneProvider` | Web Audio capture, posted as base64 WAV chunks |
| `UploadedAudioProvider` | multipart file upload |
| `SimulationAudioProvider` | synthesises speech-like audio from a script (Demo Mode) |

The browser hook (`useMicrophoneCapture`) captures at 16 kHz mono, encodes PCM16 WAV in-page and posts ~2-second chunks. WAV is chosen deliberately: the backend decodes it with the standard library and needs no ffmpeg.

### 4.2 Preprocessing (`services/audio/preprocessing.py`)

`decode → mono → resample to 16 kHz → high-pass → noise suppression → echo-cancellation hook → VAD → framing`

Implemented with the standard library only (`audioop` was removed in Python 3.13, and pulling numpy/librosa in would make Demo Mode heavy). Demo buffers are small enough that pure Python is fast enough, and the class is a drop-in seam for a vectorised implementation. Echo cancellation is an explicit documented pass-through — browser capture provides no far-end reference signal, so faking a filter would be dishonest.

Output is an `AudioFrame`: canonical PCM16 samples plus speech ratio, RMS dBFS and a timeline window.

### 4.3 Diarization (`services/diarization/`)

`MockDiarizationProvider` assigns speaker clusters from script hints when present, otherwise from a zero-crossing pitch estimate. `PyannoteDiarizationProvider` lazily imports `pyannote.audio` and fails with a clear message if the model or Hugging Face token is missing. Output is a list of `DiarizationTurn(speaker_id, start_time, end_time, confidence)`.

If diarization fails, speakers become `UNKNOWN` rather than the stage aborting.

### 4.4 ASR (`services/asr/`)

`MockASRProvider` is driven by the active `SimulationScript`: on voice activity it emits the next scripted utterance with per-word timing derived from the frame window. `FasterWhisperProvider` lazily loads `faster_whisper`, converts the frame to WAV and maps segments back into `ASRSegment(id, text, start_time, end_time, confidence)`.

### 4.5 Transcript assembly (`services/transcript_assembly.py`)

Merges ASR segments with diarization turns by maximum temporal overlap, then:

- merges consecutive fragments from the same speaker
- flags overlapping speech and reduces its confidence
- sorts chronologically and aggregates ASR + diarization confidence
- assigns a stable `ref` (`seg_001`, `seg_002`, …) used by every downstream layer

`SpeakerRoleAttributionService` scores clinician / patient / nurse language markers to propose a role. A human override always wins and is recorded with `role_source = HUMAN`, which triggers a re-structuring pass.

### 4.6 Clinical NLP (`services/nlp/`)

Runs **before** the LLM and produces grounded candidates:

- lexicon and pattern extraction for symptoms, medications, allergies, investigations, durations, severity, frequency, character, plans and follow-up
- `NegationDetector`: NegEx-style pre/post triggers with scope windowing and termination, distinguishing `NEGATED`, `UNCERTAIN` and `HISTORICAL` from `PRESENT`, and rejecting pseudo-negation
- diagnoses are only extracted from **declarative clinician assertions** — a question ("do you have hypertension?") is not an assertion, and `_is_plausible_diagnosis` rejects non-diagnosis phrases
- `TerminologyService` normalises surface forms and names the preferred coding system, but leaves `normalized_code = null`; codes are never fabricated

### 4.7 LLM structuring (`services/llm/`)

| File | Responsibility |
| --- | --- |
| `base.py` | `LLMProvider` interface and the error hierarchy (`LLMAuthError`, `LLMRateLimited`, `LLMTimeout`, `LLMUnavailable`, `LLMInvalidOutput`, `LLMSafetyBlocked`, `LLMNotConfigured`) |
| `prompts.py` | system instruction + extraction/note prompt builders |
| `schemas.py` | flat Pydantic schemas used as the response schema |
| `gemini_provider.py` | `google-genai` client, schema-constrained generation, retries, error mapping |
| `mock_provider.py` | `DeterministicLLMProvider` — a real rule-based fallback, not a stub |
| `validator.py` | JSON → Pydantic → evidence → business validation |

**Prompt input** is deliberately narrow: session context, speaker-attributed transcript segments with refs, rule-based entity candidates, and the current note state. No unrelated frontend data is sent.

**Structured output**: Gemini is configured with `response_mime_type=application/json` and a response schema, so the model returns schema-shaped JSON rather than prose that must be parsed heuristically.

**Batching** avoids one API call per word:

```
transcript segments → collect ≥ GEMINI_MIN_SEGMENTS_PER_UPDATE
                     or GEMINI_UPDATE_INTERVAL_SECONDS elapsed
                     → one structuring call → note update
```

**Retries** are bounded (`GEMINI_MAX_RETRIES`) with exponential backoff and jitter. Authentication failures are never retried. When retries are exhausted the pipeline falls back to the deterministic provider, marks the note `REVIEW_REQUIRED`, emits `PROCESSING_ERROR`, and offers a manual retry.

### 4.8 Validation (`services/llm/validator.py`)

```
Gemini output → JSON parse → Pydantic schema → evidence grounding → business rules → database
```

Rejected or flagged:

- entities citing transcript refs that do not exist
- entity values not actually present in the cited segments
- confidence outside `0..1`
- an LLM `PRESENT` status where the rule engine detected negation (rule engine wins)
- note sections with content but no evidence
- advisory or prescriptive language ("I recommend", "you should take") — MedScribe documents, it does not advise

### 4.9 Evidence linking (`services/evidence/linking.py`)

Builds an index of transcript segments by `ref` and expands each citation into a full `EvidenceReference` (segment ref, speaker label, role, timestamp, confidence, source text, validated flag, validation error). A statement with no valid evidence returns `requires_review` with a reason, which the note engine turns into a review flag.

### 4.10 Note state engine (`services/note_engine/engine.py`)

```
PROCESSING ──▶ DRAFT ──▶ REVIEW_REQUIRED ──▶ APPROVED ──▶ EXPORTED
                 ▲              │                │
                 └──── human edit / reopen ◀──────┘
```

Responsibilities:

- **Incremental updates.** Only sections the AI actually changed are rewritten.
- **Conflict handling.** A section edited by a human is never overwritten by a later AI pass; `edited_by_human` is sticky.
- **Versioning.** Every AI pass and human edit creates a `NoteVersion` with a change summary, changed sections and author type.
- **Review flags.** Missing evidence, validation failures and AI degradation all surface as named flags.
- **Approval gating.** `approve()` requires an explicit acknowledgement, an approver, and zero blocking flags. There is no path from an AI update to `APPROVED`.

### 4.11 Real-time layer (`websocket/manager.py`)

`SessionConnectionManager` keeps per-session connection sets, a monotonic sequence counter and a bounded event history. A reconnecting client sends `{"type": "SYNC", "last_sequence": n}` and receives either the missed events or a full `STATE_SNAPSHOT`. Event types: `SESSION_STARTED`, `SESSION_STATUS`, `AUDIO_STATUS`, `DIARIZATION_UPDATE`, `TRANSCRIPT_UPDATE`, `ENTITY_UPDATE`, `NOTE_UPDATE`, `EVIDENCE_UPDATE`, `PROCESSING_STATUS`, `PROCESSING_ERROR`, `SESSION_COMPLETED`, `STATE_SNAPSHOT`, `PONG`.

### 4.12 Orchestrator (`services/pipeline.py`)

One `SessionRuntime` per live session owns that session's providers, timeline cursor, batching state and counters. `SessionPipeline` handles lifecycle (`start` / `pause` / `resume` / `stop`), `ingest_audio` (the per-chunk path through every stage), `maybe_run_ai_update` (batching policy), `run_ai_update` (structuring with primary/fallback provider) and `snapshot` (WebSocket resync).

---

## 5. Data model

```
Session
 ├── Speaker            (label, role, confidence, role_source)
 ├── AudioChunk         (window, sample rate, channels, speech ratio, RMS, status)
 ├── TranscriptSegment  (ref, speaker, text, start/end, ASR + diarization confidence, overlapping)
 ├── ClinicalEntity     (ref, type, value, normalised value/code, status, confidence, source refs)
 ├── ClinicalNote       (status, version, content JSON, review flags, approver)
 │    └── NoteVersion   (version, status, content snapshot, change summary, author type)
 └── EvidenceLink       (target kind/key, statement, segment ref, speaker, timestamp, validated)

User        (email, name, role)
AuditLog    (session, actor, action, resource, detail)
```

UUID primary keys and timezone-aware timestamps throughout. Note content is stored as JSON so a section's text, confidence, evidence and human-edit state travel together and version snapshots are trivial.

**SQLite concurrency.** When the development fallback is active, connections are configured with `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=30000` and `foreign_keys=ON`. Without this, a background structuring pass and an incoming API request race for the single writer lock and one fails immediately.

---

## 6. Security, privacy and monitoring

- **Identity.** `Principal` is derived from `X-User-Email` / `X-User-Role` in development mode; the seam for real authentication is `core/security.py`.
- **RBAC.** `require_roles` guards protected routes. Only `DOCTOR` and `FACULTY` can approve documentation.
- **Audit.** Lifecycle actions, speaker overrides, note edits, approvals and exports are recorded with actor, resource and detail.
- **Encryption.** `EncryptedStorage` defines the storage interface and tamper-evident fingerprinting; it is not KMS-backed.
- **Logging.** Structured JSON with request ID and session ID context, plus stage durations (Gemini, ASR, diarization) and error codes.
- **Metrics.** An in-process registry (counters, gauges, duration observations) served as JSON or Prometheus text at `/api/metrics`.
- **Privacy.** All demo data is synthetic. Transcript text is not written to logs; only refs, counts and durations are.

---

## 7. Export

`build_export_payload` gathers session, note, transcript, entities and evidence into one provenance-complete document, then:

- **JSON** — the full payload, including every evidence chain
- **PDF** — ReportLab document with sections, entities, confidence and evidence counts
- **FHIR** — an `FHIRAdapter` that emits an R4-*shaped* bundle (Patient, Encounter, Observation, MedicationStatement, AllergyIntolerance, DiagnosticReport, CarePlan). No conformance claim is made, which is why it is called *FHIR-compatible*.

Exporting transitions the note to `EXPORTED` and writes an audit entry.

---

## 8. Frontend architecture

- **`services/api.ts`** — typed REST client; attaches identity headers; normalises errors into `ApiError`.
- **`services/socket.ts`** — reconnecting WebSocket with heartbeat, exponential backoff and sequence-based resync.
- **`store/sessionStore.ts`** — Zustand store; every mutation comes from a REST response or a socket event, so the UI always reflects pipeline state. Handles snapshot replacement, segment de-duplication by `ref`, and error de-duplication by code.
- **`components/session/`** — `TranscriptPanel`, `ClinicalNotePanel`, `IntelligencePanel`, `EvidenceViewer`, `SpeakerRoster`, `SessionBar`.
- **`hooks/useMicrophoneCapture.ts`** — Web Audio capture, downsampling, WAV encoding, chunked upload, input level metering.

The live screen is a three-column clinical workstation: transcript, note, intelligence — with the evidence viewer opening as a fourth column so provenance never covers the transcript it refers to.

---

## 9. Where real models plug in

| Capability | Interface | Real implementation | Enable with |
| --- | --- | --- | --- |
| ASR | `ASRProvider` | `FasterWhisperProvider` | `ASR_PROVIDER=faster_whisper`, `requirements-asr.txt` |
| Diarization | `DiarizationService` | `PyannoteDiarizationProvider` | `DIARIZATION_PROVIDER=pyannote`, `HUGGINGFACE_TOKEN` |
| LLM | `LLMProvider` | `GeminiProvider` | `AI_MODE=gemini`, `GEMINI_API_KEY` |
| Terminology | `TerminologyProvider` | not implemented | connect a terminology server |
| Export | `FHIRAdapter` | FHIR-shaped | extend for a specific FHIR server |
| Auth | `Principal` / `require_roles` | dev headers | replace `get_current_principal` |

Every one of these is a constructor swap, not a refactor. That separation — not the UI — is the point of the architecture.
