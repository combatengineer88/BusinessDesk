TDZIGNS LLC BUSINESSDESK - UPDATER REPAIR (v2.9.4)
===================================================

Your installed PhoenixLedger might close during an update without reopening.
The old hidden updater can also fail without showing an error.

BEFORE DOING ANYTHING:
1. Back up %LOCALAPPDATA%\PhoenixLedger\business.db (close PhoenixLedger first).
2. Do NOT delete your %LOCALAPPDATA%\PhoenixLedger folder.
3. The repair from GitHub requires v2.9.4 or newer to be PUBLISHED
   under https://github.com/combatengineer88/BusinessDesk/releases .

ONE-TIME REPAIR:
1. Extract this repair ZIP to a normal folder (not inside a compressed ZIP).
2. Close PhoenixLedger if it is running.
3. Double-click repair_from_github.bat .
4. The repair looks for the previous installed EXE in the last updater log.
5. If it finds an EXE, confirm its full path. Otherwise choose:
   NO: locate your currently installed PhoenixLedger.exe manually.
   YES: install into %LOCALAPPDATA%\Programs\PhoenixLedger\
        PhoenixLedger.exe and create a desktop shortcut.
6. It downloads the compiled Windows update ZIP directly from your GitHub
   Release, verifies SHA-256, backs up the old EXE, installs/restarts, and
   waits for the new app to report that the login window is ready.
7. If something fails, the updater displays an error and attempts rollback.

IMPORTANT LOCATIONS:
Existing/new app: Same location as the EXE you selected (shown on update screen).
Fresh install:    %LOCALAPPDATA%\Programs\PhoenixLedger\PhoenixLedger.exe
Business database:%LOCALAPPDATA%\PhoenixLedger\business.db
Update logfile:  %LOCALAPPDATA%\PhoenixLedger\updates\installation.log
Update status:   %LOCALAPPDATA%\PhoenixLedger\updates\install_status.json
Startup errors:  %LOCALAPPDATA%\PhoenixLedger\updates\startup_errors.log
Backup EXEs:     %LOCALAPPDATA%\PhoenixLedger\updates\backup_*

Double-click show_update_log.bat to open the log in Notepad.

If there is no published release v2.9.4 yet, publish it using the GitHub
repository update package first. A source-code ZIP cannot install itself.
This repair process requires a Windows computer and Internet access.
