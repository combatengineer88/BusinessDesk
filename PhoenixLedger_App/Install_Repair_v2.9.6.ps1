# One-time repair for EXE throwing "Failed to load Python DLL" after v2.9.5.
# Run from an extracted local folder; uses official GitHub latest release,
# verifies SHA-256, backs up SQLite files, and runs standalone installer.
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
$repo='combatengineer88/BusinessDesk'
$dataDir=Join-Path $env:LOCALAPPDATA 'PhoenixLedger'
$updates=Join-Path $dataDir 'updates'
$log=Join-Path $updates 'recovery_296.log'
$target=Join-Path $env:LOCALAPPDATA 'Programs\PhoenixLedger\PhoenixLedger.exe'
New-Item -ItemType Directory -Force -Path $updates | Out-Null
function Log([string]$message) {
  Add-Content -LiteralPath $log -Encoding UTF8 -Value ('['+(Get-Date -Format s)+'] '+$message)
}
function Alert([string]$message,[string]$title='PhoenixLedger repair',[string]$kind='Information') {
  [Windows.Forms.MessageBox]::Show($message,$title,'OK',$kind) | Out-Null
}
try {
  Log 'Starting one-time v2.9.6 recovery.'
  $running=@(Get-Process -Name 'PhoenixLedger' -ErrorAction SilentlyContinue)
  if ($running.Count -gt 0) {throw 'Close ALL PhoenixLedger processes in Task Manager before running this repair.'}
  if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'update_installer.ps1'))) {
    throw 'update_installer.ps1 must be extracted next to this repair script.'
  }
  $manifestUrl='https://github.com/'+$repo+'/releases/latest/download/update_manifest.json'
  Log ('Getting '+$manifestUrl)
  $manifest=Invoke-RestMethod -Uri $manifestUrl -TimeoutSec 45 -Headers @{'User-Agent'='TDZIGNS-PhoenixLedger-Recovery/2.9.6'}
  $version=[string]$manifest.version
  if ($version -notmatch '^\d+\.\d+\.\d+$' -or [version]$version -lt [version]'2.9.6') {
    throw 'The fixed v2.9.6+ ONEDIR release is not published yet. Wait for the v2.9.6 GitHub Actions run and release to finish.'
  }
  $expectedUrl='https://github.com/'+$repo+'/releases/download/v'+$version+'/PhoenixLedger_'+$version+'.zip'
  if ([string]$manifest.url -cne $expectedUrl) {throw ('Unexpected release URL: '+$manifest.url)}
  $digest=[string]$manifest.sha256
  if ($digest -notmatch '^[a-fA-F0-9]{64}$') {throw 'No valid SHA-256 digest in release manifest.'}
  $zip=Join-Path $updates ('PhoenixLedger_'+$version+'.zip')
  if (-not (Test-Path -LiteralPath $zip) -or (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash -ine $digest) {
    $part=$zip+'.part'
    try {
      Log ('Downloading '+$expectedUrl)
      Invoke-WebRequest -Uri $expectedUrl -OutFile $part -UseBasicParsing -TimeoutSec 240 -Headers @{'User-Agent'='TDZIGNS-PhoenixLedger-Recovery/2.9.6'}
      if ((Get-Item -LiteralPath $part).Length -gt 300MB) {throw 'Download exceeds the 300 MB limit.'}
      if ((Get-FileHash -LiteralPath $part -Algorithm SHA256).Hash -ine $digest) {throw 'SHA-256 mismatch. Download rejected.'}
      Move-Item -LiteralPath $part -Destination $zip -Force
    } finally {Remove-Item -LiteralPath $part -Force -ErrorAction SilentlyContinue}
  }
  # Copy databases only while all PhoenixLedger processes are closed. Include WAL/SHM.
  $backup=Join-Path $updates ('data_backup_before_296_'+(Get-Date -Format 'yyyyMMdd_HHmmss'))
  New-Item -ItemType Directory -Path $backup -Force | Out-Null
  foreach ($file in @('business.db','business.db-wal','business.db-shm')) {
    $source=Join-Path $dataDir $file
    if (Test-Path -LiteralPath $source) { Copy-Item -LiteralPath $source -Destination $backup -Force }
  }
  Log ('Database backed up to '+$backup)
  $answer=[Windows.Forms.MessageBox]::Show(
    'Install the verified PhoenixLedger '+$version+' release?' +"`r`n`r`n"+
    'New installation folder: '+(Split-Path -Parent $target)+"`r`n"+
    'The previous application folder will be preserved as a backup.'+"`r`n"+
    'Your business database will not be replaced.'+"`r`n`r`n"+
    'Continue?', 'Install repaired PhoenixLedger','YesNo','Question')
  if ($answer -ne 'Yes') {Log 'User cancelled installation.';exit 0}
  $args=@('-NoProfile','-STA','-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'update_installer.ps1'),
      '-Package',$zip,'-Target',$target,'-ProcessIdToWait','0','-DataDir',$dataDir,
      '-ExpectedSha256',$digest,'-Version',$version,'-AllowFreshInstall','-CreateShortcuts')
  Log ('Calling validated ONEDIR update installer for '+$target)
  & powershell.exe @args
  if ($LASTEXITCODE -ne 0) {throw 'The installer reported failure. Check installation.log for the detailed cause.'}
  Log ('Installation completed and startup was verified: '+$target)
  Alert ('PhoenixLedger '+$version+' started successfully.'+"`r`n`r`n"+'EXE: '+$target+"`r`n"+'Your business database was preserved.')
} catch {
  Log ('ERROR: '+$_.Exception.Message)
  Alert ($_.Exception.Message+"`r`n`r`n"+'Diagnostic log: '+$log+"`r`n"+'Installer log: '+(Join-Path $updates 'installation.log')+"`r`n`r`n"+
    'If the failure still says python312.dll, check antivirus quarantine and install/repair the Microsoft Visual C++ 2015-2022 x64 Redistributable from Microsoft.') 'PhoenixLedger repair failed' 'Error'
  exit 1
}
