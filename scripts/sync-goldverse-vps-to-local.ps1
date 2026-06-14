param(
    [Parameter(Mandatory = $true)]
    [string]$VpsHost,

    [Parameter(Mandatory = $true)]
    [string]$VpsUser,

    [string]$Branch = "main",

    [string]$LocalRepoPath = (Get-Location).Path,

    [Parameter(Mandatory = $true)]
    [string]$VpsRepoPath,

    [string]$SshKeyPath,

    [switch]$CommitVpsChanges,

    [string]$CommitMessage = "Sync VPS live changes before pull",

    [string]$VpsGitUserName = "GoldVerse VPS Sync",

    [string]$VpsGitUserEmail = "goldverse-vps-sync@aimazetechsolutions.local",

    [switch]$NoLocalPull,

    [switch]$WhatIfMode
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-LastExitCode {
    param([string]$Context)
    if ($LASTEXITCODE -ne 0) {
        throw "$Context failed with exit code $LASTEXITCODE."
    }
}

function Assert-Executable {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' not found in PATH."
    }
}

function Invoke-RemoteCommand {
    param([string]$RemoteCommand)
    $destination = "$VpsUser@$VpsHost"
    if ($WhatIfMode) {
        Write-Host "[WHATIF] ssh $destination $RemoteCommand"
        return ""
    }
    $sshArgs = @()
    if ($SshKeyPath) {
        $sshArgs += "-i"
        $sshArgs += $SshKeyPath
    }
    $sshArgs += $destination
    $sshArgs += $RemoteCommand
    $result = & ssh @sshArgs
    Assert-LastExitCode "SSH command"
    return $result
}

function Invoke-ScpDownload {
    param(
        [string]$RemotePath,
        [string]$LocalPath
    )
    $source = "$VpsUser@${VpsHost}:$RemotePath"
    if ($WhatIfMode) {
        Write-Host "[WHATIF] scp $source $LocalPath"
        return
    }
    $scpArgs = @()
    if ($SshKeyPath) {
        $scpArgs += "-i"
        $scpArgs += $SshKeyPath
    }
    $scpArgs += $source
    $scpArgs += $LocalPath
    & scp @scpArgs
    Assert-LastExitCode "SCP download"
}

Assert-Executable git
Assert-Executable ssh
Assert-Executable scp

$LocalRepoPath = (Resolve-Path $LocalRepoPath).Path
$bundleFileRemote = "/tmp/goldverse_vps_sync.bundle"
$bundleFileLocal = Join-Path ([System.IO.Path]::GetTempPath()) "goldverse_vps_sync.bundle"
$vpsRemoteRef = "refs/remotes/vps-sync/$Branch"

$remoteStatusCommand = "sudo -u odoo git -C '$VpsRepoPath' status --porcelain"
$remoteDirty = Invoke-RemoteCommand $remoteStatusCommand

if ($remoteDirty) {
    Write-Host "VPS repo has uncommitted changes:"
    Write-Host $remoteDirty
    if (-not $CommitVpsChanges) {
        throw "Remote VPS repo is dirty. Use -CommitVpsChanges to auto-commit before syncing."
    }

    Write-Host "Committing VPS changes on live VPS before sync..."
    $commitCommand = @(
        "sudo -u odoo git -C '$VpsRepoPath' config user.name '" + $VpsGitUserName.Replace("'", "''") + "'",
        "sudo -u odoo git -C '$VpsRepoPath' config user.email '" + $VpsGitUserEmail.Replace("'", "''") + "'",
        "sudo -u odoo git -C '$VpsRepoPath' add -A",
        "if ! sudo -u odoo git -C '$VpsRepoPath' diff --cached --quiet --ignore-submodules --; then sudo -u odoo git -C '$VpsRepoPath' commit -m '" + $CommitMessage.Replace("'", "''") + "'; fi"
    ) -join "; "
    Invoke-RemoteCommand $commitCommand
}

Write-Host "Preparing VPS bundle for direct local sync."
$remoteSync = @(
    "sudo -u odoo git -C '$VpsRepoPath' checkout '$Branch'",
    "sudo rm -f '$bundleFileRemote'",
    "sudo -u odoo git -C '$VpsRepoPath' bundle create '$bundleFileRemote' '$Branch'",
    "sudo chown ${VpsUser}:${VpsUser} '$bundleFileRemote'"
) -join "; "
Invoke-RemoteCommand $remoteSync

try {
    Invoke-ScpDownload -RemotePath $bundleFileRemote -LocalPath $bundleFileLocal

    if ($NoLocalPull) {
        Write-Host "Skipping local/GitHub update because -NoLocalPull is set."
        Write-Host "VPS bundle downloaded to $bundleFileLocal."
        return
    }

    git -C $LocalRepoPath checkout $Branch
    Assert-LastExitCode "Local git checkout"
    git -C $LocalRepoPath pull --ff-only origin $Branch
    Assert-LastExitCode "Local git pull"
    git -C $LocalRepoPath fetch $bundleFileLocal "${Branch}:$vpsRemoteRef"
    Assert-LastExitCode "Local git fetch from VPS bundle"
    git -C $LocalRepoPath merge --ff-only $vpsRemoteRef
    Assert-LastExitCode "Local git fast-forward merge"
    git -C $LocalRepoPath push origin $Branch
    Assert-LastExitCode "Local git push"
    Write-Host "VPS -> GitHub -> local flow completed for branch '$Branch'."
}
finally {
    if ((-not $WhatIfMode) -and (Test-Path $bundleFileLocal)) {
        Remove-Item -LiteralPath $bundleFileLocal -Force
    }
    Invoke-RemoteCommand "sudo rm -f '$bundleFileRemote'" | Out-Null
}
