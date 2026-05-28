# SaaS Architecture

AimAze Laundry ERP is designed to support both single-database multi-company deployments and database-per-tenant SaaS deployments.

## Recommended Strategy

- Small groups: one database, multi-company, strict record rules.
- Commercial SaaS: one database per tenant for stronger isolation, simpler backup/restore, and safer customization.
- Enterprise chains: one database per group, multi-company per legal entity, branch rules per operation.

## GCC Infrastructure

- UAE or GCC cloud region where possible.
- PostgreSQL 13+ with managed backups.
- Odoo behind Nginx with HTTPS.
- Object storage for offsite backups.
- Monitoring for HTTP, PostgreSQL, disk, CPU, worker count, and queue health.

## Tenant Safety

- Use company-specific accounting configuration.
- Use branch-specific user access.
- Avoid hardcoded company, currency, tax, account, journal, or local path values.
- Use the Initial Setup Wizard and SaaS Tenant records for onboarding tracking.

## Scaling

Start with 2 Odoo workers for small clients. Increase workers based on concurrent users, barcode load, and report usage. Put long-running notifications and AI work into background queues before high-volume rollout.
