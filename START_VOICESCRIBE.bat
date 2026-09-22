@echo off
setlocal enabledelayedexpansion
title VoiceScribe AI - Quick Launcher
color 0a

echo ==============================================================================
echo                      VOICESCRIBE AI - QUICK LAUNCHER
echo ==============================================================================
echo.

:: Check if first-time installation is required
if not exist "%~dp0backend\.venv" (
    echo [INFO] First-time setup detected (backend virtual environment not found).
    echo Redirecting to ONE_CLICK_INSTALL_AND_START.bat ...
    timeout /t 2 >nul
    call "%~dp0ONE_CLICK_INSTALL_AND_START.bat"
    exit /b %errorlevel%
)

if not exist "%~dp0frontend\node_modules" (
    echo [INFO] First-time setup detected (frontend packages not found).
    echo Redirecting to ONE_CLICK_INSTALL_AND_START.bat ...
    timeout /t 2 >nul
    call "%~dp0ONE_CLICK_INSTALL_AND_START.bat"
    exit /b %errorlevel%
)

:: Ensure Ollama is running if installed
ollama --version >nul 2>&1
if %errorlevel% equ 0 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 -UseBasicParsing; exit 0 } catch { exit 1 }" >nul 2>&1
    if !errorlevel! neq 0 (
        echo [INFO] Starting Ollama background service...
        start "" ollama serve
        timeout /t 2 >nul
    )
)

:: 1. Start Backend
echo [1/3] Starting Python Backend on http://127.0.0.1:8000 ...
start "VoiceScribe AI - Backend" cmd /k "cd /d ""%~dp0backend"" && call .venv\Scripts\activate.bat && uvicorn app.main:app --host 127.0.0.1 --port 8000"

timeout /t 2 >nul

:: 2. Start Frontend
echo [2/3] Starting Frontend Workstation on http://127.0.0.1:5173 ...
start "VoiceScribe AI - Frontend" cmd /k "cd /d ""%~dp0frontend"" && npm run dev"

timeout /t 3 >nul

:: 3. Open Browser
echo [3/3] Launching Web Browser...
start http://127.0.0.1:5173

echo.
echo ==============================================================================
echo VoiceScribe AI is running at http://127.0.0.1:5173 !
echo To close VoiceScribe AI, close the Backend and Frontend command windows.
echo ==============================================================================
timeout /t 5 >nul
