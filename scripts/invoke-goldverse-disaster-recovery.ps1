param(
    [string]$RepoPath = "C:\Users\ahtes\Documents\Codex\2026-05-26\continue-work-on-goldverse-premium-laundry\AimAze-Laundry-ERP-GoldVerse",
    [string]$Branch = "main",
    [string]$LocalBackupRoot = "E:\Odoo Setup\aimaze_laundry_erp\backups\goldverse_offsite",
    [string]$OffsiteBackupRoot = "C:\Users\ahtes\OneDrive\Documents\GoldVerse Offsite Backups",
    [string]$TenantRoot = "E:\Odoo Setup\aimaze_laundry_erp\Clients\GoldVerse Premium Laundry",
    [string]$PythonExe = "E:\Odoo Setup\python\python.exe",
    [string]$OdooBin = "E:\Odoo Setup\server\odoo-bin",
    [string]$ConfigPath = "E:\Odoo Setup\aimaze_laundry_erp\Clients\GoldVerse Premium Laundry\goldverse_premium_laundry.conf",
    [string]$LauncherPath = "E:\Odoo Setup\aimaze_laundry_erp\Clients\GoldVerse Premium Laundry\start_goldverse_premium_laundry.bat",
    [string]$DbName = "goldverse_premium_laundry",
    [string]$DbHost = "localhost",
    [string]$DbPort = "5432",
    [string]$DbUser = "openpg",
    [string]$DbPassword = "openpgpwd",
    [string]$DataDir = "E:\Odoo Setup\aimaze_laundry_erp\Clients\GoldVerse Premium Laundry\data",
    [string]$VpsHost = "goldverse.aimazetechsolutions.com",
    [string]$VpsUser = "opc",
    [string]$VpsBackupArchivePath = "/opt/odoo/backups/goldverse_daily/goldverse_premium_laundry_daily.tar.gz",
    [string]$VpsBackupChecksumPath = "/opt/odoo/backups/goldverse_daily/goldverse_premium_laundry_daily.tar.gz.sha256",
    [string]$SshKeyPath = "E:\Odoo Setup\aimaze_laundry_erp\Clients\GoldVerse Premium Laundry\_private\ssh\goldverse_laundry_prod_ed25519",
    [switch]$CodeOnly,
    [switch]$SkipStart,
    [switch]$NoVpsFallback,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ("[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message)
}

function Assert-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' is not available."
    }
}

function Find-PostgresTool {
    param([string]$ToolName)
    $command = Get-Command $ToolName -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $patterns = @(
        "C:\Program Files\PostgreSQL\*\bin\$ToolName.exe",
        "C:\Program Files (x86)\PostgreSQL\*\bin\$ToolName.exe"
    )

    foreach ($pattern in $patterns) {
        $match = Get-ChildItem -Path $pattern -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
        if ($match) {
            return $match.FullName
        }
    }

    throw "Could not locate PostgreSQL tool '$ToolName'. Install PostgreSQL client tools or add them to PATH before running recovery."
}

function Assert-LastExitCode {
    param([string]$Context)
    if ($LASTEXITCODE -ne 0) {
        throw "$Context failed with exit code $LASTEXITCODE."
    }
}

function Resolve-LatestArchive {
    param([string[]]$Roots)

    foreach ($root in $Roots) {
        if (-not $root) { continue }
        $latest = Join-Path $root "latest\goldverse_premium_laundry_daily.tar.gz"
        if (Test-Path -LiteralPath $latest) {
            return $latest
        }

        $historyDir = Join-Path $root "history"
        if (Test-Path -LiteralPath $historyDir) {
            $archive = Get-ChildItem -LiteralPath $historyDir -Filter "*.tar.gz" -File -ErrorAction SilentlyContinue |
                Sort-Object LastWriteTimeUtc -Descending |
                Select-Object -First 1
            if ($archive) {
                return $archive.FullName
            }
        }
    }

    return $null
}

function Test-ArchiveChecksum {
    param([string]$ArchivePath)
    $checksumPath = "$ArchivePath.sha256"
    if (-not (Test-Path -LiteralPath $checksumPath)) {
        Write-Warning "Checksum file not found for $ArchivePath. Skipping checksum verification."
        return
    }

    $expectedLine = (Get-Content -LiteralPath $checksumPath -TotalCount 1).Trim()
    $expected = ($expectedLine -split '\s+')[0].ToLowerInvariant()
    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $ArchivePath).Hash.ToLowerInvariant()
    if ($expected -ne $actual) {
        throw "Checksum mismatch for $ArchivePath"
    }
}

function Download-LatestBackupFromVps {
    param([string]$TargetDirectory)
    Assert-Command ssh
    Assert-Command scp

    New-Item -ItemType Directory -Force -Path $TargetDirectory | Out-Null
    $archivePath = Join-Path $TargetDirectory "goldverse_premium_laundry_daily.tar.gz"
    $checksumPath = "$archivePath.sha256"

    Write-Step "Downloading latest backup archive directly from VPS."
    & scp -i $SshKeyPath "$VpsUser@${VpsHost}:$VpsBackupArchivePath" $archivePath
    Assert-LastExitCode "SCP archive download"

    try {
        & scp -i $SshKeyPath "$VpsUser@${VpsHost}:$VpsBackupChecksumPath" $checksumPath
        Assert-LastExitCode "SCP checksum download"
    }
    catch {
        Write-Warning "VPS checksum download failed. A local checksum will be generated instead."
        "{0} *{1}" -f ((Get-FileHash -Algorithm SHA256 -LiteralPath $archivePath).Hash.ToLowerInvariant()), (Split-Path -Leaf $archivePath) |
            Set-Content -LiteralPath $checksumPath -Encoding ascii
    }

    return $archivePath
}

function Stop-LocalOdooIfRunning {
    $connections = Get-NetTCPConnection -LocalPort 8093 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($procId in $connections) {
        try {
            Write-Step "Stopping local Odoo process $procId on port 8093."
            Stop-Process -Id $procId -Force
        }
        catch {
            Write-Warning "Could not stop process ${procId}: $($_.Exception.Message)"
        }
    }
}

function Start-LocalOdoo {
    if (-not (Test-Path -LiteralPath $LauncherPath)) {
        throw "Launcher not found: $LauncherPath"
    }
    Write-Step "Starting local GoldVerse launcher."
    Start-Process -FilePath $LauncherPath -WindowStyle Hidden
    Start-Sleep -Seconds 10
}

function Invoke-Http200Check {
    param([string]$Url)
    $status = (Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 20).StatusCode
    if ($status -ne 200) {
        throw "Expected HTTP 200 from $Url but got $status."
    }
}

if (-not $Force) {
    throw "This recovery script is destructive. Re-run with -Force when you are ready to restore GoldVerse."
}

Assert-Command git

$RepoPath = (Resolve-Path $RepoPath).Path
$pgRestore = Find-PostgresTool -ToolName "pg_restore"
$dropDb = Find-PostgresTool -ToolName "dropdb"
$createDb = Find-PostgresTool -ToolName "createdb"
$extractRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("goldverse_recovery_" + (Get-Date -Format "yyyyMMdd_HHmmss"))

try {
    Write-Step "Restoring GoldVerse code from GitHub."
    git -C $RepoPath fetch origin
    Assert-LastExitCode "git fetch"
    git -C $RepoPath checkout $Branch
    Assert-LastExitCode "git checkout"
    git -C $RepoPath reset --hard ("origin/" + $Branch)
    Assert-LastExitCode "git reset"

    if ($CodeOnly) {
        Write-Step "Code-only recovery completed."
        return
    }

    $archivePath = Resolve-LatestArchive -Roots @($LocalBackupRoot, $OffsiteBackupRoot)
    if (-not $archivePath -and -not $NoVpsFallback) {
        $fallbackDir = Join-Path $LocalBackupRoot "latest"
        $archivePath = Download-LatestBackupFromVps -TargetDirectory $fallbackDir
    }
    if (-not $archivePath) {
        throw "No GoldVerse backup archive found in local cache or offsite path."
    }

    Write-Step "Using backup archive: $archivePath"
    Test-ArchiveChecksum -ArchivePath $archivePath

    Write-Step "Stopping local Odoo before restore."
    Stop-LocalOdooIfRunning

    New-Item -ItemType Directory -Force -Path $extractRoot | Out-Null
    Write-Step "Extracting backup archive."
    & tar -xzf $archivePath -C $extractRoot
    Assert-LastExitCode "tar extract"

    $dumpPath = Join-Path $extractRoot "database\$DbName.dump"
    $filestoreSource = Join-Path $extractRoot "filestore\$DbName"
    $configSource = Join-Path $extractRoot "config\goldverse_premium_laundry.conf"
    if (-not (Test-Path -LiteralPath $dumpPath)) {
        throw "Database dump not found in extracted archive: $dumpPath"
    }
    if (-not (Test-Path -LiteralPath $filestoreSource)) {
        throw "Filestore not found in extracted archive: $filestoreSource"
    }

    $env:PGPASSWORD = $DbPassword
    Write-Step "Dropping and recreating local database $DbName."
    & $dropDb --if-exists -h $DbHost -p $DbPort -U $DbUser $DbName
    if ($LASTEXITCODE -gt 1) {
        Assert-LastExitCode "dropdb"
    }
    & $createDb -h $DbHost -p $DbPort -U $DbUser -O $DbUser $DbName
    Assert-LastExitCode "createdb"

    Write-Step "Restoring PostgreSQL dump."
    & $pgRestore -h $DbHost -p $DbPort -U $DbUser -d $DbName --no-owner --clean --if-exists $dumpPath
    Assert-LastExitCode "pg_restore"

    $filestoreTarget = Join-Path $DataDir "filestore\$DbName"
    Write-Step "Replacing local filestore."
    if (Test-Path -LiteralPath $filestoreTarget) {
        Remove-Item -LiteralPath $filestoreTarget -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $filestoreTarget) | Out-Null
    Copy-Item -LiteralPath $filestoreSource -Destination $filestoreTarget -Recurse -Force

    if (Test-Path -LiteralPath $configSource) {
        $recoveryDocs = Join-Path $TenantRoot "docs"
        New-Item -ItemType Directory -Force -Path $recoveryDocs | Out-Null
        Copy-Item -LiteralPath $configSource -Destination (Join-Path $recoveryDocs "goldverse_premium_laundry.recovered.conf") -Force
        Write-Step "Recovered config copy saved to docs\\goldverse_premium_laundry.recovered.conf"
    }

    if (-not $SkipStart) {
        Start-LocalOdoo
        Invoke-Http200Check -Url "http://127.0.0.1:8093/web/login"
        Write-Step "Local GoldVerse recovery completed and HTTP 200 verified."
    }
    else {
        Write-Step "Recovery completed. Local Odoo start skipped by request."
    }
}
finally {
    Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $extractRoot) {
        Remove-Item -LiteralPath $extractRoot -Recurse -Force
    }
}
