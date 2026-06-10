# GoldVerse Laundry ERP

GoldVerse Laundry ERP is the GoldVerse Premium Laundry tenant package for AimAze Laundry ERP on Odoo.

This repository contains the source needed to deploy the GoldVerse build while keeping it separate from other AimAze/Odoo tenants.

## Repository Contents

- `addons/aimaze_laundry_management` - base AimAze Laundry ERP module.
- `addons/goldverse_premium_laundry_branding` - GoldVerse-specific branding, Pakistan defaults, order flow, warehouse receiving, dashboards, and report customizations.
- `addons/base_accounting_kit` - accounting report dependency used by the laundry ERP reports.
- `client/GoldVerse Premium Laundry` - client-facing notes and branding assets.
- `config/goldverse_premium_laundry.conf.example` - sanitized Odoo config template.
- `scripts/start_goldverse_premium_laundry.example.bat` - local Windows launcher template.

## Local Tenant Reference

- Database: `goldverse_premium_laundry`
- Local URL: `http://127.0.0.1:8093/web/login`
- Module to install/upgrade: `goldverse_premium_laundry_branding`
- Primary GoldVerse addon: `addons/goldverse_premium_laundry_branding`

## Deployment Notes

1. Copy the addons in `addons/` into the Odoo custom addons path, or point `addons_path` to this repository's `addons` folder.
2. Copy `config/goldverse_premium_laundry.conf.example` to a local `.conf` file outside source control.
3. Replace database credentials, paths, ports, and host settings for the target VPS or local machine.
4. Create or restore the `goldverse_premium_laundry` database.
5. Install or upgrade `goldverse_premium_laundry_branding`.

Example upgrade command:

```powershell
python odoo-bin -c path\to\goldverse_premium_laundry.conf -d goldverse_premium_laundry -u goldverse_premium_laundry_branding --stop-after-init
```

## Source Control Safety

Do not commit live `.conf` files, database dumps, filestore data, logs, backups, or secrets. Use the provided example config as the deployment template.

## Sync Workflows (local ↔ GitHub ↔ VPS)

Use these scripts for both required sync flows.

### 1) Local → GitHub → VPS Live

```powershell
.\scripts\sync-goldverse-local-to-vps.ps1 `
    -VpsHost <vps-host-or-ip> `
    -VpsUser <ssh-user> `
    -VpsRepoPath /opt/goldverse/AimAze-Laundry-ERP-GoldVerse `
    -ModulesToUpgrade "goldverse_premium_laundry_branding" `
    -OdooService odoo
```

### 2) VPS Live → GitHub → local

```powershell
.\scripts\sync-goldverse-vps-to-local.ps1 `
    -VpsHost <vps-host-or-ip> `
    -VpsUser <ssh-user> `
    -VpsRepoPath /opt/goldverse/AimAze-Laundry-ERP-GoldVerse `
    -CommitVpsChanges
```

### Recommended Sequence

1. Keep any production patch as commit-first in either side when possible.
2. If change started locally:
   local test -> local commit -> **Local → GitHub → VPS**.
3. If change started live on VPS:
   VPS change committed -> **VPS Live → GitHub → local**.
