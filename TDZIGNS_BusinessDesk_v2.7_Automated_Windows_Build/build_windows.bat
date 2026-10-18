@echo off
cd /d "%~dp0"
py -3 -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto fail
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed --name TDZIGNS_BusinessDesk --collect-all reportlab --collect-all PIL --hidden-import excel_import --add-data "update_installer.ps1;." launcher.py
if errorlevel 1 goto fail
echo EXE built at dist\TDZIGNS_BusinessDesk.exe
pause
exit /b 0
:fail
echo Build failed.
pause
exit /b 1
