@echo off
setlocal
title VoiceScribe AI - Package for Sharing
color 0e

echo ==============================================================================
echo                      VOICESCRIBE AI - PACKAGE FOR SHARING
echo ==============================================================================
echo.
echo Packaging project into a clean distribution zip (excluding .venv, node_modules,
echo local database files, logs, and temp audio)...
echo.

set "PY_CMD="
python --version >nul 2>&1 && set "PY_CMD=python"
if "%PY_CMD%"=="" (
    py -3 --version >nul 2>&1 && set "PY_CMD=py -3"
)

if "%PY_CMD%"=="" (
    echo [ERROR] Python is required to build the distribution package.
    pause
    exit /b 1
)

%PY_CMD% "%~dp0package_distribution.py"

echo.
pause
