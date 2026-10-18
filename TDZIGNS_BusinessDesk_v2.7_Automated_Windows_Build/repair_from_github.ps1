# One-time repair path for BusinessDesk installations whose built-in updater stops after exit.
# Download the latest release from the official project and launch the repaired installer.
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms

function Notify([string]$message,[string]$title='BusinessDesk recovery',[string]$kind='Information') {
  $owner = New-Object System.Windows.Forms.Form
  $owner.TopMost = $true
  [System.Windows.Forms.MessageBox]::Show($owner,$message,$title,'OK',$kind) | Out-Null
  $owner.Dispose()
}
function Get-PreviousTarget([string]$dataDir) {
  $status=Join-Path $dataDir 'updates\install_status.json'
  if (Test-Path -LiteralPath $status) {
    try {
      $j=Get-Content -LiteralPath $status -Raw | ConvertFrom-Json
      if ($j.target -and (Test-Path -LiteralPath $j.target -PathType Leaf)) {return [string]$j.target}
    } catch {}
  }
  $log=Join-Path $dataDir 'updates\installation.log'
  if (Test-Path -LiteralPath $log) {
    $lines=@(Get-Content -LiteralPath $log -Tail 70)
    for ($i=$lines.Count-1; $i -ge 0; $i--) {
      if ($lines[$i] -match '(?:SUCCESS|restarting|verifying).*?([a-zA-Z]:\\[^`"\r\n]*TDZIGNS_BusinessDesk\.exe)') {
        $candidate=$Matches[1].Trim()
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {return $candidate}
      }
    }
  }
  return ''
}
try {
  $dataDir=Join-Path $env:LOCALAPPDATA 'BusinessDesk'
  $updates=Join-Path $dataDir 'updates'
  New-Item -ItemType Directory -Path $updates -Force | Out-Null
  if (Get-Process -Name 'TDZIGNS_BusinessDesk' -ErrorAction SilentlyContinue) {
    throw 'Close all BusinessDesk windows before running recovery.'
  }
  $freshInstall=$false
  $target=Get-PreviousTarget $dataDir
  if ($target) {
    $answer=[System.Windows.Forms.MessageBox]::Show('Use the previously recorded installation?'+"`r`n`r`n"+$target,
      'Confirm current BusinessDesk location','YesNo','Question')
    if ($answer -ne 'Yes') {$target=''}
  }
  if (-not $target) {
    $recommended=Join-Path $env:LOCALAPPDATA 'Programs\TDZIGNS BusinessDesk\TDZIGNS_BusinessDesk.exe'
    $decision=[System.Windows.Forms.MessageBox]::Show(
      'If BusinessDesk is still installed, choose NO and locate its existing EXE.'+"`r`n`r`n"+
      'If the old executable is missing, choose YES to install in your Windows user folder:'+"`r`n"+$recommended,
      'Find BusinessDesk installation','YesNoCancel','Question')
    if ($decision -eq 'Cancel') {exit 0}
    if ($decision -eq 'Yes') {
      $target=$recommended
      $freshInstall = -not (Test-Path -LiteralPath $target -PathType Leaf)
    } else {
      Notify 'Locate the BusinessDesk EXE you normally launch. For a desktop shortcut, right-click it and choose Properties, then Open File Location.'
      $picker=New-Object System.Windows.Forms.OpenFileDialog
      $picker.Title='Select your existing TDZIGNS_BusinessDesk.exe (not the update ZIP)'
      $picker.Filter='BusinessDesk application|TDZIGNS_BusinessDesk.exe'
      $picker.CheckFileExists=$true
      if ($picker.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {exit 0}
      $target=$picker.FileName
    }
  }
  if ([IO.Path]::GetFileName($target) -ine 'TDZIGNS_BusinessDesk.exe') {throw 'Select the currently installed BusinessDesk executable.'}

  $manifestUrl='https://github.com/combatengineer88/BusinessDesk/releases/latest/download/update_manifest.json'
  $manifest=Invoke-RestMethod -Uri $manifestUrl -TimeoutSec 30 -Headers @{'User-Agent'='TDZIGNS-BusinessDesk-Recovery/2.9.4'}
  $version=[string]$manifest.version
  if ($version -notmatch '^\d+\.\d+\.\d+$' -or [version]$version -lt [version]'2.9.4') {
    throw 'The repaired v2.9.4 release is not available yet. Commit the v2.9.4 source, push tag v2.9.4 and wait for GitHub Actions to finish.'
  }
  $expectedUrl='https://github.com/combatengineer88/BusinessDesk/releases/download/v'+$version+'/TDZIGNS_BusinessDesk_'+$version+'.zip'
  if ([string]$manifest.url -cne $expectedUrl) {throw 'Update URL is not the expected official GitHub release path.'}
  $digest=[string]$manifest.sha256
  if ($digest -notmatch '^[a-fA-F0-9]{64}$') {throw 'Invalid release checksum.'}
  $download=Join-Path $updates ('BusinessDesk_recovery_'+$version+'.zip')
  $part=$download+'.part'
  Notify ('Downloading official BusinessDesk '+$version+' update from GitHub.'+"`r`n"+
      'The installer will reopen BusinessDesk after completing the update.')
  try {
    Invoke-WebRequest -Uri $expectedUrl -UseBasicParsing -OutFile $part -TimeoutSec 180 -Headers @{'User-Agent'='TDZIGNS-BusinessDesk-Recovery/2.9.4'}
    if ((Get-Item -LiteralPath $part).Length -gt 200MB) {throw 'Downloaded package exceeds the 200 MB update limit.'}
    if ((Get-FileHash -LiteralPath $part -Algorithm SHA256).Hash -ine $digest) {throw 'Checksum mismatch: the downloaded ZIP was rejected.'}
    Move-Item -LiteralPath $part -Destination $download -Force
  } finally {Remove-Item -LiteralPath $part -Force -ErrorAction SilentlyContinue}
  & (Join-Path $PSScriptRoot 'update_installer.ps1') -Package $download -Target $target -ProcessIdToWait 0 -DataDir $dataDir -ExpectedSha256 $digest -Version $version -AllowFreshInstall:$freshInstall
  if ($LASTEXITCODE -ne 0) {exit 1}
  if ($freshInstall) {
    try {
      $shell=New-Object -ComObject WScript.Shell
      $shortcut=$shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'TDZIGNS BusinessDesk.lnk'))
      $shortcut.TargetPath=$target
      $shortcut.WorkingDirectory=Split-Path -Parent $target
      $shortcut.IconLocation=$target+',0'
      $shortcut.Save()
      Notify ('BusinessDesk is installed and restarted.'+"`r`n`r`n"+'Location: '+$target+"`r`n"+'A desktop shortcut was also created.')
    } catch {
      Notify ('The application installed at '+$target+' but the desktop shortcut could not be created: '+$_.Exception.Message)
    }
  }
} catch {
  Notify ($_.Exception.Message+"`r`n`r`n"+'Installer log: '+(Join-Path $env:LOCALAPPDATA 'BusinessDesk\updates\installation.log')) 'BusinessDesk recovery error' 'Error'
  exit 1
}
