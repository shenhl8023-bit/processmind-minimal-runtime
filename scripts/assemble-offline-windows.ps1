param(
  [string] $PartsDir = '',
  [string] $TargetDir = ''
)

$ErrorActionPreference = 'Stop'

if (-not $PartsDir) {
  $PartsDir = (Resolve-Path $PSScriptRoot).Path
  # When shipped inside offline-bundle\, parts sit next to this script.
  if (-not (Test-Path -LiteralPath (Join-Path $PartsDir '01-runtime-python.zip'))) {
    $PartsDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
  }
}

if (-not $TargetDir) {
  $TargetDir = Join-Path (Split-Path -Parent $PartsDir) 'processmind-offline-ready'
}

$parts = @(
  '01-runtime-python.zip',
  '02-node-modules-element-plus.zip',
  '03-node-modules-rest-0.zip',
  '04-node-modules-rest-1.zip',
  '05-node-modules-rest-2.zip',
  '06-app-src-data.zip'
)

Write-Host "Parts directory: $PartsDir"
Write-Host "Target directory: $TargetDir"
Write-Host ''

foreach ($name in $parts) {
  $path = Join-Path $PartsDir $name
  if (-not (Test-Path -LiteralPath $path)) {
    throw "Missing part: $path"
  }
}

if (Test-Path -LiteralPath $TargetDir) {
  Write-Host "Removing existing target: $TargetDir"
  Remove-Item -LiteralPath $TargetDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null

foreach ($name in $parts) {
  $path = Join-Path $PartsDir $name
  Write-Host "Extracting $name ..."
  # Expand-Archive works on Windows PowerShell 5.1 and PowerShell 7+
  Expand-Archive -LiteralPath $path -DestinationPath $TargetDir -Force
}

$pythonExe = Join-Path $TargetDir '.runtime\python\python.exe'
$viteJs = Join-Path $TargetDir 'process-plan-agent-ui\node_modules\vite\bin\vite.js'
$startCmd = Join-Path $TargetDir 'start-windows.cmd'

if (-not (Test-Path -LiteralPath $pythonExe)) {
  throw "Assemble incomplete: missing $pythonExe"
}
if (-not (Test-Path -LiteralPath $viteJs)) {
  throw "Assemble incomplete: missing frontend node_modules (vite)."
}
if (-not (Test-Path -LiteralPath $startCmd)) {
  throw "Assemble incomplete: missing start-windows.cmd"
}

Write-Host ''
Write-Host 'Verifying backend imports...'
& $pythonExe -c "import fastapi, uvicorn, sqlalchemy, fitz, docx, openpyxl"
if ($LASTEXITCODE -ne 0) {
  throw 'Backend packages failed to import after assemble.'
}

Write-Host ''
Write-Host 'Assemble complete.'
Write-Host "Ready folder: $TargetDir"
Write-Host 'Next:'
Write-Host '  1) Optional: powershell -File scripts\prepare-offline-node.ps1'
Write-Host '  2) Double-click start-windows.cmd'
Write-Host ''
Write-Host 'If Node is missing, install Node.js 20+ LTS or bundle it with prepare-offline-node.ps1'
