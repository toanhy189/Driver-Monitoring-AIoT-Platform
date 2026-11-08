param([switch]$Check)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $taskPython)) {
    throw 'Create edge-ai/.venv with Python 3.13 and install requirements-lock.txt first.'
}
$taskModel = Join-Path $taskRoot 'ml-runs/nthu-gap-history-20261107/full/selected.joblib'
if (!(Test-Path -LiteralPath $taskModel)) { throw 'Copy the private approved model bundle first; see docs/final-ai-model.md.' }
$taskHash = (Get-FileHash -LiteralPath $taskModel -Algorithm SHA256).Hash.ToLowerInvariant()
if ($taskHash -ne '5e25b03d26a7577982d9c357d3f87fe2a1bf2a31c205b447b782ec5006ea7b0d') {
    throw 'Artifact differs from the frozen submission model; review the version before running.'
}
$previousMode, $previousPath = $env:AI_MODEL_MODE, $env:AI_MODEL_PATH
try {
    $env:AI_MODEL_MODE = 'ml'
    $env:AI_MODEL_PATH = $taskModel
    if ($Check) { & $taskPython -X utf8 (Join-Path $taskRoot 'main.py') --check }
    else { & $taskPython -X utf8 (Join-Path $taskRoot 'main.py') }
    $taskExit = $LASTEXITCODE
} finally {
    $env:AI_MODEL_MODE, $env:AI_MODEL_PATH = $previousMode, $previousPath
}
exit $taskExit
