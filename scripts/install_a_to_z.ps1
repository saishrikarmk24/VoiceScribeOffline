<#
.SYNOPSIS
  A-to-Z first-run installer for VoiceScribe Offline on a Windows laptop.

  Skips anything already installed. If Ollama already has a Qwen model it is
  reused (nothing is downloaded). Whisper runs on CPU, so no CUDA Toolkit,
  no PyTorch, no pyannote. Existing .env files are corrected to CPU Whisper.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = ""
)

$ErrorActionPreference = "Continue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

if (-not $RepoRoot) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}
$RepoRoot = (Resolve-Path $RepoRoot.Trim('"').TrimEnd('\')).Path
$Backend = Join-Path $RepoRoot "backend"
$Frontend = Join-Path $RepoRoot "frontend"
$VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"
$LogDir = Join-Path $RepoRoot "install-logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "install_a_to_z.log"
Set-Content -Path $LogFile -Value "VoiceScribe install $(Get-Date -Format s)"
$Total = 8

function Write-Step($n, $msg) {
    Write-Host ""
    Write-Host "[$n/$Total] $msg" -ForegroundColor Cyan
    Add-Content $LogFile "[$n/$Total] $msg"
}

function Write-Ok($msg) {
    Write-Host "  [OK] $msg" -ForegroundColor Green
    Add-Content $LogFile "OK $msg"
}

function Write-Warn($msg) {
    Write-Host "  [!] $msg" -ForegroundColor Yellow
    Add-Content $LogFile "WARN $msg"
}

function Stop-Install($msg) {
    Write-Host ""
    Write-Host "  [ERROR] $msg" -ForegroundColor Red
    Add-Content $LogFile "ERROR $msg"
    exit 1
}

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Test-Cmd($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function Install-Winget([string]$id, [string[]]$extra = @()) {
    if (-not (Test-Cmd "winget")) { return $false }
    Write-Host "  Installing $id via winget..."
    $wingetArgs = @(
        "install", "--id", $id, "-e", "--accept-package-agreements",
        "--accept-source-agreements", "--disable-interactivity"
    ) + $extra
    $p = Start-Process -FilePath "winget" -ArgumentList $wingetArgs -Wait -PassThru -NoNewWindow
    Refresh-Path
    # -1978335189 = already installed
    return ($p.ExitCode -eq 0 -or $p.ExitCode -eq -1978335189)
}

function Install-Download([string]$url, [string[]]$installerArgs, [string]$outName) {
    $dest = Join-Path $env:TEMP $outName
    try {
        Write-Host "  Downloading $outName ..."
        Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing
    } catch {
        Write-Warn "Download failed: $($_.Exception.Message)"
        return $false
    }
    Write-Host "  Running $outName ..."
    if ($outName -like "*.msi") {
        $p = Start-Process -FilePath "msiexec.exe" -ArgumentList (@("/i", "`"$dest`"") + $installerArgs) -Wait -PassThru
    } else {
        $p = Start-Process -FilePath $dest -ArgumentList $installerArgs -Wait -PassThru
    }
    Refresh-Path
    return ($p.ExitCode -eq 0)
}

function Find-Python {
    foreach ($cand in @("py", "python")) {
        if (-not (Test-Cmd $cand)) { continue }
        $ver = (& $cand --version 2>&1) | Out-String
        if ($ver -match "Python 3\.(1[0-3])") { return $cand }
    }
    return $null
}

function Set-EnvValues([string]$path, [hashtable]$values) {
    $lines = @()
    if (Test-Path $path) { $lines = @(Get-Content -Path $path -Encoding UTF8) }
    $seen = @{}
    $out = foreach ($line in $lines) {
        $replaced = $false
        foreach ($key in $values.Keys) {
            if ($line -match "^\s*$([regex]::Escape($key))\s*=") {
                "$key=$($values[$key])"
                $seen[$key] = $true
                $replaced = $true
                break
            }
        }
        if (-not $replaced) { $line }
    }
    $out = @($out)
    foreach ($key in $values.Keys) {
        if (-not $seen.ContainsKey($key)) { $out += "$key=$($values[$key])" }
    }
    # UTF-8 without BOM: a BOM would corrupt the first key for pydantic.
    [IO.File]::WriteAllLines($path, [string[]]$out, (New-Object Text.UTF8Encoding($false)))
}

function Get-OllamaModels {
    try {
        $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 5
        return ,@($tags.models | ForEach-Object { $_.name })
    } catch {
        return $null
    }
}

function Select-QwenModel([string[]]$models) {
    $preferred = @(
        { param($m) $m -eq "qwen2.5:7b" -or $m -eq "qwen2.5:7b-instruct" },
        { param($m) $m -like "qwen2.5*7b*" },
        { param($m) $m -like "qwen2.5*" },
        { param($m) $m -like "qwen*" }
    )
    foreach ($rule in $preferred) {
        $hit = $models | Where-Object { & $rule $_ } | Select-Object -First 1
        if ($hit) { return $hit }
    }
    return $null
}

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  VoiceScribe Offline  |  A-to-Z installer" -ForegroundColor Cyan
Write-Host "  Reuses installed Python / Node / Ollama / Qwen. Whisper on CPU." -ForegroundColor Cyan
Write-Host "  No CUDA Toolkit. No PyTorch. GPU is used only by Ollama." -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "  Folder: $RepoRoot"
Write-Host "  Log:    $LogFile"

if (-not (Test-Path (Join-Path $Backend "requirements.txt"))) {
    Stop-Install "backend\requirements.txt not found under $RepoRoot. Run this from the VoiceScribe folder."
}

# --- 1. VC++ runtime (ctranslate2 / faster-whisper need it) -----------------
Write-Step 1 "Visual C++ runtime"
if (Test-Path "HKLM:\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64") {
    Write-Ok "Already present"
} else {
    $ok = Install-Winget "Microsoft.VCRedist.2015+.x64"
    if (-not $ok) {
        $ok = Install-Download "https://aka.ms/vs/17/release/vc_redist.x64.exe" @("/install", "/quiet", "/norestart") "vc_redist.x64.exe"
    }
    if ($ok) { Write-Ok "Installed" } else { Write-Warn "Could not install. If Whisper fails, install https://aka.ms/vs/17/release/vc_redist.x64.exe" }
}

# --- 2. Python --------------------------------------------------------------
Write-Step 2 "Python 3.10 - 3.13"
Refresh-Path
$Py = Find-Python
if (-not $Py) {
    $ok = Install-Winget "Python.Python.3.12" @("--scope", "user")
    if (-not $ok) {
        Install-Download "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe" `
            @("/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_test=0", "Include_pip=1", "Include_launcher=1") `
            "python-3.12.10-amd64.exe" | Out-Null
    }
    Start-Sleep -Seconds 2
    Refresh-Path
    $Py = Find-Python
}
if (-not $Py) { Stop-Install "Python not found. Install 3.12 from https://www.python.org/downloads/ (tick 'Add to PATH') and rerun." }
$pyVersion = ((& $Py --version 2>&1) | Out-String).Trim()
Write-Ok $pyVersion

# --- 3. Node.js -------------------------------------------------------------
Write-Step 3 "Node.js"
Refresh-Path
if (-not (Test-Cmd "npm.cmd")) {
    $ok = Install-Winget "OpenJS.NodeJS.LTS"
    if (-not $ok) {
        Install-Download "https://nodejs.org/dist/v22.14.0/node-v22.14.0-x64.msi" @("/quiet", "/norestart") "node-v22.14.0-x64.msi" | Out-Null
    }
    Start-Sleep -Seconds 2
    Refresh-Path
}
if (-not (Test-Cmd "npm.cmd")) { Stop-Install "Node.js not found. Install LTS from https://nodejs.org/ and rerun." }
$nodeVersion = ((& node --version 2>&1) | Out-String).Trim()
Write-Ok "node $nodeVersion"

# --- 4. Ollama + Qwen (reuse existing model) --------------------------------
Write-Step 4 "Ollama + Qwen (reuses a model you already have)"
Refresh-Path
$models = Get-OllamaModels
if ($null -eq $models) {
    if (-not (Test-Cmd "ollama")) {
        $ok = Install-Winget "Ollama.Ollama"
        if (-not $ok) { Install-Download "https://ollama.com/download/OllamaSetup.exe" @("/S") "OllamaSetup.exe" | Out-Null }
        Refresh-Path
    }
    if (-not (Test-Cmd "ollama")) { Stop-Install "Ollama not found. Install from https://ollama.com and rerun." }
    Write-Host "  Starting Ollama..."
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    for ($i = 0; $i -lt 15 -and $null -eq $models; $i++) {
        Start-Sleep -Seconds 2
        $models = Get-OllamaModels
    }
}
if ($null -eq $models) { Stop-Install "Ollama is installed but not answering on http://127.0.0.1:11434. Open the Ollama app and rerun." }
Write-Ok "Ollama is running. Models: $(if ($models.Count) { $models -join ', ' } else { '(none)' })"

$QwenModel = Select-QwenModel $models
if ($QwenModel) {
    Write-Ok "Using existing model '$QwenModel' (no download)"
} else {
    $QwenModel = "qwen2.5:7b"
    Write-Host "  No Qwen model found. Pulling $QwenModel (about 4.7 GB)..."
    & ollama pull $QwenModel
    if ($LASTEXITCODE -ne 0) { Write-Warn "ollama pull failed. Rerun later: ollama pull $QwenModel" } else { Write-Ok "$QwenModel downloaded" }
}

# --- 5. .env (always forced to CPU Whisper) ---------------------------------
Write-Step 5 ".env settings (CPU Whisper + $QwenModel)"
$example = Join-Path $RepoRoot ".env.example"
$forced = @{
    "AI_MODE"                        = "local"
    "LOCAL_LLM_BASE_URL"             = "http://localhost:11434/v1"
    "LOCAL_LLM_MODEL"                = $QwenModel
    "ASR_PROVIDER"                   = "faster_whisper"
    "FASTER_WHISPER_MODEL"           = "large-v3-turbo"
    "ASR_DEVICE"                     = "cpu"
    "ASR_COMPUTE_TYPE"               = "int8"
    "INDIC_WHISPER_USE_TRANSFORMERS" = "false"
    "INDIC_ASR_PROMPT_BIASING"       = ""
    "DIARIZATION_PROVIDER"           = "local"
}
foreach ($target in @((Join-Path $RepoRoot ".env"), (Join-Path $Backend ".env"))) {
    if (-not (Test-Path $target)) { Copy-Item $example $target -Force }
    Set-EnvValues $target $forced
    Write-Ok "Updated $target"
}

# --- 6. Python venv + CPU Faster-Whisper ------------------------------------
Write-Step 6 "Python packages + CPU Faster-Whisper"
$env:CUDA_VISIBLE_DEVICES = "-1"
Set-Location $Backend
if (Test-Path $VenvPython) {
    & $VenvPython -c "import sys" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Existing backend\.venv is broken (copied from another PC?). Recreating it."
        Remove-Item -Recurse -Force (Join-Path $Backend ".venv")
    }
}
if (-not (Test-Path $VenvPython)) {
    & $Py -m venv .venv
    if (-not (Test-Path $VenvPython)) { Stop-Install "Could not create backend\.venv with $Py." }
    Write-Ok "Created backend\.venv"
}
& $VenvPython -m pip install --upgrade pip --disable-pip-version-check -q
& $VenvPython -m pip install -r requirements.txt --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { Stop-Install "pip install -r backend\requirements.txt failed (see messages above)." }
Write-Ok "Python packages installed"

Write-Host "  Downloading / loading Whisper large-v3-turbo on CPU (about 1.6 GB first time)..."
$whisperCheckPath = Join-Path $env:TEMP "voicescribe_whisper_check.py"
@"
from faster_whisper import WhisperModel
WhisperModel('large-v3-turbo', device='cpu', compute_type='int8')
print('WHISPER_CPU_OK')
"@ | Set-Content -Path $whisperCheckPath -Encoding ASCII
& $VenvPython $whisperCheckPath
if ($LASTEXITCODE -ne 0) {
    Write-Warn "Whisper failed to load on CPU. Install the VC++ runtime (step 1 link) and rerun."
} else {
    Write-Ok "Whisper is ready on CPU"
}

& $VenvPython -c "import asyncio; from app.core.database import init_database, dispose_database; asyncio.run(init_database()); asyncio.run(dispose_database())"
if ($LASTEXITCODE -eq 0) { Write-Ok "Database ready" } else { Write-Warn "Database init failed; the backend will retry on start." }

# --- 7. Frontend ------------------------------------------------------------
Write-Step 7 "Frontend packages"
Set-Location $Frontend
& npm.cmd install --no-audit --no-fund
if ($LASTEXITCODE -ne 0) { Stop-Install "npm install failed (see messages above)." }
Write-Ok "Frontend ready"

# --- 8. Launch --------------------------------------------------------------
Write-Step 8 "Launching VoiceScribe"
Set-Location $RepoRoot
$backendCmd = "cd /d `"$Backend`" && set CUDA_VISIBLE_DEVICES=-1&& `".venv\Scripts\python.exe`" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", $backendCmd
Start-Sleep -Seconds 4
Start-Process -FilePath "cmd.exe" -ArgumentList "/k", "cd /d `"$Frontend`" && npm.cmd run dev"
Start-Sleep -Seconds 5
Start-Process "http://127.0.0.1:5173"

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Green
Write-Host "  VoiceScribe is starting at http://127.0.0.1:5173" -ForegroundColor Green
Write-Host "  LLM:    $QwenModel via Ollama (GPU)" -ForegroundColor Green
Write-Host "  Speech: Faster-Whisper large-v3-turbo on CPU" -ForegroundColor Green
Write-Host "  Next time just run START_VOICESCRIBE.bat" -ForegroundColor Green
Write-Host "  Close the two black windows to stop." -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
exit 0
