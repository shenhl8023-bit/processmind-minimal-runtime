param(
  [Parameter(Mandatory = $true)]
  [string] $PythonRuntime,
  [Parameter(Mandatory = $true)]
  [string] $Wheelhouse,
  [string] $Destination = '',
  [string] $Requirements = ''
)

$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $Requirements) {
  $Requirements = Join-Path $Root 'requirements-win7-py38.txt'
}
if (-not $Destination) {
  $Destination = Join-Path $Root '.runtime\python'
}

function Resolve-ExistingPath {
  param([string] $Path, [string] $Label)
  if (-not (Test-Path -LiteralPath $Path)) {
    throw "$Label does not exist: $Path"
  }
  return (Resolve-Path -LiteralPath $Path).Path
}

$PythonRuntime = Resolve-ExistingPath $PythonRuntime 'Python 3.8.10 runtime'
$Wheelhouse = Resolve-ExistingPath $Wheelhouse 'wheelhouse'
$Requirements = Resolve-ExistingPath $Requirements 'Win7 requirements lock'

$temporaryRoot = $null
$runtimeSource = $PythonRuntime
try {
  if ((Get-Item -LiteralPath $PythonRuntime).PSIsContainer -eq $false) {
    if ([System.IO.Path]::GetExtension($PythonRuntime).ToLowerInvariant() -ne '.zip') {
      throw 'PythonRuntime must be a directory containing python.exe or a .zip archive.'
    }
    $temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('processmind-python38-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $temporaryRoot | Out-Null
    Expand-Archive -LiteralPath $PythonRuntime -DestinationPath $temporaryRoot -Force
    $runtimeSource = $temporaryRoot
  }

  $pythonSource = Get-ChildItem -LiteralPath $runtimeSource -Filter 'python.exe' -File -Recurse | Select-Object -First 1
  if ($null -eq $pythonSource) {
    throw "PythonRuntime does not contain python.exe: $PythonRuntime"
  }
  $sourceRoot = $pythonSource.Directory.FullName

  if (Test-Path -LiteralPath $Destination) {
    Remove-Item -LiteralPath $Destination -Recurse -Force
  }
  New-Item -ItemType Directory -Force -Path $Destination | Out-Null
  $Destination = (Resolve-Path -LiteralPath $Destination).Path

  Write-Host "Copying CPython runtime from $sourceRoot ..."
  Copy-Item -Path (Join-Path $sourceRoot '*') -Destination $Destination -Recurse -Force
  $PythonExe = Join-Path $Destination 'python.exe'
  if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Copied runtime is missing python.exe: $PythonExe"
  }

  # Some existing portable bundles put Node and unrelated native packages
  # beside CPython. They are not part of the ProcessMind Win7 runtime.
  foreach ($artifact in @('node.exe', 'node-LICENSE.txt', 'npm.cmd', 'npx.cmd', 'cascadio-unpack')) {
    $artifactPath = Join-Path $Destination $artifact
    if (Test-Path -LiteralPath $artifactPath) {
      Remove-Item -LiteralPath $artifactPath -Recurse -Force
    }
  }

  # The embeddable distribution disables site-packages by default. Enabling
  # site is required for the wheel-only installer below and is harmless for a
  # full CPython installation. Add an explicit root site-packages entry as
  # official embeddable ZIPs do not include one by default.
  Get-ChildItem -LiteralPath $Destination -Filter '*._pth' -File -ErrorAction SilentlyContinue | ForEach-Object {
    $pth = Get-Content -LiteralPath $_.FullName -Raw
    if ($pth -notmatch '(?m)^\s*site-packages\s*$') {
      Add-Content -LiteralPath $_.FullName -Value "`r`nsite-packages`r`n"
      $pth = Get-Content -LiteralPath $_.FullName -Raw
    }
    if ($pth -notmatch '(?m)^\s*import\s+site\s*$') {
      Add-Content -LiteralPath $_.FullName -Value "`r`nimport site`r`n"
    }
  }

  $versionOutput = (& $PythonExe --version 2>&1 | Out-String).Trim()
  if ($versionOutput -notmatch '^Python\s+3\.8\.10(?:\s|$)') {
    throw "Expected Python 3.8.10 x64, got: $versionOutput"
  }

  $sitePackages = Join-Path $Destination 'site-packages'
  $pthFile = Get-ChildItem -LiteralPath $Destination -Filter '*._pth' -File -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($null -eq $pthFile -and (Test-Path -LiteralPath (Join-Path $Destination 'Lib\site-packages'))) {
    $sitePackages = Join-Path $Destination 'Lib\site-packages'
  }
  if (Test-Path -LiteralPath $sitePackages) {
    Remove-Item -LiteralPath $sitePackages -Recurse -Force
  }
  New-Item -ItemType Directory -Force -Path $sitePackages | Out-Null

  Write-Host 'Installing the pinned Win7 dependencies from the local wheelhouse ...'
  # The wheel installer is the embedded-runtime equivalent of pip install
  # --no-index --find-links and works on a clean CPython 3.8 archive without pip.
  $wheelInstaller = Join-Path $Root 'scripts\install-win7-wheels.py'
  & $PythonExe $wheelInstaller --requirements $Requirements --wheelhouse $Wheelhouse --target $sitePackages
  if ($LASTEXITCODE -ne 0) {
    throw 'Offline dependency installation failed. Check that the wheelhouse contains CPython 3.8 win_amd64 wheels for every locked package.'
  }

  Write-Host 'Checking runtime imports ...'
  & $PythonExe -c "import fastapi, uvicorn, sqlalchemy, fitz, docx, openpyxl, lxml, pydantic, py7zr"
  if ($LASTEXITCODE -ne 0) {
    throw 'The Win7 runtime import smoke test failed.'
  }

  $validator = Join-Path $Root 'scripts\validate-python38.py'
  $apiSource = Join-Path $Root 'process-plan-agent-api\app'
  & $PythonExe $validator $apiSource
  if ($LASTEXITCODE -ne 0) {
    throw 'Python 3.8 source validation failed.'
  }

  Write-Host "Win7 Python runtime ready: $Destination"
}
finally {
  if ($temporaryRoot -and (Test-Path -LiteralPath $temporaryRoot)) {
    Remove-Item -LiteralPath $temporaryRoot -Recurse -Force -ErrorAction SilentlyContinue
  }
}
