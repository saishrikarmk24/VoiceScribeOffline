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
4. SOAP note           Gemma 4 e4b via Ollama, **GPU** ~6.6 GB
                       Temperature 0. Documents what was said only.
        │
        ▼
5. Grounding           Invented meds / diagnoses / symptoms are DROPPED
                       if they are not in the transcript.
        │
        ▼
6. Workstation         React UI at http://localhost:5173
```

VRAM: Gemma 4 e4b uses the GPU. Whisper stays on CPU so they do not share 6 GB.

---

## One-time setup (friend's laptop)

**Double-click `INSTALL_A_TO_Z.bat`.**

That is the whole setup. It installs Python, Node.js, Ollama, Gemma 4 e4b, CPU Whisper, then opens the app. No CUDA Toolkit. No PyTorch. First run can take 15–40 minutes because Gemma 4 e4b is about 6.6 GB.

After that, use `START_VOICESCRIBE.bat` to open the app again.

- App: http://localhost:5173
- API: http://localhost:8000/docs

---

## `.env` (already the default)

| Variable | Value | Why |
|---|---|---|
| `AI_MODE` | `local` | Ollama, not Gemini |
| `LOCAL_LLM_MODEL` | `gemma4:e4b` | Note model on GPU |
| `ASR_PROVIDER` | `faster_whisper` | CTranslate2 Whisper |
| `FASTER_WHISPER_MODEL` | `large-v3-turbo` | Multilingual, including mixed Indian + English. `large-v3` is more accurate for Tamil but ~2x slower on CPU. Do not use `small`/`base` for Tamil |
| `ASR_SECOND_PASS` | `indic_conformer` | Tamil/Hindi-heavy utterances go to AI4Bharat IndicConformer, far better than Whisper on Tamil. Needs `transformers torchaudio onnxruntime-gpu` and a `HUGGINGFACE_TOKEN` that accepted the model terms; falls back to Whisper if it cannot load |
| `ASR_LANGUAGES` | `ta,en,hi` | Language is detected per utterance among these only (Tanglish / Hinglish code-switching) |
| `INDIC_ASR_LANGUAGE` | `auto` | `auto` = per-utterance detection; a code like `ta` forces one language |
| `ASR_DEVICE` | `cpu` | Leaves VRAM for Gemma 4 e4b |
| `ASR_COMPUTE_TYPE` | `int8` | Fast enough on CPU |
| `DIARIZATION_PROVIDER` | `local` | CPU |
