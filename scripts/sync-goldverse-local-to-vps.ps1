param(
    [Parameter(Mandatory = $true)]
    [string]$VpsHost,

    [Parameter(Mandatory = $true)]
    [string]$VpsUser,

    [string]$Branch = "main",

    [string]$LocalRepoPath = (Get-Location).Path,

    [Parameter(Mandatory = $true)]
    [string]$VpsRepoPath,

    [string]$VpsRepoUrl,

    [string]$ModulesToUpgrade = "goldverse_premium_laundry_branding",

    [string]$OdooBin = "/opt/odoo/odoo/odoo-bin",

    [string]$OdooPython = "/opt/odoo/venv/bin/python",

    [string]$OdooConfig = "/etc/odoo/goldverse_premium_laundry.conf",

    [string]$OdooRunAsUser = "odoo",

    [string]$DbName = "goldverse_premium_laundry",

    [string]$OdooService,

    [string]$CommitMessage = "Deploy GoldVerse local changes",

    [switch]$AutoCommit,

    [switch]$NoRemotePull,

    [switch]$WhatIfMode
)

Set-StrictMode -Version Latest

function Assert-Executable {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' not found in PATH."
    }
}

function Invoke-RemoteCommand {
    param([string]$RemoteCommand)
    $destination = "$VpsUser@$VpsHost"
    $escaped = $RemoteCommand -replace '"', '`"'
    $fullCmd = "bash -lc `"$escaped`""
    if ($WhatIfMode) {
        Write-Host "[WHATIF] ssh $destination $fullCmd"
        return
    }
    ssh $destination $fullCmd
}

Assert-Executable git
Assert-Executable ssh

$LocalRepoPath = (Resolve-Path $LocalRepoPath).Path
$originUrl = (git -C $LocalRepoPath remote get-url origin).Trim()
if (-not $VpsRepoUrl) {
    $VpsRepoUrl = $originUrl
}
if (-not $VpsRepoUrl) {
    throw "Could not detect remote GitHub URL. Provide -VpsRepoUrl."
}

Write-Host "== Local -> GitHub ==" 
git -C $LocalRepoPath checkout $Branch
git -C $LocalRepoPath pull --ff-only origin $Branch

$status = git -C $LocalRepoPath status --porcelain
if ($status) {
    if (-not $AutoCommit) {
        throw "Local repo has uncommitted changes. Use -AutoCommit or commit manually first."
    }
    Write-Host "Local changes detected. Committing before push..."
    git -C $LocalRepoPath add -A
    git -C $LocalRepoPath commit -m $CommitMessage
}

git -C $LocalRepoPath push origin $Branch

if ($NoRemotePull) {
    Write-Host "Skipping VPS deployment because -NoRemotePull is set."
    Write-Host "GitHub sync complete for branch '$Branch'."
    return
}

Write-Host "== GitHub -> VPS Deployment =="

# Build the remote command list. PS variables are interpolated directly into
# the bash strings so we never declare bash variables like $APP_PATH — that
# would collide with PowerShell's own $ interpolation under Set-StrictMode and
# silently truncate the array (see git history for the prior bug).
$remoteCommands = [System.Collections.Generic.List[string]]::new()
$remoteCommands.Add("set -euo pipefail") | Out-Null
$remoteCommands.Add("if [ ! -d '$VpsRepoPath/.git' ]; then mkdir -p '$VpsRepoPath' && git clone '$VpsRepoUrl' '$VpsRepoPath'; fi") | Out-Null
$remoteCommands.Add("cd '$VpsRepoPath'") | Out-Null
$remoteCommands.Add("git fetch --all --prune") | Out-Null
$remoteCommands.Add("git checkout '$Branch'") | Out-Null
$remoteCommands.Add("git reset --hard 'origin/$Branch'") | Out-Null

if ($OdooService) {
    $remoteCommands.Add("sudo systemctl stop '$OdooService'") | Out-Null
}
if ($ModulesToUpgrade) {
    # Compose the upgrade command. If OdooPython is set, run odoo-bin under
    # that interpreter; otherwise call odoo-bin directly. Run as the OdooRunAsUser
    # (typically `odoo`) so the upgrade has write access to attachments/filestore.
    $upgradeCore = if ($OdooPython) {
        "$OdooPython $OdooBin -c '$OdooConfig' -d '$DbName' -u $ModulesToUpgrade --stop-after-init"
    } else {
        "$OdooBin -c '$OdooConfig' -d '$DbName' -u $ModulesToUpgrade --stop-after-init"
    }
    if ($OdooRunAsUser) {
        $remoteCommands.Add("sudo -u $OdooRunAsUser $upgradeCore") | Out-Null
    } else {
        $remoteCommands.Add($upgradeCore) | Out-Null
    }
}
if ($OdooService) {
    $remoteCommands.Add("sudo systemctl start '$OdooService'") | Out-Null
}

$remoteCommandText = ($remoteCommands -join " && ")
Invoke-RemoteCommand $remoteCommandText

Write-Host "Local -> GitHub -> VPS flow completed for branch '$Branch'."
