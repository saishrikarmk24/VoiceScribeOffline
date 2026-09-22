# MedScribe Live

**AI-powered clinical documentation for doctor–patient conversations.**

MedScribe Live turns a doctor–patient conversation into structured, **evidence-linked** clinical documentation:

```
Audio → Speaker-aware transcript → Clinical information → Structured note → Evidence-linked documentation
```

It is built for clinical documentation, education, faculty review and technical demonstration. **It is not a diagnostic system.** It documents what was explicitly said; it never diagnoses, recommends treatment, or approves its own output.

---

## 1. Project overview

The product is organised around one principle: **Evidence First**. Every clinical statement the system produces must be traceable back to the words that produced it:

```
Clinical note → clinical statement → evidence reference → transcript segment → speaker → timestamp → audio chunk
```

If a statement cannot be linked to transcript evidence, it is flagged `REVIEW REQUIRED` and cannot be approved until a human resolves it. The "Show Source" control on every section and entity opens that full provenance chain.

What you can do in the running application:

- create a session (demo, microphone or uploaded recording)
- start, pause, resume and end it
- watch the transcript arrive progressively with speaker roles, timestamps and confidence
- reassign speaker roles and have the note re-structured accordingly
- watch clinical entities and note sections appear as the AI layer processes batches of speech
- inspect the evidence behind any statement
- edit sections, approve the note as a human reviewer, and export JSON / PDF / FHIR-compatible JSON

---

## 2. Architecture

```
                     MEDSCRIBE LIVE
                           │
                  ┌────────▼─────────┐
                  │  AUDIO CAPTURE   │  Mic (Web Audio) / Upload / Demo feed
                  └────────┬─────────┘
                  ┌────────▼─────────┐
                  │ AUDIO PROCESSING │  decode → mono → 16 kHz → HPF → denoise → VAD
                  └────────┬─────────┘
              ┌────────────┴────────────┐
      ┌───────▼───────┐         ┌───────▼────────┐
      │     ASR       │         │  DIARIZATION   │
      │ mock / faster │         │ mock / pyannote│
      │   -whisper    │         │                │
      └───────┬───────┘         └───────┬────────┘
              └────────────┬────────────┘
                  ┌────────▼─────────┐
                  │ TRANSCRIPT       │  merge, overlap handling, role attribution
                  │ ASSEMBLY         │
                  └────────┬─────────┘
                  ┌────────▼─────────┐
                  │ CLINICAL NLP     │  entities, negation, uncertainty, normalisation
                  └────────┬─────────┘
                  ┌────────▼─────────┐
                  │ GEMINI API       │  schema-constrained structured JSON
                  └────────┬─────────┘
                  ┌────────▼─────────┐
                  │ EVIDENCE LINKING │  statement → segment → speaker → time
                  └────────┬─────────┘
                  ┌────────▼─────────┐
                  │ NOTE STATE       │  draft → review → approved → exported
                  │ ENGINE           │  versioning, conflict handling
                  └────────┬─────────┘
                  ┌────────▼──────────────────────┐
                  │ CLINICAL DASHBOARD (WebSocket)│
                  │ Transcript │ Note │ Evidence  │
                  └───────────────────────────────┘
```

The rule-based clinical NLP layer runs **before** the LLM and is also used **after** it: extracted candidates are passed to Gemini as grounding, and Gemini's output is validated against them (a rule-detected negation overrides an LLM `PRESENT` status). See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the detail.

---

## 3. Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, Zustand, React Router, Recharts, Lucide |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic, Uvicorn, WebSockets |
| Database | PostgreSQL 16 (SQLite fallback for local development) |
| AI | Google Gemini via the current `google-genai` SDK (`from google import genai`) |
| ASR / diarization | Mock providers by default; Faster-Whisper and pyannote.audio adapters included |
| Export | JSON, PDF (ReportLab), FHIR R4-shaped JSON bundle |
| Tests | pytest + pytest-asyncio (backend), Vitest + Testing Library (frontend) |

---

## 4. Setup

```bash
git clone <your-repo-url> medscribe-live
cd medscribe-live
cp .env.example .env      # Windows: copy .env.example .env
```

### Backend

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

For PostgreSQL, also install the async driver:

```bash
pip install -r requirements-postgres.txt
```

Optional heavy ML dependencies for real ASR / diarization (not needed for Demo Mode):

```bash
pip install -r requirements-asr.txt
```

### Frontend

```bash
cd frontend
npm install
```

---

## 5. Gemini API setup

1. Create a key at <https://aistudio.google.com/apikey>.
2. Put it in `.env` at the repository root:

```env
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-2.5-flash
AI_MODE=gemini
```

3. Verify it:

```bash
python scripts/test_gemini.py
```

```
============================================================
MEDSCRIBE GEMINI TEST
============================================================
API Connection       PASS
Structured Output    PASS
Schema Validation    PASS
Entity Extraction    PASS
Negation Detection   PASS
Evidence Mapping     PASS
Note Generation      PASS
```

**The key never reaches the browser.** The React app calls the FastAPI backend, and only the backend's `GeminiProvider` talks to the Gemini API.

If no key is set, MedScribe does not break: the backend switches to a deterministic rule-based provider, the UI states clearly that it is running the fallback, and the entire pipeline (including Demo Mode) stays usable.

---

## 6. Running locally

Two terminals.

**Backend** (from `backend/`, with the virtualenv active):

```bash
uvicorn app.main:app --reload
```

- API: <http://127.0.0.1:8000/api>
- Swagger UI: <http://127.0.0.1:8000/docs>
- Health: <http://127.0.0.1:8000/api/health>

**Frontend** (from `frontend/`):

```bash
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` and `/ws` to port 8000, so no CORS setup is needed in development.

### Database

PostgreSQL is the target:

```env
DATABASE_URL=postgresql+asyncpg://medscribe:medscribe@localhost:5432/medscribe
```

If Postgres is unreachable and `ALLOW_SQLITE_FALLBACK=true`, the backend logs a warning and switches to a local SQLite file (`medscribe_dev.db`) so the prototype still runs. `/api/status` always reports which backend is live and whether the fallback is in use. Never enable the fallback in production.

Schema management:

```bash
# tables are auto-created on startup when AUTO_CREATE_SCHEMA=true (the default)
# or manage them explicitly:
cd backend
alembic upgrade head
alembic revision --autogenerate -m "your change"
```

### Docker

```bash
docker compose up --build
```

- Frontend (nginx, proxies `/api` and `/ws`): <http://localhost:8080>
- Backend: <http://localhost:8000/docs>
- PostgreSQL: `localhost:5432`

Pass your key through the environment: `GEMINI_API_KEY=... docker compose up --build`.

---

## 7. Running Demo Mode

Demo Mode is the fastest way to see the whole system, and it needs no microphone and no external ASR or diarization service.

1. Go to **New Session**.
2. Keep audio source **Demo**.
3. Click **Load Demo** (or **Start Session**).

What happens:

| Time | Event |
| --- | --- |
| 00:00 | Session starts, WebSocket connects, speakers channel opens |
| 00:02 | First doctor segment appears |
| 00:05 | First patient segment appears |
| 00:08 | Transcript continues, diarization assigns `speaker_0` / `speaker_1` |
| 00:10 | Clinical entities begin appearing in the intelligence column |
| 00:12 | The note updates section by section |
| 00:15 | Evidence links appear and "Show Source" becomes usable |

The transcript is **not** dumped at once — synthesised audio is fed through the real preprocessing, diarization, ASR, assembly, NLP, structuring, evidence and note-state stages, one chunk at a time.

Only the audio is synthetic. If a Gemini key is configured, the clinical intelligence you see is genuinely produced by Gemini.

The reference conversation (`chest_discomfort`) is expected to yield: chest discomfort (symptom), *since yesterday evening* (duration), *pressure* (character), *comes and goes* (frequency), shortness of breath (**negated**), metformin (medication), no known drug allergies (allergy) — **and no diagnosis**, because none is stated.

---

## 8. Testing

Backend (111 tests):

```bash
cd backend
.venv\Scripts\python.exe -m pytest -q     # Windows
python -m pytest -q                        # macOS / Linux
```

Covers session creation and lifecycle, speaker assignment, transcript assembly, entity extraction, negation detection, the Gemini provider (error mapping, retries, malformed output, schema validation), evidence linking, the note state engine, WebSocket events and replay, API routes, review/approval and all three export formats — including a full end-to-end Demo Mode run.

Frontend (20 tests):

```bash
cd frontend
npm run test        # Vitest
npm run lint        # tsc --noEmit
npm run build       # type-check + production build
```

Covers transcript rendering, speaker assignment, the evidence viewer, clinical note rendering and editing, and session state handling (including AI failure and reconnect resync).

Gemini integration:

```bash
python scripts/test_gemini.py
```

End-to-end verification against a **running** backend — drives create → start → live transcript → entities → evidence-linked note → stop → human edit → approve → export over the real HTTP and WebSocket surface:

```bash
python scripts/verify_local.py            # default http://127.0.0.1:8000
```

```
Infrastructure                Session lifecycle             Clinical intelligence
  Backend reachable    PASS     Session created      PASS     Entities extracted     PASS
  Database connected   PASS     Transcript streams   PASS     Negation preserved     PASS
  Swagger docs served  PASS     Roles attributed     PASS     No diagnosis invented  PASS
...
All checks passed. MedScribe Live is running correctly.
```

---

## 9. Project structure

```
medscribe-live/
├── frontend/
│   └── src/
│       ├── components/       layout, session panels, UI primitives
│       ├── pages/            dashboard, new session, live, review, history, detail, settings
│       ├── hooks/            useMicrophoneCapture (16 kHz mono WAV chunking)
│       ├── services/         api.ts (REST), socket.ts (WebSocket + resync)
│       ├── store/            sessionStore (live state), uiStore (identity, toasts)
│       ├── types/            contracts mirrored from the backend schemas
│       ├── constants/        roles, statuses, sections, pipeline stages
│       └── tests/            Vitest suites + fixtures
│
├── backend/
│   ├── app/
│   │   ├── api/routes/       sessions, audio, transcript, entities, notes, evidence, exports, system
│   │   ├── core/             config, database, logging/metrics, security (RBAC, audit)
│   │   ├── models/           SQLAlchemy ORM + shared enums
│   │   ├── schemas/          Pydantic API and AI contracts
│   │   ├── services/
│   │   │   ├── audio/        capture providers, preprocessing (mono/resample/VAD/denoise)
│   │   │   ├── asr/          MockASRProvider, FasterWhisperProvider
│   │   │   ├── diarization/  MockDiarizationProvider, PyannoteDiarizationProvider
│   │   │   ├── nlp/          clinical NLP, NegEx-style negation, terminology
│   │   │   ├── llm/          base, prompts, schemas, gemini_provider, mock_provider, validator
│   │   │   ├── evidence/     evidence linking + provenance
│   │   │   ├── note_engine/  note state machine, versioning, review flags
│   │   │   ├── demo/         synthetic conversations + demo runner
│   │   │   ├── export/       JSON, PDF, FHIR adapters
│   │   │   ├── pipeline.py   the orchestrator
│   │   │   └── repository.py data access + serialisation
│   │   ├── websocket/        connection manager (broadcast, history, replay), routes
│   │   └── main.py
│   ├── alembic/              migrations
│   └── tests/
│
├── scripts/
│   ├── test_gemini.py        Gemini connectivity, structured output, negation, evidence
│   └── verify_local.py       full end-to-end check against a running backend
├── docs/ARCHITECTURE.md, docs/API.md
├── docker-compose.yml, Dockerfile (backend), frontend/Dockerfile (nginx)
└── .env.example
```

---

## 10. Current limitations

- **ASR and diarization are mock providers by default.** They are deterministic and script-driven, which is exactly what makes Demo Mode reproducible — but they do not transcribe arbitrary speech. Real providers are wired behind `ASR_PROVIDER` / `DIARIZATION_PROVIDER` and require `requirements-asr.txt`.
- **Compressed audio needs ffmpeg.** The preprocessing stage decodes WAV/PCM with the standard library. WebM/Opus/MP3 uploads are accepted and stored but not decoded; the browser capture path deliberately sends 16 kHz mono WAV to avoid this.
- **Terminology codes are never fabricated.** `TerminologyService` normalises surface forms and declares the preferred system (SNOMED CT, ICD-10, RxNorm, LOINC), but `normalized_code` stays `null` until a real terminology server is connected.
- **FHIR output is FHIR-*shaped*, not certified.** The adapter emits a plausible R4 bundle (Patient, Encounter, Observation, MedicationStatement, AllergyIntolerance, DiagnosticReport, CarePlan). No conformance claim is made.
- **Authentication is a development user system.** Identity arrives as `X-User-Email` / `X-User-Role` headers and drives RBAC and audit logging. The seams for real authentication exist; OAuth/OIDC is not implemented.
- **Encryption is an abstraction.** `EncryptedStorage` provides the interface and tamper-evident fingerprints; it is not a KMS-backed implementation.
- **Metrics are in-process.** `/api/metrics` serves JSON or Prometheus text from an in-memory registry; it resets on restart and there is no scraping stack in compose.
- **Audio is not retained for playback.** Chunk metadata (window, speech ratio, RMS) is stored and shown, so the provenance chain reaches the audio chunk, but the UI does not yet replay the audio itself.

---

## 11. Future integrations

Adapters and interfaces are already in place for:

- **Faster-Whisper** medical ASR (`ASR_PROVIDER=faster_whisper`, `FASTER_WHISPER_MODEL`)
- **pyannote.audio** diarization (`DIARIZATION_PROVIDER=pyannote`, `HUGGINGFACE_TOKEN`)
- **SNOMED CT / ICD-10 / RxNorm / LOINC** through `TerminologyProvider`
- **FHIR / HIS / EMR / EHR** through the export adapter layer
- **Prometheus / Grafana** through the metrics registry
- Real authentication and KMS-backed encryption through `core/security.py`

---

## Safety and privacy

- Education and demonstration only. Never enter real patient data.
- All seed and demo data is synthetic.
- MedScribe documents what was said. It does not diagnose, recommend treatment or prescribe.
- AI-generated documentation is never auto-approved; approval is always an explicit human action by a `DOCTOR` or `FACULTY` role and is recorded in the audit log.
- Model confidence is not a measure of clinical correctness, and the UI says so wherever confidence is displayed.
