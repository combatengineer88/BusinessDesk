# PhoenixLedger v3.5.0 — Bulk Reorder Cost & Supplier Pricing

This GitHub-ready source update builds on PhoenixLedger v3.4.0. The application remains named PhoenixLedger, and the existing GitHub repository URL is unchanged.

## Products tab

- **Reorder Cost**: total quoted price for one bulk reorder quantity, e.g. **$192.00 for 48 shirts**.
- **Item Cost**: automatically calculated as $192.00 / 48 = **$4.00 each** (cents rounded half-up).
- **Margin %**: gross margin at the current selling price, based on quoted item cost. Selling prices are not changed automatically.
- The **Bulk Cost & Pricing** button opens a resizeable editor with a fixed Save control. It offers reorder quantity, bulk total, supplier case-pack size, supplier minimum order, quantity price tiers, and cost history.
- Double-click **Reorder Cost**, **Reorder qty**, or **Item Cost** to edit inline. Changing the quoted total or reorder quantity recalculates Item Cost. Editing Item Cost manually clears its bulk quote, to avoid contradictory data.
- **Stock & Reorder Rules** also recalculates Item Cost if you change the reorder quantity of a product with an existing bulk quote.
- Existing products with no bulk quote keep their previous item costs until pricing is entered.

## Purchase orders

- Automatic draft reorders round quantities up to the assigned case-pack multiple and meet the minimum order quantity.
- Draft reorder costs use the product's supplier price tier when the ordered quantity reaches that tier; otherwise they use the quoted item cost.
- The standard PO editor suggests supplier tier pricing when you change the quantity. The actual PO unit cost remains editable and is saved with the PO.
- Supplier tiers are tied to the product's currently assigned supplier, so a supplier reassignment does not reuse the previous supplier's price tiers.

## Historical and accounting safety

- A change to a supplier quote does **not** rewrite existing PO lines, invoices, or accounting journals.
- On first migration, **inventory_unit_cost** is initialized to the prior product cost; after receipts, it is updated from the actual PO line cost using weighted average. Inventory valuation and future COGS use that separate inventory basis.
- Price changes are recorded in `product_cost_history` with timestamps, prior/new prices, change type, and user where supplied.
- Bulk quotes do not yet allocate freight, tax or handling to inventory; those would need a dedicated landed-cost receipt workflow.
- Existing `business.db` and inventory records are retained. **Back up `%LOCALAPPDATA%\PhoenixLedger\business.db` before installing.**

## Publish with your existing GitHub Actions build

1. Upload the contents of this ZIP to your existing `combatengineer88/BusinessDesk` repository, preserving the top-level `PhoenixLedger_App/` directory and `.github/workflows/windows-release.yml`.
2. Commit changes to `main`.
3. Create a new tag `v3.5.0` and push the tag; do **not** retag an older commit.
4. GitHub Actions should produce `PhoenixLedger_Setup_3.5.0.exe` and `PhoenixLedger_3.5.0.zip` with hashes and a release manifest.
5. Test a PO, the item-cost calculation, and inventory receipt behavior in your installed Windows build.

The attached ZIP is **source code**, not the compiled Windows Setup executable. The full Windows build must run through GitHub Actions.

## Tests

Run the database-level test suite inside `PhoenixLedger_App`:

```sh
python -m unittest test_inventory_costing test_inventory_management test_inventory_labels test_account_workflows test_po_editing test_customer_pricing
```

The optional Tkinter pricing dialog smoke test `test_costing_gui.py` needs a working graphical desktop.
