@echo off
cd /d "%~dp0"
py -3.12 -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto fail
py -3.12 -m PyInstaller --noconfirm --clean --onedir --windowed --icon "phoenixledger.ico" --name PhoenixLedger --collect-all reportlab --collect-all PIL --collect-all openpyxl --hidden-import excel_import --hidden-import supplier_catalog --hidden-import release_layout --hidden-import installer_assets --hidden-import document_templates --hidden-import template_editor --hidden-import visual_templates --hidden-import visual_template_editor --hidden-import home_workspace --hidden-import modern_theme --hidden-import po_editor --hidden-import responsive_ui --hidden-import address_utils --hidden-import report_export --hidden-import account_workflows --hidden-import account_dialogs --hidden-import supplier_management --add-data "update_installer.ps1;." --add-data "installer_update.ps1;." --add-data "phoenixledger_logo.png;." --add-data "phoenixledger_icon.png;." launcher.py
if errorlevel 1 goto fail
if not exist "dist\PhoenixLedger\_internal\python312.dll" goto fail
py -3.12 package_release.py
if errorlevel 1 goto fail
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" (
  echo Windows Setup was not built: install Inno Setup 6 from jrsoftware.org
  echo The update ZIP was created successfully.
  pause
  exit /b 0
)
"%ISCC%" /DBuildVersion=3.2.0 "businessdesk.iss"
if errorlevel 1 goto fail
py -3.12 package_setup.py
if errorlevel 1 goto fail
echo PhoenixLedger Setup EXE and update ZIP created successfully.
pause
exit /b 0
:fail
echo Build failed. Requires Windows and Python 3.12.
pause
exit /b 1
