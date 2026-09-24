@echo off
setlocal
title VoiceScribe AI - Gemma 2 9B Offline Edition
color 0b

echo ==============================================================================
echo          VOICESCRIBE AI - GEMMA 2 (9B) OFFLINE EDITION LAUNCHER
echo              Powered by Google Gemma 2 9B and AI4Bharat IndicWhisper
echo ==============================================================================
echo.

:: 1. Apply Gemma 2 9B Environment Configuration
echo [1/5] Applying Gemma 2 9B offline configuration...
copy /y "%~dp0.env.gemma" "%~dp0.env" >nul
copy /y "%~dp0backend\.env.gemma" "%~dp0backend\.env" >nul
echo [OK] Gemma 2 9B offline environment configured.
echo.

:: 2. Check and start Ollama with gemma2:9b
echo [2/5] Verifying Ollama and Google Gemma 2 9B...
ollama --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Ollama is not installed or not in PATH!
    echo Please install Ollama from https://ollama.ai
    pause
    exit /b 1
)

:: Check if Ollama service is active
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Starting Ollama background server...
    start "" ollama serve
    timeout /t 3 >nul
)

:: Check if gemma2:9b model is installed
ollama list | findstr /i "gemma2:9b" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] High-precision model 'gemma2:9b' not found in local library.
    echo [INFO] Downloading Google Gemma 2 9B (Q4_K_M quantized, approx 5.4GB)...
    echo [INFO] This is a one-time download for hospital-grade clinical precision.
    ollama pull gemma2:9b
) else (
    echo [OK] Google Gemma 2 9B (gemma2:9b) is ready.
)
echo.

:: 3. Setup Virtual Environment Check
echo [3/5] Verifying backend and frontend environments...
if not exist "%~dp0backend\.venv\Scripts\activate.bat" (
    echo [INFO] Creating backend virtual environment...
    cd /d "%~dp0backend"
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
    python -c "import asyncio; from app.core.database import init_database, dispose_database; asyncio.run(init_database()); asyncio.run(dispose_database())" >nul 2>&1
    cd /d "%~dp0"
)
if not exist "%~dp0frontend\node_modules" (
    echo [INFO] Installing frontend packages (first-time setup)...
    cd /d "%~dp0frontend"
    call npm install
    cd /d "%~dp0"
)
echo [OK] Environments ready.
echo.

:: 4. Launch Backend
echo [4/5] Starting Backend with Gemma 2 9B and IndicWhisper on http://127.0.0.1:8000 ...
start "VoiceScribe AI - Backend (Gemma 9B)" cmd /k "cd /d ""%~dp0backend"" && call .venv\Scripts\activate.bat && uvicorn app.main:app --host 127.0.0.1 --port 8000"

timeout /t 3 >nul

:: 5. Launch Frontend
echo [5/5] Starting Frontend Workstation on http://127.0.0.1:5173 ...
start "VoiceScribe AI - Frontend" cmd /k "cd /d ""%~dp0frontend"" && npm run dev"

timeout /t 3 >nul

:: Open browser
echo Opening Browser...
start http://127.0.0.1:5173

echo.
echo ==============================================================================
echo             VOICESCRIBE AI (GEMMA 2 9B EDITION) IS RUNNING!
echo ==============================================================================
echo.
echo  * Web App:        http://127.0.0.1:5173
echo  * Backend API:    http://127.0.0.1:8000
echo  * Active LLM:     Google Gemma 2 9B (Few-Shot In-Context Grounding)
echo  * Speech Engine:  AI4Bharat IndicWhisper & Faster-Whisper Turbo
echo  * Normalizer:     Indian Medical Phonetic Auto-Corrector Active
echo.
echo  Default Clinician:
echo    - Email: doctor.gemma@voicescribe.local
echo    - Role:  DOCTOR
echo.
echo To close VoiceScribe AI, close the Backend and Frontend command windows.
echo ==============================================================================
echo.
pause
