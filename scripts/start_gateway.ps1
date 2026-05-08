param(
    [string]$HostName = "0.0.0.0",
    [int]$Port = 8000,
    [switch]$Reload
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$gatewayDir = Join-Path $repoRoot "gateway"
$python = Join-Path $gatewayDir ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Gateway virtual environment not found. Run: cd gateway; python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
}

Set-Location $gatewayDir

$args = @(
    "-m", "uvicorn",
    "main:app",
    "--host", $HostName,
    "--port", "$Port"
)

if ($Reload) {
    $args += "--reload"
}

& $python @args

