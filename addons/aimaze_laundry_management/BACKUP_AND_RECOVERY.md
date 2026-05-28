# Backup and Recovery

## Daily Backup Strategy

- PostgreSQL dump daily.
- Filestore backup daily.
- Retain 7 daily, 4 weekly, and 6 monthly backups.
- Store at least one encrypted offsite copy.

## Example Cron

```cron
30 2 * * * /opt/aimaze-laundry/deployment/scripts/backup_odoo.sh
```

## Restore Procedure

1. Stop Odoo workers.
2. Restore PostgreSQL dump.
3. Restore filestore.
4. Start Odoo.
5. Validate login, orders, attachments, reports, and accounting menus.

## Disaster Recovery

For GCC SaaS clients, use regional object storage and periodically test restoring into a clean staging environment.
