# PhoenixLedger Inno Setup updater: external process that survives app shutdown.
# Windows PowerShell 5.1 compatible. Does not modify the business database.
param(
  [Parameter(Mandatory=$true)][string]$Installer,
  [Parameter(Mandatory=$true)][string]$Target,
  [Parameter(Mandatory=$true)][int]$ProcessIdToWait,
  [Parameter(Mandatory=$true)][string]$DataDir,
  [Parameter(Mandatory=$true)][string]$ExpectedSha256,
  [Parameter(Mandatory=$true)][string]$Version,
  [string]$HandoffFile = '',
  [string]$AttemptId = '',
  [switch]$PrepareOnly
)
$ErrorActionPreference='Stop'
$updates=Join-Path $DataDir 'updates'
New-Item -ItemType Directory -Force -Path $updates | Out-Null
$log=Join-Path $updates 'installation.log'
$statusFile=Join-Path $updates 'install_status.json'
$failure=$null
$readyFile=Join-Path $updates ('ready_'+[guid]::NewGuid().ToString('N')+'.json')
$started=$null
$backup=''

function Log([string]$line) {
  Add-Content -LiteralPath $log -Encoding UTF8 -Value ('['+(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')+'] '+$line)
}
function Status([string]$state,[string]$detail) {
  @{status=$state; message=$detail; version=$Version; attempt_id=$AttemptId;
    target=$Target; package=$Installer; log=$log; backup=$backup;
    updated_at=(Get-Date).ToString('s')} | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $statusFile -Encoding UTF8
  Log ($state+': '+$detail)
}
function Alert([string]$message) {
  try {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($message,'PhoenixLedger update failed','OK','Error') | Out-Null
  } catch {Log ('Could not display error: '+$_.Exception.Message)}
}

try {
  $Installer=[IO.Path]::GetFullPath($Installer)
  $Target=[IO.Path]::GetFullPath($Target)
  $canonical=[IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\PhoenixLedger\PhoenixLedger.exe'))
  if ($Target -ine $canonical) {throw ('Unexpected installed application path: '+$Target)}
  if ($Version -notmatch '^\d+\.\d+\.\d+$') {throw 'Invalid release version.'}
  if ($ExpectedSha256 -notmatch '^[0-9A-Fa-f]{64}$') {throw 'Invalid expected checksum.'}
  if ([IO.Path]::GetFileName($Installer) -ine ('PhoenixLedger_Setup_'+$Version+'.exe')) {
    throw 'Select the matching PhoenixLedger Setup executable.'
  }
  if (-not (Test-Path -LiteralPath $Installer -PathType Leaf)) {throw 'Windows Setup package was not found.'}
  if ((Get-Item -LiteralPath $Installer).Length -lt 1000000) {throw 'Setup executable is unexpectedly small.'}
  $stream=[IO.File]::OpenRead($Installer)
  try {
    if ($stream.ReadByte() -ne 77 -or $stream.ReadByte() -ne 90) {throw 'File is not a Windows EXE.'}
  } finally { $stream.Dispose() }
  Status 'verifying' 'Verifying Windows Setup download before closing PhoenixLedger.'
  $actual=(Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash
  if ($actual -ine $ExpectedSha256) {throw 'Windows Setup checksum mismatch. No update installed.'}
  if ($HandoffFile) {
    $handoffFull=[IO.Path]::GetFullPath($HandoffFile)
    if ([IO.Path]::GetDirectoryName($handoffFull) -ine [IO.Path]::GetFullPath($updates) -or
      [IO.Path]::GetFileName($handoffFull) -notmatch '^handoff_[0-9a-f]{32}\.ready$') {
      throw 'Invalid updater handoff path.'
    }
    [IO.File]::WriteAllText($handoffFull,'PREPARED',[Text.UTF8Encoding]::new($false))
  }
  Status 'prepared' 'Windows Setup passed hash and format checks; waiting for PhoenixLedger to exit.'
  if ($PrepareOnly) {Status 'preflight_success' 'Windows Setup verified; no files changed.';exit 0}
  if ($ProcessIdToWait -gt 0) {
    $existing=Get-Process -Id $ProcessIdToWait -ErrorAction SilentlyContinue
    if ($existing -and (-not $existing.WaitForExit(90000))) {
      throw 'PhoenixLedger did not exit within 90 seconds; installation cancelled.'
    }
  }
  $appDir=Split-Path -Parent $Target
  if (Test-Path -LiteralPath $Target) {
    $backup=Join-Path $updates ('pre_setup_app_'+(Get-Date -Format 'yyyyMMdd_HHmmss'))
    Status 'backing_up' ('Copying old application to '+$backup)
    Copy-Item -LiteralPath $appDir -Destination $backup -Recurse -Force -ErrorAction Stop
  }
  $setupLog=Join-Path $updates ('inno_setup_'+(Get-Date -Format 'yyyyMMdd_HHmmss')+'.log')
  Status 'installing' ('Running Windows Setup. Detailed Inno log: '+$setupLog)
  # /VERYSILENT avoids an interactive dialog when installing via the Updates tab.
  # The normal Setup EXE remains fully interactive when launched manually.
  $args='/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /SP- /LOG="'+$setupLog+'"'
  $setup=Start-Process -FilePath $Installer -ArgumentList $args -PassThru -Wait -ErrorAction Stop
  if ($setup.ExitCode -ne 0) {throw ('Windows Setup exited with code '+$setup.ExitCode+'; inspect '+$setupLog)}
  if (-not (Test-Path -LiteralPath $Target)) {throw 'Setup reported success but the expected installed EXE is missing.'}
  if (-not (Test-Path -LiteralPath (Join-Path $appDir '_internal\python312.dll'))) {
    throw 'Installed application is missing its Python runtime DLL.'
  }
  Status 'restarting' ('Launching '+$Target)
  $env:BUSINESSDESK_UPDATE_READY_FILE=$readyFile
  try {
    $started=Start-Process -FilePath $Target -WorkingDirectory $appDir -PassThru -ErrorAction Stop
  } finally {Remove-Item Env:BUSINESSDESK_UPDATE_READY_FILE -ErrorAction SilentlyContinue}
  $deadline=(Get-Date).AddSeconds(90)
  $confirmed=$false
  while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 700
    if (Test-Path -LiteralPath $readyFile) {
      $info=Get-Content -LiteralPath $readyFile -Raw | ConvertFrom-Json
      if ([IO.Path]::GetFullPath([string]$info.exe) -ine $Target) {throw 'Application restarted from a different location.'}
      if ([string]$info.version -ne $Version) {throw ('Application restarted with an unexpected version: '+$info.version)}
      $confirmed=$true;break
    }
    $started.Refresh()
    if ($started.HasExited) {throw ('Updated PhoenixLedger exited before login window appeared (exit '+$started.ExitCode+').')}
  }
  if (-not $confirmed) {throw 'PhoenixLedger did not confirm startup in 90 seconds. See startup_errors.log.'}
  Status 'success' ('PhoenixLedger '+$Version+' restarted successfully from '+$Target)
} catch {
  $failure=$_.Exception.Message
  Status 'failed' $failure
  # Preserve any existing app backups for manual recovery. The database is never deleted.
  Alert ($failure+"`r`n`r`n"+'Log file: '+$log+"`r`n"+'Application backup: '+$backup)
} finally {
  Remove-Item -LiteralPath $readyFile -ErrorAction SilentlyContinue
}
if ($failure) {exit 1}
exit 0
