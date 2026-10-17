param(
  [Parameter(Mandatory=$true)][string]$Package,
  [Parameter(Mandatory=$true)][string]$Target,
  [Parameter(Mandatory=$true)][int]$ProcessIdToWait,
  [Parameter(Mandatory=$true)][string]$DataDir,
  [Parameter(Mandatory=$true)][string]$ExpectedSha256
)
$ErrorActionPreference = 'Stop'
$log = Join-Path $DataDir 'updates\installation.log'
New-Item -ItemType Directory -Path (Join-Path $DataDir 'updates') -Force | Out-Null
$backupDir = Join-Path $DataDir ('updates\backup_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
$stage = Join-Path $DataDir ('updates\unpack_' + [guid]::NewGuid().ToString('N'))
$replaced = $false
try {
  if (-not [System.IO.Path]::GetFullPath($Target).EndsWith('TDZIGNS_BusinessDesk.exe',[System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Update target is not the expected application executable.'
  }
  if ((Get-FileHash -LiteralPath $Package -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedSha256.ToLowerInvariant()) {
    throw 'Downloaded package hash mismatch.'
  }
  $existing = if ($ProcessIdToWait -gt 0) { Get-Process -Id $ProcessIdToWait -ErrorAction SilentlyContinue } else { $null }
  if ($existing) {
    $existing.WaitForExit(60000) | Out-Null
    if (-not $existing.HasExited) { throw 'Application did not exit within 60 seconds.' }
  }
  New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
  New-Item -ItemType Directory -Path $stage -Force | Out-Null
  # Back up all business files with SQLite's online backup already performed in the app.
  Copy-Item -LiteralPath $Target -Destination (Join-Path $backupDir 'TDZIGNS_BusinessDesk.exe') -ErrorAction Stop
  if ([IO.Path]::GetExtension($Package) -ieq '.exe') {
    $exe = $Package
    $stream=[IO.File]::OpenRead($exe)
    try {if ($stream.ReadByte() -ne 77 -or $stream.ReadByte() -ne 90) {throw 'Not a Windows EXE.'}} finally {$stream.Dispose()}
  } elseif ([IO.Path]::GetExtension($Package) -ieq '.zip') {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive=[IO.Compression.ZipFile]::OpenRead($Package)
    try {
      $entries=@($archive.Entries | Where-Object {$_.Name -ne ''})
      if ($entries.Count -ne 1 -or $entries[0].FullName -ne 'TDZIGNS_BusinessDesk.exe') {throw 'ZIP must contain only TDZIGNS_BusinessDesk.exe.'}
    } finally {$archive.Dispose()}
    Expand-Archive -LiteralPath $Package -DestinationPath $stage -Force
    $exe=Join-Path $stage 'TDZIGNS_BusinessDesk.exe'
  } else {throw 'Choose a Windows .exe or update .zip.'}
  if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'Update ZIP must contain TDZIGNS_BusinessDesk.exe at its root.' }
  if ((Get-Item -LiteralPath $exe).Length -lt 100000) { throw 'Update executable is unexpectedly small.' }
  Copy-Item -LiteralPath $exe -Destination $Target -Force -ErrorAction Stop
  $replaced = $true
  $started=$false
  $lastLaunchError=''
  for ($attempt=1; $attempt -le 5 -and -not $started; $attempt++) {
    try {
      Start-Sleep -Milliseconds 800
      $launched=Start-Process -FilePath $Target -WorkingDirectory (Split-Path -Parent $Target) -PassThru -ErrorAction Stop
      Start-Sleep -Seconds 2
      $launched.Refresh()
      if ($launched.HasExited) { $lastLaunchError='Updated application exited immediately with code '+$launched.ExitCode }
      else { $started=$true }
    } catch { $lastLaunchError=$_.Exception.Message }
  }
  if (-not $started) { throw ('Application restart failed: '+$lastLaunchError) }
  ('SUCCESS ' + (Get-Date) + ' - ' + $Target) | Out-File -FilePath $log -Append
} catch {
  ('FAILED ' + (Get-Date) + ' - ' + $_.Exception.Message) | Out-File -FilePath $log -Append
  if ($replaced -and (Test-Path -LiteralPath (Join-Path $backupDir 'TDZIGNS_BusinessDesk.exe'))) {
    try {
      Copy-Item -LiteralPath (Join-Path $backupDir 'TDZIGNS_BusinessDesk.exe') -Destination $Target -Force
      Start-Process -FilePath $Target -WorkingDirectory (Split-Path -Parent $Target)
      'ROLLED BACK executable' | Out-File -FilePath $log -Append
    } catch { ('ROLLBACK FAILED: ' + $_.Exception.Message) | Out-File -FilePath $log -Append }
  }
  exit 1
} finally {
  Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
}
