# PhoenixLedger v3.1.0 — Receiving, Payables & Customer Credit

This release replaces all three former **Planned** Home workflow steps with functional, database-backed features. It includes the whole source tree for the GitHub repository and the existing Windows Setup build process.

## Features

**Partial PO receiving** — In Purchase Orders, select an Open/Partially Received PO and choose **Receive partial PO**. For each line, enter the *quantity delivered in this shipment*, click **Update selected line**, then **Save receipt**. Only that shipment increases product inventory and posts a balanced Inventory debit / Accounts Payable credit. Subsequent deliveries can be entered until all lines have been received. The PO status changes from Open to Partially Received to Received. **Receive entire PO** now processes only remaining quantities. POs with any receipt remain locked against item editing to preserve inventory history.

**Supplier payments** — Select a PO with accrued, unpaid supplier liability and choose **Pay supplier**. Enter the amount, payment method and reference/check number. Payments cannot exceed the accrued unpaid value of received goods; balanced Accounts Payable debit / Cash credit entries post to the journal. Supplier payments are associated with the PO, not unassigned supplier deposits.

**Customer credit accounts** — Select a customer and click **Credit account**. Enable the account, configure a dollar credit limit and Net-days due terms. Use **Charge existing invoice** to mark an existing unpaid invoice on account, or select **Charge to customer credit account** when creating an Invoice. Estimates can optionally be converted into on-account invoices. New charges cannot exceed available credit. Payment entries can be made in the credit screen and are applied to the oldest outstanding on-account invoices first, using the existing invoice payments table and Accounts Receivable journal trigger. Invoice charges, balances and due dates appear in the credit account screen.

**Home** — The former Planned supplier partial receipt, supplier payment and customer credit shortcuts and flowchart nodes are enabled and open the real screens.

**Reports** — Supplier payable balances and Customer credit accounts reports can be exported in CSV or branded PDF alongside existing reports.

## Accounting integrity and migrations

- New columns: `po_items.received_qty`; `documents.credit_account`, `documents.credit_due_on`.
- New tables: `po_receipts`, `po_receipt_lines`, `supplier_payments`, `customer_credit_accounts`. Migrations are idempotent and preserve existing records.
- Existing POs already marked Received remain fully received in the new tracking; the previous `po` journal is counted towards supplier payables. They are **not received again**, avoiding duplicate inventory.
- **Only new receipts** create new PO receipt journals. Payments on customer credit reduce existing invoice balances with no extra Accounts Receivable posting beyond the normal payments trigger.
- Keep a database backup before installing. Data directory: `%LOCALAPPDATA%\PhoenixLedger\business.db`. The old `%LOCALAPPDATA%\BusinessDesk` directory remains untouched by the new build.
- Customer credit is **trade credit (invoice on account)**, not a stored-value gift card or refund balance. Cash invoices and old invoices not marked on-account are outside the customer credit balance.

## Publish to GitHub

1. Unzip and upload `PhoenixLedger_App/` plus `.github/workflows/windows-release.yml` to `combatengineer88/BusinessDesk`, preserving paths and replacing matching files.
2. Commit to `main` and create/push the new tag `v3.1.0`.
3. Wait for GitHub Actions. It should publish `PhoenixLedger_Setup_3.1.0.exe`, `PhoenixLedger_3.1.0.zip`, checksums and `update_manifest.json`.
4. Install from the published Windows Setup EXE or update from within the app once the release is available. The source ZIP is not the compiled installer.

## Testing performed

Automated purchasing, customer credit, migrations, document templates, existing sales/accounting, and graphical Home/PO/editor tests were run on Linux (Tkinter GUI via Xvfb). GitHub Actions / Windows Setup still need to run successfully before production deployment.
