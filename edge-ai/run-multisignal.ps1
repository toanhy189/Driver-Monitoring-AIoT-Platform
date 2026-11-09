param([string]$BundlePath = "$PSScriptRoot/ml-runs/multisignal-20261110/candidate", [ValidateSet('cpu','cuda')][string]$Device = 'cpu', [switch]$Check)
$ErrorActionPreference = 'Stop'
$taskPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
$taskBundle = (Resolve-Path -LiteralPath $BundlePath).Path
if (!(Test-Path -LiteralPath (Join-Path $taskBundle 'manifest.json'))) { throw 'Train or copy the private multisignal bundle first.' }
$taskPrevious = @{}
foreach ($taskName in @('AI_MODEL_MODE','AI_MULTISIGNAL_BUNDLE','AI_MULTISIGNAL_DEVICE','AI_EYE_CLOSURE_GUARD_ENABLED')) {
    $taskPrevious[$taskName] = [Environment]::GetEnvironmentVariable($taskName, 'Process')
}
try {
    $env:AI_MODEL_MODE = 'multisignal'
    $env:AI_MULTISIGNAL_BUNDLE = $taskBundle
    $env:AI_MULTISIGNAL_DEVICE = $Device
    $env:AI_EYE_CLOSURE_GUARD_ENABLED = 'false'
    $taskLaunchPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        if ($Check) { & $taskPython -X utf8 (Join-Path $PSScriptRoot 'main.py') --check }
        else {
            Write-Host 'Experimental eye/mouth candidate. Camera, local audio and configured MQTT/video workers will start. Q exits.'
            & $taskPython -X utf8 (Join-Path $PSScriptRoot 'main.py')
        }
        $taskExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $taskLaunchPreference }
} finally {
    foreach ($taskName in $taskPrevious.Keys) {
        [Environment]::SetEnvironmentVariable($taskName, $taskPrevious[$taskName], 'Process')
    }
}
exit $taskExit
