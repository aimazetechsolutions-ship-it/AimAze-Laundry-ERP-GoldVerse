param(
    [string]$TaskName = "GoldVerse VPS To Local Sync",
    [string]$TaskLogPath = "E:\Odoo Setup\aimaze_laundry_erp\logs\goldverse_vps_sync_nightly.log",
    [string]$LocalBackupRoot = "E:\Odoo Setup\aimaze_laundry_erp\backups\goldverse_offsite",
    [string]$OffsiteBackupRoot = "C:\Users\ahtes\OneDrive\Documents\GoldVerse Offsite Backups",
    [string]$VpsHost = "goldverse.aimazetechsolutions.com",
    [string]$VpsUser = "opc",
    [string]$SshKeyPath = "E:\Odoo Setup\aimaze_laundry_erp\Clients\GoldVerse Premium Laundry\_private\ssh\goldverse_laundry_prod_ed25519",
    [int]$FreshHours = 36
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function New-HealthItem {
    param(
        [string]$Area,
        [string]$Status,
        [string]$Detail
    )
    [pscustomobject]@{
        Area = $Area
        Status = $Status
        Detail = $Detail
    }
}

function Get-AgeStatus {
    param(
        [datetime]$Timestamp,
        [int]$FreshHours
    )
    $age = (Get-Date) - $Timestamp
    if ($age.TotalHours -le $FreshHours) {
        return @{ Status = "OK"; Age = $age }
    }
    if ($age.TotalHours -le ($FreshHours * 2)) {
        return @{ Status = "WARN"; Age = $age }
    }
    return @{ Status = "FAIL"; Age = $age }
}

function Format-Age {
    param([timespan]$Age)
    "{0}h {1}m" -f [math]::Floor($Age.TotalHours), $Age.Minutes
}

function Get-LatestFileInfo {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    return Get-Item -LiteralPath $Path
}

function Add-FileHealth {
    param(
        [System.Collections.Generic.List[object]]$Results,
        [string]$Area,
        [string]$ArchivePath,
        [string]$ChecksumPath,
        [string]$LogPath
    )

    $archive = Get-LatestFileInfo -Path $ArchivePath
    $checksum = Get-LatestFileInfo -Path $ChecksumPath
    $log = Get-LatestFileInfo -Path $LogPath

    if (-not $archive) {
        $Results.Add((New-HealthItem -Area $Area -Status "FAIL" -Detail "Archive missing: $ArchivePath"))
        return
    }

    $fresh = Get-AgeStatus -Timestamp $archive.LastWriteTime -FreshHours $FreshHours
    $detail = "Archive {0:n1} MB, age {1}" -f ($archive.Length / 1MB), (Format-Age $fresh.Age)
    if ($checksum) {
        $detail += ", checksum present"
    }
    else {
        $detail += ", checksum missing"
    }
    if ($log) {
        $detail += ", log updated " + $log.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")
    }
    $status = $fresh.Status
    if (-not $checksum -and $status -eq "OK") {
        $status = "WARN"
    }
    $Results.Add((New-HealthItem -Area $Area -Status $status -Detail $detail))
}

function Invoke-VpsHealthProbe {
    $remoteCommand = @'
sudo bash -lc '
service_state=$(systemctl is-active goldverse-odoo 2>/dev/null || true)
printf "SERVICE|%s\n" "$service_state"
for f in \
  /opt/odoo/backups/goldverse_daily/goldverse_premium_laundry_daily.tar.gz \
  /opt/odoo/backups/goldverse_daily/goldverse_premium_laundry_daily.tar.gz.sha256 \
  /opt/odoo/backups/goldverse_daily/latest.log
do
  if [ -f "$f" ]; then
    printf "FILE|%s|%s|%s\n" "$f" "$(stat -c %Y "$f")" "$(stat -c %s "$f")"
  else
    printf "FILE|%s|MISSING|0\n" "$f"
  fi
done
'
'@
    $sshArgs = @("-i", $SshKeyPath, "$VpsUser@$VpsHost", $remoteCommand)
    return & ssh @sshArgs
}

$results = New-Object 'System.Collections.Generic.List[object]'

try {
    $task = Get-ScheduledTask -TaskName $TaskName
    $taskInfo = Get-ScheduledTaskInfo -TaskName $TaskName
    $logonType = [string]$task.Principal.LogonType
    $taskStatus = if ($taskInfo.LastTaskResult -eq 0) { "OK" } else { "WARN" }
    $taskAge = Get-AgeStatus -Timestamp $taskInfo.LastRunTime -FreshHours $FreshHours
    if ($taskStatus -eq "OK" -and $taskAge.Status -ne "OK") {
        $taskStatus = $taskAge.Status
    }
    $results.Add((New-HealthItem -Area "Windows Task" -Status $taskStatus -Detail ("Last result {0}, last run {1}, logon {2}" -f $taskInfo.LastTaskResult, $taskInfo.LastRunTime.ToString("yyyy-MM-dd HH:mm:ss"), $logonType)))
}
catch {
    $results.Add((New-HealthItem -Area "Windows Task" -Status "FAIL" -Detail $_.Exception.Message))
}

if (Test-Path -LiteralPath $TaskLogPath) {
    $taskLog = Get-Item -LiteralPath $TaskLogPath
    $age = Get-AgeStatus -Timestamp $taskLog.LastWriteTime -FreshHours $FreshHours
    $results.Add((New-HealthItem -Area "Sync Log" -Status $age.Status -Detail ("Updated {0}, age {1}" -f $taskLog.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss"), (Format-Age $age.Age))))
}
else {
    $results.Add((New-HealthItem -Area "Sync Log" -Status "WARN" -Detail "Task log missing: $TaskLogPath"))
}

Add-FileHealth -Results $results -Area "Local Cache" `
    -ArchivePath (Join-Path $LocalBackupRoot "latest\goldverse_premium_laundry_daily.tar.gz") `
    -ChecksumPath (Join-Path $LocalBackupRoot "latest\goldverse_premium_laundry_daily.tar.gz.sha256") `
    -LogPath (Join-Path $LocalBackupRoot "latest\latest.log")

Add-FileHealth -Results $results -Area "OneDrive Offsite" `
    -ArchivePath (Join-Path $OffsiteBackupRoot "latest\goldverse_premium_laundry_daily.tar.gz") `
    -ChecksumPath (Join-Path $OffsiteBackupRoot "latest\goldverse_premium_laundry_daily.tar.gz.sha256") `
    -LogPath (Join-Path $OffsiteBackupRoot "latest\latest.log")

try {
    $probeLines = Invoke-VpsHealthProbe
    $serviceLine = $probeLines | Where-Object { $_ -like "SERVICE|*" } | Select-Object -First 1
    if ($serviceLine) {
        $serviceState = ($serviceLine -split '\|', 2)[1]
        $serviceStatus = if ($serviceState -eq "active") { "OK" } else { "WARN" }
        $results.Add((New-HealthItem -Area "VPS Service" -Status $serviceStatus -Detail "goldverse-odoo is $serviceState"))
    }
    $fileLines = @($probeLines | Where-Object { $_ -like "FILE|*" })
    $archiveLine = $fileLines | Where-Object { $_ -like "FILE|*/goldverse_premium_laundry_daily.tar.gz|*" } | Select-Object -First 1
    $checksumLine = $fileLines | Where-Object { $_ -like "FILE|*/goldverse_premium_laundry_daily.tar.gz.sha256|*" } | Select-Object -First 1
    $logLine = $fileLines | Where-Object { $_ -like "FILE|*/latest.log|*" } | Select-Object -First 1

    if ($archiveLine) {
        $parts = $archiveLine -split '\|'
        if ($parts[2] -eq "MISSING") {
            $results.Add((New-HealthItem -Area "VPS Backup" -Status "FAIL" -Detail "VPS archive missing"))
        }
        else {
            $ts = [DateTimeOffset]::FromUnixTimeSeconds([int64]$parts[2]).LocalDateTime
            $fresh = Get-AgeStatus -Timestamp $ts -FreshHours $FreshHours
            $archiveSizeMb = [math]::Round(([int64]$parts[3] / 1MB), 1)
            $checksumPresent = $false
            if ($checksumLine) {
                $checksumParts = $checksumLine -split '\|'
                $checksumPresent = $checksumParts[2] -ne "MISSING"
            }
            $logStamp = $null
            if ($logLine) {
                $logParts = $logLine -split '\|'
                if ($logParts[2] -ne "MISSING") {
                    $logStamp = [DateTimeOffset]::FromUnixTimeSeconds([int64]$logParts[2]).LocalDateTime
                }
            }
            $detail = "Archive {0} MB, age {1}" -f $archiveSizeMb, (Format-Age $fresh.Age)
            $detail += if ($checksumPresent) { ", checksum present" } else { ", checksum missing" }
            if ($logStamp) {
                $detail += ", log updated " + $logStamp.ToString("yyyy-MM-dd HH:mm:ss")
            }
            $status = $fresh.Status
            if (-not $checksumPresent -and $status -eq "OK") {
                $status = "WARN"
            }
            $results.Add((New-HealthItem -Area "VPS Backup" -Status $status -Detail $detail))
        }
    }
    else {
        $results.Add((New-HealthItem -Area "VPS Backup" -Status "FAIL" -Detail "VPS backup probe returned no archive line"))
    }
}
catch {
    $results.Add((New-HealthItem -Area "VPS Backup" -Status "FAIL" -Detail $_.Exception.Message))
}

$statusOrder = @{ FAIL = 0; WARN = 1; OK = 2 }
$results = $results | Sort-Object { $statusOrder[$_.Status] }, Area

Write-Host ""
Write-Host "GoldVerse Backup Health Check" -ForegroundColor Cyan
Write-Host ("Generated: {0}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"))
Write-Host ""

foreach ($item in $results) {
    $color = switch ($item.Status) {
        "OK" { "Green" }
        "WARN" { "Yellow" }
        default { "Red" }
    }
    Write-Host ("[{0}] {1}" -f $item.Status.PadRight(4), $item.Area) -ForegroundColor $color
    Write-Host ("       {0}" -f $item.Detail)
}

Write-Host ""
$overall = if ($results.Status -contains "FAIL") { "FAIL" } elseif ($results.Status -contains "WARN") { "WARN" } else { "OK" }
$overallColor = if ($overall -eq "OK") { "Green" } elseif ($overall -eq "WARN") { "Yellow" } else { "Red" }
Write-Host ("Overall Backup Health: {0}" -f $overall) -ForegroundColor $overallColor
