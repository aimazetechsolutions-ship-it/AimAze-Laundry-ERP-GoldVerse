# AimAze Laundry ERP

Professional Odoo 19 Community addon for laundry and dry-cleaning businesses in the UAE and Pakistan. It is built as a standalone commercial module by AimAze Tech Solutions, powered by Odoo.

## Scope

- Walk-in and corporate laundry order management
- Garment/service line tracking with tag and barcode numbers
- Pickup, delivery, driver proof, and delivery charges
- Branch-aware operations workflow from draft to paid
- Advance payment and final payment registration through Odoo Accounting
- Customer invoices through `account.move`
- Consumable usage and optional stock deduction
- Machine maintenance, staff productivity, QC, complaints, loyalty, notifications
- AED/PKR ready through Odoo company currency and standard multi-company accounting
- Portal pages for customer order tracking

## Accounting Flow

1. Create and confirm a laundry order.
2. Register advance payment using the order button. This creates and posts an `account.payment` linked to the order.
3. Create invoice from the order. Invoice lines are generated from garment/service lines and use product/service tax settings.
4. Register final payment for the balance.
5. Customer ledger uses standard Odoo partner receivable/payments plus laundry order references.

## UAE and Pakistan Currency

The module does not hardcode currency conversion. Configure:

- UAE company currency: AED
- Pakistan company currency: PKR
- Branches under the correct company
- Tax per company:
  - UAE default can be configured as 5% VAT on services/products
  - Pakistan tax is manual/configurable and not hardcoded

All order, branch, invoice, payment, and report monetary fields derive from company currency.

## Future API Structure

WhatsApp/SMS integrations are represented by `aimaze.laundry.notification.log`. Add provider-specific connectors later without changing order flow.

## Enterprise Phase 2

Phase 2 upgrades the module for enterprise laundry operations in UAE, Pakistan, and GCC markets:

- Quick Counter Order wizard for walk-in entry, mobile lookup, quick customer creation, service pricing, discounts, delivery charges, and advance collection.
- Garment lifecycle tracking with UID/barcode, stage buttons, photos, QC result, rewash count, lost item flag, and garment history.
- Configurable notification providers, templates, and queue records for WhatsApp, SMS, and email architecture.
- Customer wallets, wallet transactions, subscription packages, and active customer subscriptions.
- Laundry accounting configuration for advance liability, wallet liability, income, delivery, discount, compensation, journal, and tax setup by company.
- Branch profitability reporting for revenue, discount, tax, consumable cost, delivery cost, maintenance cost, compensation cost, and estimated net margin.
- Driver mobile view and department screens for washing, drying, ironing, QC, and packing.
- Secure JSON controller placeholders for customer portal and mobile/API readiness.

No country, account, currency, or paid provider credential is hardcoded. Configure company currency as AED or PKR in Odoo, then set branch, journal, tax, and laundry accounting configuration per company.

## Phase 3 Commercial Productization

- Modern dashboard KPI cards, mobile-friendly driver fields, and smarter order/garment tracking controls.
- Barcode/RFID scan wizard for order, garment, and delivery package workflows.
- Customer portal enhancements for orders, garment status, wallet, subscriptions, pickup requests, and complaints.
- Initial Setup Wizard for company currency, branch, journals, taxes, and accounting accounts.
- AI-ready analysis model without paid API dependency.
- SaaS/API documentation for future mobile and cloud deployment.
- Arabic translation placeholder and TRN/commercial-registration report readiness.

## Phase 4 SaaS and Mobile Ecosystem

- Authenticated Flutter-ready REST API structure for customer, driver, and staff apps.
- SaaS tenant tracking, backup configuration, integration/API logging, and monitoring documentation.
- WhatsApp/SMS provider retry metadata and notification queue scheduler placeholder.
- Docker, Docker Compose, Nginx, backup, and restore deployment scaffolding.
- Additional performance indexes for barcode, delivery, payment, order-line, and scan-heavy operations.
- Production security, scalability, launch, and recovery guides for commercial rollout.

## Phase 5 Premium UI/UX

- AimAze design system with reusable colors, cards, badges, timelines, kanban cards, and responsive utilities.
- Modern executive dashboard, quick counter POS, garment tracking, driver cards, portal cards, and branded PDF reports.
- Smart buttons for orders, customers, and branches to surface invoices, payments, wallets, deliveries, complaints, and revenue.
- Lightweight Owl KPI card scaffold for future live dashboard components.
