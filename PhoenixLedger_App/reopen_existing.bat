@echo off
powershell.exe -NoProfile -STA -ExecutionPolicy Bypass -File "%~dp0reopen_existing.ps1"
if errorlevel 1 pause
