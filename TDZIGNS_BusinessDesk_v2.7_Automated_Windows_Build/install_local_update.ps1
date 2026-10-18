# Offline update installer for TDZIGNS BusinessDesk. Run after closing the app.
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.IO.Compression.FileSystem
$ErrorActionPreference='Stop'
try {
  $folder=New-Object System.Windows.Forms.FolderBrowserDialog
  $folder.Description='Select folder containing your downloaded ZIP or EXE update'
  if ($folder.ShowDialog() -ne 'OK') { exit }
  $file=New-Object System.Windows.Forms.OpenFileDialog
  $file.InitialDirectory=$folder.SelectedPath
  $file.Filter='BusinessDesk updates (*.zip;*.exe)|*.zip;*.exe'
  if ($file.ShowDialog() -ne 'OK') { exit }
  $package=$file.FileName
  if ([IO.Path]::GetExtension($package) -ieq '.zip') {
    $archive=[System.IO.Compression.ZipFile]::OpenRead($package)
    try {
      $entries=@($archive.Entries | Where-Object {$_.Name -ne ''})
      if ($entries.Count -ne 1 -or $entries[0].FullName -ne 'TDZIGNS_BusinessDesk.exe') {throw 'Not an installable Windows ZIP. Build the EXE first.'}
    } finally {$archive.Dispose()}
  } elseif ([IO.Path]::GetExtension($package) -ine '.exe') {throw 'Select a ZIP or EXE.'}
  $version='local'
  $targetPicker=New-Object System.Windows.Forms.OpenFileDialog
  $targetPicker.Title='Select your currently installed TDZIGNS_BusinessDesk.exe'
  $targetPicker.Filter='TDZIGNS executable (TDZIGNS_BusinessDesk.exe)|TDZIGNS_BusinessDesk.exe'
  if ($targetPicker.ShowDialog() -ne 'OK') { exit }
  $target=$targetPicker.FileName
  if ([IO.Path]::GetFullPath($package) -eq [IO.Path]::GetFullPath($target)) {throw 'The selected update and installed executable cannot be the same file.'}
  if ((Get-Process -Name 'TDZIGNS_BusinessDesk' -ErrorAction SilentlyContinue)) {throw 'Close BusinessDesk before installing a local update.'}
  $hash=(Get-FileHash -LiteralPath $package -Algorithm SHA256).Hash.ToLowerInvariant()
  $checksum=[IO.Path]::ChangeExtension($package,'.sha256')
  if (Test-Path $checksum) {
    $expected=((Get-Content -LiteralPath $checksum -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
    if ($expected -ne $hash) {throw 'Checksum mismatch. Update rejected.'}
  } else {
    $confirm=[System.Windows.Forms.MessageBox]::Show('No .sha256 file found. Install only from a trusted source. Continue?','Unverified update','YesNo','Warning')
    if ($confirm -ne 'Yes') {exit}
  }
  $dataDir=Join-Path $env:LOCALAPPDATA 'BusinessDesk'
  $backup=Join-Path $dataDir ('updates\offline_backup_'+(Get-Date -Format 'yyyyMMdd_HHmmss'))
  New-Item -ItemType Directory -Path $backup -Force | Out-Null
  foreach($name in @('business.db','business.db-wal','business.db-shm')){
    $src=Join-Path $dataDir $name
    if(Test-Path $src){Copy-Item -LiteralPath $src -Destination $backup -Force}
  }
  & (Join-Path $PSScriptRoot 'update_installer.ps1') -Package $package -Target $target -ProcessIdToWait 0 -DataDir $dataDir -ExpectedSha256 $hash
  [System.Windows.Forms.MessageBox]::Show("Update $version installation requested. Check the app version after it opens.",'TDZIGNS BusinessDesk') | Out-Null
} catch {
  [System.Windows.Forms.MessageBox]::Show($_.Exception.Message,'Update failed') | Out-Null
  exit 1
}
