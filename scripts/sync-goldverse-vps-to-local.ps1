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

    [string]$LogPath,

    [string]$RemoteBackupArchivePath = "/opt/odoo/backups/goldverse_daily/goldverse_premium_laundry_daily.tar.gz",

    [string]$RemoteBackupLogPath = "/opt/odoo/backups/goldverse_daily/latest.log",

    [string]$RemoteBackupChecksumPath = "/opt/odoo/backups/goldverse_daily/goldverse_premium_laundry_daily.tar.gz.sha256",

    [string]$LocalBackupCacheRoot = "E:\Odoo Setup\aimaze_laundry_erp\backups\goldverse_offsite",

    [string]$OffsiteBackupRoot = "C:\Users\ahtes\OneDrive\Documents\GoldVerse Offsite Backups",

    [int]$BackupHistoryCount = 14,

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

function Ensure-Directory {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Write-ArchiveChecksumFile {
    param([string]$ArchivePath)
    $hash = Get-FileHash -Algorithm SHA256 -LiteralPath $ArchivePath
    $checksumPath = "$ArchivePath.sha256"
    "{0} *{1}" -f $hash.Hash.ToLowerInvariant(), (Split-Path -Leaf $ArchivePath) | Set-Content -LiteralPath $checksumPath -Encoding ascii
    return $checksumPath
}

function Trim-BackupHistory {
    param(
        [string]$HistoryDirectory,
        [int]$KeepCount
    )
    if (-not (Test-Path -LiteralPath $HistoryDirectory)) {
        return
    }

    $archives = @(Get-ChildItem -LiteralPath $HistoryDirectory -File -Filter "*.tar.gz" | Sort-Object LastWriteTimeUtc -Descending)
    if ($archives.Count -le $KeepCount) {
        return
    }

    $archives | Select-Object -Skip $KeepCount | ForEach-Object {
        $stem = $_.Name -replace '\.tar\.gz$',''
        $basePath = Join-Path $HistoryDirectory $stem
        Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath "$($_.FullName).sha256" -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath "$basePath.log" -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath "$basePath.sha256" -Force -ErrorAction SilentlyContinue
    }
}

function Publish-BackupSet {
    param(
        [string]$RootPath,
        [string]$ArchiveSourcePath,
        [string]$LogSourcePath,
        [string]$Stamp
    )

    if (-not $RootPath) {
        return
    }

    Ensure-Directory $RootPath
    $latestDir = Join-Path $RootPath "latest"
    $historyDir = Join-Path $RootPath "history"
    Ensure-Directory $latestDir
    Ensure-Directory $historyDir

    $latestArchivePath = Join-Path $latestDir "goldverse_premium_laundry_daily.tar.gz"
    $latestLogPath = Join-Path $latestDir "latest.log"
    $historyArchivePath = Join-Path $historyDir ("goldverse_premium_laundry_daily_{0}.tar.gz" -f $Stamp)
    $historyLogPath = Join-Path $historyDir ("goldverse_premium_laundry_daily_{0}.log" -f $Stamp)

    Copy-Item -LiteralPath $ArchiveSourcePath -Destination $latestArchivePath -Force
    Copy-Item -LiteralPath $ArchiveSourcePath -Destination $historyArchivePath -Force
    Copy-Item -LiteralPath $LogSourcePath -Destination $latestLogPath -Force
    Copy-Item -LiteralPath $LogSourcePath -Destination $historyLogPath -Force

    $latestChecksumPath = Write-ArchiveChecksumFile -ArchivePath $latestArchivePath
    $historyChecksumPath = Write-ArchiveChecksumFile -ArchivePath $historyArchivePath

    Write-Host ("Published backup set to {0}" -f $RootPath)
    Write-Host ("  latest archive: {0}" -f $latestArchivePath)
    Write-Host ("  latest checksum: {0}" -f $latestChecksumPath)
    Write-Host ("  history archive: {0}" -f $historyArchivePath)
    Write-Host ("  history checksum: {0}" -f $historyChecksumPath)

    Trim-BackupHistory -HistoryDirectory $historyDir -KeepCount $BackupHistoryCount
}

Assert-Executable git
Assert-Executable ssh
Assert-Executable scp

$LocalRepoPath = (Resolve-Path $LocalRepoPath).Path
$bundleFileRemote = "/tmp/goldverse_vps_sync.bundle"
$backupArchiveRemoteTemp = "/tmp/goldverse_premium_laundry_daily.tar.gz"
$backupLogRemoteTemp = "/tmp/goldverse_premium_laundry_daily_latest.log"
$backupChecksumRemoteTemp = "/tmp/goldverse_premium_laundry_daily.tar.gz.sha256"
$bundleFileLocal = Join-Path ([System.IO.Path]::GetTempPath()) "goldverse_vps_sync.bundle"
$backupArchiveLocal = Join-Path ([System.IO.Path]::GetTempPath()) "goldverse_premium_laundry_daily.tar.gz"
$backupLogLocal = Join-Path ([System.IO.Path]::GetTempPath()) "goldverse_premium_laundry_daily_latest.log"
$backupChecksumLocal = Join-Path ([System.IO.Path]::GetTempPath()) "goldverse_premium_laundry_daily.sha256"
$vpsRemoteRef = "refs/remotes/vps-sync/$Branch"
$transcriptStarted = $false
$backupStamp = Get-Date -Format "yyyyMMdd-HHmmss"

if ($LogPath) {
    $logDirectory = Split-Path -Parent $LogPath
    if ($logDirectory) {
        New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
    }
    Start-Transcript -Path $LogPath -Force | Out-Null
    $transcriptStarted = $true
}

try {
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
        "sudo rm -f '$backupArchiveRemoteTemp' '$backupLogRemoteTemp' '$backupChecksumRemoteTemp'",
        "sudo -u odoo git -C '$VpsRepoPath' bundle create '$bundleFileRemote' '$Branch'",
        "sudo cp '$RemoteBackupArchivePath' '$backupArchiveRemoteTemp'",
        "sudo cp '$RemoteBackupLogPath' '$backupLogRemoteTemp'",
        "if sudo test -f '$RemoteBackupChecksumPath'; then sudo cp '$RemoteBackupChecksumPath' '$backupChecksumRemoteTemp'; fi",
        "sudo chown ${VpsUser}:${VpsUser} '$bundleFileRemote' '$backupArchiveRemoteTemp' '$backupLogRemoteTemp'",
        "if sudo test -f '$backupChecksumRemoteTemp'; then sudo chown ${VpsUser}:${VpsUser} '$backupChecksumRemoteTemp'; fi"
    ) -join "; "
    Invoke-RemoteCommand $remoteSync

    Invoke-ScpDownload -RemotePath $bundleFileRemote -LocalPath $bundleFileLocal
    Invoke-ScpDownload -RemotePath $backupArchiveRemoteTemp -LocalPath $backupArchiveLocal
    Invoke-ScpDownload -RemotePath $backupLogRemoteTemp -LocalPath $backupLogLocal
    try {
        $remoteChecksum = Invoke-RemoteCommand "cat '$backupChecksumRemoteTemp'"
        $remoteChecksum | Set-Content -LiteralPath $backupChecksumLocal -Encoding ascii
    }
    catch {
        Write-Warning "Remote checksum download failed. A fresh checksum will be generated locally."
    }

    if ((Get-Item -LiteralPath $backupArchiveLocal).Length -le 0) {
        throw "Downloaded VPS backup archive is empty: $backupArchiveLocal"
    }

    Publish-BackupSet -RootPath $LocalBackupCacheRoot -ArchiveSourcePath $backupArchiveLocal -LogSourcePath $backupLogLocal -Stamp $backupStamp
    Publish-BackupSet -RootPath $OffsiteBackupRoot -ArchiveSourcePath $backupArchiveLocal -LogSourcePath $backupLogLocal -Stamp $backupStamp

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
    if (-not $WhatIfMode) {
        @($bundleFileLocal, $backupArchiveLocal, $backupLogLocal, $backupChecksumLocal) | ForEach-Object {
            if (Test-Path -LiteralPath $_) {
                Remove-Item -LiteralPath $_ -Force
            }
        }
    }
    Invoke-RemoteCommand "sudo rm -f '$bundleFileRemote' '$backupArchiveRemoteTemp' '$backupLogRemoteTemp' '$backupChecksumRemoteTemp'" | Out-Null
    if ($transcriptStarted) {
        Stop-Transcript | Out-Null
    }
}
