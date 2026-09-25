@echo off
setlocal
title VoiceScribe Offline - A to Z installer
color 0b
echo.
echo ==============================================================================
echo   VoiceScribe Offline  -  one file, first-time setup on a friend's PC
echo ==============================================================================
echo   This installs Python, Node.js, Ollama, Qwen 2.5 7B, CPU Whisper, then
echo   starts the app. You do NOT install CUDA Toolkit or PyTorch.
echo   First run can take 15-40 minutes (Qwen 7B is about 4.7 GB).
echo ==============================================================================
echo.

cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_a_to_z.ps1" -RepoRoot "%~dp0"
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
