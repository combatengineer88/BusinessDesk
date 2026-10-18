@echo off
set "UPDATEDIR=%LOCALAPPDATA%\BusinessDesk\updates"
if not exist "%UPDATEDIR%" (
 echo No BusinessDesk update logs were found yet.
 pause
 exit /b 1
)
explorer "%UPDATEDIR%"
if exist "%UPDATEDIR%\installation.log" start "" notepad "%UPDATEDIR%\installation.log"
