# PhoenixLedger v3.0.1 — Build and rebrand repair

## Fixed
- `package_release.py` now reads the version from `businessdesk.py`, preventing the ZIP/manifest mismatch (`PhoenixLedger_2.9.12.zip` vs `PhoenixLedger_3.0.0.zip`).
- `test_install_location.py` uses `PHOENIXLEDGER.EXE` in its Windows filename case-insensitivity test; the old BusinessDesk executable must not be accepted as a PhoenixLedger install target.
- Changes application version to **3.0.1** since tag `v3.0.0` is already published as a Git reference to a failed build.
- Inno Setup AppId is now unique to PhoenixLedger (not BusinessDesk) and does not reuse the old installation path. This avoids collisions with an existing BusinessDesk installation.
- Adds a Phoenix icon asset, applies it to the Windows executable and installer, and shows it in the application header.

## Apply on GitHub
1. Copy files in `PhoenixLedger_App/` into the existing `PhoenixLedger_App/` directory, replacing matching files. Do not delete unrelated files.
2. Replace `.github/workflows/windows-release.yml` at the repository root.
3. Commit to `main`.
4. Push tag `v3.0.1` (do not retry the failed `v3.0.0` tag).
5. Build should generate `PhoenixLedger_Setup_3.0.1.exe`.

## Important
The new installer is a separate Windows installation from old BusinessDesk, preserving the old app and records. PhoenixLedger copies user data from `%LOCALAPPDATA%\BusinessDesk` to `%LOCALAPPDATA%\PhoenixLedger` on first launch when the destination does not exist. **Close BusinessDesk and back up its database before migrating.** The original data is not deleted.

GitHub is still hosted at `combatengineer88/BusinessDesk`; this is intentional to avoid breaking release URLs.
