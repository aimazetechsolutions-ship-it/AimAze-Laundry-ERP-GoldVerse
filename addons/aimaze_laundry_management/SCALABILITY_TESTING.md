# Scalability Testing

## Test Scenarios

- 10,000 garments with barcode history.
- 100,000 notification and accounting transactions.
- 50 concurrent backend users.
- 20 concurrent scanner users.
- Multi-branch dashboards with date filters.
- Heavy report export during operations.

## Metrics

- Average API response time.
- Barcode scan response time.
- Dashboard load time.
- PostgreSQL CPU, locks, and slow queries.
- Odoo worker memory.
- Queue retry backlog.

## Acceptance Targets

- Barcode lookup below 500 ms on indexed data.
- Common order list below 2 seconds with filters.
- Dashboard below 5 seconds for branch/date-filtered data.
- No cross-tenant or cross-branch record leakage.
