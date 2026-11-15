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
3. Commit changes to `main`; push version tag `v3.6.0` from that commit.
4. GitHub Actions produces `PhoenixLedger_Setup_3.6.0.exe` and a signed-by-checksum update ZIP (after successful Windows tests).

## Test commands (developer)

- `python -m unittest -q test_catalog_csv test_inventory_costing test_inventory_management test_supplier_products test_invoice_fix`
- On Linux with virtual desktop: `xvfb-run -a python test_ui_refresh_gui.py`
- The Windows installer and actual operating-system maximize behavior must still be tested on a Windows PC.
