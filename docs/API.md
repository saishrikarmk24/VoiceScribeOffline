# MedScribe Live — API

Base URL: `http://127.0.0.1:8000`
API prefix: `/api` (configurable via `API_PREFIX`)
Interactive docs: `/docs` (Swagger UI) · machine-readable schema: `/openapi.json`

Every request may carry a development identity:

```
X-User-Email: dev.clinician@medscribe.local
X-User-Role: DOCTOR        # DOCTOR | STUDENT | FACULTY | ADMIN
```

Missing headers fall back to `DEV_USER_EMAIL` / `DEV_USER_ROLE`. The role drives RBAC (only `DOCTOR` and `FACULTY` may approve documentation) and is recorded in the audit log.

Errors use FastAPI's shape:

```json
{ "detail": "Note 6f2c… not found" }
```

| Status | Meaning in MedScribe |
| --- | --- |
| 400 | invalid state for the requested action |
| 403 | role is not permitted (e.g. a `STUDENT` approving a note) |
| 404 | session, note or speaker does not exist |
| 409 | illegal note state transition (e.g. approving with unresolved review flags) |
| 422 | request body failed schema validation |

Session paths accept **either** the UUID **or** the human reference (`SIM-2026-001`).

---

## System

### `GET /api/health`
Liveness plus database reachability.

```json
{
  "status": "ok",
  "environment": "development",
  "version": "0.1.0",
  "database": { "connected": true, "dialect": "sqlite", "using_fallback": true, "url": "sqlite+aiosqlite:///./medscribe_dev.db" },
  "ai": { "mode": "gemini", "provider": "gemini", "model": "gemini-2.5-flash", "gemini_configured": true },
  "websocket": { "connections": 0, "sessions": 0, "history_limit": 400 },
  "active_sessions": 0
}
```

### `GET /api/status`
Full component status — used by the sidebar and dashboard.

```json
{
  "environment": "development",
  "version": "0.1.0",
  "database": { "connected": true, "dialect": "postgresql", "using_fallback": false, "url": "postgresql+asyncpg://***@localhost:5432/medscribe" },
  "ai": {
    "mode": "gemini", "configured_mode": "gemini",
    "provider": "gemini", "model": "gemini-2.5-flash", "mock": false, "gemini_configured": true,
    "update_interval_seconds": 10.0, "min_segments_per_update": 3, "max_retries": 3
  },
  "providers": {
    "asr": { "name": "mock", "mock": true },
    "diarization": { "name": "mock", "mock": true },
    "terminology": { "name": "mock", "fabricates_codes": false },
    "security": { "dev_auth": true, "retention_days": 30 }
  },
  "websocket": { "connections": 1, "sessions": 1 },
  "demo_mode_enabled": true
}
```

### `GET /api/ai/check`
Live connectivity probe against the configured AI provider. Returns `{ "provider": …, "mock": false, "ok": true, … }`, or `ok: false` with a mapped error code (`LLM_AUTH`, `LLM_RATE_LIMIT`, `LLM_TIMEOUT`, `LLM_UNAVAILABLE`, `LLM_NOT_CONFIGURED`).

### `GET /api/metrics`
JSON counters and duration observations. Add `?prometheus=true` for Prometheus text exposition.

---

## Sessions

### `POST /api/sessions` → `201`

```json
{
  "name": "Outpatient chest discomfort encounter",
  "patient_id": "SIM-PT-0042",
  "scenario": "Standardised patient reporting intermittent chest discomfort",
  "simulation_type": "OUTPATIENT",
  "doctor_name": "Dr. A. Rao",
  "faculty_name": "Prof. M. Iyer",
  "mode": "DEMO",
  "audio_source": "SIMULATION"
}
```

- `simulation_type` (encounter type): `OSCE | WARD_ROUND | OUTPATIENT | EMERGENCY | TEACHING | OTHER`
- `mode`: `DEMO | MICROPHONE | UPLOAD`
- `audio_source`: `SIMULATION | MICROPHONE | UPLOAD` (defaulted from `mode`)

Creates the session, assigns a reference (`SIM-YYYY-NNN`) and an empty `PROCESSING` note.

### `GET /api/sessions?limit=25&offset=0&status=LIVE`
Paginated: `{ "items": [SessionSummary], "total": n, "limit": n, "offset": n }`.

### `GET /api/sessions/dashboard`
Aggregate metrics, recent sessions, sessions per day and entity-type distribution.

### `GET /api/sessions/scripts`
Synthetic conversations available for Demo Mode: `{ "scripts": [{ "key", "title", "description", "utterances" }], "demo_mode_enabled": true }`.

### `GET /api/sessions/{session_id}`
Full session, including speakers, counts and note status.

### `DELETE /api/sessions/{session_id}`
Cascades to transcript, entities, note, versions and evidence. Requires `DOCTOR`, `FACULTY` or `ADMIN`.

### Lifecycle

| Endpoint | Effect |
| --- | --- |
| `POST /api/sessions/{id}/start` | `CREATED → LIVE`; creates the runtime, and in Demo Mode starts the demo driver |
| `POST /api/sessions/{id}/pause` | `LIVE → PAUSED`; audio ingestion suspends, state is preserved |
| `POST /api/sessions/{id}/resume` | `PAUSED → LIVE` |
| `POST /api/sessions/{id}/stop` | runs a final structuring pass, then `→ REVIEW` |

All four return the updated session.

### `POST /api/sessions/{id}/process`
Forces a structuring pass immediately — the "Run AI update" / retry action after an AI failure.

```json
{ "ok": true, "message": "Note updated to version 4", "detail": { "changed_sections": ["assessment"] } }
```

---

## Audio

### `POST /api/sessions/{id}/audio/chunk`
Browser microphone buffer. Base64 keeps it JSON-transportable.

```json
{
  "audio_base64": "UklGRiQ…",
  "mime_type": "audio/wav",
  "sample_rate": 16000,
  "channels": 1,
  "duration_seconds": 2.0
}
```

Send 16 kHz mono PCM16 WAV. Compressed containers (WebM/Opus, MP3) are accepted and stored but not decoded without ffmpeg. Max 8 MB per chunk.

### `POST /api/sessions/{id}/audio/upload`
`multipart/form-data` with `file`. Processes a full recording in one pass.

### `GET /api/sessions/{id}/audio-chunks`
Chunk metadata — window, sample rate, channels, size, speech ratio, RMS dBFS, status.

---

## Transcript and speakers

### `GET /api/sessions/{id}/transcript`

```json
[
  {
    "id": "e0e1…", "ref": "seg_002", "sequence": 2,
    "speaker_id": "b1c2…", "speaker_label": "speaker_1", "role": "PATIENT",
    "text": "I've been having chest discomfort since yesterday evening.",
    "start_time": 3.6, "end_time": 8.1,
    "confidence": 0.94, "asr_confidence": 0.94, "diarization_confidence": 0.91,
    "overlapping": false, "is_final": true
  }
]
```

`ref` is the stable identifier every clinical statement cites.

### `GET /api/sessions/{id}/speakers`
`role_source` is `SYSTEM` (attributed automatically) or `HUMAN` (overridden).

### `PATCH /api/speakers/{speaker_id}`

```json
{ "role": "NURSE", "display_name": "Nurse Menon" }
```

Roles: `DOCTOR | PATIENT | NURSE | STAFF | BACKGROUND | UNKNOWN`. A human override is authoritative, is broadcast over the WebSocket, and triggers a re-structuring pass so the note reflects the corrected attribution.

---

## Clinical information

### `GET /api/sessions/{id}/entities`
Optional filters: `entity_type`, `status`.

```json
[
  {
    "id": "…", "ref": "ent_001",
    "entity_type": "SYMPTOM", "value": "chest discomfort",
    "normalized_value": "chest discomfort", "normalized_code": null, "terminology_system": "SNOMED CT",
    "status": "PRESENT", "confidence": 0.93,
    "source_segment_refs": ["seg_002"], "detail": "since yesterday evening",
    "review_required": false, "review_reason": null,
    "evidence": [ { "transcript_segment_ref": "seg_002", "speaker_role": "PATIENT", "timestamp": 3.6, "confidence": 0.94, "source_text": "I've been having chest discomfort…", "validated": true, "validation_error": null } ]
  }
]
```

Types: `SYMPTOM, FINDING, MEDICATION, ALLERGY, DIAGNOSIS_MENTIONED, PROCEDURE, INVESTIGATION, DURATION, SEVERITY, FREQUENCY, CHARACTER, PLAN, FOLLOW_UP, MEDICAL_HISTORY`
Statuses: `PRESENT, NEGATED, UNCERTAIN, HISTORICAL, UNKNOWN`

`normalized_code` is `null` unless a real terminology server has verified it — codes are never fabricated.

### `GET /api/sessions/{id}/entities/summary`
Counts by type and status.

---

## Clinical note

### `GET /api/sessions/{id}/note`

```json
{
  "id": "…", "session_id": "…",
  "status": "DRAFT", "version": 4,
  "content": {
    "chief_complaint": {
      "text": "Chest discomfort since yesterday evening.",
      "confidence": 0.91,
      "evidence": [ { "transcript_segment_ref": "seg_002", "…": "…" } ],
      "review_required": false, "review_reason": null, "edited_by_human": false
    },
    "history_of_present_illness": { "…": "…" },
    "relevant_medical_history": { "…": "…" },
    "assessment": { "…": "…" },
    "plan": { "…": "…" },
    "follow_up": { "…": "…" },
    "symptoms": [ClinicalEntity], "medications": [], "allergies": [], "findings": [], "investigations": [],
    "generated_at": "2026-08-18T12:04:11Z", "model": "gemini-2.5-flash", "version": 4
  },
  "review_flags": [ { "section": "assessment", "label": "Assessment", "reason": "No transcript evidence", "severity": "WARNING" } ],
  "model": "gemini-2.5-flash",
  "approved_by": null, "approved_at": null, "exported_at": null,
  "updated_at": "2026-08-18T12:04:11Z"
}
```

Statuses: `PROCESSING → DRAFT → REVIEW_REQUIRED → APPROVED → EXPORTED`.
Absent information is `"Not mentioned"`, never invented.

### `GET /api/sessions/{id}/note/versions`
Version history with change summary, changed sections and author type (`AI` or `HUMAN`).

### `PATCH /api/notes/{note_id}`
Human edit. Only supplied sections are replaced.

```json
{ "assessment": "Clinician documented intermittent pressure-like chest discomfort.", "editor": "Dr. A. Rao" }
```

Creates a `HUMAN` version, marks the section `edited_by_human` (so later AI passes will not overwrite it), clears that section's review flag and broadcasts `NOTE_UPDATE`.

### `POST /api/notes/{note_id}/approve`

```json
{ "approved_by": "Dr. A. Rao", "acknowledgement": true }
```

Requires `DOCTOR` or `FACULTY` (403 otherwise), `acknowledgement: true`, and no blocking review flags (409 otherwise). Sets the session to `APPROVED` and writes an audit entry. **There is no path from an AI update to `APPROVED`.**

### `POST /api/notes/{note_id}/reopen`
Returns an `APPROVED`/`EXPORTED` note to `DRAFT` and clears approval metadata.

---

## Evidence

### `GET /api/sessions/{id}/evidence?target_key=chief_complaint`

```json
[
  {
    "id": "…", "target_kind": "SECTION", "target_key": "chief_complaint",
    "clinical_statement": "Chest discomfort since yesterday evening.",
    "segment_ref": "seg_002", "speaker_label": "speaker_1", "speaker_role": "PATIENT",
    "source_text": "I've been having chest discomfort since yesterday evening.",
    "timestamp": 3.6, "confidence": 0.94,
    "validated": true, "validation_error": null
  }
]
```

`target_key` is a section key (`chief_complaint`, `assessment`, …) or an entity ref (`ent_001`).

### `GET /api/sessions/{id}/evidence/{target_key}/detail`
Powers **Show Source** — the complete provenance chain.

```json
{
  "target_key": "chief_complaint",
  "clinical_statement": "Chest discomfort since yesterday evening.",
  "chain": [ { "evidence": {"…": "…"}, "segment": {"…": "…"}, "audio_chunk_id": "9c1f…" } ],
  "validated_count": 1,
  "total_count": 1
}
```

An empty `chain` means the statement is not traceable and is flagged `REVIEW REQUIRED`.

---

## Export

### `POST /api/sessions/{id}/export?format=JSON|PDF|FHIR`

| Format | Content type | Contents |
| --- | --- | --- |
| `JSON` | `application/json` | session, note, transcript, entities and the full evidence chain |
| `PDF` | `application/pdf` | rendered note with sections, entities, confidence and evidence counts |
| `FHIR` | `application/fhir+json` | R4-*shaped* bundle: Patient, Encounter, Observation, MedicationStatement, AllergyIntolerance, DiagnosticReport, CarePlan |

Returns the file with `Content-Disposition: attachment; filename="…"`, transitions the note to `EXPORTED` and writes an audit entry. FHIR output is *compatible-shaped*; no conformance claim is made.

### `GET /api/sessions/{id}/export/preview`
Inspect the JSON payload and FHIR bundle (with resource counts) without downloading.

---

## Audit

### `GET /api/sessions/{id}/audit`

```json
{ "entries": [ { "id": "…", "action": "NOTE_APPROVED", "actor_email": "dev.clinician@medscribe.local", "created_at": "2026-08-18T12:10:03Z", "detail": { "approved_by": "Dr. A. Rao", "version": 5 } } ] }
```

Actions include `SESSION_CREATED`, `SESSION_STARTED`, `SESSION_PAUSED`, `SESSION_RESUMED`, `SESSION_STOPPED`, `SPEAKER_ROLE_UPDATED`, `NOTE_EDITED`, `NOTE_APPROVED`, `NOTE_REOPENED`, `SESSION_EXPORTED`, `SESSION_DELETED`.

---

## WebSocket

```
ws://127.0.0.1:8000/ws/sessions/{session_id}
```

Every frame:

```json
{ "type": "TRANSCRIPT_UPDATE", "session_id": "…", "payload": { }, "emitted_at": "2026-08-18T12:03:58Z", "sequence": 42 }
```

### Server → client

| Type | Payload |
| --- | --- |
| `SESSION_STARTED` | session, providers, `ai` status |
| `SESSION_STATUS` | `status`, `duration_seconds`, `ai` |
| `AUDIO_STATUS` | `timeline_seconds`, `voice_activity`, `speech_ratio`, `rms_dbfs` |
| `DIARIZATION_UPDATE` | `speakers`, `turns` |
| `TRANSCRIPT_UPDATE` | `segments`, `replace` |
| `ENTITY_UPDATE` | `entities` (full current set) |
| `NOTE_UPDATE` | `note`, `changed_sections`, `change_summary`, `author_type` |
| `EVIDENCE_UPDATE` | `evidence` |
| `PROCESSING_STATUS` | `stage`, `detail`, `ai` |
| `PROCESSING_ERROR` | `code`, `message`, `stage`, `recoverable` |
| `SESSION_COMPLETED` | `status`, `duration_seconds` |
| `STATE_SNAPSHOT` | session, segments, speakers, entities, note, evidence, ai, stage |
| `PONG` | heartbeat reply |

Stages: `AUDIO_CAPTURE, AUDIO_PREPROCESSING, DIARIZATION, ROLE_ATTRIBUTION, ASR, TRANSCRIPT_ASSEMBLY, CLINICAL_NLP, LLM_STRUCTURING, EVIDENCE_LINKING, NOTE_STATE, IDLE`.

### Client → server

```json
{ "type": "PING" }
{ "type": "SYNC", "last_sequence": 42 }
```

`SYNC` replays events after `last_sequence`, or returns a `STATE_SNAPSHOT` when the gap exceeds the retained history. The frontend client sends this automatically on reconnect, so a dropped connection never leaves stale state on screen.

---

## Configuration reference

| Variable | Default | Purpose |
| --- | --- | --- |
| `GEMINI_API_KEY` | — | Gemini key; backend only, never sent to the browser |
| `GEMINI_MODEL` | `gemini-2.5-flash` | model, configurable without code changes |
| `AI_MODE` | `gemini` | `gemini` or `mock` (deterministic rule-based) |
| `GEMINI_UPDATE_INTERVAL_SECONDS` | `10` | batching interval for structuring calls |
| `GEMINI_MIN_SEGMENTS_PER_UPDATE` | `3` | minimum segments before a call |
| `GEMINI_TIMEOUT_SECONDS` | `45` | per-call timeout |
| `GEMINI_MAX_RETRIES` | `3` | bounded retries; auth errors are never retried |
| `DATABASE_URL` | `postgresql+asyncpg://…` | target database |
| `ALLOW_SQLITE_FALLBACK` | `true` | development convenience; disable in production |
| `AUTO_CREATE_SCHEMA` | `true` | create tables at startup instead of running Alembic |
| `ENABLE_DEMO_MODE` | `true` | allow Demo Mode sessions |
| `DEMO_SEGMENT_INTERVAL_SECONDS` | `2.5` | pacing between demo utterances |
| `ASR_PROVIDER` | `mock` | `mock` or `faster_whisper` |
| `DIARIZATION_PROVIDER` | `mock` | `mock` or `pyannote` |
| `HUGGINGFACE_TOKEN` | — | required by pyannote |
| `AUDIO_SAMPLE_RATE` | `16000` | canonical pipeline rate |
| `DEV_AUTH_ENABLED` | `true` | development identity headers |
| `CORS_ORIGINS` | `http://localhost:5173,…` | comma-separated allowed origins |
| `LOG_LEVEL` | `INFO` | structured log level |
| `ENABLE_METRICS` | `true` | expose `/api/metrics` |
