param(
    [string]$TargetDir = ".third_party\CosyVoice",
    [string]$RepoUrl = "https://github.com/FunAudioLLM/CosyVoice.git"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$targetPath = Join-Path $repoRoot $TargetDir
$parent = Split-Path -Parent $targetPath

if (-not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
}

if (Test-Path -LiteralPath $targetPath) {
    Write-Host "CosyVoice repo already exists: $targetPath"
    Write-Host "Updating repository..."
    git -C $targetPath pull --ff-only
    git -C $targetPath submodule update --init --recursive
} else {
    Write-Host "Cloning CosyVoice repo into: $targetPath"
    git clone --recursive $RepoUrl $targetPath
}

Write-Host ""
Write-Host "CosyVoice repo is ready."
Write-Host "Set this in gateway/.env:"
Write-Host "COSYVOICE_REPO=$targetPath"

