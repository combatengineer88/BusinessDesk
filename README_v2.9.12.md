# TDZIGNS LLC PhoenixLedger v3.0.0

## Fixes and additions

**Home supplier and customer flowcharts:** Replaced curved/diagonal arrow connectors with straight horizontal/vertical paths. The supply side now has a proper split to full/partial receiving and a matching merge before supplier payment, like the supplied sketch. Planned nodes remain disabled.

**Customer addresses:** Added separate City, State, and ZIP/Postal Code columns to the Customers table and fields in Add/Edit Customer. The existing Address column remains the street/freeform address. Existing address values are left intact: **the migration intentionally does not attempt to split old freeform addresses.** You can edit older customers to fill the new fields. CSV/Excel customer imports can accept headers `City`, `State`, `ZIP` or `Postal Code` and preserve leading zeros when the Excel value is stored as text.

**Estimates and invoices:** The product picker now has a bottom-pinned, prominent `Save Estimate` or `Save Invoice` button that stays visible when the window is resized. The Add/Update/Remove actions are in a responsive toolbar. Quantities and prices can still be corrected before saving. The final confirmation commits the new document using the existing inventory and accounting procedures.

**Branded reports:** Reports tab provides **Export CSV** and **Export branded PDF** for Sales by month, Payments by month, Expenses by category, Low stock, and Invoice balances. PDFs include the saved company name/logo/contact details, a professional letterhead, alternating table rows, currency formatting, landscape pages for wider reports, and page numbers. Records remain unchanged. Empty and multi-page reports are supported. Set business name, address, phone, email and logo in Settings/Updates to customize report branding.

**Responsive UI:** Action bars wrap horizontally rather than clipping buttons, including Customers, Products, Estimates/Invoices, Purchase Orders, Reports, Admin, and Settings/Updates. Admin and Settings pages are vertically scrollable, with an update URL input that scales to the available width. Tab captions become compact at narrower window widths without losing navigation or saved drag order. Customer tables have horizontal scrolling to reach all columns. Dialog Save buttons are pinned below variable-height content.

## Database migration / compatibility

- Startup adds `customers.city`, `customers.state`, and `customers.zip_code` using `ALTER TABLE` when absent. Existing records/financial data are not changed or reset.
- Classic and visual PDF templates combine street, city, state and ZIP for newly edited customers.
- When an older test database has not yet been migrated, both PDF renderers can still read the legacy address field.
- Back up `%LOCALAPPDATA%\PhoenixLedger\business.db` with the app closed before upgrading. Do not extract compiled files into an arbitrary temporary ZIP directory.

## GitHub Release / Windows Setup

The archive's **contents** map onto `combatengineer88/BusinessDesk`. The application remains inside `PhoenixLedger_App/` for compatibility, and the workflow is at `.github/workflows/windows-release.yml` at repository root. Replace matching files, commit on `main`, then create and push tag `v3.0.0`. GitHub Actions should produce `PhoenixLedger_Setup_3.0.0.exe` and an update manifest for the built-in GitHub updater. Downloading this source-code ZIP is **not** the same as installing the Windows Setup EXE.

## Testing

Tests passed in the Linux/Xvfb development environment: 10 new regression checks (including graphical estimate save and responsive tabs, database migration, PDF generation and orthogonal connectors) as well as previous supplier, customer pricing, PO, document template, visual template and Home tests. PDF output was visually reviewed. The Windows GitHub Actions build and installer upgrade must still run on a real Windows runner before deployment.
