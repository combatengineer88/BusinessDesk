# TDZIGNS LLC BusinessDesk v2.0

Windows desktop business manager, offline by default. Includes v1 customer, employee, inventory, estimates, invoices, expenses, and reports, plus v2 enhancements.

## New in v2
- **TDZIGNS LLC branding:** configurable business contact information and logo, shown on PDFs.
- **Branded PDF invoices, estimates, and purchase orders** (ReportLab).
- **Product images:** copy an image into local application data; view in the app (Pillow recommended).
- **Barcode/SKU lookup:** type or scan a barcode in the Products search box. USB keyboard-emulating barcode scanners work; no hardware integration is required.
- **Supplier and purchase order management:** create supplier, PO, PDF, receive full order into stock and accounts payable.
- **Basic double-entry ledger:** balanced journal entries automatically created for **new** v2 invoices, invoice item cost of goods sold, payments, expenses, and PO receipts; manual entries; account balances and CSV export.
- **Optional update checker:** configure an HTTPS JSON manifest URL, check manually, and download a SHA-256 verified ZIP into local staging. Installation is manual. No network required during normal business use.

## Run on Windows
1. Install Python 3.11+ (enable the Python launcher `py`).
2. Extract this ZIP to a local folder.
3. Double-click `run_windows.bat` while online for **one-time installation** of PDF/image dependencies.
4. On first launch, create your admin account. Existing v1 databases are upgraded in place.
5. Use **Updates / Branding** to enter TDZIGNS LLC contact details and choose a logo.
6. Subsequent runs work offline.

## Build a portable EXE
On Windows, run `build_windows.bat` (internet needed to install dependencies). Output: `dist\\TDZIGNS_BusinessDesk.exe`. This is a **portable EXE, not an MSI installer**. Build and test it on Windows. Distributing an unsigned executable can trigger SmartScreen warnings.

## Update manifest format
Host this JSON at an HTTPS URL you control, with a HTTPS URL to a ZIP package and its exact SHA-256 checksum:

```json
{
  "version": "2.1.0",
  "url": "https://example.com/releases/TDZIGNS_BusinessDesk_2.1.0.zip",
  "sha256": "64_lowercase_hex_characters_for_the_zip"
}
```

Enter the manifest URL under Updates / Branding and click **Check for update**. This is not an unattended installer: updates are verified and staged for manual installation, protecting your business data. Never use an untrusted update URL.

## Data and backup
All data is stored in `%LOCALAPPDATA%\\BusinessDesk\\business.db`; product images are stored in `%LOCALAPPDATA%\\BusinessDesk\\product_images`. Use Administration > Backup database. **Back up the product_images folder and business logo too**; the database backup alone does not include image files. No data is uploaded by the application unless you explicitly use the update check.

## Limitations and accounting cautions
- Multiple employee **accounts on one PC**, not concurrent use across networked computers.
- Staff roles remain basic; only administrators can add users, back up, configure updates/branding, and make manual journal entries. This is not a comprehensive permission system.
- Journal entries are posted only for transactions created **after** v2 is installed; v1 data is not automatically backfilled. Reconcile opening balances with your accountant before relying on ledger totals.
- The ledger is an initial bookkeeping aid, **not** full GAAP accounting, tax software, or a substitute for a bookkeeper. No chart-of-accounts enforcement, closing periods, bank reconciliation, depreciation, vendor payment posting, or tax return filing.
- PO receiving is full-order only, and accounts payable payments are not implemented. Inventory valuation may need adjustment for purchases, opening stock, freight, and costing method.
- Expenses are assumed paid immediately from Cash; there is no bank selection. Tax on invoices is manually entered and not jurisdiction-validated.
- Invoices deduct inventory immediately. No invoice edit, void, return, refund, credit note, partial PO receipt, or sales discount workflow yet.
- Barcode scanning is via keyboard-wedge scanners; scanner drivers/label printing are not included.
- PDF invoices use supplied business information; review tax/legal requirements before sending.
- **Auto-updater** means optional checking and verified download, not automatic execution or installation. Optional check-at-sign-in is supported; update installation still requires manual action.
- There is no audit log, encrypted database, password reset, or automated backup schedule. Protect Windows user accounts and use regular backups.
- This code has automated non-GUI smoke tests but has not been tested on a physical Windows computer. Test thoroughly with sample data before using live transactions.

## Files
- `businessdesk.py`: v2 application
- `core_v1.py`: v1 application foundation
- `requirements.txt`: ReportLab and Pillow
- `run_windows.bat`, `build_windows.bat`: run and package scripts
- `test_smoke.py`: automated database and PDF test


## Version 2.1.0 — one-click updater foundation

**Important one-time upgrade:** Version 2.0.1 cannot install itself automatically. Extract this release, run `build_windows.bat` on Windows, then use the new `dist\\TDZIGNS_BusinessDesk.exe` going forward. Copy it to a **writable application folder** such as `%LOCALAPPDATA%\\TDZIGNS LLC\\App` (not `Program Files`). Future EXE releases can be installed directly through **Updates / Branding**.

### How to configure future updates
1. Publish each new Windows EXE as a ZIP with exactly one root entry named `TDZIGNS_BusinessDesk.exe`.
2. Host the ZIP at a stable **HTTPS** URL (for example, a GitHub Releases asset).
3. Calculate the SHA-256 of the ZIP (Windows: `certutil -hashfile filename.zip SHA256`).
4. Host a JSON manifest at a stable HTTPS URL that you control:
```json
{
  "version": "2.2.0",
  "url": "https://your-domain.example/releases/TDZIGNS_BusinessDesk_2.2.0.zip",
  "sha256": "replace_with_the_64_character_lowercase_sha256_of_the_zip"
}
```
5. In the program, enter the manifest URL in **Updates / Branding** and save it. Click **Check for update** or enable check-at-sign-in.
6. An administrator approves download and installation. The updater verifies SHA-256, backs up the live SQLite database, exits the app, replaces the EXE, and restarts it.
7. The updater keeps a copy of the previous EXE in `%LOCALAPPDATA%\\BusinessDesk\\updates\\backup_*`. It restores the old EXE if replacement or relaunch fails. See `updates\\installation.log` for details.

**No release hosting is configured automatically.** You must publish future packages and maintain the manifest; otherwise the app has nothing to download. Updates need internet access, but daily business operations remain offline.

**Limitations:** The updater works for a packaged EXE, not Python source runs. It cannot overwrite a protected folder without Windows permissions. This is a SHA-256 integrity check against the manifest, not cryptographic publisher authentication; protect the manifest hosting account and preferably code-sign EXEs. Windows may warn about unsigned applications. Test on Windows before using with live records. Database migrations should be designed to remain backward-compatible; reverting the EXE does not automatically revert database migrations. Backups are created before installation. No update can be installed while the app remains open.

## Version 2.2.0 — local offline updates
Two ways to install a downloaded update package:
1. **Inside the app:** Updates / Branding > Install local update ZIP or Select update folder. Select a `TDZIGNS_BusinessDesk_2.3.0.zip` (or later version). Administrator approval is required; the app backs up the SQLite database and restarts via the helper.
2. **Outside the app:** Close BusinessDesk, then run `install_local_update.bat` from the extracted source folder. Select the folder with the downloaded update ZIP, select the ZIP, and select the existing `TDZIGNS_BusinessDesk.exe` to replace. The script backs up database files and invokes the same helper.

Update packages must contain exactly one root file `TDZIGNS_BusinessDesk.exe`. Put a matching `.sha256` file alongside the ZIP when possible. The checksum is for integrity, not publisher authentication: obtain update packages only from a trusted source. Offline updates require a packaged EXE; they cannot hot-update a Python source run. The external installer uses Windows PowerShell and should be run with permissions to write to the EXE's folder. Updates are not installed unless approved. The helper attempts executable rollback on failure; database migrations are not automatically rolled back.

Run `package_release.py` after building a Windows EXE to generate the ZIP, SHA-256 sidecar, and manifest for publishing.

## Version 2.3.0 — Excel import
- **Customers tab > Import customers from Excel** and **Products / Catalog > Import products from Excel**.
- Supports `.xlsx` and `.xlsm` workbooks. `.xls` files should first be saved as `.xlsx`.
- Uses the first worksheet and the first row as column headers; order of columns does not matter.
- Required customer column: `Name` (also accepts `Customer Name` or `Company`).
- Optional customer columns: `Email`, `Phone`, `Address`, `Notes`.
- Required product columns: `SKU`, `Name`, `Price`.
- Optional product columns: `Barcode`, `Description`, `Cost`, `Qty`.
- Monetary values are dollar amounts, e.g. `19.95`; stock is a whole number.
- The preview displays the first eight records. Any invalid row prevents the entire import, with row numbers shown.
- Duplicate products match existing SKUs; duplicate customers match names (case-insensitive). Choose **Update**, **Skip**, or **Cancel**. Product update quantities replace current stock; they do not add to it.
- Import is transactional: a database error rolls back all imported records.
- Admin login is required. Back up your database before importing.
- The import is for business records only, not invoice histories or accounting entries. Inventory import does not create purchase-order or journal entries.
- Python dependency `openpyxl` added to `requirements.txt`; rebuild the Windows EXE using `build_windows.bat`.
- Existing online and local ZIP update paths are retained. A v2.3 EXE ZIP can be published using `package_release.py`.

## 2.3.1 Updater fix
- Local picker accepts any ZIP filename and validates its contents before installation.
- Source-code ZIPs now receive a specific explanation instead of an obscure expected-file error.
- Windows update packages must contain the compiled `TDZIGNS_BusinessDesk.exe` at the ZIP root.
- Build the executable using `build_windows.bat`, then run `py -3 package_release.py` to generate a Windows update ZIP and `.sha256` checksum.
- **The ZIP distributed here is still source code, not a compiled Windows executable.** This environment cannot build/test a Windows executable.
- Existing 2.3.0 installations require a manual one-time source rebuild to obtain this fix.

## v2.3.2: Find the installer and install standalone EXE updates

**The local package installer is named `install_local_update.bat` and is in the ROOT of this ZIP, next to `businessdesk.py` and `build_windows.bat`.** It is a Windows batch launcher, not a compiled installer EXE.

For an update while BusinessDesk is closed:
1. Extract this source ZIP with Windows Explorer (do not run scripts directly inside the compressed ZIP).
2. Double-click `install_local_update.bat`.
3. Choose the folder holding the update.
4. Select a compiled `TDZIGNS_BusinessDesk.exe` **or** a release ZIP containing it.
5. Choose your currently installed `TDZIGNS_BusinessDesk.exe` (a different file).
6. Review the checksum warning and complete the update.

For an update from within the program, open **Updates / Branding** and use **Install local ZIP or EXE** or **Select update folder**. Both accept standalone compiled EXEs and installable ZIPs. Administrator approval is required.

The downloaded source ZIP is not a compiled Windows EXE. To create the first executable, run `build_windows.bat` on Windows. For subsequent builds, `package_release.py` can create a ZIP and checksum, or the compiled EXE can be selected directly.

**Safety:** Keep your original EXE and a database backup. No Windows execution tests have been run in this environment. The SHA-256 sidecar validates integrity only when obtained from a trusted source; it does not authenticate a publisher. The updater needs write access to the installation directory. Do not run downloaded programs from untrusted sources.

## Version 2.4.0 — Archive current database and create new

In **Administration**, sign in as an administrator and select **Archive current database and create new**. Choose a **new, unused `.db` filename** in a safe location (external drive is supported). Confirm the operation. BusinessDesk uses SQLite's online backup API to create and integrity-check a full archive before replacing the live database with a clean one.

The new database retains **the currently signed-in administrator's login/password**, TDZIGNS LLC branding and update settings. It resets customer and product records, invoices, estimates, payments, expenses, suppliers, purchase orders, accounting entries, and other employee accounts. Recreate additional employee accounts under Administration.

**Important:** This is not a restore feature. To open an old archive again, close BusinessDesk and restore the archived file as `%LOCALAPPDATA%\\BusinessDesk\\business.db` after making a backup of the currently active database. Do not replace the database while BusinessDesk is running. Product images and the invoice logo are stored separately from SQLite and are not removed by creating a new database.

Do not choose the live database as the archive location. Archive creation will refuse to overwrite an existing file. Keep multiple backups on a separate drive. Tested for Python syntax; Windows GUI still requires testing.


## Version 2.5.0 — Import customers and suppliers from Excel

- **Customers** → **Import customers from Excel**
- **Purchase Orders** → **Import suppliers from Excel**
- Existing product import remains available.
- Supported workbooks: `.xlsx` and `.xlsm`; first worksheet, headings in first row.
- Customers: required `Name` (or `Customer Name`/`Company`); optional `Email`, `Phone`, `Address`, `Notes`.
- Suppliers: required `Name` (or `Supplier Name`/`Vendor Name`/`Company`); optional `Email`, `Phone`, `Address`.
- Imports show a preview and validate all rows. Any invalid row stops the entire import.
- Existing records are matched by name, case-insensitively. Choose Update, Skip, or Cancel.
- Imports are transactional. Only administrator accounts may import.
- Build on Windows using `build_windows.bat`. This is source code, not an installable Windows update ZIP.

## Version 2.7.0 — Automatically built Windows update ZIPs

This repository includes `.github/workflows/windows-release.yml`. Upload the **contents** of this source folder to a GitHub repository (including the hidden `.github` folder). Under **Actions → Build BusinessDesk Windows update → Run workflow**, start a Windows build. Once it completes, download the `BusinessDesk-Windows-Update` artifact, unzip the artifact, and select the contained `TDZIGNS_BusinessDesk_2.7.0.zip` in **BusinessDesk → Updates → Install local ZIP or EXE**. That inner ZIP contains the actual compiled Windows EXE. You do not need to run PyInstaller yourself.

Alternatively, push the tag `v2.7.0` to the repository. The workflow then publishes a GitHub Release containing the ready-to-install ZIP and its `.sha256` checksum. This requires permission to create releases. A GitHub Actions build is necessary: the source ZIP downloaded from ChatGPT is not itself installable through BusinessDesk.

IMPORTANT: If your existing BusinessDesk updater supports local ZIP packages, it can consume the generated compiled update ZIP without replacing the updater first. The updater expects `TDZIGNS_BusinessDesk.exe` at the root of the *inner* ZIP, not the source ZIP or GitHub Actions artifact ZIP.

Do not publish untrusted binaries. Verify GitHub Actions logs and test the new EXE on Windows before deploying to production. The build workflow has not been executed in this environment.


## 2.8.0 — One-click update checks through GitHub Releases

When running the compiled Windows app, the **Updates / Branding → Check GitHub for updates** button uses the preconfigured public release URL:

`https://github.com/combatengineer88/BusinessDesk/releases/latest/download/update_manifest.json`

The updater compares versions, asks before installing, downloads and SHA-256-verifies the package, backs up the database and existing executable, and runs the PowerShell installer for restart or rollback. Administrator login is required. The optional check-at-login toggle also uses this URL even if nothing has been manually saved.

### Configure this particular GitHub repository

The repository currently stores application sources under `TDZIGNS_BusinessDesk_v2.7_Automated_Windows_Build/`. **Keep that folder name for now** because the workflow refers to it. Upload the v2.8 source files from this ZIP into that existing folder, replacing the existing files, and place the updated workflow at repository root `.github/workflows/windows-release.yml`.

After committing those files to `main`, create and push an exact version tag `v2.8.0` from the new commit. The root workflow is triggered by tags `v*`, builds a Windows EXE, creates a ZIP, checksum and manifest, and publishes all three assets on the public **GitHub Releases** page, marked latest. **A normal Actions run via Run workflow only creates an Actions artifact; it does not publish a release, and the app cannot see those artifacts through the Releases URL.**

To create a tag using the GitHub website: open Releases → Draft a new release → Choose a tag → Create new tag `v2.8.0` on `main` → publish the release. **However**, creating the release *before* the tag-triggered workflow finishes can conflict with the `gh release create` step. Prefer creating the tag via Git on your computer (`git tag v2.8.0` then `git push origin v2.8.0`) so the workflow publishes the release itself. Alternatively edit the workflow to upload into an already-existing release.

After GitHub Actions finishes, check the repo **Releases** page for the three assets: `TDZIGNS_BusinessDesk_2.8.0.zip`, `TDZIGNS_BusinessDesk_2.8.0.sha256`, `update_manifest.json`. The manifest's URL points to the first ZIP and includes its SHA-256. Test the update on a nonproduction database.

**Bootstrap:** Older compiled BusinessDesk versions do not yet have the built-in GitHub Releases URL. Install 2.8.0 once using the older local update feature (download the compiled 2.8.0 ZIP from GitHub Releases). All later versions can be installed by clicking **Check GitHub for updates**.

The source ZIP created by ChatGPT is not itself a compiled update and does not install through the app. No Windows build or release has been executed from this environment.


## v2.9.0 — Customer-specific prices and sales-tax exemption

**Customers tab:** Add or edit customers and tick **Tax-exempt customer** (unchecked by default). Existing customers automatically migrate with tax_exempt=0. Before marking a customer exempt, confirm you have the required exemption documentation; tax treatment varies by jurisdiction and transaction.

**Customers tab → Customer product prices:** Select a customer, click **Customer product prices**, select a catalog product, enter the negotiated unit price, and click **Save price**. You can reset to **Use catalog price**. These overrides apply to new documents and do not change the global catalog price or previously created estimates/invoices.

**Estimates / Invoices → New document:** Select the customer by name (no numeric customer ID necessary). The product picker searches SKU/name and shows both catalog and customer prices. Enter a quantity, edit the unit price for this one estimate/invoice if needed, and click **Add product**. Select an added line to modify its quantity/price using **Update selected line**. The price on each saved document remains frozen even if negotiated pricing later changes.

**Taxes:** For tax-exempt customers, document sales tax is automatically forced to zero. For taxable customers, the entered percentage remains applicable. BusinessDesk does not validate exemption certificates, supply product-specific tax codes, or calculate jurisdiction-dependent tax rules; review actual sales tax obligations before sending invoices.

**Backwards-compatible SQLite migration:** Adds `customers.tax_exempt` (default 0) and `customer_prices` with foreign keys. Does not delete existing customer, invoice, or catalog data. Back up `%LOCALAPPDATA%\BusinessDesk\business.db` before deploying.

**GitHub automated Windows release:** Replace the existing application source files under `TDZIGNS_BusinessDesk_v2.7_Automated_Windows_Build/` and the repository-root `.github/workflows/windows-release.yml`. Commit to `main`, then create and push tag `v2.9.0` (tag must reference updated source commit). GitHub Actions will build a compiled installer ZIP and publish a release containing `update_manifest.json` so v2.8+ clients can check GitHub for updates. This source package itself is not a compiled Windows update. Check Actions and test on Windows before production deployment.

**Tested:** `python test_customer_pricing.py` (4 database regression tests passing); Python compilation. GUI and Windows installer have not been exercised here.
