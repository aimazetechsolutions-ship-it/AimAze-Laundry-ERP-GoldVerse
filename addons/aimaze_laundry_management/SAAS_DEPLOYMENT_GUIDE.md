# SaaS Deployment Guide

This module is designed for Odoo 19 Community and can run as a standalone AimAze Laundry ERP database or inside a multi-company Odoo environment.

## Ubuntu Production Checklist

1. Install PostgreSQL 13 or newer.
2. Install Odoo 19 Community with a dedicated Linux user.
3. Place `aimaze_laundry_management` in a dedicated custom addons path.
4. Configure `addons_path` without mixing unrelated hospitality or real-estate modules unless intentionally sharing the same Odoo instance.
5. Create a dedicated laundry database.
6. Install the module from Apps.
7. Run the Initial Setup Wizard.
8. Configure company currency, branch, journals, taxes, and accounting accounts.
9. Enable SSL through Nginx or another reverse proxy.
10. Schedule database and filestore backups.

## SaaS Configuration

- Use one Odoo database per client for stronger isolation, or one database with strict multi-company rules for group deployments.
- Keep each company currency independent: AED for UAE, PKR for Pakistan.
- Do not hardcode accounts, taxes, journals, or local file paths.
- Use the setup wizard for first-time configuration.
- Configure record rules and user branch access before giving staff accounts.

## Security Checklist

- No SSH keys in the addon.
- No API tokens in XML, Python, or docs.
- No database passwords in the repository.
- Use HTTPS only.
- Restrict Odoo database manager access in production.
- Keep backups encrypted and tested.
