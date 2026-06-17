param(
    [string]$TaskName = "GoldVerse VPS To Local Sync"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

[xml]$taskXml = schtasks /Query /TN $TaskName /XML
$ns = New-Object System.Xml.XmlNamespaceManager($taskXml.NameTable)
$ns.AddNamespace("t", "http://schemas.microsoft.com/windows/2004/02/mit/task")

function Set-OrCreateNodeValue {
    param(
        [string]$XPath,
        [string]$Value
    )

    $node = $taskXml.SelectSingleNode($XPath, $ns)
    if (-not $node) {
        throw "Task XML node not found: $XPath"
    }
    $node.InnerText = $Value
}

Set-OrCreateNodeValue -XPath "/t:Task/t:RegistrationInfo/t:Description" -Value "Sync GoldVerse live VPS repo changes to local and GitHub, then mirror the nightly backup into local and OneDrive offsite storage before the 1:00 AM VPS backup."
Set-OrCreateNodeValue -XPath "/t:Task/t:Settings/t:DisallowStartIfOnBatteries" -Value "false"
Set-OrCreateNodeValue -XPath "/t:Task/t:Settings/t:StopIfGoingOnBatteries" -Value "false"
Set-OrCreateNodeValue -XPath "/t:Task/t:Settings/t:MultipleInstancesPolicy" -Value "Queue"
Set-OrCreateNodeValue -XPath "/t:Task/t:Settings/t:StartWhenAvailable" -Value "true"

$networkNode = $taskXml.SelectSingleNode("/t:Task/t:Settings/t:RunOnlyIfNetworkAvailable", $ns)
if (-not $networkNode) {
    $networkNode = $taskXml.CreateElement("RunOnlyIfNetworkAvailable", $taskXml.DocumentElement.NamespaceURI)
    [void]$taskXml.Task.Settings.AppendChild($networkNode)
}
$networkNode.InnerText = "true"

$wakeNode = $taskXml.SelectSingleNode("/t:Task/t:Settings/t:WakeToRun", $ns)
if (-not $wakeNode) {
    $wakeNode = $taskXml.CreateElement("WakeToRun", $taskXml.DocumentElement.NamespaceURI)
    [void]$taskXml.Task.Settings.AppendChild($wakeNode)
}
$wakeNode.InnerText = "true"

$enabledNode = $taskXml.SelectSingleNode("/t:Task/t:Settings/t:Enabled", $ns)
if (-not $enabledNode) {
    $enabledNode = $taskXml.CreateElement("Enabled", $taskXml.DocumentElement.NamespaceURI)
    [void]$taskXml.Task.Settings.AppendChild($enabledNode)
}
$enabledNode.InnerText = "true"

$executionNode = $taskXml.SelectSingleNode("/t:Task/t:Settings/t:ExecutionTimeLimit", $ns)
if (-not $executionNode) {
    $executionNode = $taskXml.CreateElement("ExecutionTimeLimit", $taskXml.DocumentElement.NamespaceURI)
    [void]$taskXml.Task.Settings.AppendChild($executionNode)
}
$executionNode.InnerText = "PT2H"

$restartNode = $taskXml.SelectSingleNode("/t:Task/t:Settings/t:RestartOnFailure", $ns)
if (-not $restartNode) {
    $restartNode = $taskXml.CreateElement("RestartOnFailure", $taskXml.DocumentElement.NamespaceURI)
    [void]$taskXml.Task.Settings.AppendChild($restartNode)
}

$intervalNode = $restartNode.SelectSingleNode("t:Interval", $ns)
if (-not $intervalNode) {
    $intervalNode = $taskXml.CreateElement("Interval", $taskXml.DocumentElement.NamespaceURI)
    [void]$restartNode.AppendChild($intervalNode)
}
$intervalNode.InnerText = "PT15M"

$countNode = $restartNode.SelectSingleNode("t:Count", $ns)
if (-not $countNode) {
    $countNode = $taskXml.CreateElement("Count", $taskXml.DocumentElement.NamespaceURI)
    [void]$restartNode.AppendChild($countNode)
}
$countNode.InnerText = "3"

$tempXmlPath = Join-Path $env:TEMP "goldverse-sync-task.xml"
$utf16 = New-Object System.Text.UnicodeEncoding($false, $true)
[System.IO.File]::WriteAllText($tempXmlPath, $taskXml.OuterXml, $utf16)

try {
    schtasks /Create /TN $TaskName /XML $tempXmlPath /F | Out-Null
}
finally {
    Remove-Item -LiteralPath $tempXmlPath -Force -ErrorAction SilentlyContinue
}

Write-Host "Task '$TaskName' hardened successfully."
Write-Host "Note: logon mode remains InteractiveToken until the task is recreated with saved user credentials."
