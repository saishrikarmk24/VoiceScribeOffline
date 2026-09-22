# ==============================================================================
# VoiceScribe AI - 100% Offline Local Clinical Workstation Launch Script
# ==============================================================================

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "    VoiceScribe AI - 100% Offline Local Clinical Workstation          " -ForegroundColor Cyan
Write-Host "    Zero API Keys | Zero Cloud Dependencies | 100% Free & Private     " -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

$offlineRoot = $PSScriptRoot
$backendDir = Join-Path $offlineRoot "backend"
$frontendDir = Join-Path $offlineRoot "frontend"

# 1. Verify Ollama / Local LLM Server Status
Write-Host "[1/4] Checking Local Offline LLM Server (Ollama)..." -ForegroundColor Yellow
$ollamaRunning = $false
try {
    $response = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method Get -TimeoutSec 3 -ErrorAction Stop
    $ollamaRunning = $true
    Write-Host "  [+] Ollama server is running at http://localhost:11434" -ForegroundColor Green
    
    # Check if target model is present
    $modelNames = $response.models | ForEach-Object { $_.name }
    $targetModel = "qwen2.5:1.5b"
    $hasModel = $modelNames | Where-Object { $_ -like "*$targetModel*" -or $_ -like "*qwen2.5:3b*" -or $_ -like "*qwen2.5:7b*" }
    
    if ($hasModel) {
        Write-Host "  [+] Found clinical model: $hasModel" -ForegroundColor Green
    } else {
        Write-Host "  [-] Model '$targetModel' not found. Download with: ollama pull $targetModel" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  [-] Ollama is not currently running at http://localhost:11434" -ForegroundColor Yellow
    Write-Host "      To use local offline AI note generation:" -ForegroundColor Yellow
    Write-Host "      1. Download free Ollama from https://ollama.com" -ForegroundColor Yellow
    Write-Host "      2. Run: ollama pull qwen2.5:7b (or qwen2.5:3b)" -ForegroundColor Yellow
    Write-Host "      Note: The system will gracefully use local rule-based draft parsing until Ollama starts." -ForegroundColor Gray
}

# 2. Verify Local Faster-Whisper ASR
Write-Host ""
Write-Host "[2/4] Checking Local Faster-Whisper Speech Recognition..." -ForegroundColor Yellow
try {
    $whisperVer = python -c "import faster_whisper; print(faster_whisper.__version__)" 2>$null
    if ($whisperVer) {
        Write-Host "  [+] faster-whisper v$whisperVer installed and ready on CPU" -ForegroundColor Green
    } else {
        Write-Host "  [-] faster-whisper not detected in python. Install with: pip install faster-whisper" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  [-] Python environment check skipped." -ForegroundColor Gray
}

# 3. Launch Backend
Write-Host ""
Write-Host "[3/4] Starting MedScribe Offline Backend (FastAPI on port 8000)..." -ForegroundColor Yellow
$backendProcess = Start-Process -FilePath "python" -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 8000" -WorkingDirectory $backendDir -PassThru

Start-Sleep -Seconds 3

# 4. Launch Frontend
Write-Host ""
Write-Host "[4/4] Starting MedScribe Offline Frontend (Vite on port 5173)..." -ForegroundColor Yellow
$frontendProcess = Start-Process -FilePath "npm.cmd" -ArgumentList "run dev" -WorkingDirectory $frontendDir -PassThru

Start-Sleep -Seconds 2

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "  MedScribe Offline is LIVE at: http://localhost:5173                 " -ForegroundColor Green
Write-Host "  Backend API Documentation:    http://localhost:8000/docs            " -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "Press Ctrl+C or close this window to stop the offline services."
Write-Host ""

try {
    Start-Process "http://localhost:5173"
    Wait-Process -Id $backendProcess.Id
} finally {
    if ($backendProcess -and (-not $backendProcess.HasExited)) {
        Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($frontendProcess -and (-not $frontendProcess.HasExited)) {
        Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
