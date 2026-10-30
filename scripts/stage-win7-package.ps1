param(
  [Parameter(Mandatory = $true)]
  [string] $SourceRoot,
  [Parameter(Mandatory = $true)]
  [string] $Destination,
  [string] $PythonRuntime = ''
)

$ErrorActionPreference = 'Stop'

$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
New-Item -ItemType Directory -Force -Path $Destination | Out-Null
$Destination = (Resolve-Path -LiteralPath $Destination).Path

function Normalize-RelativePath {
  param([string] $Path)
  return $Path.Replace('\', '/').TrimStart('/')
}

function Get-RelativePath {
  param([string] $Base, [string] $Path)
  return Normalize-RelativePath $Path.Substring($Base.Length).TrimStart([char[]]('/\'))
}

function Test-ForbiddenRelativePath {
  param([string] $RelativePath)
  $path = Normalize-RelativePath $RelativePath
  $name = (Split-Path -Leaf $path).ToLowerInvariant()
  if ($name -in @('.env.example', '.env.compose.example')) { return $false }
  if ($path -match '(^|/)node_modules(?:/|$)') { return $true }
  if ($path -match '^\.runtime/node(?:/|$)') { return $true }
  if ($path -match '(^|/)(?:\.venv|__pycache__|\.pytest_cache|tests)(?:/|$)') { return $true }
  if ($path -match '(^|/)\.env(?:\.|$)') { return $true }
  if ($path -match '(^|/)(?:uploads?|logs?)(?:/|$)') { return $true }
  if ($name -match '\.db$' -or $name -match '\.(?:sqlite|sqlite3)$' -or $name -match '\.(?:db|sqlite|sqlite3)-(?:wal|shm)$') { return $true }
  if ($name -in @('node.exe', 'node-license.txt', 'npm.cmd', 'npx.cmd')) { return $true }
  if ($name -in @('process_settings.json', 'credentials.json', '.npmrc', '.pypirc', '.ds_store')) { return $true }
  if ($name -match '^(?:credentials?|secrets?|tokens?)(?:\..+)?$') { return $true }
  return $false
}

function Copy-TreeFiltered {
  param(
    [string] $Source,
    [string] $Target,
    [string] $RelativePath
  )

  New-Item -ItemType Directory -Force -Path $Target | Out-Null
  Get-ChildItem -LiteralPath $Source -Force | ForEach-Object {
    $childRelative = Normalize-RelativePath (Join-Path $RelativePath $_.Name)
    if (($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
      throw "Win7 package staging refused reparse point '$childRelative'."
    }
    if (Test-ForbiddenRelativePath $childRelative) {
      return
    }
    if ($_.PSIsContainer) {
      Copy-TreeFiltered -Source $_.FullName -Target (Join-Path $Target $_.Name) -RelativePath $childRelative
      return
    }
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $Target $_.Name) -Force
  }
}

function Copy-FileIfPresent {
  param([string] $RelativePath)
  $source = Join-Path $SourceRoot $RelativePath
  if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
    throw "Required Win7 package file is missing: $RelativePath"
  }
  $target = Join-Path $Destination $RelativePath
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
  $item = Get-Item -LiteralPath $source -Force
  if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw "Win7 package staging refused reparse point '$RelativePath'."
  }
  Copy-Item -LiteralPath $source -Destination $target -Force
}

$frontend = Join-Path $SourceRoot 'process-plan-agent-ui\dist'
if (-not (Test-Path -LiteralPath (Join-Path $frontend 'index.html') -PathType Leaf)) {
  throw 'Missing frontend build: process-plan-agent-ui\dist\index.html. Run npm run build first.'
}

if (-not $PythonRuntime) {
  $PythonRuntime = Join-Path $SourceRoot '.runtime\python'
}
$PythonRuntime = (Resolve-Path -LiteralPath $PythonRuntime).Path
if (-not (Test-Path -LiteralPath (Join-Path $PythonRuntime 'python.exe') -PathType Leaf)) {
  throw "Missing CPython 3.8.10 runtime: $PythonRuntime\python.exe"
}

Copy-TreeFiltered -Source (Join-Path $SourceRoot 'process-plan-agent-api') -Target (Join-Path $Destination 'process-plan-agent-api') -RelativePath 'process-plan-agent-api'
Copy-TreeFiltered -Source $frontend -Target (Join-Path $Destination 'process-plan-agent-ui\dist') -RelativePath 'process-plan-agent-ui/dist'
Copy-TreeFiltered -Source (Join-Path $SourceRoot 'docs\配置模板') -Target (Join-Path $Destination 'docs\配置模板') -RelativePath 'docs/配置模板'
Copy-TreeFiltered -Source (Join-Path $SourceRoot 'prerequisites') -Target (Join-Path $Destination 'prerequisites') -RelativePath 'prerequisites'
Copy-TreeFiltered -Source $PythonRuntime -Target (Join-Path $Destination '.runtime\python') -RelativePath '.runtime/python'

foreach ($file in @(
  'start-win7.bat',
  'stop-win7.cmd',
  'status-win7.cmd',
  'requirements-win7-py38.txt',
  '.env.example',
  'README.md',
  'docs\用户使用说明.md',
  'docs\系统简介.md',
  'docs\Win7功能测试方案-20261025.md',
  'docs\Win7缺陷清单-20261025.md'
)) {
  Copy-FileIfPresent $file
}

foreach ($file in @(
  'scripts\win7_launcher.py',
  'scripts\validate-python38.py',
  'scripts\verify-win7-package.py'
)) {
  Copy-FileIfPresent $file
}

# A second pass protects the package if an allowlisted source directory is
# changed later.  This also makes the contract visible to CI and reviewers.
Get-ChildItem -LiteralPath $Destination -Recurse -Force | ForEach-Object {
  $relative = Get-RelativePath $Destination $_.FullName
  if (($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw "Win7 package staging found a reparse point '$relative'."
  }
  if (Test-ForbiddenRelativePath $relative) {
    throw "Win7 package staging found a forbidden artifact '$relative'."
  }
}

Write-Host "Win7 package staging ready: $Destination"
