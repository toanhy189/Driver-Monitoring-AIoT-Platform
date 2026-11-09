param([string]$DataDir = "$PSScriptRoot/../ml-data/yawdd-20261110")
$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath($DataDir)
New-Item -ItemType Directory -Path $taskRoot -Force | Out-Null
$taskRoot = (Resolve-Path -LiteralPath $taskRoot).Path
$taskRef = '222e94371df161bd673fcec4a1a755afef18ddd7'
$taskBase = 'https://opensource.silicon-austria.com/api/v4/projects/18/repository/files/'
$taskFiles = @(
    @{Name='annotations.zip'; Remote='dataset.zip'; Hash='b5ca0bc584e5b1311d62de2f37f848bdeb1f5a5cf239a5c5e420f853465b6d66'},
    @{Name='author-demo.avi'; Remote='assets%2F1-FemaleNoGlasses-Yawning.avi'; Hash='11015776ca2194d8b5c636c106a140bb8d03c4120ecdc3b29b83a35917702163'}
)
foreach ($taskFile in $taskFiles) {
    $taskTarget = [IO.Path]::GetFullPath((Join-Path $taskRoot $taskFile.Name))
    $taskPart = $taskTarget + '.part'
    foreach ($taskPath in @($taskTarget,$taskPart)) {
        if (!$taskPath.StartsWith($taskRoot + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Download target left its named directory' }
    }
    if ((Test-Path -LiteralPath $taskTarget) -and (Get-FileHash -LiteralPath $taskTarget -Algorithm SHA256).Hash.ToLower() -eq $taskFile.Hash) { continue }
    & curl.exe --fail --location --silent --show-error --retry 2 --max-time 900 --output $taskPart ($taskBase+$taskFile.Remote+'/raw?ref='+$taskRef)
    if ($LASTEXITCODE -ne 0) { throw "Download failed: $($taskFile.Name)" }
    if ((Get-FileHash -LiteralPath $taskPart -Algorithm SHA256).Hash.ToLower() -ne $taskFile.Hash) { throw "Checksum mismatch: $($taskFile.Name)" }
    Move-Item -LiteralPath $taskPart -Destination $taskTarget -Force
}
$taskRecord = [ordered]@{
    source='https://opensource.silicon-austria.com/mujtabaa/yawdd'; commit=$taskRef
    annotations_sha256=$taskFiles[0].Hash; author_demo_sha256=$taskFiles[1].Hash
    usage='Non-commercial research under the original YawDD and derived annotation terms'
    original_full_videos_downloaded=$false; status='VERIFIED_ANNOTATIONS_AND_PUBLIC_DEMO'
}
[IO.File]::WriteAllText((Join-Path $taskRoot 'source.json'),($taskRecord | ConvertTo-Json),[Text.UTF8Encoding]::new($false))
Write-Host 'Verified YawDD+ annotations and one author demo. This does not include the original full video dataset.'
