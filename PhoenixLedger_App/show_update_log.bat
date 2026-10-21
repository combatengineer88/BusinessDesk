@echo off
set "UPDATEDIR=%LOCALAPPDATA%\PhoenixLedger\updates"
if not exist "%UPDATEDIR%" (
 echo No PhoenixLedger update logs were found yet.
 pause
 exit /b 1
)
explorer "%UPDATEDIR%"
if exist "%UPDATEDIR%\installation.log" start "" notepad "%UPDATEDIR%\installation.log"
