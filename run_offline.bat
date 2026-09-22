@echo off
title VoiceScribe AI - Offline Edition
echo ======================================================================
echo    VoiceScribe AI - 100% Offline Local Clinical Workstation
echo    Zero API Keys ^| Zero Cloud Dependencies ^| 100%% Free ^& Private
echo ======================================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_offline.ps1"
pause
