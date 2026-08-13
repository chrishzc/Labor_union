[CmdletBinding()]
# Recovery-only inspection remains available while new task installation is retired.
param(
    [string]$TaskName = "LaborUnionDurableJobWorker",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
if ($DryRun) {
    Get-Command Get-ScheduledTask -ErrorAction Stop | Out-Null
    Get-Command Get-ScheduledTaskInfo -ErrorAction Stop | Out-Null
    Write-Host "[DRY-RUN] Scheduled-task status launcher is available; no task was queried."
    exit 0
}
$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($null -eq $task) {
    throw "Scheduled task is not installed: $TaskName"
}

$info = Get-ScheduledTaskInfo -TaskName $TaskName
[pscustomobject]@{
    TaskName = $TaskName
    State = [string]$task.State
    LastRunTime = $info.LastRunTime
    LastTaskResult = $info.LastTaskResult
    NextRunTime = $info.NextRunTime
}
