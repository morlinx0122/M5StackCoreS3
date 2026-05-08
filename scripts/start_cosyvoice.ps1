param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 9002
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$gatewayDir = Join-Path $repoRoot "gateway"
$python = Join-Path $gatewayDir ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Gateway virtual environment not found. Run Gateway setup first."
}

Set-Location $gatewayDir
& $python -m uvicorn optional_services.cosyvoice_server:app --host $HostName --port $Port

