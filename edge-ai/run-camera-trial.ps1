param([string]$CalibrationPath, [switch]$Check)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$taskPython = Join-Path $taskRoot '.venv/Scripts/python.exe'
$taskModel = Join-Path $taskRoot 'ml-runs/nthu-camera-review-20261108/low-false-alarm/selected.joblib'
if (!(Test-Path -LiteralPath $taskPython)) { throw 'Create the locked edge-ai environment first.' }
if (!(Test-Path -LiteralPath $taskModel)) { throw 'Copy the private experimental model bundle first.' }
if ((Get-FileHash -LiteralPath $taskModel -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'a46e09221e8159235a3628f44aab73ddffb266b54ada5e9b24d324bb03fe7e15') {
    throw 'Experimental model hash differs; review it before running.'
}
if ($CalibrationPath) { $CalibrationPath = (Resolve-Path -LiteralPath $CalibrationPath).Path }
$taskNames = @('AI_MODEL_MODE', 'AI_MODEL_PATH', 'AI_EYE_CLOSURE_GUARD_ENABLED', 'AI_EYE_CLOSURE_CALIBRATION', 'AI_DEBUG_PREDICTIONS')
$taskPrevious = @{}
foreach ($taskName in $taskNames) { $taskPrevious[$taskName] = [Environment]::GetEnvironmentVariable($taskName, 'Process') }
try {
    $env:AI_MODEL_MODE = 'ml'
    $env:AI_MODEL_PATH = $taskModel
    $env:AI_EYE_CLOSURE_GUARD_ENABLED = 'true'
    $env:AI_EYE_CLOSURE_CALIBRATION = $CalibrationPath
    $env:AI_DEBUG_PREDICTIONS = 'true'
    # Windows PowerShell 5.1 wraps redirected native stderr as error records.
    # Python logging uses stderr even on success; judge the process exit code.
    $taskLaunchPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        if ($Check) { & $taskPython -X utf8 (Join-Path $taskRoot 'main.py') --check }
        else { & $taskPython -X utf8 (Join-Path $taskRoot 'main.py') }
        $taskExit = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $taskLaunchPreference
    }
} finally {
    foreach ($taskName in $taskNames) { [Environment]::SetEnvironmentVariable($taskName, $taskPrevious[$taskName], 'Process') }
}
exit $taskExit
