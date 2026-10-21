# PhoenixLedger v3.0.0 — Full Rebrand Update

This release rebrands BusinessDesk to **PhoenixLedger** while preserving compatibility with the existing GitHub repository and migrating local data from `%LOCALAPPDATA%\BusinessDesk` to `%LOCALAPPDATA%\PhoenixLedger` on first launch.

## Highlights
- App name changed to PhoenixLedger
- Windows installer and update assets renamed to `PhoenixLedger_*`
- Blue phoenix logo included and used as the default app/report logo
- Existing BusinessDesk data is copied forward automatically on first launch
- Current GitHub repository URL remains supported for updates

## Publishing
1. Upload this package to your repository.
2. Commit to `main`.
3. Push tag `v3.0.0`.
4. GitHub Actions should build `PhoenixLedger_Setup_3.0.0.exe`.
