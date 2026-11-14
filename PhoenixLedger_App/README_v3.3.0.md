# PhoenixLedger v3.3.0 — Inventory editing and barcode sticker printing

This source update builds on PhoenixLedger v3.2.1 without deleting or replacing the existing business database.

## New Products tab controls

- **Double-click an editable table cell** (SKU, barcode, name, supplier, description, price, cost, or stock) to edit it in place. Press Enter or click away to save, Escape to cancel. The existing **Edit** dialog is still available.
- **Attach barcode PNG:** Select a product, choose a genuine PNG. The image is validated, copied to `%LOCALAPPDATA%\PhoenixLedger\barcode_images`, and linked to that product. This is separate from the general product photo.
- **View barcode PNG:** Inspect the barcode attachment for the selected product.
- **Print barcode stickers:** Ctrl/Shift-click multiple product rows, click the sticker button, and enter the required number of stickers per item.
- Supported US Letter sheets: Avery 5160/8160 (30 labels, 2-5/8 x 1 in) and Avery 5163/8163 (10 labels, 4 x 2 in).
- Choose the first sheet position when part of a label sheet has already been used. Optionally include selling prices.
- Attached PNGs are printed as provided; without an attached image PhoenixLedger generates a vector Code 128 barcode from the product barcode value, or from its SKU if the barcode field is blank.
- Save as PDF or select **Save & Open to Print**. In the PDF viewer select **Actual Size / 100%**; disable **Fit to page** or other scaling. Print a plain-paper alignment test before using purchased adhesive sheets.

## Data safety

Database migration adds only `products.barcode_image_path` if missing. It preserves products, existing product photos, stock counts, supplier links, purchase orders, invoices and accounting records. Existing QR/barcode text is not overwritten.

Make a backup of `%LOCALAPPDATA%\PhoenixLedger\business.db` before installing. If a particular barcode is attached, keep the new `barcode_images` folder as part of your normal backups.

## Publishing to GitHub

The ZIP root contains `.github/workflows/windows-release.yml` and `PhoenixLedger_App`. Replace matching files in the existing repository, keeping the folder hierarchy. Commit to `main` and push tag `v3.3.0`. The existing workflow builds `PhoenixLedger_Setup_3.3.0.exe` and `PhoenixLedger_3.3.0.zip` on Windows.

**This is a source update, not a precompiled Windows installer.** The final Windows build/install still needs verification by GitHub Actions.

## Verification

- `test_inventory_labels.py` tests migration, attached PNG validation, in-grid data edits, printed label counts, both sheet sizes, page breaks and barcode fallback.
- `test_inventory_gui.py` runs on a graphical desktop (or `xvfb-run -a python test_inventory_gui.py` on Linux) and verifies the Products controls, double-click editing, multi-select and Save PDF.
