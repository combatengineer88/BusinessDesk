# PhoenixLedger v3.2.1 — Offline Account Recovery

**Two ways to get back into your account:**

1. **Emergency account recovery ZIP** (separate download): run `Recover_PhoenixLedger_Windows.bat` on the PC with your database. It lists registered usernames, creates a full SQLite backup, and changes the selected password. Does not require signing in or upgrading.
2. **In-app recovery:** after signing in, administrators are invited to generate a one-time recovery code and store it securely. The login screen has **Forgot username or password?**, which accepts a saved code and enables a new password. Codes are hashed and consumed after use. Admins can also reset employee passwords from Administration > Account recovery.

**Security:** All operations are local. Recovery codes are never stored as plaintext. Users cannot reveal existing passwords. The emergency tool should be used only by the Windows owner who has legitimate access to the business database.

**Migration:** The `account_recovery` table is created automatically without modifying customers, suppliers, products, estimates, invoices, POs, inventory, accounting, or other business data.

**Publish:** Upload the contents to the existing GitHub repo, commit to `main`, and push tag `v3.2.1`; GitHub Actions creates `PhoenixLedger_Setup_3.2.1.exe`. Keep old databases and back up before upgrading.
