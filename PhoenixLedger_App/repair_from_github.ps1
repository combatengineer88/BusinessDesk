# Legacy entry point. Migrate old one-file installs to the v2.9.6 onedir layout.
$ErrorActionPreference='Stop'
& (Join-Path $PSScriptRoot 'Install_Repair_v2.9.6.ps1')
if ($LASTEXITCODE -ne 0) {exit 1}
