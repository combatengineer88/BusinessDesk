@echo off
cd /d "%~dp0"
py -3 -m pip install -r requirements.txt
if errorlevel 1 goto fail
py -3 businessdesk.py
exit /b 0
:fail
echo Dependency installation failed. Internet is needed for initial setup, but not normal operation.
pause
exit /b 1
