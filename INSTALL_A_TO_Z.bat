@echo off
setlocal
title VoiceScribe Offline - A to Z installer
color 0b
echo.
echo ==============================================================================
echo   VoiceScribe Offline  -  one file, first-time setup on a friend's PC
echo ==============================================================================
echo   Installs only what is missing, reuses your existing Ollama Qwen model,
echo   sets up Whisper on CPU, then starts the app. No CUDA Toolkit / PyTorch.
echo   First run downloads Whisper turbo (about 1.6 GB).
echo ==============================================================================
echo.

cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_a_to_z.ps1"
set "ERR=%ERRORLEVEL%"
echo.
if not "%ERR%"=="0" (
    echo Installer exited with code %ERR%.
    echo Log: "%~dp0install-logs\install_a_to_z.log"
    echo.
    pause
    exit /b %ERR%
)
echo.
pause
