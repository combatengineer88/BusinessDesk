TDZIGNS LLC BUSINESSDESK v2.9.4 — UPDATE RESTART RELIABILITY
===============================================================

WHAT WAS WRONG
The previous GUI closed immediately after starting the PowerShell helper,
without establishing that the helper had validated the update package and
was ready to replace the installed EXE. Because PowerShell was hidden,
failures could leave the application closed with no obvious explanation.
The precise reason for a specific user's failure requires their installation.log.

WHAT CHANGED IN v2.9.4
- GUI remains open until the installer verifies and unpacks the new EXE and
  writes a unique PREPARED acknowledgment file.
- If preparation fails, the GUI remains open and displays a specific error.
- The installer runs in a visible console instead of a detached hidden process.
- Once PhoenixLedger exits, the helper backs up/replaces the original EXE,
  launches it, and checks that the login screen signals startup.
- On startup failure it reports the error and tries to restore/reopen the old EXE.
- The updater records the original program location and writes a manual
  Reopen PhoenixLedger.cmd file inside the user's updates folder.
- GitHub Windows Actions checks that the update ZIP can be verified and the
  installer can complete its preparation handshake.

IF BUSINESSDESK IS CURRENTLY CLOSED
1. Extract the Recovery Kit ZIP on your Windows PC.
2. Double-click reopen_existing.bat. It tries the path saved by the last
   update, or lets you browse for your installed PhoenixLedger EXE.
3. Check for errors in:
   %LOCALAPPDATA%\PhoenixLedger\updates\installation.log
   %LOCALAPPDATA%\PhoenixLedger\updates\startup_errors.log
   %LOCALAPPDATA%\PhoenixLedger\updates\install_status.json
4. If the installed EXE cannot be opened, first publish v2.9.4 to the
   official GitHub Release, then run repair_from_github.bat from the kit.
   It will download the signed-off release ZIP and offer an install target.

PUBLISHING v2.9.4
- Upload the extracted GitHub Update ZIP contents to combatengineer88/BusinessDesk,
  maintaining the .github/workflows folder at repository ROOT and application
  files inside PhoenixLedger_App.
- Commit changes on main and push the NEW tag v2.9.4.
- Verify GitHub Actions passes and release v2.9.4 contains the executable ZIP.
- Use repair_from_github.bat for the one-time transition when the older
  updater is unable to restart PhoenixLedger.
- From v2.9.4 onward, use Check GitHub for updates normally.

DATA SAFETY
Back up %LOCALAPPDATA%\PhoenixLedger\business.db before recovery. Keep all
PhoenixLedger application-data folders and backups. The recovery installer
replaces the program EXE, not the business database.

VALIDATION
Three Python handoff tests and Python syntax checks passed. Actual Windows
install/restart behavior and the new CI PowerShell preflight require testing.
