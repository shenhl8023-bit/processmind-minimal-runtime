param(
  [Parameter(Mandatory = $true)]
  [string] $PythonRuntime,
  [Parameter(Mandatory = $true)]
  [string] $Wheelhouse,
  [string] $OutputDir = '',
  [string] $PackageVersion = '1.0.0'
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

$date = Get-Date -Format 'yyyyMMdd'
$zipName = "processmind-win7-windows-$date.zip"
$zipPath = Join-Path $OutputDir $zipName
$stage = Join-Path $OutputDir ("stage-" + $date)
$runtimeBuild = Join-Path $OutputDir ("runtime-" + $date)
$runtimeDestination = Join-Path $runtimeBuild 'python'
$buildRuntime = Join-Path $PSScriptRoot 'build-win7-runtime.ps1'
$stagePackage = Join-Path $PSScriptRoot 'stage-win7-package.ps1'

if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
if (Test-Path -LiteralPath $runtimeBuild) { Remove-Item -LiteralPath $runtimeBuild -Recurse -Force }
if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null

try {
  Write-Host 'Building isolated CPython 3.8.10 runtime ...'
  & $buildRuntime -PythonRuntime $PythonRuntime -Wheelhouse $Wheelhouse -Destination $runtimeDestination
  if ($LASTEXITCODE -ne 0) { throw 'Win7 runtime build failed.' }

  $runtimePython = Join-Path $runtimeDestination 'python.exe'
  & $runtimePython -c "import fastapi, uvicorn, sqlalchemy, fitz, docx, openpyxl, lxml, pydantic, py7zr, eval_type_backport"
  if ($LASTEXITCODE -ne 0) { throw 'Win7 runtime import verification failed.' }

  Write-Host 'Staging application and static frontend ...'
  & $stagePackage -SourceRoot $Root -Destination $stage -PythonRuntime $runtimeDestination
  if ($LASTEXITCODE -ne 0) { throw 'Win7 package staging failed.' }

  $manifest = [ordered]@{
    package = 'ProcessMind'
    package_version = $PackageVersion
    target_os = 'Windows 7 SP1'
    architecture = 'x64'
    python = '3.8.10'
    frontend_target = 'chrome109'
    api = [ordered]@{ host = '127.0.0.1'; port = 8000 }
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

  $manifestCopy = Join-Path $OutputDir 'manifest.json'
  $checksumCopy = Join-Path $OutputDir 'SHA256SUMS.txt'
  Copy-Item -LiteralPath $manifestPath -Destination $manifestCopy -Force
  Copy-Item -LiteralPath $checksumPath -Destination $checksumCopy -Force

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
}
finally {
  if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
  if (Test-Path -LiteralPath $runtimeBuild) { Remove-Item -LiteralPath $runtimeBuild -Recurse -Force }
}

$sizeMb = [math]::Round((Get-Item -LiteralPath $zipPath).Length / 1MB, 1)
Write-Host ''
Write-Host "Win7 package ready: $zipPath ($sizeMb MB)"
Write-Host 'The package contains no CEF/Qt or Node.js runtime; Chrome 109 or Edge 109 is required on the target machine.'
