# PhoenixLedger v3.4.0 — Inventory Management Upgrade

A repository-ready source update for the existing Windows GitHub Actions/Inno Setup release process.

## Features

1. **Inventory Overview** in the Products tab: active SKUs, low-stock count, out-of-stock count, stock value at product cost. Search and filter by low stock, out of stock, reorder needs, made-to-order and supplier-direct items.
2. **Scan to Adjust**: USB/Bluetooth keyboard-wedge barcode scanners (or manual SKU input). Press Enter to find a product; choose Add, Remove, or Set, enter a quantity and reason, and save. Negative inventory is refused. Each update is audited with the signed-in user's name.
3. **Inventory Movement History**: database-backed audit with UTC timestamp, SKU, before/after, delta, source, reason and user; export CSV. The migration creates a one-time opening balance for pre-existing products; it cannot reconstruct transactions from before this version.
4. **Stock & Reorder Rules**: configure reorder point, reorder batch quantity, optional shelf/bin location and item type for one or more selected products. Modes: stocked, made_to_order, supplier_direct. Only stocked items trigger reorder alerts. **Existing invoicing behavior for made-to-order/supplier-direct items is unchanged; fulfill stock before invoicing as needed.**
5. **Suggested Reorders**: calculates proposed quantities considering quantities already on Draft, Open and Partially Received POs. One click generates editable **Draft** POs grouped by primary supplier. Products with no supplier are shown but skipped. Duplicate reruns do not create the same on-order quantities again. Review each draft in Purchase Orders, edit it, and **Approve Draft PO** to mark it Open. Drafts cannot be received and do not post inventory/accounting entries.

## Compatibility and accounting

- Existing customers, product IDs, stock levels, supplier associations, invoices, POs, receipts, and accounting entries are preserved by migration.
- SQLite triggers capture all product quantity changes after migration, even when made via previous editing screens and Excel import, including reason/source annotations for scan adjustments, Excel imports, invoices and PO receipts.
- Editing reorder settings or generating draft POs does **not** change stock or accounting entries.
- Inventory movement history is a quantity audit ledger, not a financial general ledger. It does not retroactively rewrite accounting entries for manually corrected stock.
- Product catalog items marked made-to-order or supplier-direct are excluded from low-stock alerts, but current sales/invoicing stock rules remain unchanged.
- Scanners must act as keyboard input and ideally send Enter after the barcode. Scanner hardware/drivers are not bundled.
- The application remains offline and data stays in `%LOCALAPPDATA%\PhoenixLedger\business.db`.

## Build and publish

1. Back up `%LOCALAPPDATA%\PhoenixLedger\business.db` before updating.
2. Extract the source ZIP into the root of `combatengineer88/BusinessDesk`, replacing matching files in `PhoenixLedger_App/` and `.github/workflows/windows-release.yml`. Keep other repository files.
3. Commit to `main`.
4. Tag the commit `v3.4.0` and push the tag.
5. The workflow should produce `PhoenixLedger_Setup_3.4.0.exe` and `PhoenixLedger_3.4.0.zip`, with checksums and update manifest.
6. Install the Setup EXE or update through PhoenixLedger after GitHub publishes the release.

**This download is the source update, not a compiled Windows installer.** Build results on GitHub and the installed Windows UI still require verification.
