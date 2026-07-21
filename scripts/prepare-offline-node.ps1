param(
  [string] $SourceNodeDir = '',
  [string] $SourceNodeZip = ''
)

$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RuntimeDir = Join-Path $Root '.runtime'
$TargetDir = Join-Path $RuntimeDir 'node'
$TargetExe = Join-Path $TargetDir 'node.exe'

function Resolve-SystemNodeDir {
  $command = Get-Command 'node.exe' -ErrorAction SilentlyContinue
  if ($command -and $command.Source) {
    return (Split-Path -Parent $command.Source)
  }

  $fallback = Join-Path $env:ProgramFiles 'nodejs'
  if (Test-Path -LiteralPath (Join-Path $fallback 'node.exe')) {
    return $fallback
  }

  return $null
}

function Copy-NodeTree {
  param(
    [Parameter(Mandatory = $true)]
    [string] $FromDir
  )

  $sourceExe = Join-Path $FromDir 'node.exe'
  if (-not (Test-Path -LiteralPath $sourceExe)) {
    throw "node.exe was not found under: $FromDir"
  }

  if (Test-Path -LiteralPath $TargetDir) {
    Remove-Item -LiteralPath $TargetDir -Recurse -Force
  }
  New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null

  # Official Node win-x64 zip and system installs both work as a directory copy.
  Copy-Item -Path (Join-Path $FromDir '*') -Destination $TargetDir -Recurse -Force

  if (-not (Test-Path -LiteralPath $TargetExe)) {
    throw "Failed to prepare bundled Node at $TargetExe"
  }
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

if ($SourceNodeZip) {
  if (-not (Test-Path -LiteralPath $SourceNodeZip)) {
    throw "Node zip not found: $SourceNodeZip"
  }

  $extractRoot = Join-Path $RuntimeDir 'node-extract-temp'
  if (Test-Path -LiteralPath $extractRoot) {
    Remove-Item -LiteralPath $extractRoot -Recurse -Force
  }
  New-Item -ItemType Directory -Force -Path $extractRoot | Out-Null
  Expand-Archive -LiteralPath $SourceNodeZip -DestinationPath $extractRoot -Force

  $nested = Get-ChildItem -LiteralPath $extractRoot -Directory | Select-Object -First 1
  $fromDir = if ($nested -and (Test-Path -LiteralPath (Join-Path $nested.FullName 'node.exe'))) {
    $nested.FullName
  } elseif (Test-Path -LiteralPath (Join-Path $extractRoot 'node.exe')) {
    $extractRoot
  } else {
    throw "Could not find node.exe inside zip: $SourceNodeZip"
  }

  Copy-NodeTree -FromDir $fromDir
  Remove-Item -LiteralPath $extractRoot -Recurse -Force -ErrorAction SilentlyContinue
}
elseif ($SourceNodeDir) {
  Copy-NodeTree -FromDir $SourceNodeDir
}
else {
  $systemDir = Resolve-SystemNodeDir
  if (-not $systemDir) {
    throw @'
Node.js was not found on this machine.

Install Node.js 20+ first, or run one of:
  powershell -File scripts\prepare-offline-node.ps1 -SourceNodeDir "C:\Program Files\nodejs"
  powershell -File scripts\prepare-offline-node.ps1 -SourceNodeZip "D:\path\node-v22.x.x-win-x64.zip"
'@
  }
  Write-Host "Copying local Node from: $systemDir"
  Copy-NodeTree -FromDir $systemDir
}

$version = & $TargetExe -v
Write-Host "Bundled Node is ready: $TargetExe ($version)"
Write-Host 'Offline packages that include .runtime\node can start without a system Node install.'
