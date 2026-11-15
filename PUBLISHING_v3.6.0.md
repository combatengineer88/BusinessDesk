# PhoenixLedger v3.6.0 — publishing checklist

The prior tag `v3.5.0` points to a commit that still contains `VERSION = '3.4.0'`. **Do not rerun that tag**, and do not just update README files.

1. Extract `PhoenixLedger_v3.6.0_UI_Refresh_GitHub_Update.zip`.
2. Upload **all files** from the archive's `PhoenixLedger_App` directory to `PhoenixLedger_App/` in the existing repository, replacing matching files and adding new ones. Also replace `.github/workflows/windows-release.yml`.
3. Commit the updated contents to `main`.
4. Open `https://github.com/combatengineer88/BusinessDesk/blob/main/PhoenixLedger_App/businessdesk.py` and verify `VERSION = '3.6.0'`. Also verify `PhoenixLedger_App/release_preflight.py` appears in GitHub. **If the version is still 3.4.0, don't create the tag yet.**
5. Create tag `v3.6.0` from the new `main` commit. If you use git CLI from a current checkout:

   ```powershell
   git switch main
   git pull origin main
   # Copy the extracted update's contents into the repository before these commands.
   git add PhoenixLedger_App .github/workflows/windows-release.yml README_v3.6.0.md
   git commit -m "PhoenixLedger v3.6.0 - UI refresh and CSV export"
   python PhoenixLedger_App/release_preflight.py v3.6.0
   git push origin main
   git tag v3.6.0
   git push origin v3.6.0
   ```

6. Watch the `Build and Publish PhoenixLedger Updates` workflow. It should publish `PhoenixLedger_Setup_3.6.0.exe` and the complete onedir ZIP.

**Do not overwrite the current business database.** Back it up before installing.

The update includes 3.5.0 bulk pricing features as well as new 3.6.0 UI features, so a separate 3.5.0 build is not required.
