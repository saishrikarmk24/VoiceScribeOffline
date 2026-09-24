# VoiceScribe AI (100% Local Offline Edition)

Welcome to the **100% Local Offline Edition** of VoiceScribe AI. This edition runs completely air-gapped on your PC with **zero external API calls**, **zero subscription fees**, and **100% patient data privacy**.

---

## 🏗 System Architecture

```
[ Consultation Audio (Microphone / Upload) ]
                    |
                    v
1. Speech-to-Text: Faster-Whisper (small.en)
   - CTranslate2 CPU int8 inference
   - Fast, high-accuracy clinical transcription without internet
                    |
                    v
2. Diarization: Local Acoustic MFCC Clustering
   - Separates doctor and patient speaker turns locally
                    |
                    v
3. Clinical Structuring & SOAP Note Generation: Google Gemma 2 via Ollama
   - Local LLM server running on http://localhost:11434/v1
   - Pydantic JSON Schema enforcement with Few-Shot Clinical In-Context Learning
   - Generates Presenting Complaint, HPI, Physical Exam, Assessment, Plan & Follow-up
                    |
                    v
4. Frontend Workstation (React + Vite)
   - Real-time animated pipeline, 3-panel clinical workstation
```

---

## 🚀 Quick Start (One-Time Setup)

### Step 1: Install Ollama (Free & Open Source)
1. Download Ollama for Windows from: **[https://ollama.com](https://ollama.com)**
2. Run the installer. Ollama will start automatically in your Windows taskbar.

### Step 2: Download the Recommended Clinical Model
Open PowerShell or Command Prompt and run:

* **Recommended Clinical Model (Hospital-Grade Precision)**:
  ```bash
  ollama pull gemma2:9b
  ```
  *(~5.4 GB download. Google Gemma 2 9B Q4_K_M quantized. Top-tier clinical structuring & zero-hallucination scribe engine)*

* **Lightweight Alternative (Low VRAM / CPU-only)**:
  ```bash
  ollama pull gemma2:2b
  ```
  *(~1.6 GB download. Extremely fast, lightweight, fits in 4–8 GB RAM)*

---

## 🏃 Running the Offline System

To start both the offline backend and frontend with a single click:

* **Double-click**: `run_offline.bat`
* **Or run in PowerShell**:
  ```powershell
  cd d:\MedScribe-Offline
  .\run_offline.ps1
  ```

The launcher will:
1. Verify Ollama is running and check for downloaded models.
2. Verify `faster-whisper` speech recognition.
3. Launch the FastAPI offline backend on `http://localhost:8000`.
4. Launch the web application on `http://localhost:5173`.
5. Open your browser automatically.

---

## ⚙️ Environment Configuration (`.env`)

The `.env` file in this directory is pre-configured for offline mode:

| Variable | Setting | Description |
|---|---|---|
| `AI_MODE` | `local` | Uses local Ollama server instead of Gemini |
| `LOCAL_LLM_BASE_URL` | `http://localhost:11434/v1` | Local OpenAI-compatible endpoint |
| `LOCAL_LLM_MODEL` | `gemma2:9b` | Name of the Ollama model to use |
| `ASR_PROVIDER` | `indic_whisper` | AI4Bharat IndicWhisper / Faster-Whisper |
| `FASTER_WHISPER_MODEL` | `large-v3-turbo` | Whisper model size (`large-v3-turbo`, `small`, `medium`) |
| `DIARIZATION_PROVIDER` | `local` | Offline acoustic speaker separation |
| `DATABASE_URL` | `sqlite+aiosqlite:///./medscribe_offline.db` | Local SQLite database |

---

## 📊 Comparison: Cloud vs Offline Edition

| Feature | Cloud Edition (`d:\MedScribe`) | Offline Edition (`d:\MedScribe-Offline`) |
|---|---|---|
| **Internet Required** | Yes (Google Gemini API) | **No (100% Air-Gapped)** |
| **API Costs** | Gemini API (Free tier / Pay per token) | **$0.00 Forever (Free Open Source)** |
| **Speech-to-Text** | Gemini Audio API | **AI4Bharat IndicWhisper & Faster-Whisper** |
| **Phonetic Normalizer**| Cloud LLM | **Local Indian Medical Normalizer** |
| **Clinical Reasoning** | Gemini 3.7 Flash | **Google Gemma 2 9B (Few-Shot)** |
| **Data Privacy** | Encrypted transit to cloud | **Never leaves host machine** |
| **Deployment Target** | Cloud / Web SaaS / Mobile | **Hospital on-premise / Local clinic** |
