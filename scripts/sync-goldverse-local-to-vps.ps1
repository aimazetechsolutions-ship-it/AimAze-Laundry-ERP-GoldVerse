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

    [string]$OdooBin = "/opt/odoo/odoo-bin",

    [string]$OdooConfig = "/opt/odoo/config/goldverse_premium_laundry.conf",

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
$remoteCommands = @(
    "set -euo pipefail",
    "REPO_URL='$VpsRepoUrl'",
    "APP_PATH='$VpsRepoPath'",
    "if [ ! -d '$APP_PATH/.git' ]; then",
    "  mkdir -p '$APP_PATH'",
    "  git clone '$REPO_URL' '$APP_PATH'",
    "fi",
    "cd '$APP_PATH'",
    "git fetch --all --prune",
    "git checkout '$Branch'",
    "git reset --hard 'origin/$Branch'"
)

if ($ModulesToUpgrade) {
    $remoteCommands += "$OdooBin -c '$OdooConfig' -d '$DbName' -u $ModulesToUpgrade --stop-after-init"
}
if ($OdooService) {
    $remoteCommands += "sudo systemctl restart '$OdooService'"
}

$remoteCommandText = ($remoteCommands -join "; ")
Invoke-RemoteCommand $remoteCommandText

Write-Host "Local -> GitHub -> VPS flow completed for branch '$Branch'."
