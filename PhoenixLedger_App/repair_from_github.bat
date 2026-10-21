@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0repair_from_github.ps1"
if errorlevel 1 (
 echo PhoenixLedger recovery was unsuccessful. See the error dialog or installation.log.
 pause
)
