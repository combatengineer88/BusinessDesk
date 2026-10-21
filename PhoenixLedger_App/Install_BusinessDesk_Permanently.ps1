# Legacy entry point. The v2.9.6 repair installs the complete Python runtime.
$ErrorActionPreference='Stop'
& (Join-Path $PSScriptRoot 'Install_Repair_v2.9.6.ps1')
if ($LASTEXITCODE -ne 0) {exit 1}
