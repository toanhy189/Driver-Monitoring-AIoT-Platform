param(
    [string]$BundlePath = "$PSScriptRoot/ml-runs/multisignal-v2-20261110/selected",
    [ValidateSet('cpu','cuda')][string]$Device = 'cpu',
    [string]$CalibrationPath,
    [string]$ProfileId,
    [ValidateSet('glasses','no-glasses')][string]$Condition = 'glasses',
    [int]$Camera = 0,
    [switch]$EyeTrial,
    [switch]$HeadTrial,
    [switch]$DisableHeadDownRisk,
    [switch]$Check,
    [switch]$Demo
)
$ErrorActionPreference = 'Stop'
$taskPython = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
$taskBundle = (Resolve-Path -LiteralPath $BundlePath).Path
$taskManifest = Get-Content -Raw -LiteralPath (Join-Path $taskBundle 'manifest.json') | ConvertFrom-Json
if ($taskManifest.format -ne 'driver-multisignal-v2') { throw 'A separate v2 bundle is required.' }
if ($Condition -eq 'glasses' -and !$CalibrationPath) {
    $taskReviewedPath = Join-Path $PSScriptRoot 'ml-runs/eye-calibration/20261110T113633Z-c1a71e6e-v5/report.json'
    $taskReviewPath = Join-Path (Split-Path -Parent $taskReviewedPath) 'fresh-trial-review.json'
    if (!(Test-Path -LiteralPath $taskReviewedPath -PathType Leaf) -or !(Test-Path -LiteralPath $taskReviewPath -PathType Leaf)) {
        throw 'The reviewed glasses profile is missing on this machine. Supply its actual CalibrationPath and ProfileId; no automatic fallback.'
    }
    $taskReview = Get-Content -LiteralPath $taskReviewPath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($taskReview.status -ne 'PASSED') { throw 'The saved glasses profile has not passed its fresh trial.' }
    $taskReviewedProfile = Get-Content -LiteralPath $taskReviewedPath -Raw -Encoding utf8 | ConvertFrom-Json
    $CalibrationPath = $taskReviewedPath
    if (!$ProfileId) { $ProfileId = $taskReviewedProfile.profile_id }
    Write-Host 'Using the reviewed glasses v5 profile for this operator/camera setup.'
}
if ($CalibrationPath -and !$ProfileId) { throw 'A calibration requires its matching ProfileId.' }
if ($Camera -lt 0) { throw 'Camera index must be nonnegative.' }
if ($Demo -and ($EyeTrial -or $HeadTrial)) {
    throw 'Guided trials are private diagnostics. Run without -Demo.'
}
if ($EyeTrial -and $HeadTrial) { throw 'Choose either -EyeTrial or -HeadTrial.' }
$taskPrevious = @{}
foreach ($taskName in @('AI_MODEL_MODE','AI_MULTISIGNAL_BUNDLE','AI_MULTISIGNAL_DEVICE',
    'AI_EYE_CLOSURE_GUARD_ENABLED','AI_EYE_CLOSURE_CALIBRATION','AI_PROFILE_ID','AI_CAPTURE_CONDITION','AI_CAMERA_INDEX','AI_HEAD_DOWN_RISK_ENABLED')) {
    $taskPrevious[$taskName] = [Environment]::GetEnvironmentVariable($taskName, 'Process')
}
try {
    if (!$Demo) {
        $taskArgs = @('-X','utf8', (Join-Path $PSScriptRoot 'diagnose_multisignal.py'),
            '--bundle',$taskBundle,'--condition',$Condition,'--camera',"$Camera",'--device',$Device,'--auto-close')
        if ($HeadTrial) { $taskArgs += '--head-trial' }
        elseif ($EyeTrial) { $taskArgs += '--eye-trial' } else { $taskArgs += '--acceptance' }
        if (!$DisableHeadDownRisk) { $taskArgs += '--head-down-risk' }
        if ($CalibrationPath) { $taskArgs += @('--calibration',(Resolve-Path -LiteralPath $CalibrationPath).Path,'--profile-id',$ProfileId) }
        if ($Check) { $taskArgs += '--check' }
        else {
            Write-Host 'PRIVATE v2 trial: no MQTT/HTTP/device loads. Q exits.'
            if (!$CalibrationPath -and $Condition -eq 'no-glasses') {
                Write-Host 'No-glasses EAR guard ACTIVE: EAR < 0.20 continuously for 1s; uncalibrated demo fallback.'
            } elseif (!$CalibrationPath) {
                Write-Host 'Glasses EAR guard OFF: requires a matching calibration that has not failed review.'
            }
            if ($HeadTrial) {
                Write-Host 'Private head trial; phases 1..7, no MQTT/HTTP/device outputs.'
                if (!$DisableHeadDownRisk) { Write-Host 'Sustained head-down rule ACTIVE locally: look forward first, then >=12deg downward for 3s maps to DROWSY.' }
            }
            elseif ($EyeTrial) { Write-Host 'Phases 1..4: open, closed, open, talk; auto-close after phase 4.' }
            else { Write-Host 'Full guided phases 1..9; auto-close after phase 9.' }
        }
    } else {
        $env:AI_MODEL_MODE = 'multisignal'
        $env:AI_MULTISIGNAL_BUNDLE = $taskBundle
        $env:AI_MULTISIGNAL_DEVICE = $Device
        $env:AI_EYE_CLOSURE_GUARD_ENABLED = if ($CalibrationPath -or $Condition -eq 'no-glasses') { 'true' } else { 'false' }
        $env:AI_EYE_CLOSURE_CALIBRATION = if ($CalibrationPath) { (Resolve-Path -LiteralPath $CalibrationPath).Path } else { $null }
        $env:AI_PROFILE_ID = $ProfileId
        $env:AI_CAPTURE_CONDITION = $Condition
        $env:AI_CAMERA_INDEX = "$Camera"
        $env:AI_HEAD_DOWN_RISK_ENABLED = if ($DisableHeadDownRisk) { 'false' } else { 'true' }
        $taskArgs = @('-X','utf8',(Join-Path $PSScriptRoot 'main.py'))
        if ($Check) { $taskArgs += '--check' }
        else {
            Write-Host 'V2 DEMO: camera, audio, video upload and MQTT can trigger configured ESP32 outputs. Q exits.'
            if (!$DisableHeadDownRisk) { Write-Host 'Look FORWARD and hold still for the first 5 seconds. Sustained head-down >=12deg for 3s maps to DROWSY (posture warning).' }
        }
    }
    $taskPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $taskPython @taskArgs
        $taskExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $taskPreference }
} finally {
    foreach ($taskName in $taskPrevious.Keys) {
        [Environment]::SetEnvironmentVariable($taskName, $taskPrevious[$taskName], 'Process')
    }
}
exit $taskExit
