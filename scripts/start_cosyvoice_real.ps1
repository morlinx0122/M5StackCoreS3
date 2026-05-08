param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 9002,
    [string]$RepoDir = ".third_party\CosyVoice",
    [string]$ModelDir = ".models\CosyVoice2-0.5B",
    [string]$Mode = "cosyvoice2_zero_shot",
    [string]$PromptText = $env:COSYVOICE_PROMPT_TEXT,
    [string]$PromptAudio = $env:COSYVOICE_PROMPT_AUDIO,
    [switch]$UseCuda
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$gatewayDir = Join-Path $repoRoot "gateway"
$python = Join-Path $gatewayDir ".venv\Scripts\python.exe"
$cosyRepo = Join-Path $repoRoot $RepoDir
$cosyModel = Join-Path $repoRoot $ModelDir

if (-not (Test-Path -LiteralPath $python)) {
    throw "Gateway virtual environment not found. Run Gateway setup first."
}

if (-not (Test-Path -LiteralPath $cosyRepo)) {
    throw "CosyVoice repo not found: $cosyRepo. Run scripts/setup_cosyvoice_repo.ps1 first."
}

if (-not (Test-Path -LiteralPath $cosyModel)) {
    throw "CosyVoice model not found: $cosyModel. Download the model first or pass -ModelDir."
}

$env:COSYVOICE_REPO = $cosyRepo
$env:COSYVOICE_MODEL = $cosyModel
$env:COSYVOICE_SERVER_MODE = $Mode
if (-not $UseCuda) {
    $env:CUDA_VISIBLE_DEVICES = "-1"
}
if ($PromptText) {
    $env:COSYVOICE_PROMPT_TEXT = $PromptText
}
if ($PromptAudio) {
    $env:COSYVOICE_PROMPT_AUDIO = $PromptAudio
}

Set-Location $gatewayDir
& $python -m uvicorn optional_services.cosyvoice_server:app --host $HostName --port $Port
