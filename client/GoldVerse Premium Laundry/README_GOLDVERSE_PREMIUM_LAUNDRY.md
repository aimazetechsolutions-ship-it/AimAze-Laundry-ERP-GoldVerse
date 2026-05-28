# GoldVerse Premium Laundry Tenant

This folder is the standalone local runtime for the GoldVerse Premium Laundry client inside AimAze Laundry ERP.

## Local Runtime

- Client: GoldVerse Premium Laundry
- Database: `goldverse_premium_laundry`
- Local URL: `http://127.0.0.1:8093/web/login`
- Odoo config: `goldverse_premium_laundry.conf`
- Launcher: `start_goldverse_premium_laundry.bat`
- Filestore/data: `data/`
- Logs: `logs/`
- Backups: `backups/`

## Separation Rules

This tenant is separate from:

- `aimaze_laundry_erp`
- `GV`
- Hospitality ERP databases
- Real Estate ERP databases

The config uses a strict `dbfilter` so this runtime opens only `goldverse_premium_laundry`.

## SaaS/VPS Notes

For GitHub or VPS deployment, do not commit or upload:

- `.conf` files containing database connection settings
- SSH keys
- log files
- filestore data
- database backups
- secrets or API tokens

Commit only reusable module code, deployment templates, and sanitized documentation.
