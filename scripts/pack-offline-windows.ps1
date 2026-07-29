param(
  [string] $OutputDir = '',
  [switch] $SkipNodePrepare
)

$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $OutputDir) {
  $OutputDir = Join-Path $Root 'dist-offline'
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$date = Get-Date -Format 'yyyyMMdd'
$zipName = "processmind-offline-windows-$date.zip"
$zipPath = Join-Path $OutputDir $zipName
$stage = Join-Path $OutputDir "stage-$date"

$PythonExe = Join-Path $Root '.runtime\python\python.exe'
$ViteScript = Join-Path $Root 'process-plan-agent-ui\node_modules\vite\bin\vite.js'
$BundledNode = Join-Path $Root '.runtime\node\node.exe'
$PrepareNode = Join-Path $PSScriptRoot 'prepare-offline-node.ps1'
$StagePackage = Join-Path $PSScriptRoot 'stage-offline-package.ps1'

if (-not (Test-Path -LiteralPath $PythonExe)) {
  throw 'Missing .runtime\python. Run bootstrap-windows.cmd first.'
}
if (-not (Test-Path -LiteralPath $ViteScript)) {
  throw 'Missing frontend node_modules. Run bootstrap-windows.cmd first.'
}

Write-Host 'Checking backend imports...'
& $PythonExe -c "import fastapi, uvicorn, sqlalchemy, fitz, docx, openpyxl"
if ($LASTEXITCODE -ne 0) {
  throw 'Backend packages incomplete. Run bootstrap-windows.cmd first.'
}

if (-not $SkipNodePrepare -and -not (Test-Path -LiteralPath $BundledNode)) {
  Write-Host 'Bundled Node missing; trying prepare-offline-node.ps1...'
  try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $PrepareNode
  }
  catch {
    Write-Warning "Could not bundle Node automatically: $_"
    Write-Warning 'Package will still be created; target machine needs system Node or a later prepare-offline-node run.'
  }
}

if (Test-Path -LiteralPath $stage) {
  Remove-Item -LiteralPath $stage -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $stage | Out-Null

Write-Host "Staging files into $stage ..."
if (Test-Path -LiteralPath $zipPath) {
  Remove-Item -LiteralPath $zipPath -Force
}
try {
  & $StagePackage -SourceRoot $Root -Destination $stage
}
catch {
  if (Test-Path -LiteralPath $stage) {
    Remove-Item -LiteralPath $stage -Recurse -Force
  }
  throw
}

# Keep .runtime/python and optional .runtime/node; drop runtime noise
$stageRuntime = Join-Path $stage '.runtime'
New-Item -ItemType Directory -Force -Path (Join-Path $stageRuntime 'logs') | Out-Null
Remove-Item -LiteralPath (Join-Path $stageRuntime 'service-pids.json') -Force -ErrorAction SilentlyContinue
Get-ChildItem -LiteralPath (Join-Path $stageRuntime 'logs') -ErrorAction SilentlyContinue | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue

Write-Host "Compressing $zipPath ..."
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zipPath -CompressionLevel Optimal

$hasNode = Test-Path -LiteralPath (Join-Path $stage '.runtime\node\node.exe')
Remove-Item -LiteralPath $stage -Recurse -Force

$sizeMb = [math]::Round((Get-Item -LiteralPath $zipPath).Length / 1MB, 1)
Write-Host ''
Write-Host "Offline package ready: $zipPath ($sizeMb MB)"
if ($hasNode) {
  Write-Host 'Includes bundled Node (.runtime\node). Target machine needs no system Node.'
}
else {
  Write-Host 'WARNING: Bundled Node NOT included. Target needs Node 20+ or run prepare-offline-node.ps1 before packing.'
}
Write-Host 'See README.md for install steps.'
