# BusinessDesk v2.9.6 ONEDIR updater. PowerShell 5.1 compatible.
# This installer intentionally runs OUTSIDE the application process.
param(
  [Parameter(Mandatory=$true)][string]$Package,
  [Parameter(Mandatory=$true)][string]$Target,
  [Parameter(Mandatory=$true)][int]$ProcessIdToWait,
  [Parameter(Mandatory=$true)][string]$DataDir,
  [Parameter(Mandatory=$true)][string]$ExpectedSha256,
  [string]$Version = '',
  [switch]$AllowFreshInstall,
  [switch]$CreateShortcuts,
  [string]$HandoffFile = '',
  [string]$AttemptId = '',
  [switch]$PrepareOnly
)
$ErrorActionPreference='Stop'
$updates=Join-Path $DataDir 'updates'
New-Item -ItemType Directory -Path $updates -Force | Out-Null
$log=Join-Path $updates 'installation.log'
$statusFile=Join-Path $updates 'install_status.json'
$targetDir=''
$stage=''
$previousDir=''
$smokeData=''
$readyFile=Join-Path $updates ('ready_'+[guid]::NewGuid().ToString('N')+'.json')
$installed=$false
$oldMoved=$false
$started=$null
$failure=$null

function Write-Log([string]$message) {
  Add-Content -LiteralPath $log -Encoding UTF8 -Value ('['+(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')+'] '+$message)
}
function Write-Status([string]$state,[string]$message) {
  $status=@{status=$state;message=$message;version=$Version;target=$Target;package=$Package;
    attempt_id=$AttemptId;log=$log;backup=$previousDir;updated_at=(Get-Date).ToString('s')}
  $status | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $statusFile -Encoding UTF8
  Write-Log ($state+': '+$message)
}
function Show-Failure([string]$message) {
  try {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($message,'BusinessDesk update failed','OK','Error') | Out-Null
  } catch { Write-Log ('Could not show error message: '+$_.Exception.Message) }
}
function Ensure-Zip-Safe([string]$zip,[string]$outDir) {
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $archive=[IO.Compression.ZipFile]::OpenRead($zip)
  try {
    $entries=@($archive.Entries | Where-Object {$_.Name -ne ''})
    if ($entries.Count -lt 3 -or $entries.Count -gt 12000) {throw 'Unexpected update file count.'}
    $names=@($entries | ForEach-Object {$_.FullName.Replace('\','/')})
    if (-not ($names -ccontains 'TDZIGNS_BusinessDesk.exe')) {throw 'Update missing TDZIGNS_BusinessDesk.exe.'}
    if (-not ($names -ccontains '_internal/python312.dll')) {throw 'Update missing _internal/python312.dll. Download the entire v2.9.6+ GitHub release ZIP.'}
    $total=[int64]0
    $seen=@{}
    $root=[IO.Path]::GetFullPath($outDir).TrimEnd('\')+'\'
    foreach ($entry in $entries) {
      $name=$entry.FullName.Replace('\','/')
      if (-not ($name -ceq 'TDZIGNS_BusinessDesk.exe' -or $name.StartsWith('_internal/')) -or
          $name.StartsWith('/') -or $name.Contains('\') -or
          $name -match '(^|/)\.\.(/|$)' -or $name.Contains(':')) {
        throw ('Unsafe path in update ZIP: '+$name)
      }
      if ($seen.ContainsKey($name.ToLowerInvariant())) {throw ('Duplicate ZIP entry: '+$name)}
      $seen[$name.ToLowerInvariant()]=$true
      $total += [int64]$entry.Length
      if ($total -gt 1000000000) {throw 'Update would extract more than 1GB.'}
      $absolute=[IO.Path]::GetFullPath((Join-Path $outDir $name.Replace('/','\')))
      if (-not $absolute.StartsWith($root,[StringComparison]::OrdinalIgnoreCase)) {
        throw ('Unsafe extraction destination: '+$name)
      }
    }
    if (($archive.GetEntry('TDZIGNS_BusinessDesk.exe')).Length -lt 100000) {throw 'Invalid Windows executable size.'}
    foreach ($entry in $entries) {
      $output=Join-Path $outDir $entry.FullName.Replace('/','\')
      $folder=Split-Path -Parent $output
      if (-not (Test-Path -LiteralPath $folder)) {New-Item -Path $folder -ItemType Directory -Force | Out-Null}
      [IO.Compression.ZipFileExtensions]::ExtractToFile($entry,$output,$false)
    }
  } finally { $archive.Dispose() }
}
function Make-Shortcuts([string]$exe) {
  $wsh=New-Object -ComObject WScript.Shell
  foreach ($folder in @([Environment]::GetFolderPath('Desktop'),[Environment]::GetFolderPath('Programs'))) {
    if (-not $folder) {continue}
    if (-not (Test-Path -LiteralPath $folder)) {New-Item -ItemType Directory -Path $folder -Force | Out-Null}
    $link=$wsh.CreateShortcut((Join-Path $folder 'TDZIGNS BusinessDesk.lnk'))
    $link.TargetPath=$exe
    $link.WorkingDirectory=Split-Path -Parent $exe
    $link.IconLocation=$exe+',0'
    $link.Save()
  }
}

try {
  Write-Log 'Starting BusinessDesk ONEDIR update helper.'
  $Package=[IO.Path]::GetFullPath($Package)
  $Target=[IO.Path]::GetFullPath($Target)
  $canonical=[IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Programs\TDZIGNS BusinessDesk\TDZIGNS_BusinessDesk.exe'))
  if ($Target -ine $canonical) {throw ('Refusing unexpected target location: '+$Target+'. Expected: '+$canonical)}
  $targetDir=Split-Path -Parent $Target
  $parentDir=Split-Path -Parent $targetDir
  $basename=Split-Path -Leaf $targetDir
  if ($Package -eq $Target) {throw 'Package is the installed executable.'}
  if (-not (Test-Path -LiteralPath $Package -PathType Leaf)) {throw ('Update ZIP missing: '+$Package)}
  if ([IO.Path]::GetExtension($Package) -ine '.zip') {throw 'BusinessDesk v2.9.6+ requires a full update ZIP, not a single EXE.'}
  if ($ExpectedSha256 -notmatch '^[A-Fa-f0-9]{64}$') {throw 'Invalid SHA-256 digest.'}
  Write-Status 'verifying' ('Checking update ZIP; target '+$Target)
  $actual=(Get-FileHash -LiteralPath $Package -Algorithm SHA256).Hash
  if ($actual -ine $ExpectedSha256) {throw 'Update ZIP SHA-256 hash mismatch. Installation stopped.'}
  New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
  $stage=Join-Path $parentDir ($basename+'.stage_'+[guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $stage -Force | Out-Null
  Ensure-Zip-Safe $Package $stage
  $candidate=Join-Path $stage 'TDZIGNS_BusinessDesk.exe'
  if (-not (Test-Path -LiteralPath $candidate)) {throw 'Prepared EXE not found.'}
  if (-not (Test-Path -LiteralPath (Join-Path $stage '_internal\python312.dll'))) {throw 'Missing Python runtime DLL after extraction.'}

  # Test all imports and DLL loading *before* shutting down the old application.
  # Use an isolated smoke-test LOCALAPPDATA so production database is untouched.
  $smokeData=Join-Path $updates ('smoke_'+[guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $smokeData -Force | Out-Null
  $previousLocal=$env:LOCALAPPDATA
  try {
    $env:LOCALAPPDATA=$smokeData
    $probe=Start-Process -FilePath $candidate -ArgumentList '--smoke-test' -WorkingDirectory $stage -PassThru -ErrorAction Stop
    $finished=$probe.WaitForExit(45000)
    if (-not $finished) {
      try { & taskkill.exe /PID $probe.Id /T /F 2>$null | Out-Null } catch {}
      throw 'Runtime smoke test timed out. A DLL loading error dialog or security software may be blocking startup.'
    }
    if ($probe.ExitCode -ne 0) {throw ('Runtime smoke test failed with exit code '+$probe.ExitCode+'. Check Windows runtime dependencies, antivirus quarantine, or application packaging.')}
  } finally { $env:LOCALAPPDATA=$previousLocal }
  Write-Status 'prepared' 'Verified update ZIP and Python DLL; smoke test passed.'
  if ($HandoffFile) {
    $handoffFull=[IO.Path]::GetFullPath($HandoffFile)
    $updatesFull=[IO.Path]::GetFullPath($updates)
    if ([IO.Path]::GetDirectoryName($handoffFull) -ine $updatesFull -or
        [IO.Path]::GetFileName($handoffFull) -notmatch '^handoff_[0-9a-f]{32}\.ready$') {
      throw 'Unexpected update handoff path.'
    }
    [IO.File]::WriteAllText($handoffFull,'PREPARED',[Text.UTF8Encoding]::new($false))
    Write-Log 'Handoff acknowledged; awaiting application shutdown.'
  }
  if ($PrepareOnly) {Write-Status 'preflight_success' 'ZIP and Python runtime validated; no files changed.';return}
  if ($ProcessIdToWait -gt 0) {
    $old=Get-Process -Id $ProcessIdToWait -ErrorAction SilentlyContinue
    if ($old) {
      Write-Status 'waiting' 'Waiting for existing BusinessDesk process to exit.'
      if (-not $old.WaitForExit(90000)) {throw 'Existing BusinessDesk process did not close within 90 seconds.'}
    }
  }
  # Backup whole installed folder to preserve EXE AND its runtime files.
  $previousDir=Join-Path $parentDir ($basename+'.backup_'+(Get-Date -Format 'yyyyMMdd_HHmmss')+'_'+[guid]::NewGuid().ToString('N').Substring(0,6))
  if (Test-Path -LiteralPath $targetDir) {
    Write-Status 'backing_up' ('Moving previous application folder to '+$previousDir)
    Move-Item -LiteralPath $targetDir -Destination $previousDir -ErrorAction Stop
    $oldMoved=$true
  } elseif (-not $AllowFreshInstall) {throw ('Application is not installed at '+$Target+'. Run the repair installer instead.')}
  Write-Status 'installing' ('Installing app and Python DLLs to '+$targetDir)
  Move-Item -LiteralPath $stage -Destination $targetDir -ErrorAction Stop
  $stage=''
  $installed=$true
  $env:BUSINESSDESK_UPDATE_READY_FILE=$readyFile
  try {
    $started=Start-Process -FilePath $Target -WorkingDirectory $targetDir -PassThru -ErrorAction Stop
  } finally {Remove-Item Env:BUSINESSDESK_UPDATE_READY_FILE -ErrorAction SilentlyContinue}
  $deadline=(Get-Date).AddSeconds(90)
  $ready=$false
  while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 650
    if (Test-Path -LiteralPath $readyFile) {
      $marker=Get-Content -LiteralPath $readyFile -Raw | ConvertFrom-Json
      if ([IO.Path]::GetFullPath([string]$marker.exe) -ine $Target) {throw 'New application started from the wrong location.'}
      if ($Version -and [string]$marker.version -ne $Version) {throw ('Version mismatch. Started '+$marker.version+', expected '+$Version)}
      $ready=$true;break
    }
    $started.Refresh()
    if ($started.HasExited) {throw ('New BusinessDesk exited before startup confirmation. Code: '+$started.ExitCode)}
  }
  if (-not $ready) {throw 'New BusinessDesk did not confirm successful startup within 90 seconds.'}
  try { Make-Shortcuts $Target } catch { Write-Log ('Shortcut warning: '+$_.Exception.Message) }
  Write-Status 'success' ('BusinessDesk '+$Version+' is running from '+$Target+'. Previous app at '+$previousDir)
} catch {
  $failure=$_.Exception.Message
  Write-Status 'failed' $failure
  if ($started) {
    try {
      $started.Refresh()
      if (-not $started.HasExited) {
        & taskkill.exe /PID $started.Id /T /F 2>$null | Out-Null
        $started.WaitForExit(10000) | Out-Null
      }
    } catch { Write-Log ('Could not stop failed app: '+$_.Exception.Message) }
  }
  if ($oldMoved) {
    try {
      if (Test-Path -LiteralPath $targetDir) {
        $failedDir=Join-Path (Split-Path -Parent $targetDir) ((Split-Path -Leaf $targetDir)+'.failed_'+[guid]::NewGuid().ToString('N').Substring(0,6))
        Move-Item -LiteralPath $targetDir -Destination $failedDir -ErrorAction Stop
      }
      Move-Item -LiteralPath $previousDir -Destination $targetDir -ErrorAction Stop
      Write-Status 'rolled_back' ('Restored old application folder after update error: '+$failure)
      Start-Process -FilePath $Target -WorkingDirectory $targetDir -ErrorAction Stop | Out-Null
    } catch { Write-Status 'rollback_failed' ($failure+'; rollback: '+$_.Exception.Message) }
  } elseif ($installed) {
    Write-Log ('Fresh installation failed; candidate remains at '+$targetDir+' for diagnosis.')
  }
  if (-not $PrepareOnly) { Show-Failure ($failure+"`r`n`r`n"+'Installation log: '+$log+"`r`n"+'Previous installed folder: '+$previousDir) }
} finally {
  Remove-Item -LiteralPath $readyFile -ErrorAction SilentlyContinue
  if ($stage -and (Test-Path -LiteralPath $stage)) {Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue}
  if ($smokeData -and (Test-Path -LiteralPath $smokeData)) {Remove-Item -LiteralPath $smokeData -Recurse -Force -ErrorAction SilentlyContinue}
}
if ($failure) {exit 1}
exit 0
