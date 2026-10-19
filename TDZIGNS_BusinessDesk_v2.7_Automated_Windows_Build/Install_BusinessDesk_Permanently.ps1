# Repair utility: move BusinessDesk from transient Explorer ZIP extraction to
# a permanent, user-writable installation under LOCALAPPDATA\Programs.
# Does not delete or replace the existing business database.
param()
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$DataDir=Join-Path $env:LOCALAPPDATA 'BusinessDesk'
$Updates=Join-Path $DataDir 'updates'
$Target=Join-Path $env:LOCALAPPDATA 'Programs\TDZIGNS BusinessDesk\TDZIGNS_BusinessDesk.exe'
$Log=Join-Path $Updates 'permanent_install.log'
New-Item -ItemType Directory -Path $Updates -Force | Out-Null
function Log([string]$text) {
  Add-Content -LiteralPath $Log -Encoding UTF8 -Value ('['+(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')+'] '+$text)
}
function Notice([string]$text, [string]$title='BusinessDesk permanent installation', [string]$icon='Information') {
  [System.Windows.Forms.MessageBox]::Show($text,$title,'OK',$icon) | Out-Null
}
try {
  Log 'Beginning permanent installation.'
  $running=@(Get-Process -Name 'TDZIGNS_BusinessDesk' -ErrorAction SilentlyContinue)
  if ($running.Count -gt 0) {
    throw ('BusinessDesk is currently running ('+$running.Count+' processes). Close every BusinessDesk window and try again. If needed use Task Manager, but save work before ending a process.')
  }
  $manifestUrl='https://github.com/combatengineer88/BusinessDesk/releases/latest/download/update_manifest.json'
  Log ('Fetching '+$manifestUrl)
  $manifest=Invoke-RestMethod -Uri $manifestUrl -TimeoutSec 45 -Headers @{'User-Agent'='BusinessDesk-Permanent-Install/1.0'}
  $version=[string]$manifest.version
  if ($version -notmatch '^\d+\.\d+\.\d+$') { throw 'GitHub release has an invalid version number.' }
  if ([version]$version -lt [version]'2.9.4') {throw 'The latest GitHub release is older than v2.9.4.'}
  $releaseUrl='https://github.com/combatengineer88/BusinessDesk/releases/download/v'+$version+'/TDZIGNS_BusinessDesk_'+$version+'.zip'
  if ([string]$manifest.url -cne $releaseUrl) {throw 'Release URL does not match the official BusinessDesk GitHub repository.'}
  $sha=[string]$manifest.sha256
  if ($sha -notmatch '^[0-9A-Fa-f]{64}$') {throw 'The GitHub release manifest is missing a valid SHA-256 checksum.'}

  $cached=Join-Path $Updates ('BusinessDesk_'+$version+'.zip')
  $download=Join-Path $Updates ('BusinessDesk_permanent_'+$version+'.zip')
  $useCached=$false
  if (Test-Path -LiteralPath $cached -PathType Leaf) {
    $cachedHash=(Get-FileHash -LiteralPath $cached -Algorithm SHA256).Hash
    if ($cachedHash -ieq $sha) {
      $download=$cached;$useCached=$true
      Log ('Using already downloaded and verified update: '+$cached)
    }
  }
  if (-not $useCached) {
    $tmp=$download+'.part'
    try {
      Log ('Downloading '+$releaseUrl)
      Invoke-WebRequest -Uri $releaseUrl -OutFile $tmp -UseBasicParsing -TimeoutSec 240 -Headers @{'User-Agent'='BusinessDesk-Permanent-Install/1.0'}
      if ((Get-Item -LiteralPath $tmp).Length -gt 200MB) {throw 'The downloaded update exceeds 200 MB.'}
      if ((Get-FileHash -LiteralPath $tmp -Algorithm SHA256).Hash -ine $sha) {throw 'Downloaded ZIP checksum mismatch; nothing was installed.'}
      Move-Item -LiteralPath $tmp -Destination $download -Force
    } finally {Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue}
  }

  # A database backup is taken before the freshly installed program starts.
  # The application must be closed for a consistent raw copy including WAL files.
  $dataBackup=Join-Path $Updates ('backup_before_permanent_install_'+(Get-Date -Format 'yyyyMMdd_HHmmss'))
  New-Item -ItemType Directory -Path $dataBackup -Force | Out-Null
  foreach ($name in @('business.db','business.db-wal','business.db-shm')) {
    $source=Join-Path $DataDir $name
    if (Test-Path -LiteralPath $source -PathType Leaf) {
      Copy-Item -LiteralPath $source -Destination $dataBackup -Force
    }
  }
  Log ('Database files backed up to '+$dataBackup)
  $confirm=[System.Windows.Forms.MessageBox]::Show(
    'The trusted GitHub release v'+$version+' is ready.'+"`r`n`r`n"+
    'BusinessDesk will be installed here:'+"`r`n"+$Target+"`r`n`r`n"+
    'Your business database is stored separately and will not be replaced.'+"`r`n`r`n"+
    'Desktop and Start Menu shortcuts will be created. Continue?',
    'Confirm permanent installation','YesNo','Question')
  if ($confirm -ne 'Yes') {Log 'User cancelled.';exit 0}

  # update_installer.ps1 operates in a separate process and checks its own log,
  # package hash, ZIP contents, application restart marker, and rollback.
  $args=@('-NoProfile','-STA','-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'update_installer.ps1'),
    '-Package',$download,'-Target',$Target,'-ProcessIdToWait','0','-DataDir',$DataDir,
    '-ExpectedSha256',$sha,'-Version',$version,'-CreateShortcuts')
  if (-not (Test-Path -LiteralPath $Target -PathType Leaf)) {$args+='-AllowFreshInstall'}
  Log ('Launching update helper; target '+$Target)
  & powershell.exe @args
  if ($LASTEXITCODE -ne 0) {throw ('Installer returned exit code '+$LASTEXITCODE+'. Check installation.log for details.')}
  Log ('Installed and relaunched BusinessDesk at '+$Target)
  Notice ('BusinessDesk v'+$version+' has been installed and reopened.'+"`r`n`r`n"+
    'Permanent EXE location:'+"`r`n"+$Target+"`r`n`r`n"+
    'A desktop shortcut and Start Menu entry were created.')
} catch {
  $reason=$_.Exception.Message
  Log ('ERROR: '+$reason)
  Notice ($reason+"`r`n`r`n"+'Diagnostic logs:'+"`r`n"+$Log+"`r`n"+
    (Join-Path $Updates 'installation.log')+'`r`n'+'No business database files were removed.') 'BusinessDesk installation failed' 'Error'
  exit 1
}
