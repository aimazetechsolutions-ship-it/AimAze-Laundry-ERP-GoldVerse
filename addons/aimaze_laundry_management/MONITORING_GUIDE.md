# Monitoring Guide

Phase 4 adds `aimaze.laundry.integration.log` for API, notification, payment, delivery, workflow, backup, and security events.

## Recommended Stack

- Uptime monitoring: Better Stack, UptimeRobot, Pingdom, or Cloudflare Health Checks.
- Server metrics: Prometheus + Grafana, Netdata, or managed cloud monitoring.
- Logs: Loki, ELK, Better Stack Logs, or cloud-native logging.
- Database: PostgreSQL disk, locks, slow queries, connections, and replication health.

## What to Monitor

- Failed mobile API requests.
- Failed notification queue items.
- Failed payments or accounting entries.
- Failed delivery updates.
- Backup completion and restore test date.
- Disk and filestore growth.

## Log Rotation

Rotate Odoo and Nginx logs daily, compress old logs, and keep production logs according to client policy.
