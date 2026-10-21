# Reopen the already-installed PhoenixLedger executable. Does not modify databases.
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Windows.Forms
function Notice([string]$message,[string]$title='PhoenixLedger', [string]$icon='Information') {
  [System.Windows.Forms.MessageBox]::Show($message,$title,'OK',$icon) | Out-Null
}
try {
  $statusPath=Join-Path $env:LOCALAPPDATA 'PhoenixLedger\updates\install_status.json'
  $exe=''
  if (Test-Path -LiteralPath $statusPath) {
    try {
      $status=Get-Content -LiteralPath $statusPath -Raw | ConvertFrom-Json
      if ($status.target -and [IO.Path]::GetFileName([string]$status.target) -ieq 'PhoenixLedger.exe' -and
          (Test-Path -LiteralPath ([string]$status.target) -PathType Leaf)) { $exe=[string]$status.target }
    } catch {}
  }
  if (-not $exe) {
    Notice 'Select the PhoenixLedger.exe you normally use (or check your desktop shortcut Properties > Open File Location).'
    $picker=New-Object System.Windows.Forms.OpenFileDialog
    $picker.Title='Locate your existing PhoenixLedger installation'
    $picker.Filter='PhoenixLedger application (PhoenixLedger.exe)|PhoenixLedger.exe'
    if ($picker.ShowDialog() -ne 'OK') {exit 0}
    $exe=$picker.FileName
  }
  if ([IO.Path]::GetFileName($exe) -ine 'PhoenixLedger.exe') {throw 'Selected file has an unexpected name.'}
  Start-Process -FilePath $exe -WorkingDirectory (Split-Path -Parent $exe) -ErrorAction Stop
  Notice ('PhoenixLedger launch requested.'+"`r`n"+'Application path: '+$exe)
} catch {
  Notice ($_.Exception.Message+"`r`n"+'If the application is missing, install the latest GitHub release using repair_from_github.bat.') 'Could not reopen PhoenixLedger' 'Error'
  exit 1
}
