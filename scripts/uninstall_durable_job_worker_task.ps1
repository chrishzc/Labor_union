[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$TaskName = "LaborUnionDurableJobWorker"
)

$ErrorActionPreference = "Stop"
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $task) {
    Write-Host "Scheduled task is not installed: $TaskName"
    exit 0
}

if ($PSCmdlet.ShouldProcess($TaskName, "Remove durable job worker scheduled task")) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed scheduled task: $TaskName"
}
