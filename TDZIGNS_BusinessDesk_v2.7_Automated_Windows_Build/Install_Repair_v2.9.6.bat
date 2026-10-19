@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0Install_Repair_v2.9.6.ps1"
if errorlevel 1 (
  echo Repair failed. Check %%LOCALAPPDATA%%\BusinessDesk\updates\installation.log
  pause
)
