# Accounting Flow Explanation

The module uses Odoo standard accounting objects rather than a custom ledger.

- Customer invoices: `account.move`
- Payments and advance receipts: `account.payment`
- Receivable accounts: partner/accounting configuration
- Income accounts: product/service configuration
- Taxes: product/service `account.tax`
- Branch cash/bank journals: branch configuration

Advance payments are linked to the laundry order and visible from the order. Final reconciliation can be completed through standard Odoo accounting workflows.

Known implementation note: automatic reconciliation between advance payments and final invoices can be extended per client chart of accounts and localization rules.

## Phase 2 Advanced Accounting

Configure `AimAze Laundry ERP > Configuration > Accounting Configuration` for each company before go-live.

- Advance collection remains linked to the laundry order through Odoo payments and is visible on the order balance.
- Wallet top-up can post an accounting entry when wallet liability account and payment journal are configured.
- Wallet usage can reduce wallet liability and credit customer receivable when wallet liability and customer receivable accounts are configured.
- Refund wallet transactions can reduce liability and credit the selected payment journal.
- Customer invoices continue to use standard `account.move` and use service/product taxes and income configuration.
- UAE VAT and Pakistan tax are selectable configuration fields, not hardcoded values.
- Branch-level journals are supported through branch setup and company accounting configuration.

Production note: final invoice/payment reconciliation should be completed using Odoo Accounting matching so the customer ledger remains auditable.

## Phase 3 Accounting Cleanup

Phase 3 keeps accounting configuration company-specific and validates missing configuration before advanced accounting reports or wallet flows are used.

- Advance payments are flagged on `account.payment` through the linked laundry order.
- Wallet top-ups post to wallet liability when accounts and journals are configured.
- Wallet usage reduces wallet liability and can settle customer receivables.
- Branch reports use branch-linked orders and branch journals where available.
- Customer ledger reports use posted receivable move lines.
- Refunds and credit notes remain handled through Odoo accounting, with laundry links retained where available.
