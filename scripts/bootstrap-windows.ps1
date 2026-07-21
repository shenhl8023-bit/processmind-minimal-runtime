$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Runtime = Join-Path $Root '.runtime'
$PythonDir = Join-Path $Runtime 'python'
$PythonExe = Join-Path $PythonDir 'python.exe'
$PythonZip = Join-Path $Runtime 'python-embed.zip'
$GetPip = Join-Path $Runtime 'get-pip.py'
$BundledNode = Join-Path $Runtime 'node\node.exe'
$Downloader = Join-Path $PSScriptRoot 'download-url.js'
$ApiRequirements = Join-Path $Root 'process-plan-agent-api\requirements.txt'
$PinnedRequirements = Join-Path $Root 'requirement.txt'
$UiDir = Join-Path $Root 'process-plan-agent-ui'
$ViteScript = Join-Path $UiDir 'node_modules\vite\bin\vite.js'
$Offline = $env:PROCESSMIND_OFFLINE -eq '1'

function Find-CommandPath {
  param(
    [string] $Name,
    [string[]] $Fallbacks = @()
  )

  $command = Get-Command $Name -ErrorAction SilentlyContinue
  if ($command) {
    return $command.Source
  }

  foreach ($fallback in $Fallbacks) {
    if (Test-Path -LiteralPath $fallback) {
      return $fallback
    }
  }

  throw "$Name was not found."
}

function Test-BackendReady {
  if (-not (Test-Path -LiteralPath $PythonExe)) {
    return $false
  }

  & $PythonExe -c "import fastapi, uvicorn, sqlalchemy, fitz, docx, openpyxl" *> $null
  return ($LASTEXITCODE -eq 0)
}

function Test-FrontendReady {
  return (Test-Path -LiteralPath $ViteScript)
}

function Get-NodeAndNpm {
  if (Test-Path -LiteralPath $BundledNode) {
    $nodeDir = Split-Path -Parent $BundledNode
    $npmCmd = Join-Path $nodeDir 'npm.cmd'
    if (-not (Test-Path -LiteralPath $npmCmd)) {
      throw "Bundled Node is missing npm.cmd at $npmCmd"
    }
    return @{
      Node = $BundledNode
      Npm = $npmCmd
    }
  }

  return @{
    Node = (Find-CommandPath 'node.exe' @("$env:ProgramFiles\nodejs\node.exe"))
    Npm = (Find-CommandPath 'npm.cmd' @("$env:ProgramFiles\nodejs\npm.cmd"))
  }
}

New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Runtime 'logs') | Out-Null

$backendReady = Test-BackendReady
$frontendReady = Test-FrontendReady

if ($backendReady -and $frontendReady) {
  Write-Host 'Offline/local runtime already ready (Python packages + node_modules).'
  if (Test-Path -LiteralPath $BundledNode) {
    Write-Host "Bundled Node: $BundledNode"
  }
  Write-Host 'Windows bootstrap is ready.'
  exit 0
}

if ($Offline -and (-not $backendReady -or -not $frontendReady)) {
  throw @'
PROCESSMIND_OFFLINE=1 but required runtime files are incomplete.

Expected:
  .runtime\python\python.exe with backend packages installed
  process-plan-agent-ui\node_modules (vite present)

Rebuild the offline package on a machine with network access, then copy it again.
'@
}

if (-not $backendReady) {
  if (-not (Test-Path -LiteralPath $PythonExe)) {
    Write-Host 'Downloading portable Python...'
    if (-not (Test-Path -LiteralPath $PythonZip) -or (Get-Item -LiteralPath $PythonZip).Length -lt 1000000) {
      $tools = Get-NodeAndNpm
      & $tools.Node $Downloader 'https://www.python.org/ftp/python/3.13.5/python-3.13.5-embed-amd64.zip' $PythonZip
      if ($LASTEXITCODE -ne 0) {
        throw 'Python download failed.'
      }
    }

    New-Item -ItemType Directory -Force -Path $PythonDir | Out-Null
    Expand-Archive -LiteralPath $PythonZip -DestinationPath $PythonDir -Force
  }

  $PthFile = Join-Path $PythonDir 'python313._pth'
  if (Test-Path -LiteralPath $PthFile) {
    $pth = Get-Content -LiteralPath $PthFile
    $updated = $pth -replace '^#import site$', 'import site'
    Set-Content -LiteralPath $PthFile -Value $updated -Encoding ASCII
  }

  Write-Host 'Checking pip...'
  & $PythonExe -m pip --version *> $null
  if ($LASTEXITCODE -ne 0) {
    if (-not (Test-Path -LiteralPath $GetPip)) {
      $tools = Get-NodeAndNpm
      & $tools.Node $Downloader 'https://bootstrap.pypa.io/get-pip.py' $GetPip
      if ($LASTEXITCODE -ne 0) {
        throw 'get-pip.py download failed.'
      }
    }

    & $PythonExe $GetPip --no-cache-dir --no-warn-script-location
    if ($LASTEXITCODE -ne 0) {
      throw 'pip installation failed.'
    }
  }

  $requirementsToInstall = if (Test-Path -LiteralPath $PinnedRequirements) {
    $PinnedRequirements
  } else {
    $ApiRequirements
  }

  Write-Host "Installing backend dependencies from $(Split-Path -Leaf $requirementsToInstall)..."
  $env:PIP_NO_CACHE_DIR = '1'
  $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
  & $PythonExe -m pip install --no-cache-dir --timeout 120 --retries 5 --no-warn-script-location -r $requirementsToInstall
  if ($LASTEXITCODE -ne 0) {
    throw 'Backend dependency installation failed.'
  }
}
else {
  Write-Host 'Backend Python runtime already ready.'
}

if (-not $frontendReady) {
  $tools = Get-NodeAndNpm
  Write-Host 'Installing frontend dependencies...'
  Push-Location $UiDir
  try {
    & $tools.Npm ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) {
      throw 'Frontend dependency installation failed.'
    }
  }
  finally {
    Pop-Location
  }
}
else {
  Write-Host 'Frontend node_modules already ready.'
}

Write-Host 'Windows bootstrap is ready.'
