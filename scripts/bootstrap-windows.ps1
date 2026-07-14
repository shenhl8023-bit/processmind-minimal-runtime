$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Runtime = Join-Path $Root '.runtime'
$PythonDir = Join-Path $Runtime 'python'
$PythonExe = Join-Path $PythonDir 'python.exe'
$PythonZip = Join-Path $Runtime 'python-embed.zip'
$GetPip = Join-Path $Runtime 'get-pip.py'
$Downloader = Join-Path $PSScriptRoot 'download-url.js'
$ApiRequirements = Join-Path $Root 'process-plan-agent-api\requirements.txt'
$UiDir = Join-Path $Root 'process-plan-agent-ui'

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

$NodeExe = Find-CommandPath 'node.exe' @("$env:ProgramFiles\nodejs\node.exe")
$NpmCmd = Find-CommandPath 'npm.cmd' @("$env:ProgramFiles\nodejs\npm.cmd")

New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Runtime 'logs') | Out-Null

if (-not (Test-Path -LiteralPath $PythonExe)) {
  Write-Host 'Downloading portable Python...'
  if (-not (Test-Path -LiteralPath $PythonZip) -or (Get-Item -LiteralPath $PythonZip).Length -lt 1000000) {
    & $NodeExe $Downloader 'https://www.python.org/ftp/python/3.13.5/python-3.13.5-embed-amd64.zip' $PythonZip
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
    & $NodeExe $Downloader 'https://bootstrap.pypa.io/get-pip.py' $GetPip
    if ($LASTEXITCODE -ne 0) {
      throw 'get-pip.py download failed.'
    }
  }

  & $PythonExe $GetPip --no-cache-dir --no-warn-script-location
  if ($LASTEXITCODE -ne 0) {
    throw 'pip installation failed.'
  }
}

Write-Host 'Installing backend dependencies...'
$env:PIP_NO_CACHE_DIR = '1'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
& $PythonExe -m pip install --no-cache-dir --timeout 120 --retries 5 --no-warn-script-location -r $ApiRequirements
if ($LASTEXITCODE -ne 0) {
  throw 'Backend dependency installation failed.'
}

Write-Host 'Installing frontend dependencies...'
Push-Location $UiDir
try {
  & $NpmCmd ci --no-audit --no-fund
  if ($LASTEXITCODE -ne 0) {
    throw 'Frontend dependency installation failed.'
  }
}
finally {
  Pop-Location
}

Write-Host 'Windows bootstrap is ready.'
