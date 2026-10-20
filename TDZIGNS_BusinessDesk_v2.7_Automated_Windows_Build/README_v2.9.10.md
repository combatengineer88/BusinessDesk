# TDZIGNS BusinessDesk v2.9.10 — Purchase order editing and save fix

This update replaces the New PO workflow with a single, resizable purchase-order editor. A large **Save Purchase Order** button remains visible in the bottom footer even at smaller Windows window sizes or high-DPI display scaling.

## New PO
1. Open **Purchase Orders** → **New PO**.
2. Select a supplier from the dropdown. Only products assigned to that supplier are available.
3. Select each product, enter quantity and unit cost, and click **Add Product**.
4. To correct a quantity or cost, click the line item, change the values, and choose **Update Selected Line**. **Remove Selected Line** deletes an item before saving.
5. Enter notes, review the running total, then click **Save Purchase Order**. Cancelling does not write a PO.

## Edit existing PO
In Purchase Orders, select an **Open** PO and click **Edit selected PO** (or double-click its row). Change quantities, unit costs, notes, add or remove items, then click **Save Changes**. Editing is transactional; a failed save rolls back changes. The supplier is locked for an existing PO, so use a new PO for a different supplier.

**Received POs cannot be edited.** Receiving already updated inventory and accounting. Keeping those orders read-only prevents stock and ledger discrepancies.

## Windows installer and GitHub automation
The existing Inno Setup installer workflow is retained. Commit this package to `combatengineer88/BusinessDesk` with `.github/workflows/windows-release.yml` at repository root and the other files under `TDZIGNS_BusinessDesk_v2.7_Automated_Windows_Build`. Push version tag **v2.9.10** to publish `TDZIGNS_BusinessDesk_Setup_2.9.10.exe`.

This source package is **not** the finished Windows installer. Back up the business database before upgrading. Tests include 7 data-layer and 3 graphical PO editor tests. Windows installation and application restart must still be verified on your PC.
