@echo off
setlocal enabledelayedexpansion
title VoiceScribe AI - One Click Installer & Launcher
color 0b

echo ==============================================================================
echo                      VOICESCRIBE AI - ONE-CLICK SETUP & LAUNCH
echo ==============================================================================
echo.

:: -------------------------------------------------------------------------
:: 1. Detect Python
:: -------------------------------------------------------------------------
echo [1/6] Detecting Python installation...
set "PYTHON_CMD="
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python"
) else (
    py -3 --version >nul 2>&1
    if %errorlevel% equ 0 (
        set "PYTHON_CMD=py -3"
    ) else (
        py --version >nul 2>&1
        if %errorlevel% equ 0 (
            set "PYTHON_CMD=py"
        )
    )
)

if "%PYTHON_CMD%"=="" (
    echo [ERROR] Python is not installed or not in PATH!
    echo Please download and install Python 3.10+ from https://www.python.org/downloads/
    echo [CRITICAL] Be sure to check the box "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

%PYTHON_CMD% --version
echo [OK] Python is ready (%PYTHON_CMD%).
echo.

:: -------------------------------------------------------------------------
:: 2. Detect Node.js & npm
:: -------------------------------------------------------------------------
echo [2/6] Detecting Node.js and npm...
npm --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js / npm is not installed or not in PATH!
    echo Please install Node.js (LTS version) from https://nodejs.org/
    echo.
    pause
    exit /b 1
)
node --version
echo [OK] Node.js is ready.
echo.

:: -------------------------------------------------------------------------
:: 3. Detect and Configure Ollama (Local LLM Server)
:: -------------------------------------------------------------------------
echo [3/6] Checking Ollama Local AI runtime...
ollama --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Ollama CLI detected.
    
    :: Check if Ollama service is reachable on port 11434
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1
    if !errorlevel! neq 0 (
        echo [INFO] Starting Ollama background server...
        start "" ollama serve
        timeout /t 3 >nul
    )
    
    :: Check if qwen2.5:7b model is downloaded
    ollama list | findstr /i "qwen2.5:7b" >nul 2>&1
    if !errorlevel! neq 0 (
        echo [INFO] Model 'qwen2.5:7b' not found in local library.
        echo [INFO] Downloading 'qwen2.5:7b' (~4.7 GB Q4, GPU). Whisper stays on CPU.
        ollama pull qwen2.5:7b
    ) else (
        echo [OK] Model 'qwen2.5:7b' is installed and ready.
    )
) else (
    echo [NOTICE] Ollama command not found in system PATH.
    echo If Ollama is running elsewhere, VoiceScribe will automatically connect to http://localhost:11434.
    echo For 100%% offline AI, download Ollama from https://ollama.ai and run: ollama pull qwen2.5:7b
)
echo.

:: -------------------------------------------------------------------------
:: 4. Environment Configurations (.env)
:: -------------------------------------------------------------------------
echo [4/6] Verifying offline configuration files...
if not exist "%~dp0.env" (
    echo Creating root .env from template...
    copy "%~dp0.env.example" "%~dp0.env" >nul
)
if not exist "%~dp0backend\.env" (
    echo Creating backend .env from template...
    copy "%~dp0.env.example" "%~dp0backend\.env" >nul
)
echo [OK] Configuration files verified.
echo.

:: -------------------------------------------------------------------------
:: 5. Setup Python Backend Virtual Environment
:: -------------------------------------------------------------------------
echo [5/6] Setting up Python backend virtual environment...
cd /d "%~dp0backend"
if not exist ".venv" (
    echo Creating clean virtual environment (.venv)...
    %PYTHON_CMD% -m venv .venv
)

call .venv\Scripts\activate.bat
echo Verifying and installing Python dependencies...
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [WARNING] Retrying dependency installation with output...
    pip install -r requirements.txt
)

echo Verifying local database schema and auto-migration...
python -c "import asyncio; from app.core.database import init_database, dispose_database; asyncio.run(init_database()); asyncio.run(dispose_database()); print('[OK] Database schema verified.')"
echo [OK] Backend environment is ready.
cd /d "%~dp0"
echo.

:: -------------------------------------------------------------------------
:: 6. Setup Frontend Web Application
:: -------------------------------------------------------------------------
echo [6/6] Setting up Frontend Web App...
cd /d "%~dp0frontend"
if not exist "node_modules" (
    echo Installing Frontend npm packages (first-time setup)...
    call npm install
) else (
    echo [OK] Frontend packages are installed.
)
cd /d "%~dp0"
echo.

:: -------------------------------------------------------------------------
:: Launch Applications
:: -------------------------------------------------------------------------
echo ==============================================================================
echo                     LAUNCHING VOICESCRIBE AI SERVICES
echo ==============================================================================
echo.

echo Starting Python Backend on http://127.0.0.1:8000 ...
start "VoiceScribe AI - Backend" cmd /k "cd /d ""%~dp0backend"" && call .venv\Scripts\activate.bat && uvicorn app.main:app --host 127.0.0.1 --port 8000"

timeout /t 3 >nul

echo Starting Frontend Web App on http://127.0.0.1:5173 ...
start "VoiceScribe AI - Frontend" cmd /k "cd /d ""%~dp0frontend"" && npm run dev"

timeout /t 3 >nul

echo Opening Browser...
start http://127.0.0.1:5173

echo.
echo ==============================================================================
echo                        VOICESCRIBE AI IS RUNNING!
echo ==============================================================================
echo.
echo  * Web App:       http://127.0.0.1:5173
echo  * Backend API:   http://127.0.0.1:8000
echo  * API Docs:      http://127.0.0.1:8000/docs
echo  * Offline Model: Qwen 2.5 7B (Ollama, GPU)
echo  * Speech Engine: Faster-Whisper large-v3-turbo int8 (CPU)
echo  * Normalizer:    Indian Medical Phonetic Auto-Corrector Active
echo.
echo  Default Clinician Login:
echo    - Email: doctor.offline@voicescribe.local
echo    - Role:  DOCTOR
echo.
echo  Google Meet Extension:
echo    1. Open Chrome and go to: chrome://extensions
echo    2. Turn ON 'Developer mode' (top-right toggle)
echo    3. Click 'Load unpacked' and choose the 'extension' folder in this directory.
echo.
echo To stop VoiceScribe AI, simply close the Backend and Frontend command windows.
echo ==============================================================================
echo.
pause
