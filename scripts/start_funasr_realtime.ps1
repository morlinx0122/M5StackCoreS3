param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 9003,
    [string]$Device = "cpu",
    [string]$StreamingModel = "paraformer-zh-streaming",
    [string]$VadModel = "fsmn-vad",
    [string]$FinalModel = "iic/SenseVoiceSmall"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$gatewayDir = Join-Path $repoRoot "gateway"
$python = Join-Path $gatewayDir ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Gateway virtual environment not found. Run Gateway setup first."
}

$env:FUNASR_DEVICE = $Device
$env:FUNASR_STREAMING_MODEL = $StreamingModel
$env:FUNASR_VAD_MODEL = $VadModel
$env:FUNASR_FINAL_MODEL = $FinalModel

Set-Location $gatewayDir
& $python -m uvicorn optional_services.funasr_realtime_server:app --host $HostName --port $Port
