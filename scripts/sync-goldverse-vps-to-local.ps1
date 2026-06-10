param(
    [Parameter(Mandatory = $true)]
    [string]$VpsHost,

    [Parameter(Mandatory = $true)]
    [string]$VpsUser,

    [string]$Branch = "main",

    [string]$LocalRepoPath = (Get-Location).Path,

    [Parameter(Mandatory = $true)]
    [string]$VpsRepoPath,

    [switch]$CommitVpsChanges,

    [string]$CommitMessage = "Sync VPS live changes before pull",

    [switch]$NoLocalPull,

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
        return ""
    }
    $result = ssh $destination $fullCmd
    return $result
}

Assert-Executable git
Assert-Executable ssh

$LocalRepoPath = (Resolve-Path $LocalRepoPath).Path

$remoteStatusCommand = "cd '$VpsRepoPath'; git status --porcelain"
$remoteDirty = Invoke-RemoteCommand $remoteStatusCommand

if ($remoteDirty) {
    Write-Host "VPS repo has uncommitted changes:"
    Write-Host $remoteDirty
    if (-not $CommitVpsChanges) {
        throw "Remote VPS repo is dirty. Use -CommitVpsChanges to auto-commit before syncing."
    }

    Write-Host "Committing VPS changes and pushing to GitHub..."
    $commitCommand = @(
        "cd '$VpsRepoPath'",
        "git add -A",
        "git commit -m '" + $CommitMessage.Replace("'", "''") + "'",
        "git push origin $Branch"
    ) -join "; "
    Invoke-RemoteCommand $commitCommand
}

Write-Host "Pulling VPS Git repo to GitHub mainline."
$remoteSync = @(
    "cd '$VpsRepoPath'",
    "git checkout '$Branch'",
    "git pull --ff-only origin $Branch"
) -join "; "
Invoke-RemoteCommand $remoteSync

if ($NoLocalPull) {
    Write-Host "Skipping local GitHub pull because -NoLocalPull is set."
    Write-Host "VPS -> GitHub sync complete."
    return
}

git -C $LocalRepoPath checkout $Branch
git -C $LocalRepoPath pull --ff-only origin $Branch
Write-Host "VPS -> GitHub -> local flow completed for branch '$Branch'."
