# PhoenixLedger v3.6.0 — Interface and Catalog CSV Refresh

## New behavior

- Product catalog CSV export now matches the **currently displayed Products table**: same column titles, order, values and filtered rows. **Image** and **Barcode PNG** columns report **Yes** or **No**, never local file paths. Currency and margin columns match the on-screen representation. CSV is plain text and cannot preserve button styling, column widths, or colors. For existing report CSVs, exports are unchanged.
- Common buttons throughout PhoenixLedger have rounded, lightly raised borders, visible state changes, and a restrained shadow. Keyboard access and normal `ttk.Button` commands continue to work.
- Main window starts **maximized** (Windows `zoomed`), with the Windows taskbar and title-bar controls still accessible. Maximized is *not* exclusive fullscreen.
- Products, Suppliers, Customers, Purchase Orders, Estimates/Invoices, and Expenses now support contextual right-click quick actions; **Menu** key / **Shift+F10** is also supported in tables. Right-clicking a row selects it without unexpectedly discarding other selected products.
- Toolbars in smaller windows keep a few rows of actions and put remaining actions under **More actions ▾** rather than forcing data tables off-screen.

## Source files added

- `catalog_csv.py` and `test_catalog_csv.py`
- `context_actions.py` and `test_ui_refresh_gui.py` (the GUI test is run on a desktop / Xvfb, not the headless GitHub Windows workflow)

## Database compatibility

No schema changes, new tables or migrations. Product photos and barcode PNGs remain where they are, and their paths remain in the internal database; only the CSV presentation changes. Existing customer pricing, POs, accounting, stock movements, and reports are unaffected.

## GitHub release

1. Back up `%LOCALAPPDATA%\PhoenixLedger\business.db`.
2. Upload `PhoenixLedger_App/` and `.github/workflows/windows-release.yml` to the existing repository, preserving the folder structure and replacing matching files.
3. **Before tagging:** open `PhoenixLedger_App/businessdesk.py` on the repository's `main` branch and confirm it contains `VERSION = '3.6.0'`. If it says `3.4.0`, the new app sources were not uploaded/committed. Also check that the updated `release_preflight.py` exists.
4. Commit and push to `main` first. Create a **new tag `v3.6.0` pointing to that commit on main** (not to the failed v3.5.0 tag). You can verify locally by running `python PhoenixLedger_App/release_preflight.py v3.6.0`, or use the GitHub website to inspect the committed file.
5. GitHub Actions produces `PhoenixLedger_Setup_3.6.0.exe` and a SHA-256-verified update ZIP (after successful Windows tests).

## Test commands (developer)

- `python -m unittest -q test_catalog_csv test_inventory_costing test_inventory_management test_supplier_products test_invoice_fix`
- On Linux with virtual desktop: `xvfb-run -a python test_ui_refresh_gui.py`
- The Windows installer and actual operating-system maximize behavior must still be tested on a Windows PC.

## Why GitHub v3.5.0 failed

The GitHub Action for tag `v3.5.0` stopped at "Validate tag and application version" because the tagged version of `PhoenixLedger_App/businessdesk.py` still said `VERSION = '3.4.0'`. The corrected 3.5.0 source archive was separate from the GitHub repository; it had not been committed in the tag's source snapshot. Re-running the old workflow will check out the same old tag and fail again. This v3.6.0 archive **contains the v3.5.0 pricing changes as well as the v3.6.0 interface changes**, so a successful v3.6.0 release can replace the failed v3.5.0 release.

`release_preflight.py` now runs as an early GitHub Actions step with a clear diagnostic and can be used locally before tagging. The main app source, installer template, and release packaging script agree on version 3.6.0.

## File upload checklist

Upload the **contents** of this ZIP at the repository root (not a new wrapper directory):

- `PhoenixLedger_App/` (replace existing matching files and add all new files)
- `.github/workflows/windows-release.yml` (replace the existing workflow)
- `README_v3.6.0.md` (optional release notes)

Back up `%LOCALAPPDATA%\PhoenixLedger\business.db` before installing. No database migration is required for the UI/CSV changes. Windows installer construction and real Windows startup maximizing need verification in GitHub Actions/on Windows.
