param(
  [Parameter(Mandatory = $true)]
  [string] $PythonRuntime,
  [Parameter(Mandatory = $true)]
  [string] $Wheelhouse,
  [string] $OutputDir = '',
  [string] $PackageVersion = '1.0.0',
  [ValidateSet('full', 'basic-trial')]
  [string] $Edition = 'full'
)

$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $OutputDir) {
  $OutputDir = Join-Path $Root 'dist-win7'
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$OutputDir = (Resolve-Path -LiteralPath $OutputDir).Path

$frontendIndex = Join-Path $Root 'process-plan-agent-ui\dist\index.html'
if (-not (Test-Path -LiteralPath $frontendIndex -PathType Leaf)) {
  throw 'Missing process-plan-agent-ui\dist\index.html. Run npm run build before packaging.'
}
$prerequisitePayload = Join-Path $Root 'prerequisites\Windows6.1-KB2533623-x64.msu'
$prerequisiteInstaller = Join-Path $Root 'prerequisites\install-kb2533623.bat'
if (-not (Test-Path -LiteralPath $prerequisitePayload -PathType Leaf) -or
    -not (Test-Path -LiteralPath $prerequisiteInstaller -PathType Leaf)) {
  throw 'Missing Win7 prerequisite files. Expected prerequisites\install-kb2533623.bat and Windows6.1-KB2533623-x64.msu.'
}

$profilePath = Join-Path $Root 'product-profile.json'
if ($Edition -eq 'basic-trial') {
  $profilePath = Join-Path $Root 'profiles\basic-trial.json'
}
$profile = Get-Content -LiteralPath $profilePath -Raw | ConvertFrom-Json
if ($profile.edition -ne $Edition) { throw 'Product profile does not match the requested edition.' }
$buildId = Get-Date -Format 'yyyyMMdd-HHmmss'
$suffix = ''
if ($Edition -eq 'basic-trial') { $suffix = '-basic-trial' }
$zipName = "processmind-win7-windows$suffix-$buildId.zip"
$zipPath = Join-Path $OutputDir $zipName
$artifactStem = [System.IO.Path]::GetFileNameWithoutExtension($zipPath)
$manifestCopy = Join-Path $OutputDir ($artifactStem + '.manifest.json')
$checksumCopy = Join-Path $OutputDir ($artifactStem + '.SHA256SUMS.txt')
$stage = Join-Path $OutputDir ("stage" + $suffix + "-" + $buildId)
$runtimeBuild = Join-Path $OutputDir ("runtime" + $suffix + "-" + $buildId)
$runtimeDestination = Join-Path $runtimeBuild 'python'
$buildRuntime = Join-Path $PSScriptRoot 'build-win7-runtime.ps1'
$stagePackage = Join-Path $PSScriptRoot 'stage-win7-package.ps1'

$existingArtifact = @($zipPath, $manifestCopy, $checksumCopy, $stage, $runtimeBuild) |
  Where-Object { Test-Path -LiteralPath $_ } |
  Select-Object -First 1
if ($existingArtifact) {
  throw "Refusing to overwrite an existing Win7 build artifact: $existingArtifact"
}
New-Item -ItemType Directory -Force -Path $stage | Out-Null

try {
  Write-Host 'Building isolated CPython 3.8.10 runtime ...'
  & $buildRuntime -PythonRuntime $PythonRuntime -Wheelhouse $Wheelhouse -Destination $runtimeDestination
  if ($LASTEXITCODE -ne 0) { throw 'Win7 runtime build failed.' }

  $runtimePython = Join-Path $runtimeDestination 'python.exe'
  & $runtimePython -c "import fastapi, uvicorn, sqlalchemy, fitz, docx, openpyxl, lxml, pydantic, py7zr, eval_type_backport"
  if ($LASTEXITCODE -ne 0) { throw 'Win7 runtime import verification failed.' }

  Write-Host 'Staging application and static frontend ...'
  & $stagePackage -SourceRoot $Root -Destination $stage -PythonRuntime $runtimeDestination -ProductProfile $profilePath
  if ($LASTEXITCODE -ne 0) { throw 'Win7 package staging failed.' }

  $manifest = [ordered]@{
    package = 'ProcessMind'
    package_version = $PackageVersion
    edition = $profile.edition
    trial_expires_at = $profile.expires_at
    target_os = 'Windows 7 SP1'
    architecture = 'x64'
    python = '3.8.10'
    frontend_target = 'chrome109'
    api = [ordered]@{ host = '127.0.0.1'; port = 8000 }
    launcher_config = 'launcher-config.json'
    browser_baseline = @('Chrome 109', 'Edge 109')
    embedded_browser = $false
    node_runtime_included = $false
    windows_prerequisite = [ordered]@{
      id = 'KB2533623'
      installer = 'prerequisites/install-kb2533623.bat'
      payload = 'prerequisites/Windows6.1-KB2533623-x64.msu'
      reboot_required = $true
    }
    created_at_utc = [DateTime]::UtcNow.ToString('o')
    checksum_file = 'SHA256SUMS.txt'
  }
  $manifestPath = Join-Path $stage 'manifest.json'
  $manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding UTF8

  $checksumPath = Join-Path $stage 'SHA256SUMS.txt'
  $checksumLines = New-Object System.Collections.Generic.List[string]
  Get-ChildItem -LiteralPath $stage -File -Recurse | Sort-Object FullName | ForEach-Object {
    if ($_.FullName -eq $checksumPath) { return }
    $relative = $_.FullName.Substring($stage.Length).TrimStart([char[]]('/\')).Replace('\', '/')
    $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    [void] $checksumLines.Add("$hash  $relative")
  }
  $checksumLines | Set-Content -LiteralPath $checksumPath -Encoding UTF8

  Write-Host 'Verifying staged runtime binaries, dependency versions and package checksums ...'
  $packageVerifier = Join-Path $stage 'scripts\verify-win7-package.py'
  & $runtimePython -B $packageVerifier $stage
  if ($LASTEXITCODE -ne 0) { throw 'Win7 package verification failed; ZIP was not created.' }

  Write-Host "Compressing $zipPath ..."
  # Compress-Archive skips hidden files and directories on Windows. The
  # delivery package intentionally contains hidden paths such as .runtime,
  # so use the .NET directory API to include every staged file.
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  [System.IO.Compression.ZipFile]::CreateFromDirectory(
    $stage,
    $zipPath,
    [System.IO.Compression.CompressionLevel]::Optimal,
    $false
  )
  if (-not (Test-Path -LiteralPath $zipPath -PathType Leaf)) { throw 'ZIP output was not created.' }
  Copy-Item -LiteralPath $manifestPath -Destination $manifestCopy
  Copy-Item -LiteralPath $checksumPath -Destination $checksumCopy
}
finally {
  if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
  if (Test-Path -LiteralPath $runtimeBuild) { Remove-Item -LiteralPath $runtimeBuild -Recurse -Force }
}

$sizeMb = [math]::Round((Get-Item -LiteralPath $zipPath).Length / 1MB, 1)
Write-Host ''
Write-Host "Win7 package ready: $zipPath ($sizeMb MB)"
Write-Host 'The package contains no CEF/Qt or Node.js runtime; Chrome 109 or Edge 109 is required on the target machine.'
