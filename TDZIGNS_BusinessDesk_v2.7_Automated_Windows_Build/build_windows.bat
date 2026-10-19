@echo off
cd /d "%~dp0"
py -3.12 -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto fail
py -3.12 -m PyInstaller --noconfirm --clean --onedir --windowed --name TDZIGNS_BusinessDesk --collect-all reportlab --collect-all PIL --collect-all openpyxl --hidden-import excel_import --hidden-import supplier_catalog --hidden-import release_layout --add-data "update_installer.ps1;." launcher.py
if errorlevel 1 goto fail
if not exist "dist\TDZIGNS_BusinessDesk\_internal\python312.dll" goto fail
py -3.12 package_release.py
if errorlevel 1 goto fail
echo Ready-to-install update ZIP created.
pause
exit /b 0
:fail
echo Build failed. Requires Windows and Python 3.12.
pause
exit /b 1
