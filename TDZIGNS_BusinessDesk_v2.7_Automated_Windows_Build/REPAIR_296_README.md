# TDZIGNS LLC BusinessDesk v2.9.6 — Windows Python DLL startup repair

## Why v2.9.5 failed

The message "Failed to load Python DLL ...Temp\\_MEI...\\python312.dll — The specified module could not be found" comes from the PyInstaller **one-file** bootloader, before Python or BusinessDesk's error logger can start. The failure can be caused by missing or blocked Python runtime DLLs or a dependent Windows runtime. Seeing the message alone does not identify which DLL/dependency is absent.

v2.9.6 switches GitHub's release build to PyInstaller **one-folder (onedir)** mode. The release ZIP now contains both `TDZIGNS_BusinessDesk.exe` and `_internal/python312.dll` with the rest of the bundled Python runtime. It is *not* a ZIP containing only the EXE.

## Publish v2.9.6

1. Extract `BusinessDesk_v2.9.6_GitHub_Repository_Update.zip`.
2. Commit the contained application files to `TDZIGNS_BusinessDesk_v2.7_Automated_Windows_Build/` in `combatengineer88/BusinessDesk` (overwrite matching files). Commit `.github/workflows/windows-release.yml` at the repository ROOT.
3. Wait for commit to land on `main`, then create and push tag `v2.9.6`. From Git Bash or GitHub Desktop command prompt:

   ```shell
   git checkout main
   git pull origin main
   git tag v2.9.6
   git push origin v2.9.6
   ```

4. Check GitHub Actions. The workflow builds using `--onedir`, checks for the Python DLL, starts the EXE with `--smoke-test`, verifies packaging and installer handoff, and then publishes `TDZIGNS_BusinessDesk_2.9.6.zip`, its `.sha256`, and `update_manifest.json` to GitHub Releases.
5. **Do not run the old v2.9.5 in-app updater for v2.9.6**: it only understands EXE-only ZIPs. Use the one-time repair kit below to migrate.

## Repair existing Windows installation

1. **Publish and verify the GitHub v2.9.6 release first.** `Install_Repair_v2.9.6.bat` downloads the latest official compiled release, not the source ZIP.
2. Extract `BusinessDesk_v2.9.6_One_Time_Repair_Kit.zip` (don't execute from inside the compressed folder).
3. Close BusinessDesk and any `TDZIGNS_BusinessDesk.exe` processes in Task Manager.
4. Double-click `Install_Repair_v2.9.6.bat` and approve the installation.
5. The helper downloads the official release from `combatengineer88/BusinessDesk`, checks the manifest and SHA-256 checksum, backs up `business.db` (+ WAL/SHM if present), expands into a temporary application **directory**, tests Python startup, backs up the old installation directory, activates the new directory, relaunches the program, and waits for its startup marker.
6. The program will live at `%LOCALAPPDATA%\Programs\TDZIGNS BusinessDesk\TDZIGNS_BusinessDesk.exe` with the adjacent `_internal` folder. The helper also creates a desktop and Start Menu shortcut.
7. If you already have the compiled GitHub Release ZIP and its checksum, use `install_local_update.bat` instead of the downloader.
8. Logs and pre-install DB backups are stored under `%LOCALAPPDATA%\BusinessDesk\updates\`.

On failure, installation should leave the old folder intact or roll it back and log an error. Test on a backup database first. The Windows flow requires real machine testing, despite the CI tests.

## If you still get a Python DLL error

The Python DLL error may come from Windows missing a dependency or blocking a DLL, not just the extraction layout. Check Windows Security protection history for quarantined files and install/repair Microsoft's official **Microsoft Visual C++ Redistributable 2015–2022 x64**. Use the official Microsoft link: https://aka.ms/vs/17/release/vc_redist.x64.exe . Don't copy random DLLs from third-party download websites. Share `installation.log` or `recovery_296.log` for further diagnosis.

## Future in-app updates

BusinessDesk v2.9.6 and newer accept a **full onedir release ZIP** through Check GitHub for updates, verify its checksum, stage and test the complete folder, wait for the existing process to exit, back up the old folder, swap in the new one, and restart with a startup handshake. The application data directory is unchanged.
