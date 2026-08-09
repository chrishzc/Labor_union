[CmdletBinding()]
param(
    [string]$TaskName = "LaborUnionDurableJobWorker",
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),
    [switch]$StartNow
)

$ErrorActionPreference = "Stop"

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Administrator privileges are required to register a SYSTEM scheduled task."
    }
}

function Resolve-WorkerPaths {
    param([string]$Root)

    $resolvedRoot = (Resolve-Path -LiteralPath $Root).Path
    $pythonPath = Join-Path $resolvedRoot ".venv\\Scripts\\python.exe"
    $workerPath = Join-Path $resolvedRoot "scripts\\run_durable_job_worker.py"
    foreach ($path in @($pythonPath, $workerPath, (Join-Path $resolvedRoot ".env"))) {
        if (-not (Test-Path -LiteralPath $path)) {
            throw "Required worker deployment file is missing: $path"
        }
    }
    return @{ Root = $resolvedRoot; Python = $pythonPath; Worker = $workerPath }
}

Assert-Administrator
$paths = Resolve-WorkerPaths $ProjectRoot
$action = New-ScheduledTaskAction `
    -Execute $paths.Python `
    -Argument ('"{0}"' -f $paths.Worker) `
    -WorkingDirectory $paths.Root
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Labor Union durable job worker; supervised at system startup." `
    -Force | Out-Null

if ($StartNow) {
    Start-ScheduledTask -TaskName $TaskName
}

Write-Host "Registered scheduled task: $TaskName"
Write-Host "Worker root: $($paths.Root)"
Write-Host "Start immediately: $([bool]$StartNow)"
