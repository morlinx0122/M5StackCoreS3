$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$promptAudioPath = Join-Path $repoRoot '.tmp/clean_prompt.wav'

if (-not (Test-Path -LiteralPath $promptAudioPath)) {
    throw ('Prompt audio not found: ' + $promptAudioPath)
}

$promptTextCodes = @(
    0x4F60, 0x597D, 0xFF0C, 0x6211, 0x662F, 0x684C, 0x9762,
    0x673A, 0x5668, 0x4EBA, 0x3002, 0x73B0, 0x5728, 0x5F00,
    0x59CB, 0x8FDB, 0x884C, 0x8BED, 0x97F3, 0x5408, 0x6210,
    0x6D4B, 0x8BD5, 0xFF0C, 0x8BF7, 0x4FDD, 0x6301, 0x58F0,
    0x97F3, 0x6E05, 0x6670, 0x81EA, 0x7136, 0x3002
)
$env:COSYVOICE_PROMPT_TEXT = -join ($promptTextCodes | ForEach-Object { [char]$_ })
$env:COSYVOICE_PROMPT_AUDIO = $promptAudioPath

$realScript = Join-Path $PSScriptRoot 'start_cosyvoice_real.ps1'
& powershell -NoProfile -ExecutionPolicy Bypass -File $realScript
