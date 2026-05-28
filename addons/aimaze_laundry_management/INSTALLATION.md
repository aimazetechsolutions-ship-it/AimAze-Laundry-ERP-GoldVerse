# Installation

1. Copy `aimaze_laundry_management` to your Odoo custom addons path.
2. Ensure Odoo 19 Community dependencies are installed: Accounting, Sales, Inventory, Purchase, HR, Maintenance, Portal, POS if used.
3. Restart Odoo.
4. Update Apps List.
5. Install **AimAze Laundry ERP**.
6. Assign users to the required laundry security groups.

## Initial Configuration

1. Configure companies:
   - UAE company: AED
   - Pakistan company: PKR
2. Configure branches under **AimAze Laundry ERP > Configuration > Branches**.
3. Configure taxes on products/services.
4. Configure journals on each branch for sales, cash, and bank.
5. Configure services and rate cards.
6. Configure delivery zones and payment methods.

## Production Notes

- Do not install in the same database as unrelated HMS or real-estate products unless intentional.
- Use a separate database for each standalone client deployment.
- Configure HTTPS, backups, email, and access rights before client handover.

## Phase 2 Upgrade

After pulling Phase 2, restart Odoo and upgrade the module:

```bash
odoo-bin -d your_database -u aimaze_laundry_management --stop-after-init
```

Then configure:

1. Company currency and country for UAE AED or Pakistan PKR.
2. Branches, journals, services, rate cards, and taxes.
3. `AimAze Laundry ERP > Configuration > Accounting Configuration`.
4. Notification templates/providers if WhatsApp, SMS, or email queues will be used.
5. Driver users linked to HR employees for the driver mobile view.
6. Branch access on users for branch isolation.

## Phase 3 Initial Setup

After installation, open `AimAze Laundry ERP > Configuration > Initial Setup Wizard`.

Use the wizard to set company country, currency, default branch, journals, tax, advance liability account, wallet liability account, laundry income account, and delivery income account.

For UAE companies, use AED and configure VAT as 5% through Odoo taxes. For Pakistan companies, use PKR and configure taxes manually according to client requirements.

## Phase 4 Upgrade

After pulling Phase 4, upgrade the module and review:

1. `AimAze Laundry ERP > Configuration > SaaS Tenants`
2. `AimAze Laundry ERP > Configuration > Backup Configuration`
3. `AimAze Laundry ERP > Notifications > Integration Logs`
4. `AimAze Laundry ERP > Notifications > Providers`

Mobile API routes require an authenticated Odoo user session and are documented in `MOBILE_API_GUIDE.md`.
