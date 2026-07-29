param(
  [Parameter(Mandatory = $true)]
  [string] $SourceRoot,
  [Parameter(Mandatory = $true)]
  [string] $Destination
)

$ErrorActionPreference = 'Stop'

$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
New-Item -ItemType Directory -Force -Path $Destination | Out-Null
$Destination = (Resolve-Path -LiteralPath $Destination).Path

$allowedTopLevelDirectories = @(
  '.runtime',
  'docker',
  'docs',
  'process-plan-agent-api',
  'process-plan-agent-ui',
  'scripts'
)

$allowedTopLevelFiles = @(
  '.env.compose.example',
  '.env.example',
  '.gitignore',
  'bootstrap-windows.cmd',
  'bootstrap.sh',
  'docker-compose.yml',
  'Dockerfile.api',
  'Dockerfile.web',
  'README.md',
  'requirement.txt',
  'start-api.cmd',
  'start-api.sh',
  'start-ui.cmd',
  'start-ui.sh',
  'start-windows.cmd',
  'stop-windows.cmd'
)

$excludedDirectoryNames = [System.Collections.Generic.HashSet[string]]::new(
  [System.StringComparer]::OrdinalIgnoreCase
)
@(
  '.git', '.agents', '__pycache__', '.pytest_cache', '.playwright-cli',
  '.mypy_cache', '.ruff_cache', '.tox', '.nox', '.venv', 'venv',
  'coverage', 'htmlcov', 'dist-offline', 'output'
) | ForEach-Object { [void] $excludedDirectoryNames.Add($_) }

function Normalize-RelativePath {
  param([string] $Path)
  return $Path.Replace('\', '/').TrimStart('/')
}

function Test-ExcludedDirectory {
  param([string] $RelativePath)

  $normalized = Normalize-RelativePath $RelativePath
  $name = Split-Path -Leaf $normalized
  if ($excludedDirectoryNames.Contains($name)) { return $true }
  if ($name -eq 'node_modules' -and $normalized -notmatch '^process-plan-agent-ui/node_modules(?:/|$)') {
    return $true
  }
  if ($normalized -match '^process-plan-agent-api/(?:data|uploads|logs)(?:/|$)') { return $true }
  if ($normalized -match '^process-plan-agent-ui/(?:dist|logs)(?:/|$)') { return $true }
  if ($normalized -match '^\.runtime/logs(?:/|$)') { return $true }
  return $false
}

function Test-ExcludedFile {
  param([string] $RelativePath)

  $normalized = Normalize-RelativePath $RelativePath
  $name = (Split-Path -Leaf $normalized).ToLowerInvariant()
  $extension = [System.IO.Path]::GetExtension($name).ToLowerInvariant()

  if ($normalized -in @('.env.example', '.env.compose.example')) { return $false }
  if ($name -match '^\.env(?:\.|$)') { return $true }
  if ($name -in @('process_settings.json', 'service-pids.json', '.npmrc', '.pypirc', 'credentials.json')) {
    return $true
  }
  if (
    $name -match '^(?:credentials?|secrets?|tokens?|client[_-]?secrets?|service[_-]?account)(?:\..+)?$' -and
    $extension -in @('', '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.config', '.xml', '.properties', '.csv', '.txt')
  ) {
    return $true
  }
  if ($name -in @('id_rsa', 'id_dsa', 'id_ecdsa', 'id_ed25519')) { return $true }
  if ($extension -in @('.zip', '.log', '.pyc', '.pyo', '.db', '.sqlite', '.sqlite3', '.key', '.pfx', '.p12', '.jks')) {
    return $true
  }
  if ($name -match '\.(?:db|sqlite|sqlite3)-(?:wal|shm)$') { return $true }
  if ($name -like 'processmind-*-202*.zip' -or $name -like 'processmind-offline-*.zip') { return $true }
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
    $childRelativePath = Normalize-RelativePath (Join-Path $RelativePath $_.Name)
    if (($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
      throw "Offline package staging refused reparse point '$childRelativePath'."
    }
    if ($_.PSIsContainer) {
      if (Test-ExcludedDirectory $childRelativePath) { return }
      Copy-TreeFiltered -Source $_.FullName -Target (Join-Path $Target $_.Name) -RelativePath $childRelativePath
      return
    }
    if (Test-ExcludedFile $childRelativePath) { return }
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $Target $_.Name) -Force
  }
}

function Test-PlaceholderSecretValue {
  param([string] $Value)

  $normalized = $Value.Trim().Trim('"').Trim("'").Trim().TrimEnd(',')
  if (-not $normalized) { return $true }
  if ($normalized -match '^\$\{[^}]+\}$') { return $true }
  if ($normalized -match '^\{[A-Za-z_][A-Za-z0-9_.-]*\}$') { return $true }
  if ($normalized -match '^%[^%]+%$') { return $true }
  if ($normalized -match '^\$env:[A-Za-z_][A-Za-z0-9_]*$') { return $true }
  if ($normalized -match '^<[^>]+>$') { return $true }
  if ($normalized -match '^(?i:null|none|unset|placeholder|example|changeme|change-me|your-api-key-here|__use_saved__|api[_-]?key|token|password|passwd|secret|a[ -](?:secret|password)|\*+)$') {
    return $true
  }
  if ($normalized -match '^(?i:test|example|dummy|fake|sample)(?:[-_].*)?$') {
    return $true
  }
  return $false
}

function Test-LooksLikeText {
  param([string] $Content)

  if ($null -eq $Content -or $Content.Length -eq 0) { return $true }
  return -not [regex]::IsMatch($Content, '[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')
}

function Get-ScannableTextContent {
  param(
    [System.IO.FileInfo] $File,
    [string] $RelativePath
  )

  if ($File.Length -eq 0) { return '' }

  $maxScanBytes = 10MB
  $probeByteCount = [int] [math]::Min($File.Length, 64KB)
  $stream = [System.IO.File]::Open($File.FullName, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
  try {
    $probeBytes = [byte[]]::new($probeByteCount)
    [void] $stream.Read($probeBytes, 0, $probeByteCount)
  }
  finally {
    $stream.Dispose()
  }

  $encoding = $null
  if ($probeByteCount -ge 4 -and $probeBytes[0] -eq 0x00 -and $probeBytes[1] -eq 0x00 -and $probeBytes[2] -eq 0xFE -and $probeBytes[3] -eq 0xFF) {
    $encoding = [System.Text.UTF32Encoding]::new($true, $true, $true)
  }
  elseif ($probeByteCount -ge 4 -and $probeBytes[0] -eq 0xFF -and $probeBytes[1] -eq 0xFE -and $probeBytes[2] -eq 0x00 -and $probeBytes[3] -eq 0x00) {
    $encoding = [System.Text.UTF32Encoding]::new($false, $true, $true)
  }
  elseif ($probeByteCount -ge 2 -and $probeBytes[0] -eq 0xFE -and $probeBytes[1] -eq 0xFF) {
    $encoding = [System.Text.UnicodeEncoding]::new($true, $true, $true)
  }
  elseif ($probeByteCount -ge 2 -and $probeBytes[0] -eq 0xFF -and $probeBytes[1] -eq 0xFE) {
    $encoding = [System.Text.UnicodeEncoding]::new($false, $true, $true)
  }
  else {
    $encoding = [System.Text.UTF8Encoding]::new($false, $true)
  }

  try {
    $probeContent = $encoding.GetString($probeBytes)
  }
  catch [System.Text.DecoderFallbackException] {
    return $null
  }
  if (-not (Test-LooksLikeText $probeContent)) { return $null }
  if ($File.Length -gt $maxScanBytes) {
    throw "Offline package safety check failed: text file is too large to scan safely: '$RelativePath'."
  }

  try {
    $content = $encoding.GetString([System.IO.File]::ReadAllBytes($File.FullName))
  }
  catch [System.Text.DecoderFallbackException] {
    return $null
  }
  if (-not (Test-LooksLikeText $content)) { return $null }
  return $content
}

function Assert-OfflinePackageSafe {
  param([string] $PackageRoot)

  $secretKeyPattern = '(?:[A-Z0-9_]*(?:API[_-]?KEY|PASSWORD|PASSWD|SECRET)|TOKEN|[A-Z0-9_]*(?:API|AUTH|ACCESS|BEARER|REFRESH|SESSION)[_-]?TOKEN)'
  $quotedAssignmentPattern = '(?im)(?<![A-Z0-9_.])["'']?(?<key>' + $secretKeyPattern + ')["'']?[ \t]*[:=][ \t]*["''](?<value>[^"''\r\n]*)["'']'
  $dependencySecretKeyPattern = '(?:[A-Z0-9_]*(?:API_KEY|API_TOKEN|ACCESS_TOKEN|AUTH_TOKEN|BEARER_TOKEN|PASSWORD|PASSWD|SECRET))'
  $dependencyQuotedAssignmentPattern = '(?m)(?<![A-Z0-9_.])["'']?(?<key>' + $dependencySecretKeyPattern + ')["'']?[ \t]*[:=][ \t]*["''](?<value>[^"''\r\n]*)["'']'
  $lineAssignmentPattern = '(?im)^[ \t]*(?:export[ \t]+)?["'']?(?<key>' + $secretKeyPattern + ')["'']?[ \t]*[:=][ \t]*(?<value>[^#\r\n]*?)[ \t]*[,;]?[ \t]*\r?$'
  $settingsRowPattern = '(?is)"key"\s*:\s*"(?<key>' + $secretKeyPattern + ')"\s*,\s*"value"\s*:\s*"(?<value>[^"]*)"'
  $xmlElementPattern = '(?is)<(?<key>' + $secretKeyPattern + ')(?:\s+[^>]*)?>\s*(?<value>[^<]*)\s*</\k<key>\s*>'
  $csvRowPattern = '(?im)^[ \t]*["'']?(?<key>' + $secretKeyPattern + ')["'']?[ \t]*,[ \t]*["'']?(?<value>[^,"''\r\n]*)["'']?(?:,|\r?$)'
  $tokenPattern = '(?i)\b(?:sk|nvapi|tvly)-[a-z0-9_-]{20,}\b'
  $privateKeyPattern = '(?im)-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----'

  Get-ChildItem -LiteralPath $PackageRoot -Recurse -Force | ForEach-Object {
    if (($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
      $relativePath = Normalize-RelativePath $_.FullName.Substring($PackageRoot.Length)
      throw "Offline package safety check failed: reparse point '$relativePath' is not allowed."
    }
  }

  Get-ChildItem -LiteralPath $PackageRoot -File -Recurse -Force | ForEach-Object {
    $relativePath = Normalize-RelativePath $_.FullName.Substring($PackageRoot.Length)
    if (Test-ExcludedFile $relativePath) {
      throw "Offline package safety check failed: forbidden runtime or secret artifact '$relativePath'."
    }
    if ($relativePath -match '^(?:data|uploads)(?:/|$)' -or $relativePath -match '^process-plan-agent-api/(?:data|uploads|logs)(?:/|$)') {
      throw "Offline package safety check failed: runtime data artifact '$relativePath'."
    }

    $name = $_.Name.ToLowerInvariant()
    $extension = $_.Extension.ToLowerInvariant()
    $isConfigFile = $name -match '^\.env(?:\.|$)' -or $extension -in @(
      '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.config', '.xml', '.properties', '.props', '.conf', '.csv'
    )
    $isBundledDependency = (
      $relativePath -match '^\.runtime/' -or
      $relativePath -match '^process-plan-agent-ui/node_modules/'
    )
    $content = Get-ScannableTextContent -File $_ -RelativePath $relativePath
    if ($null -eq $content) { return }

    $sourceAssignmentPattern = if ($isBundledDependency -and -not $isConfigFile) {
      $dependencyQuotedAssignmentPattern
    }
    else {
      $quotedAssignmentPattern
    }
    foreach ($match in [regex]::Matches($content, $sourceAssignmentPattern)) {
      if (-not (Test-PlaceholderSecretValue $match.Groups['value'].Value)) {
        throw "Offline package safety check failed: non-placeholder secret '$($match.Groups['key'].Value)' in '$relativePath'."
      }
    }
    if ($isConfigFile) {
      foreach ($match in [regex]::Matches($content, $lineAssignmentPattern)) {
        if (-not (Test-PlaceholderSecretValue $match.Groups['value'].Value)) {
          throw "Offline package safety check failed: non-placeholder secret '$($match.Groups['key'].Value)' in '$relativePath'."
        }
      }
      foreach ($match in [regex]::Matches($content, $settingsRowPattern)) {
        if (-not (Test-PlaceholderSecretValue $match.Groups['value'].Value)) {
          throw "Offline package safety check failed: stored secret '$($match.Groups['key'].Value)' in '$relativePath'."
        }
      }
      foreach ($match in [regex]::Matches($content, $xmlElementPattern)) {
        if (-not (Test-PlaceholderSecretValue $match.Groups['value'].Value)) {
          throw "Offline package safety check failed: non-placeholder secret '$($match.Groups['key'].Value)' in '$relativePath'."
        }
      }
      foreach ($match in [regex]::Matches($content, $csvRowPattern)) {
        if (-not (Test-PlaceholderSecretValue $match.Groups['value'].Value)) {
          throw "Offline package safety check failed: non-placeholder secret '$($match.Groups['key'].Value)' in '$relativePath'."
        }
      }
    }
    if ([regex]::IsMatch($content, $tokenPattern)) {
      throw "Offline package safety check failed: probable API token in '$relativePath'."
    }
    if ([regex]::IsMatch($content, $privateKeyPattern)) {
      throw "Offline package safety check failed: private key material in '$relativePath'."
    }
  }
}

foreach ($directoryName in $allowedTopLevelDirectories) {
  $sourcePath = Join-Path $SourceRoot $directoryName
  if (-not (Test-Path -LiteralPath $sourcePath -PathType Container)) { continue }
  $sourceItem = Get-Item -LiteralPath $sourcePath -Force
  if (($sourceItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw "Offline package staging refused reparse point '$directoryName'."
  }
  Copy-TreeFiltered -Source $sourcePath -Target (Join-Path $Destination $directoryName) -RelativePath $directoryName
}

foreach ($fileName in $allowedTopLevelFiles) {
  $sourcePath = Join-Path $SourceRoot $fileName
  if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) { continue }
  $sourceItem = Get-Item -LiteralPath $sourcePath -Force
  if (($sourceItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
    throw "Offline package staging refused reparse point '$fileName'."
  }
  Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $Destination $fileName) -Force
}

Assert-OfflinePackageSafe -PackageRoot $Destination
