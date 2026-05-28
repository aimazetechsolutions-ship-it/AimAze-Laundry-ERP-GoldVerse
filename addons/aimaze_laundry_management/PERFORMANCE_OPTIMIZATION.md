# Performance Optimization

Phase 4 adds database indexes for order, garment, delivery, barcode scan, order line, and payment fields used by mobile APIs, dashboards, barcode workflows, and reports.

## Optimized Areas

- Order state, payment status, branch, company, customer, barcode, and order date.
- Garment UID, barcode, RFID UID, branch, company, and stage.
- Delivery state, driver, branch, company, pickup date, and delivery date.
- Barcode scan lookup fields.
- Payment laundry linkage fields.

## Dashboard Guidance

Use date and branch filters. Avoid very large all-time dashboards for SaaS clients. For high-volume tenants, add materialized summary tables or scheduled KPI snapshots.

## Barcode Guidance

Use exact barcode/RFID lookups. Avoid wildcard searches on barcode fields during scanning.

## Load Testing Targets

- 10,000 garments
- 100,000 accounting/notification transactions
- 50 concurrent backend users
- Barcode-heavy scan workflows
- Multi-branch dashboard filtering
