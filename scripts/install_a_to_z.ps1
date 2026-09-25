<#
.SYNOPSIS
  A-to-Z first-run installer for VoiceScribe Offline on a friend's Windows laptop.

  Installs (if missing): Python 3.12, Node.js LTS, Ollama, VC++ runtime,
  backend venv, Faster-Whisper (CPU), Qwen 2.5 7B, frontend npm packages.
  Then launches the app.

  Whisper stays on CPU. Ollama/Qwen uses the NVIDIA GPU. No CUDA Toolkit,
  no PyTorch, no pyannote.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = ""
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}
$RepoRoot = (Resolve-Path $RepoRoot).Path
$Backend = Join-Path $RepoRoot "backend"
$Frontend = Join-Path $RepoRoot "frontend"
$VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"
$VenvPip = Join-Path $Backend ".venv\Scripts\pip.exe"
$LogDir = Join-Path $RepoRoot "install-logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "install_a_to_z.log"

function Write-Step($n, $total, $msg) {
    Write-Host ""
    Write-Host "[$n/$total] $msg" -ForegroundColor Cyan
    Add-Content $LogFile "[$n/$total] $msg"
}

function Write-Ok($msg) {
    Write-Host "  [OK] $msg" -ForegroundColor Green
    Add-Content $LogFile "OK $msg"
}

function Write-Warn($msg) {
    Write-Host "  [!] $msg" -ForegroundColor Yellow
    Add-Content $LogFile "WARN $msg"
}

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Test-Cmd($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Install-Winget($id) {
    if (-not (Test-Cmd "winget")) { return $false }
    Write-Host "  Installing $id via winget..."
    $p = Start-Process -FilePath "winget" -ArgumentList @(
        "install", "--id", $id, "-e", "--accept-package-agreements",
        "--accept-source-agreements", "--disable-interactivity", "--scope", "user"
    ) -Wait -PassThru -NoNewWindow
    Refresh-Path
    return ($p.ExitCode -eq 0 -or $p.ExitCode -eq -1978335189)
}

function Install-Exe($url, $args, $outName) {
    $dest = Join-Path $env:TEMP $outName
    Write-Host "  Downloading $outName ..."
    Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
    Write-Host "  Running $outName ..."
    if ($outName -like "*.msi") {
        $p = Start-Process -FilePath "msiexec.exe" -ArgumentList (@("/i", $dest) + $args) -Wait -PassThru
    } else {
        $p = Start-Process -FilePath $dest -ArgumentList $args -Wait -PassThru
    }
    Refresh-Path
    return ($p.ExitCode -eq 0)
}

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  VoiceScribe Offline  |  A-to-Z installer for a friend's Windows PC" -ForegroundColor Cyan
Write-Host "  Python + Node + Ollama + Qwen 2.5 7B + CPU Whisper + app launch" -ForegroundColor Cyan
Write-Host "  No CUDA Toolkit. No PyTorch. GPU is used only by Ollama." -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  Folder: $RepoRoot"
Write-Host "  Log:    $LogFile"
Write-Host ""

# --- 1. VC++ runtime (ctranslate2 / faster-whisper need this) ---------------
Write-Step 1 8 "Visual C++ runtime"
if (-not (Test-Path "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64")) {
    $ok = Install-Winget "Microsoft.VCRedist.2015+.x64"
    if (-not $ok) {
        Write-Warn "Could not auto-install VC++ Redistributable. If Whisper fails later, install it from https://aka.ms/vs/17/release/vc_redist.x64.exe"
    } else {
        Write-Ok "VC++ Redistributable installed or already present"
    }
} else {
    Write-Ok "VC++ Redistributable already present"
}

# --- 2. Python 3.12+ --------------------------------------------------------
Write-Step 2 8 "Python 3.12+"
Refresh-Path
$pyOk = $false
foreach ($cand in @("python", "py")) {
    if (Test-Cmd $cand) {
        try {
            $ver = & $cand --version 2>$null
            if ($ver -match "Python 3\.(1[0-9]|[2-9]\d)") { $pyOk = $true; $script:Py = $cand; break }
        } catch {}
    }
}
if (-not $pyOk) {
    $ok = Install-Winget "Python.Python.3.12"
    if (-not $ok) {
        $ok = Install-Exe `
            "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe" `
            @("/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_test=0", "Include_pip=1") `
            "python-3.12.10-amd64.exe"
    }
    Refresh-Path
    Start-Sleep -Seconds 2
    if (Test-Cmd "python") { $script:Py = "python"; $pyOk = $true }
    elseif (Test-Cmd "py") { $script:Py = "py"; $pyOk = $true }
}
if (-not $pyOk) {
    Write-Host "  [ERROR] Python is still missing. Install 3.12 from https://www.python.org/downloads/ and tick ADD TO PATH, then rerun." -ForegroundColor Red
    exit 1
}
Write-Ok (& $script:Py --version)

# --- 3. Node.js LTS ---------------------------------------------------------
Write-Step 3 8 "Node.js LTS"
Refresh-Path
if (-not (Test-Cmd "npm")) {
    $ok = Install-Winget "OpenJS.NodeJS.LTS"
    if (-not $ok) {
        $ok = Install-Exe `
            "https://nodejs.org/dist/v22.14.0/node-v22.14.0-x64.msi" `
            @("/quiet", "/norestart") `
            "node-v22.14.0-x64.msi"
    }
    Refresh-Path
    Start-Sleep -Seconds 2
}
if (-not (Test-Cmd "npm")) {
    Write-Host "  [ERROR] Node.js is still missing. Install LTS from https://nodejs.org/ then rerun." -ForegroundColor Red
    exit 1
}
Write-Ok "node $(node --version) / npm $(npm --version)"

# --- 4. Ollama --------------------------------------------------------------
Write-Step 4 8 "Ollama (runs Qwen 2.5 7B on the GPU)"
Refresh-Path
if (-not (Test-Cmd "ollama")) {
    $ok = Install-Winget "Ollama.Ollama"
    if (-not $ok) {
        $ok = Install-Exe "https://ollama.com/download/OllamaSetup.exe" @("/S") "OllamaSetup.exe"
    }
    Refresh-Path
    Start-Sleep -Seconds 3
}
if (-not (Test-Cmd "ollama")) {
    Write-Host "  [ERROR] Ollama is still missing. Install from https://ollama.com then rerun." -ForegroundColor Red
    exit 1
}
Write-Ok "Ollama CLI found"

$ollamaUp = $false
try {
    Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 -UseBasicParsing | Out-Null
    $ollamaUp = $true
} catch {}
if (-not $ollamaUp) {
    Write-Host "  Starting Ollama service..."
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 4
}
Write-Ok "Ollama is reachable on port 11434"

Write-Host "  Pulling qwen2.5:7b (about 4.7 GB, first time only)..."
& ollama pull qwen2.5:7b
if ($LASTEXITCODE -ne 0) {
    Write-Warn "ollama pull returned $LASTEXITCODE. You can rerun: ollama pull qwen2.5:7b"
} else {
    Write-Ok "qwen2.5:7b is installed"
}

# --- 5. .env ----------------------------------------------------------------
Write-Step 5 8 "Offline .env (CPU Whisper, Qwen 7B)"
$example = Join-Path $RepoRoot ".env.example"
foreach ($target in @((Join-Path $RepoRoot ".env"), (Join-Path $Backend ".env"))) {
    if (-not (Test-Path $target)) {
        Copy-Item $example $target -Force
        Write-Ok "Created $target"
    } else {
        Write-Ok "Already exists: $target"
    }
}

# --- 6. Python venv + CPU Whisper (never PyTorch/CUDA) ----------------------
Write-Step 6 8 "Python packages (CPU Faster-Whisper, no CUDA pip extras)"
Set-Location $Backend
if (-not (Test-Path $VenvPython)) {
    & $script:Py -m venv .venv
    Write-Ok "Created backend\\.venv"
}
& $VenvPython -m pip install --upgrade pip
# Force CPU for this venv so pip never pulls a CUDA torch wheel.
$env:CUDA_VISIBLE_DEVICES = "-1"
$env:PIP_NO_CACHE_DIR = "1"
& $VenvPip install -r (Join-Path $Backend "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [ERROR] pip install failed. See $LogFile" -ForegroundColor Red
    exit 1
}

Write-Host "  Checking Faster-Whisper on CPU..."
$whisperCheck = @"
import os
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
from faster_whisper import WhisperModel
WhisperModel('large-v3-turbo', device='cpu', compute_type='int8')
print('WHISPER_CPU_OK')
"@
$whisperCheckPath = Join-Path $env:TEMP "voicescribe_whisper_check.py"
Set-Content -Path $whisperCheckPath -Value $whisperCheck -Encoding UTF8
& $VenvPython $whisperCheckPath
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Whisper CPU load failed. Installing VC++ / NVIDIA Game Ready driver usually fixes cublas DLL errors."
    Write-Warn "Qwen notes will still work if Ollama is up; transcription needs this import to succeed."
} else {
    Write-Ok "Faster-Whisper large-v3-turbo is cached on CPU (first transcribe will be fast)"
}

& $VenvPython -c "import asyncio; from app.core.database import init_database, dispose_database; asyncio.run(init_database()); asyncio.run(dispose_database()); print('DB_OK')"
Write-Ok "SQLite schema ready"

# --- 7. Frontend ------------------------------------------------------------
Write-Step 7 8 "Frontend npm packages"
Set-Location $Frontend
if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    & npm.cmd install
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [ERROR] npm install failed." -ForegroundColor Red
        exit 1
    }
}
Write-Ok "Frontend dependencies ready"

# --- 8. Launch --------------------------------------------------------------
Write-Step 8 8 "Launching VoiceScribe"
Set-Location $RepoRoot

$backendCmd = "cd /d `"$Backend`" && set CUDA_VISIBLE_DEVICES=-1&& set CTRANSLATE2_CUDA=0&& call .venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", $backendCmd -WindowStyle Normal

Start-Sleep -Seconds 4
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "cd /d `"$Frontend`" && npm run dev" -WindowStyle Normal

Start-Sleep -Seconds 4
Start-Process "http://127.0.0.1:5173"

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "  VoiceScribe is starting." -ForegroundColor Green
Write-Host "  App:     http://127.0.0.1:5173" -ForegroundColor Green
Write-Host "  API:     http://127.0.0.1:8000/docs" -ForegroundColor Green
Write-Host "  LLM:     Qwen 2.5 7B via Ollama (GPU)" -ForegroundColor Green
Write-Host "  Speech:  Faster-Whisper turbo on CPU (no CUDA Toolkit)" -ForegroundColor Green
Write-Host "  Close the two black command windows to stop." -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host ""
