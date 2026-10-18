# TDZIGNS BusinessDesk v2.9.4 standalone updater.
# Runs in a separate PowerShell process after the main application exits.
param(
  [Parameter(Mandatory=$true)][string]$Package,
  [Parameter(Mandatory=$true)][string]$Target,
  [Parameter(Mandatory=$true)][int]$ProcessIdToWait,
  [Parameter(Mandatory=$true)][string]$DataDir,
  [Parameter(Mandatory=$true)][string]$ExpectedSha256,
  [string]$Version = '',
  [switch]$AllowFreshInstall,
  [string]$HandoffFile = '',
  [string]$AttemptId = '',
  [switch]$PrepareOnly
)
$ErrorActionPreference = 'Stop'
$updates = Join-Path $DataDir 'updates'
New-Item -ItemType Directory -Path $updates -Force | Out-Null
$log = Join-Path $updates 'installation.log'
$statusFile = Join-Path $updates 'install_status.json'
$backupDir = Join-Path $updates ('backup_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '_' + [guid]::NewGuid().ToString('N').Substring(0,6))
$backupExe = Join-Path $backupDir 'TDZIGNS_BusinessDesk.exe'
$stage = Join-Path $updates ('unpack_' + [guid]::NewGuid().ToString('N'))
$readyFile = Join-Path $updates ('ready_' + [guid]::NewGuid().ToString('N') + '.json')
$replacementAttempted = $false
$hadPrevious = $false
$launch = $null
$failure = $null

function Write-Log([string]$text) {
  Add-Content -LiteralPath $log -Encoding UTF8 -Value ('[' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + '] ' + $text)
}
function Write-Status([string]$state, [string]$detail) {
  $report = @{
    status = $state
    message = $detail
    version = $Version
    target = $Target
    package = $Package
    attempt_id = $AttemptId
    backup = $(if (Test-Path -LiteralPath $backupExe) { $backupExe } else { '' })
    updated_at = (Get-Date).ToString('s')
    log = $log
  }
  $report | ConvertTo-Json -Depth 3 | Set-Content -LiteralPath $statusFile -Encoding UTF8
  Write-Log ($state + ': ' + $detail)
}
function Show-Error([string]$detail) {
  try {
    Add-Type -AssemblyName System.Windows.Forms
    $form = New-Object System.Windows.Forms.Form
    $form.TopMost = $true
    $form.ShowInTaskbar = $false
    [System.Windows.Forms.MessageBox]::Show($form, $detail, 'BusinessDesk update did not finish', 'OK', 'Error') | Out-Null
    $form.Dispose()
  } catch { Write-Log ('Could not show error dialog: ' + $_.Exception.Message) }
}
function Copy-WithRetry([string]$from, [string]$to) {
  $lastError = ''
  for ($attempt = 1; $attempt -le 12; $attempt++) {
    try {
      Copy-Item -LiteralPath $from -Destination $to -Force -ErrorAction Stop
      return
    } catch {
      $lastError = $_.Exception.Message
      Start-Sleep -Seconds 1
    }
  }
  throw ('Could not replace executable at ' + $to + '. ' + $lastError + '. Check installation folder permissions or antivirus locks.')
}

try {
  $Package = [IO.Path]::GetFullPath($Package)
  $Target = [IO.Path]::GetFullPath($Target)
  if ([IO.Path]::GetFileName($Target) -ine 'TDZIGNS_BusinessDesk.exe') {
    throw 'Unexpected installed executable name. The target must be TDZIGNS_BusinessDesk.exe.'
  }
  $hadPrevious = Test-Path -LiteralPath $Target -PathType Leaf
  if (-not $hadPrevious -and -not $AllowFreshInstall) {
    throw ('The installed executable was not found at: ' + $Target)
  }
  if (-not $hadPrevious) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $Target) -Force | Out-Null
  }
  if (-not (Test-Path -LiteralPath $Package -PathType Leaf)) {
    throw ('The downloaded update file is missing: ' + $Package)
  }
  if ($Package -ieq $Target) { throw 'The update package and installed executable cannot be the same file.' }
  if ($ExpectedSha256 -notmatch '^[a-fA-F0-9]{64}$') { throw 'Invalid expected SHA-256 hash.' }
  Write-Status 'verifying' ('Installing into: ' + $Target)
  $actual = (Get-FileHash -LiteralPath $Package -Algorithm SHA256).Hash
  if ($actual -ine $ExpectedSha256) { throw 'Update SHA-256 checksum does not match; no application files were changed.' }

  New-Item -ItemType Directory -Path $stage -Force | Out-Null
  if ([IO.Path]::GetExtension($Package) -ieq '.zip') {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [IO.Compression.ZipFile]::OpenRead($Package)
    try {
      $entries = @($archive.Entries | Where-Object { $_.Name -ne '' })
      if ($entries.Count -ne 1 -or $entries[0].FullName -cne 'TDZIGNS_BusinessDesk.exe') {
        throw 'Invalid Windows update ZIP: it must contain only TDZIGNS_BusinessDesk.exe at its root.'
      }
      if ($entries[0].Length -lt 100000 -or $entries[0].Length -gt 400MB) {
        throw 'Update executable has an invalid size.'
      }
      $exeOut = Join-Path $stage 'TDZIGNS_BusinessDesk.exe'
      [IO.Compression.ZipFileExtensions]::ExtractToFile($entries[0], $exeOut, $false)
    } finally { $archive.Dispose() }
  } elseif ([IO.Path]::GetExtension($Package) -ieq '.exe') {
    $exeOut = $Package
  } else { throw 'Please choose a compiled Windows EXE or Windows update ZIP.' }

  $exeStream = [IO.File]::OpenRead($exeOut)
  try {
    if ($exeStream.ReadByte() -ne 77 -or $exeStream.ReadByte() -ne 90) { throw 'The update is not a valid Windows executable.' }
    if ($exeStream.Length -lt 100000) { throw 'Update executable is unexpectedly small.' }
  } finally { $exeStream.Dispose() }

  Write-Status 'prepared' ('Verified Windows update; installation location: ' + $Target)
  if ($HandoffFile) {
    $handoffFull=[IO.Path]::GetFullPath($HandoffFile)
    $updatesFull=[IO.Path]::GetFullPath($updates)
    if ([IO.Path]::GetDirectoryName($handoffFull) -ine $updatesFull -or
        [IO.Path]::GetFileName($handoffFull) -notmatch '^handoff_[0-9a-f]{32}\.ready$') {
      throw 'Refusing an unsafe updater handoff path.'
    }
    [IO.File]::WriteAllText($handoffFull, 'PREPARED', [Text.UTF8Encoding]::new($false))
    Write-Log 'Handoff acknowledged; waiting for the old application to exit.'
  }
  # Used by CI to verify the release package, helper invocation, and handoff
  # without changing a production executable or launching the GUI.
  if ($PrepareOnly) {
    Write-Status 'preflight_success' 'Update package verified and installation handoff acknowledged.'
    return
  }
  if ($ProcessIdToWait -gt 0) {
    $running = Get-Process -Id $ProcessIdToWait -ErrorAction SilentlyContinue
    if ($running) {
      Write-Status 'waiting' 'Waiting for BusinessDesk to close before replacing the EXE.'
      $running.WaitForExit(90000) | Out-Null
      if (-not $running.HasExited) { throw 'The original BusinessDesk process did not exit within 90 seconds.' }
    }
  }

  New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
  if ($hadPrevious) {
    Copy-Item -LiteralPath $Target -Destination $backupExe -Force -ErrorAction Stop
    Write-Status 'replacing' ('Original executable backed up to ' + $backupExe)
  } else {
    Write-Status 'installing' ('Fresh per-user installation at ' + $Target)
  }
  $replacementAttempted = $true
  Copy-WithRetry $exeOut $Target
  Write-Status 'restarting' ('Updated executable installed at ' + $Target + '; starting BusinessDesk...')

  # A successful Start-Process does not prove the app opened. The new app writes
  # this marker once the login window has been initialized by Tkinter.
  $env:BUSINESSDESK_UPDATE_READY_FILE = $readyFile
  try {
    $launch = Start-Process -FilePath $Target -WorkingDirectory (Split-Path -Parent $Target) -PassThru -ErrorAction Stop
  } finally {
    Remove-Item Env:BUSINESSDESK_UPDATE_READY_FILE -ErrorAction SilentlyContinue
  }
  $deadline = (Get-Date).AddSeconds(90)
  $restartConfirmed = $false
  $lastReason = 'The updated application did not confirm its startup.'
  while ((Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 750
    if (Test-Path -LiteralPath $readyFile) {
      $ready = Get-Content -LiteralPath $readyFile -Raw | ConvertFrom-Json
      if ([IO.Path]::GetFullPath($ready.exe) -ine $Target) {
        throw ('Updated application started from an unexpected path: ' + $ready.exe)
      }
      if ($Version -and $ready.version -ne $Version) {
        throw ('Restarted version mismatch: expected ' + $Version + ', got ' + $ready.version)
      }
      $restartConfirmed = $true
      break
    }
    if ($launch) {
      $launch.Refresh()
      if ($launch.HasExited) {
        $lastReason = ('Updated application exited before becoming ready (exit code ' + $launch.ExitCode + ').')
        break
      }
    }
  }
  if (-not $restartConfirmed) { throw $lastReason }
  Write-Status 'success' ('Version ' + $Version + ' installed and reopened at ' + $Target)
} catch {
  $failure = $_.Exception.Message
  Write-Status 'failed' $failure
  # Do not leave a failed new application running during rollback.
  if ($replacementAttempted -and $hadPrevious -and (Test-Path -LiteralPath $backupExe)) {
    try {
      if ($launch) {
        $launch.Refresh()
        if (-not $launch.HasExited) {
          # Force the PyInstaller one-file bootloader and its child to exit before rollback.
          & taskkill.exe /PID $launch.Id /T /F 2>$null | Out-Null
          $launch.WaitForExit(15000) | Out-Null
        }
      }
      Copy-WithRetry $backupExe $Target
      Write-Status 'rolled_back' ('Update failed: ' + $failure + '. Previous executable was restored at ' + $Target)
      # A rollback uses the original build, which may not implement the startup marker.
      Start-Process -FilePath $Target -WorkingDirectory (Split-Path -Parent $Target) -ErrorAction Stop | Out-Null
    } catch {
      Write-Status 'rollback_failed' ('Update failure: ' + $failure + '. Rollback error: ' + $_.Exception.Message)
    }
  } elseif ($replacementAttempted -and -not $hadPrevious) {
    try {
      if ($launch) {
        $launch.Refresh()
        if (-not $launch.HasExited) { & taskkill.exe /PID $launch.Id /T /F 2>$null | Out-Null }
      }
      Remove-Item -LiteralPath $Target -Force -ErrorAction Stop
    } catch {Write-Log ('Fresh-install cleanup failed: ' + $_.Exception.Message)}
  }
  Show-Error ('The BusinessDesk update could not be completed.' + "`r`n`r`n" + $failure + "`r`n`r`n" +
    'Expected installation location:' + "`r`n" + $Target + "`r`n`r`n" +
    'Update log:' + "`r`n" + $log + "`r`n" +
    'Startup errors:' + "`r`n" + (Join-Path $updates 'startup_errors.log') + "`r`n`r`n" +
    'The previous EXE was restored if possible. Your database was not removed.')
} finally {
  Remove-Item -LiteralPath $readyFile -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $stage -Force -Recurse -ErrorAction SilentlyContinue
}
if ($failure) { exit 1 }
exit 0
