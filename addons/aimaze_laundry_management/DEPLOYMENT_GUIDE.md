# Deployment Guide

## Ubuntu 24 Deployment

1. Install PostgreSQL 13 or newer.
2. Install Odoo 19 Community.
3. Add `aimaze_laundry_management` to a custom addons path.
4. Configure `proxy_mode = True` behind Nginx.
5. Create a dedicated laundry database per client.
6. Install the module and run Initial Setup Wizard.
7. Configure HTTPS, email, backups, and monitoring.

## Docker Deployment

Copy `.env.example` to `.env`, fill secure values, then run:

```bash
docker compose up -d --build
```

## SSL and Domain

Use Nginx with Let's Encrypt or Cloudflare Origin Certificates. Enable Cloudflare proxy, WAF rules, rate limits, and bot protection for public portals.

## Production Security

Disable public database manager access, restrict admin users, enforce HTTPS, schedule backups, and rotate credentials regularly.
