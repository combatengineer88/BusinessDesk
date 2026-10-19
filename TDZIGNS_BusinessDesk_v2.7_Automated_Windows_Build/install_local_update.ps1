# Offline ONEDIR release installer for BusinessDesk 2.9.6 and later.
# Select the complete compiled ZIP, not the source ZIP and not an EXE alone.
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
$DataDir=Join-Path $env:LOCALAPPDATA 'BusinessDesk'
$Updates=Join-Path $DataDir 'updates'
$Target=Join-Path $env:LOCALAPPDATA 'Programs\TDZIGNS BusinessDesk\TDZIGNS_BusinessDesk.exe'
New-Item -ItemType Directory -Path $Updates -Force | Out-Null
try {
  if (@(Get-Process -Name 'TDZIGNS_BusinessDesk' -ErrorAction SilentlyContinue).Count -gt 0) {
    throw 'Close BusinessDesk completely before installing a local update.'
  }
  $picker=New-Object System.Windows.Forms.OpenFileDialog
  $picker.Title='Select compiled BusinessDesk v2.9.6+ update ZIP (not source ZIP)'
  $picker.Filter='BusinessDesk Windows release ZIP (*.zip)|*.zip'
  if ($picker.ShowDialog() -ne 'OK') {exit 0}
  $Package=$picker.FileName
  if ((Get-Item -LiteralPath $Package).Length -gt 300MB) {throw 'Release archive is too large.'}
  $match=[regex]::Match([IO.Path]::GetFileName($Package),'^TDZIGNS_BusinessDesk_(\d+\.\d+\.\d+)\.zip$')
  if (-not $match.Success) {throw 'Expected a compiled release ZIP named TDZIGNS_BusinessDesk_X.Y.Z.zip.'}
  $Version=$match.Groups[1].Value
  if ([version]$Version -lt [version]'2.9.6') {throw 'This installer supports the ONEDIR format introduced with v2.9.6.'}
  $Hash=(Get-FileHash -LiteralPath $Package -Algorithm SHA256).Hash.ToLowerInvariant()
  $checksum=[IO.Path]::ChangeExtension($Package,'.sha256')
  if (Test-Path -LiteralPath $checksum) {
    $expected=((Get-Content -LiteralPath $checksum -Raw).Trim() -split '\s+')[0]
    if ($expected -ine $Hash) {throw 'Downloaded release ZIP does not match its SHA-256 file.'}
  } else {
    $answer=[Windows.Forms.MessageBox]::Show('No SHA-256 checksum file was found beside the ZIP. Only install a trusted GitHub Release download. Continue?',
      'Unverified local release','YesNo','Warning')
    if ($answer -ne 'Yes') {exit 0}
  }
  $backup=Join-Path $Updates ('data_backup_before_offline_'+(Get-Date -Format 'yyyyMMdd_HHmmss'))
  New-Item -ItemType Directory -Path $backup -Force | Out-Null
  foreach ($file in @('business.db','business.db-wal','business.db-shm')) {
    $src=Join-Path $DataDir $file
    if (Test-Path -LiteralPath $src) {Copy-Item -LiteralPath $src -Destination $backup -Force}
  }
  & (Join-Path $PSScriptRoot 'update_installer.ps1') -Package $Package -Target $Target -ProcessIdToWait 0 -DataDir $DataDir -ExpectedSha256 $Hash -Version $Version -AllowFreshInstall -CreateShortcuts
  if ($LASTEXITCODE -ne 0) {throw 'The updater failed. Check installation.log in your BusinessDesk updates folder.'}
  [Windows.Forms.MessageBox]::Show('BusinessDesk has restarted successfully.'+"`r`n"+'Location: '+$Target,'BusinessDesk update') | Out-Null
} catch {
  [Windows.Forms.MessageBox]::Show($_.Exception.Message+"`r`n`r`n"+'Log: '+(Join-Path $Updates 'installation.log'),'BusinessDesk update failed','OK','Error') | Out-Null
  exit 1
}
