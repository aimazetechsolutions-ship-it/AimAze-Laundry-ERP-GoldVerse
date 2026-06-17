# GoldVerse Disaster Recovery

This document covers the practical GoldVerse recovery flow for local, GitHub, and VPS.

## Protection Layout

GoldVerse now has four recovery layers:

1. Live VPS production
2. VPS nightly compressed backup
3. Local recovery cache on this machine
4. OneDrive-backed offsite copy

## Nightly Automation Order

1. `12:50 AM` Windows task: `GoldVerse VPS To Local Sync`
2. `1:00 AM` VPS cron backup

The Windows sync now does all of the following in one run:

1. Pull VPS code changes into local and GitHub
2. Download the latest VPS backup archive
3. Save a copy in the local recovery cache
4. Save a second copy in the OneDrive-backed offsite folder
5. Generate and retain checksum files

## Backup Locations

### Live VPS

- Archive: `/opt/odoo/backups/goldverse_daily/goldverse_premium_laundry_daily.tar.gz`
- Checksum: `/opt/odoo/backups/goldverse_daily/goldverse_premium_laundry_daily.tar.gz.sha256`
- Log: `/opt/odoo/backups/goldverse_daily/latest.log`

### Local recovery cache

- Root: `E:\Odoo Setup\aimaze_laundry_erp\backups\goldverse_offsite`
- Latest archive: `E:\Odoo Setup\aimaze_laundry_erp\backups\goldverse_offsite\latest\goldverse_premium_laundry_daily.tar.gz`
- History folder: `E:\Odoo Setup\aimaze_laundry_erp\backups\goldverse_offsite\history`

### OneDrive offsite copy

- Root: `C:\Users\ahtes\OneDrive\Documents\GoldVerse Offsite Backups`
- Latest archive: `C:\Users\ahtes\OneDrive\Documents\GoldVerse Offsite Backups\latest\goldverse_premium_laundry_daily.tar.gz`
- History folder: `C:\Users\ahtes\OneDrive\Documents\GoldVerse Offsite Backups\history`

## One-Click Local Disaster Recovery

Use this when the local GoldVerse copy is damaged, deleted, or out of sync.

### Launcher

- `scripts\run-goldverse-local-disaster-recovery.bat`

### PowerShell script

- `scripts\invoke-goldverse-disaster-recovery.ps1`

### What it does

1. Resets the local GoldVerse repo to `origin/main`
2. Finds the newest backup archive from:
   - local recovery cache first
   - OneDrive offsite copy second
   - live VPS direct download third
3. Verifies archive checksum
4. Stops local GoldVerse
5. Drops and recreates local database `goldverse_premium_laundry`
6. Restores PostgreSQL dump
7. Restores filestore
8. Starts local GoldVerse again
9. Verifies `http://127.0.0.1:8093/web/login`

### Important

This script is destructive for the local GoldVerse database and repo state.

Use it only when you intentionally want to rebuild local GoldVerse from backup.

## New VPS Recovery Procedure

Use this if the live VPS itself is lost.

### Required items

1. GitHub repo: `AimAze-Laundry-ERP-GoldVerse`
2. Latest backup archive from OneDrive offsite or local cache
3. GoldVerse SSH key and config

### Restore outline

1. Provision new VPS
2. Install Odoo 19 runtime and PostgreSQL
3. Clone the GoldVerse repo into:
   - `/opt/odoo/AimAze-Laundry-ERP-GoldVerse`
4. Restore database dump from the latest archive
5. Restore filestore from the latest archive
6. Restore `goldverse_premium_laundry.conf`
7. Restore `goldverse-odoo.service`
8. Start service
9. Verify live login URL

## Manual Verification Checklist

After any recovery:

1. Login page returns HTTP `200`
2. GoldVerse orders load
3. Latest customers exist
4. Latest invoices and payments exist
5. Filestore attachments and receipts open
6. Dashboard opens
7. Backup automation still exists

## Remaining Limitation

The Windows sync task is still tied to the current Windows user context. For full unattended execution when no user session is open, the task should be changed to run whether the user is logged on or not with saved credentials.
