param(
  [Parameter(Mandatory = $true)]
  [ValidateSet('Start', 'Stop')]
  [string] $Action
)

$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$RuntimeDir = Join-Path $Root '.runtime'
$LogDir = Join-Path $RuntimeDir 'logs'
$StateFile = Join-Path $RuntimeDir 'service-pids.json'
$PythonExe = Join-Path $RuntimeDir 'python\python.exe'
$ViteScript = Join-Path $Root 'process-plan-agent-ui\node_modules\vite\bin\vite.js'
$ApiDir = Join-Path $Root 'process-plan-agent-api'
$UiDir = Join-Path $Root 'process-plan-agent-ui'

function Find-Node {
  $bundled = Join-Path $RuntimeDir 'node\node.exe'
  if (Test-Path -LiteralPath $bundled) {
    return $bundled
  }

  $command = Get-Command 'node.exe' -ErrorAction SilentlyContinue
  if ($command) {
    return $command.Source
  }

  $fallback = Join-Path $env:ProgramFiles 'nodejs\node.exe'
  if (Test-Path -LiteralPath $fallback) {
    return $fallback
  }

  throw @'
Node.js was not found.

Options:
1. Run: powershell -File scripts\prepare-offline-node.ps1
2. Install Node.js 20+ system-wide
3. Place a portable Node at .runtime\node\node.exe
'@
}

function Get-PortOwner {
  param([int] $Port)

  $connection = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
    Select-Object -First 1
  if ($connection) {
    return [int] $connection.OwningProcess
  }

  return $null
}

function Get-ManagedProcess {
  param(
    [ValidateSet('api', 'ui')]
    [string] $Service,
    [int] $ProcessId
  )

  if ($ProcessId -le 0) {
    return $null
  }

  $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
  if (-not $process) {
    return $null
  }

  if ($Service -eq 'api') {
    if ($process.ExecutablePath -and
        $process.ExecutablePath.Equals($PythonExe, [StringComparison]::OrdinalIgnoreCase) -and
        $process.CommandLine -and
        $process.CommandLine.IndexOf('uvicorn app.main:app', [StringComparison]::OrdinalIgnoreCase) -ge 0) {
      return $process
    }
  }
  elseif ($process.CommandLine -and
          $process.CommandLine.IndexOf($ViteScript, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
    return $process
  }

  return $null
}

function Read-State {
  if (-not (Test-Path -LiteralPath $StateFile)) {
    return $null
  }

  try {
    return Get-Content -Raw -LiteralPath $StateFile | ConvertFrom-Json
  }
  catch {
    return $null
  }
}

function Write-State {
  param(
    [int] $ApiProcessId,
    [int] $UiProcessId
  )

  $current = Read-State
  if ($current -and
      [int] $current.api -eq $ApiProcessId -and
      [int] $current.ui -eq $UiProcessId) {
    return
  }

  New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
  [ordered]@{
    api = $ApiProcessId
    ui = $UiProcessId
  } | ConvertTo-Json | Set-Content -LiteralPath $StateFile -Encoding UTF8
}

function Stop-ManagedProcess {
  param(
    [ValidateSet('api', 'ui')]
    [string] $Service,
    [int] $ProcessId
  )

  $process = Get-ManagedProcess -Service $Service -ProcessId $ProcessId
  if (-not $process) {
    return $false
  }

  Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
  Wait-Process -Id $ProcessId -Timeout 5 -ErrorAction SilentlyContinue
  return $true
}

function Wait-Endpoint {
  param(
    [string] $Name,
    [string] $Url,
    [int] $ProcessId
  )

  for ($attempt = 0; $attempt -lt 40; $attempt++) {
    if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) {
      throw "$Name exited before it became ready."
    }

    try {
      Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 | Out-Null
      return
    }
    catch {
      Start-Sleep -Milliseconds 500
    }
  }

  throw "$Name did not become ready within 20 seconds."
}

function Show-LogTail {
  param([string] $Path)

  if ((Test-Path -LiteralPath $Path) -and (Get-Item -LiteralPath $Path).Length -gt 0) {
    Write-Host "`nLast lines from $Path"
    Get-Content -LiteralPath $Path -Tail 20
  }
}

function Start-Application {
  if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw 'The local Python runtime is missing. Run bootstrap-windows.cmd first.'
  }
  if (-not (Test-Path -LiteralPath $ViteScript)) {
    throw 'Frontend dependencies are missing. Run bootstrap-windows.cmd first.'
  }

  $nodeExe = Find-Node
  New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

  $apiOut = Join-Path $LogDir 'api.out.log'
  $apiErr = Join-Path $LogDir 'api.err.log'
  $uiOut = Join-Path $LogDir 'ui.out.log'
  $uiErr = Join-Path $LogDir 'ui.err.log'
  $started = @()

  try {
    $apiProcessId = Get-PortOwner -Port 8000
    if ($apiProcessId) {
      if (-not (Get-ManagedProcess -Service api -ProcessId $apiProcessId)) {
        throw "Port 8000 is already used by another program (PID $apiProcessId)."
      }
      Write-Host "API is already running (PID $apiProcessId)."
    }
    else {
      $env:PROCESSMIND_DATA_DIR = Join-Path $Root 'data'
      $apiProcess = Start-Process -FilePath $PythonExe `
        -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000') `
        -WorkingDirectory $ApiDir `
        -RedirectStandardOutput $apiOut `
        -RedirectStandardError $apiErr `
        -WindowStyle Hidden `
        -PassThru
      $apiProcessId = $apiProcess.Id
      $started += @{ Service = 'api'; ProcessId = $apiProcessId }
      Write-Host "Starting API (PID $apiProcessId)..."
    }

    $uiProcessId = Get-PortOwner -Port 5173
    if ($uiProcessId) {
      if (-not (Get-ManagedProcess -Service ui -ProcessId $uiProcessId)) {
        throw "Port 5173 is already used by another program (PID $uiProcessId)."
      }
      Write-Host "Web UI is already running (PID $uiProcessId)."
    }
    else {
      $uiProcess = Start-Process -FilePath $nodeExe `
        -ArgumentList @("`"$ViteScript`"", '--host', '127.0.0.1', '--port', '5173') `
        -WorkingDirectory $UiDir `
        -RedirectStandardOutput $uiOut `
        -RedirectStandardError $uiErr `
        -WindowStyle Hidden `
        -PassThru
      $uiProcessId = $uiProcess.Id
      $started += @{ Service = 'ui'; ProcessId = $uiProcessId }
      Write-Host "Starting Web UI (PID $uiProcessId)..."
    }

    Wait-Endpoint -Name 'API' -Url 'http://127.0.0.1:8000/' -ProcessId $apiProcessId
    Wait-Endpoint -Name 'Web UI' -Url 'http://127.0.0.1:5173/' -ProcessId $uiProcessId
    Write-State -ApiProcessId $apiProcessId -UiProcessId $uiProcessId

    Write-Host ''
    Write-Host 'ProcessMind is ready.'
    Write-Host 'Web:      http://127.0.0.1:5173'
    Write-Host 'API docs: http://127.0.0.1:8000/docs'
    if ($env:PROCESSMIND_NO_BROWSER -ne '1') {
      Start-Process 'http://127.0.0.1:5173'
    }
  }
  catch {
    foreach ($entry in $started) {
      Stop-ManagedProcess -Service $entry.Service -ProcessId $entry.ProcessId | Out-Null
    }
    Show-LogTail -Path $apiErr
    Show-LogTail -Path $uiErr
    throw
  }
}

function Stop-Application {
  $state = Read-State
  $stoppedAny = $false

  foreach ($service in @('ui', 'api')) {
    $port = if ($service -eq 'api') { 8000 } else { 5173 }
    $processId = 0

    if ($state -and $state.$service) {
      $candidateId = [int] $state.$service
      if (Get-ManagedProcess -Service $service -ProcessId $candidateId) {
        $processId = $candidateId
      }
    }

    if (-not $processId) {
      $candidateId = Get-PortOwner -Port $port
      if ($candidateId -and (Get-ManagedProcess -Service $service -ProcessId $candidateId)) {
        $processId = $candidateId
      }
    }

    if ($processId -and (Stop-ManagedProcess -Service $service -ProcessId $processId)) {
      Write-Host "Stopped $service (PID $processId)."
      $stoppedAny = $true
    }
    else {
      Write-Host "$service is not running."
    }
  }

  Remove-Item -LiteralPath $StateFile -Force -ErrorAction SilentlyContinue
  if ($stoppedAny) {
    Write-Host 'ProcessMind has stopped.'
  }
  else {
    Write-Host 'No ProcessMind services needed to be stopped.'
  }
}

if ($Action -eq 'Start') {
  Start-Application
}
else {
  Stop-Application
}
