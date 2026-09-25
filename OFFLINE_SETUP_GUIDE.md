# VoiceScribe AI — offline edition (RTX 4050)

Runs air-gapped on a **6 GB RTX 4050 laptop**. No Gemini key. No cloud ASR.

## Pipeline (this is the whole stack)

```
Mic / upload WAV (16 kHz mono)
        │
        ▼
1. Preprocess          VAD, resample — CPU
        │
        ▼
2. Speech-to-text      Faster-Whisper large-v3-turbo, int8, **CPU**
                       Multilingual (Hindi / Tamil / English / mixed).
        │
        ▼
3. Speakers            Local pitch clustering — CPU
        │
        ▼
4. SOAP note           Qwen 2.5 7B via Ollama, Q4, **GPU** ~4.7 GB
                       Temperature 0. Documents what was said only.
        │
        ▼
5. Grounding           Invented meds / diagnoses / symptoms are DROPPED
                       if they are not in the transcript.
        │
        ▼
6. Workstation         React UI at http://localhost:5173
```

VRAM: Qwen 7B uses the GPU. Whisper stays on CPU so they do not share 6 GB.

---

## One-time setup

### 1. Ollama

Install from https://ollama.com then:

```bash
ollama pull qwen2.5:7b
```

(~4.7 GB)

### 2. Python ASR extras

```bash
cd backend
.venv\Scripts\activate
pip install -r requirements-asr.txt
```

### 3. Start

Double-click `run_offline.bat` or:

```powershell
cd D:\MedScribe-Offline
.\run_offline.ps1
```

- App: http://localhost:5173
- API: http://localhost:8000/docs

---

## `.env` (already the default)

| Variable | Value | Why |
|---|---|---|
| `AI_MODE` | `local` | Ollama, not Gemini |
| `LOCAL_LLM_MODEL` | `qwen2.5:7b` | Note model on GPU |
| `ASR_PROVIDER` | `faster_whisper` | CTranslate2 Whisper |
| `FASTER_WHISPER_MODEL` | `large-v3-turbo` | Multilingual, including mixed Indian + English |
| `ASR_DEVICE` | `cpu` | Leaves VRAM for Qwen 7B |
| `ASR_COMPUTE_TYPE` | `int8` | Fast enough on CPU |
| `DIARIZATION_PROVIDER` | `local` | CPU |
