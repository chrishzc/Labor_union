[CmdletBinding(SupportsShouldProcess)]
# Recovery-only removal remains available while new task installation is retired.
param(
    [string]$TaskName = "LaborUnionDurableJobWorker",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
if ($DryRun) {
    Get-Command Get-ScheduledTask -ErrorAction Stop | Out-Null
    Get-Command Unregister-ScheduledTask -ErrorAction Stop | Out-Null
    Write-Host "[DRY-RUN] Scheduled-task uninstall launcher is available; no task was queried or removed."
    exit 0
}
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $task) {
    Write-Host "Scheduled task is not installed: $TaskName"
    exit 0
}

if ($PSCmdlet.ShouldProcess($TaskName, "Remove durable job worker scheduled task")) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    Write-Host "Removed scheduled task: $TaskName"
}
