param(
    [string]$RepoDir = ".third_party\CosyVoice"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$gatewayDir = Join-Path $repoRoot "gateway"
$python = Join-Path $gatewayDir ".venv\Scripts\python.exe"
$cosyRepo = Join-Path $repoRoot $RepoDir
$requirements = Join-Path $cosyRepo "requirements.txt"

if (-not (Test-Path -LiteralPath $python)) {
    throw "Gateway virtual environment not found. Run Gateway setup first."
}

if (-not (Test-Path -LiteralPath $requirements)) {
    throw "CosyVoice requirements not found: $requirements. Run scripts/setup_cosyvoice_repo.ps1 first."
}

$tmpDir = "C:\tmp"
if (-not (Test-Path -LiteralPath $tmpDir)) {
    New-Item -ItemType Directory -Path $tmpDir | Out-Null
}

$constraints = Join-Path $tmpDir "cosyvoice-build-constraints.txt"
Set-Content -Path $constraints -Value @(
    "setuptools<81"
) -Encoding ASCII

& $python -m pip install "setuptools<81" wheel -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host=mirrors.aliyun.com

$previousConstraint = $env:PIP_CONSTRAINT
$env:PIP_CONSTRAINT = $constraints
& $python -m pip install -r $requirements -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host=mirrors.aliyun.com
if ($null -eq $previousConstraint) {
    Remove-Item Env:\PIP_CONSTRAINT -ErrorAction SilentlyContinue
} else {
    $env:PIP_CONSTRAINT = $previousConstraint
}
