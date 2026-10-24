# PhoenixLedger v3.2.0 — Suppliers Directory, Banner, Document References

This source update keeps the existing GitHub repository and `PhoenixLedger_App` project folder.

## What's new

- A dedicated **Suppliers** tab after Customers, with searchable supplier directory and full add/edit forms.
- Company name, contact, email, phone, website, street address, city, state, ZIP/postal code, notes and linked product/PO counts.
- **Import suppliers from Excel** (`.xlsx` / `.xlsm`), with header mapping, validation, preview and skip/update duplicate handling. Names match case-insensitively; matching records keep the same ID and therefore retain products/POs/receipts/payments.
- The phoenix icon in the app's slate banner uses a transparent PNG and the exact slate background, avoiding a light square around it.
- Estimate, Invoice and Purchase Order PDFs show the proper document number next to the **Date** in the Document Details section. This applies to both classic and visual PDF templates. Older saved **stock-style** visual designs are upgraded in memory during rendering; customized layouts can still be edited manually.
- PDF title remains 'ESTIMATE', 'INVOICE', or 'PURCHASE ORDER', avoiding a duplicate number outside the Document Details section.

## Installation / publishing

1. Back up `%LOCALAPPDATA%\PhoenixLedger\business.db` and keep your original BusinessDesk backup if present.
2. Upload this ZIP's `PhoenixLedger_App/` folder into the matching folder in your repository, replacing matching files. Replace `.github/workflows/windows-release.yml` at the repository root.
3. Commit to `main` and create/push **tag `v3.2.0`**.
4. GitHub Actions should publish **`PhoenixLedger_Setup_3.2.0.exe`**, update ZIP, checksums and manifest. The downloadable source ZIP is **not** the Windows installer.

## Notes

- The app's database migration adds optional supplier fields without deleting existing supplier rows or changing IDs.
- Supplier Excel import treats duplicate names as the same supplier in Update mode and preserves fields for columns omitted from the workbook.
- Existing accounting balances and PO/credit workflows are not changed by this update.
