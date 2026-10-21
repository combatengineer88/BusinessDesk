# TDZIGNS LLC PhoenixLedger v2.9.11 — Home Workflow Dashboard

This update adds a **Home** tab based on the supplied flowchart sketch while preserving the modern professional UI, reorderable top tabs, existing business logic, data files, GitHub updater, and Inno Setup Windows installer.

## Home layout

- Home opens as the first tab at login by default. All existing tabs remain available across the top, and the tab order remains user-reorderable.
- A scrollable **Quick Access** menu on the left groups the actual actions available for Suppliers, Customers, Products and Management.
- The center canvas contains two distinctly colored workflow lanes:
  - **Supplier / Supply Chain:** Create PO → Receive full PO, with partial receiving and supplier-payment steps marked **Planned**.
  - **Customer / Sales Chain:** Create estimate → Convert estimate → Receive invoice payment.
- Each enabled workflow box opens the matching PhoenixLedger tab and runs the existing action. Actions that require a saved record open a selection dialog first.
- Cards at the top show database-backed counts for suppliers, open purchase orders, customers, and open estimates.
- The workflow canvas supports horizontal/vertical scrolling at smaller window sizes, and the sidebar scrolls independently.

## Supported quick actions

**Suppliers:** Add supplier, import suppliers from Excel, create PO, edit open PO, receive an entire open PO.

**Customers:** Add customer, import customer Excel list, edit customer, customer-specific prices, new estimate, convert an existing estimate into an invoice, record an invoice payment.

**Products:** Add product, import products from Excel, edit existing product.

**Management:** Dashboard, add expense, reports, accounting, template designer (admin), administration (admin), settings/updates.

**Not yet implemented:** Partial PO receiving, supplier payments, and customer-account credits. These are visually marked **Planned** and are not interactive. No accounting/inventory mutation is performed for these placeholders.

## Publishing v2.9.11

1. Extract the **PhoenixLedger_v2.9.11_Home_GitHub_Update.zip** archive.
2. Upload or replace matching files within your repository `combatengineer88/BusinessDesk`.
3. Keep `.github/workflows/windows-release.yml` at **repository root**. Keep application files in `PhoenixLedger_App/`.
4. Commit changes to branch `main`.
5. Push tag `v2.9.11`; the GitHub Actions Windows build will compile and publish `PhoenixLedger_Setup_2.9.11.exe`.
6. Use the built-in GitHub updater or the Windows Setup EXE to install. The ZIP provided here contains source and workflow files, not a compiled Windows installer.

**Data:** This release changes the UI only; it does not add tables or modify business records. Back up your database before any software update.

## Testing

- 7 graphical Home tests (Xvfb): Home first, full tab list, chart/action tags, real supplier create, PO edit/receiving with inventory and accounting, and saved reorder behavior.
- Existing product supplier, PO editor, customer pricing, Excel imports, invoice, document template, update-layout, and installer-asset regression tests passed.
- A rendered screenshot from the actual Tk UI is provided separately for reference; its records are demo data.
- No Windows executable was built or tested in this environment. GitHub Actions and user Windows machine must verify the final installer.
