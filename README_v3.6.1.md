# PhoenixLedger v3.6.1 — Excel Import Repair

This is the complete source tree based on v3.6.0, with no feature removals.

## Fix
- Exclude optional `numpy` from both Windows PyInstaller build commands (`--exclude-module numpy`). PhoenixLedger's XLSX import uses `openpyxl`, which works without NumPy. A partially bundled NumPy distribution can cause `module numpy has no attribute short` during import.
- Extend the Windows executable `--smoke-test` to **write and read an XLSX workbook** with `openpyxl`, so the GitHub runner catches a broken Excel import before publishing the installer.
- Align the app, batch build, and Inno Setup versions at **3.6.1**. The GitHub workflow already enforces matching tags.

## Publish
1. Extract the ZIP and copy its `PhoenixLedger_App` and `.github/workflows/windows-release.yml` into your existing repository, replacing matching files.
2. Commit and push **main**. Verify the file `PhoenixLedger_App/businessdesk.py` has `VERSION = '3.6.1'` on GitHub.
3. Create and push **v3.6.1** from that commit. Do not create the tag from an older commit.
4. The Windows build should publish `PhoenixLedger_Setup_3.6.1.exe` and `PhoenixLedger_3.6.1.zip` after all validations pass.

## Data
No database schema changes. Existing business data, products, imports, and release/update configuration are retained. Make a backup of `%LOCALAPPDATA%\PhoenixLedger\business.db` before upgrading.

## Tests
A source import test, Python compilation check, and static package checks were run in the preparation environment. **A real Windows GitHub Actions build and installer test remain necessary.**
