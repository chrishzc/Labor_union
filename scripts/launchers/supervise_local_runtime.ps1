#requires -Version 5.1
# File: supervise_local_runtime.ps1
# Description: Owns local Windows runtime identities, readiness checks, and scoped cleanup.
<#
.SYNOPSIS
  Own and supervise the Windows local development runtime.

.DESCRIPTION
  This is deliberately a small process supervisor. It starts each service as
  a direct child, waits for the two HTTP endpoints, reports JSON-line runtime
  events, and propagates any child failure. Cleanup is limited to immutable
  PID/start-time identities created or discovered by this invocation.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,

    [Parameter(Mandatory = $true)]
    [string]$PythonPath,

    [int]$ApiPort = 8000,
    [int]$ReactPort = 5173,

    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$script:Owned = [System.Collections.Generic.List[object]]::new()
$script:IdentityRegistry = [System.Collections.Generic.List[object]]::new()
$script:ExitCode = 0
$script:Stopping = $false
$script:RunId = [guid]::NewGuid().ToString("N")
$script:RunStartedAt = (Get-Date).ToUniversalTime()
$script:CleanupUnknown = $false
$script:ReactContainerName = $null
$script:UnknownRootPids = [System.Collections.Generic.List[int]]::new()

function Get-RootStartTime {
    $root = @($script:Owned | Select-Object -First 1)
    if ($root.Count -eq 0) { return $null }
    return ([datetime]$root[0].StartTime).ToUniversalTime().ToString("o")
}

function Write-RuntimeEvent {
    param(
        [Parameter(Mandatory = $true)][string]$Event,
        [string]$Label,
        [int]$ProcessId = 0,
        [int]$Code = 0,
        [string]$Detail,
        [int[]]$StoppedPids,
        [int[]]$SkippedPids,
        [int[]]$FailedPids,
        [int[]]$UnknownPids,
        [hashtable]$ChildExitCodes
    )
    $payload = [ordered]@{
        schema = "local-runtime-supervision.v1"
        event = $Event
        run_id = $script:RunId
        timestamp_utc = (Get-Date).ToUniversalTime().ToString("o")
        run_started_at_utc = $script:RunStartedAt.ToString("o")
        root_start_time = Get-RootStartTime
        label = $Label
        pid = if ($ProcessId) { $ProcessId } else { $null }
        exit_code = if ($Code -ne 0) { $Code } else { $null }
        child_exit_codes = if ($null -ne $ChildExitCodes) { $ChildExitCodes } else { @{} }
        stopped_pids = if ($null -ne $StoppedPids) { @($StoppedPids) } else { @() }
        skipped_pids = if ($null -ne $SkippedPids) { @($SkippedPids) } else { @() }
        failed_pids = if ($null -ne $FailedPids) { @($FailedPids) } else { @() }
        unknown_pids = if ($null -ne $UnknownPids) { @($UnknownPids) } else { @() }
        detail = if ($Detail) { $Detail } else { $null }
    }
    # The prefix makes the evidence machine-readable without hiding it from a
    # developer watching the launcher console.
    Write-Host ("RUNTIME_EVENT " + ($payload | ConvertTo-Json -Compress))
}

function Get-ProcessSnapshot {
    param([int]$ProcessId)
    try {
        $process = Get-Process -Id $ProcessId -ErrorAction Stop
        $exitCode = $null
        $state = "alive"
        try {
            if ($process.HasExited) {
                $state = "exited"
                $exitCode = [int]$process.ExitCode
            }
        }
        catch {
            return [pscustomobject]@{ Id = $ProcessId; State = "unknown"; StartTime = $null; Process = $process; ExitCode = $null; Alive = $false; Error = $_.Exception.Message }
        }
        try { $startTime = $process.StartTime.ToUniversalTime() }
        catch {
            return [pscustomobject]@{ Id = $ProcessId; State = "unknown"; StartTime = $null; Process = $process; ExitCode = $exitCode; Alive = $false; Error = $_.Exception.Message }
        }
        return [pscustomobject]@{
            Id = $ProcessId
            State = $state
            StartTime = $startTime
            Process = $process
            ExitCode = $exitCode
            Alive = $state -eq "alive"
            Error = $null
        }
    }
    catch {
        $notFound = $_.FullyQualifiedErrorId -match "NoProcessFoundForGivenId|ProcessNotFound"
        $state = if ($notFound) { "exited" } else { "unknown" }
        return [pscustomobject]@{ Id = $ProcessId; State = $state; StartTime = $null; Process = $null; ExitCode = $null; Alive = $false; Error = $_.Exception.Message }
    }
}

function Get-LastKnownExitCode {
    param([Parameter(Mandatory = $true)]$Entry)
    if ($null -ne $Entry.ExitCode) { return $Entry.ExitCode }
    if ($null -eq $Entry.Process) { return $null }
    try {
        $Entry.Process.Refresh()
        if ($Entry.Process.HasExited) {
            $Entry.ExitCode = [int]$Entry.Process.ExitCode
            return $Entry.ExitCode
        }
    }
    catch { }
    return $null
}

function Test-SameProcessIdentity {
    param(
        [Parameter(Mandatory = $true)]$Entry,
        [Parameter(Mandatory = $true)]$Snapshot
    )
    return ([datetime]$Snapshot.StartTime).ToUniversalTime().Ticks -eq ([datetime]$Entry.StartTime).ToUniversalTime().Ticks
}

function Mark-CleanupUnknown {
    param([int]$ProcessId)
    $script:CleanupUnknown = $true
    if (-not $script:UnknownRootPids.Contains($ProcessId)) {
        [void]$script:UnknownRootPids.Add($ProcessId)
    }
}

function Add-Identity {
    param(
        [Parameter(Mandatory = $true)][int]$ProcessId,
        [Parameter(Mandatory = $true)][datetime]$StartTime,
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][int]$RootPid,
        [Parameter(Mandatory = $true)][bool]$IsRoot,
        [int]$Depth = 0,
        $Process,
        $ExitCode
    )
    foreach ($existing in @($script:IdentityRegistry)) {
        if ($existing.Pid -eq $ProcessId -and
            ([datetime]$existing.StartTime).ToUniversalTime().Ticks -eq $StartTime.ToUniversalTime().Ticks) {
            if ($null -ne $Process) { $existing.Process = $Process }
            if ($null -ne $ExitCode) { $existing.ExitCode = $ExitCode }
            return $existing
        }
    }
    $entry = [pscustomobject]@{
        Label = $Label
        Pid = $ProcessId
        RootPid = $RootPid
        IsRoot = $IsRoot
        Depth = $Depth
        StartTime = $StartTime.ToUniversalTime()
        Process = $Process
        ExitCode = $ExitCode
        LastSeenAt = (Get-Date).ToUniversalTime()
    }
    $script:IdentityRegistry.Add($entry)
    return $entry
}

function Get-ProcessTreeSnapshot {
    try {
        $processes = @()
        foreach ($process in @(Get-CimInstance -ClassName Win32_Process)) {
            try {
                $creation = [System.Management.ManagementDateTimeConverter]::ToDateTime([string]$process.CreationDate).ToUniversalTime()
                $processes += [pscustomobject]@{ Pid = [int]$process.ProcessId; ParentPid = [int]$process.ParentProcessId; CreationDate = $creation; State = "known" }
            }
            catch {
                $processes += [pscustomobject]@{ Pid = [int]$process.ProcessId; ParentPid = [int]$process.ParentProcessId; CreationDate = $null; State = "unknown" }
            }
        }
        return [pscustomobject]@{ State = "known"; Processes = $processes; Error = $null }
    }
    catch {
        return [pscustomobject]@{ State = "unknown"; Processes = @(); Error = $_.Exception.Message }
    }
}

function Get-DescendantIds {
    param([int[]]$RootIds, [object[]]$Processes)
    $children = @{}
    foreach ($process in $Processes) {
        $parent = [int]$process.ParentPid
        if (-not $children.ContainsKey($parent)) { $children[$parent] = [System.Collections.Generic.List[int]]::new() }
        $children[$parent].Add([int]$process.Pid)
    }
    $seen = [System.Collections.Generic.HashSet[int]]::new()
    $queue = [System.Collections.Generic.Queue[int]]::new()
    foreach ($root in $RootIds) { if ($root -gt 0) { $queue.Enqueue($root) } }
    while ($queue.Count -gt 0) {
        $current = $queue.Dequeue()
        if (-not $seen.Add($current)) { continue }
        if ($children.ContainsKey($current)) {
            foreach ($child in $children[$current]) { $queue.Enqueue($child) }
        }
    }
    return @($seen)
}

function Refresh-OwnedIdentityRegistry {
    foreach ($entry in @($script:IdentityRegistry)) {
        $snapshot = Get-ProcessSnapshot -ProcessId $entry.Pid
        if ($snapshot.State -eq "unknown") {
            Mark-CleanupUnknown -ProcessId ([int]$entry.Pid)
        }
        elseif ($snapshot.State -eq "alive" -and (Test-SameProcessIdentity -Entry $entry -Snapshot $snapshot)) {
            $entry.Process = $snapshot.Process
            if ($null -ne $snapshot.ExitCode) { $entry.ExitCode = $snapshot.ExitCode }
            $entry.LastSeenAt = (Get-Date).ToUniversalTime()
        }
        else {
            [void](Get-LastKnownExitCode -Entry $entry)
        }
    }

    $treeSnapshot = Get-ProcessTreeSnapshot
    if ($treeSnapshot.State -eq "unknown") {
        foreach ($root in @($script:Owned)) { Mark-CleanupUnknown -ProcessId ([int]$root.Pid) }
        return
    }
    $processById = @{}
    foreach ($process in $treeSnapshot.Processes) { $processById[[int]$process.Pid] = $process }

    # Only roots matched in this one immutable Win32_Process snapshot may be
    # used as numeric traversal anchors. A dead or reused PID is never passed
    # to Get-DescendantIds.
    $activeRoots = [System.Collections.Generic.List[int]]::new()
    foreach ($root in @($script:Owned)) {
        $snapshot = Get-ProcessSnapshot -ProcessId $root.Pid
        $record = $null
        if ($processById.ContainsKey([int]$root.Pid)) { $record = $processById[[int]$root.Pid] }
        $sameCreation = $null -ne $record -and $record.State -eq "known" -and
            ([datetime]$record.CreationDate).ToUniversalTime().Ticks -eq ([datetime]$root.StartTime).ToUniversalTime().Ticks
        if ($snapshot.State -eq "alive" -and $sameCreation -and (Test-SameProcessIdentity -Entry $root -Snapshot $snapshot)) {
            $root.Process = $snapshot.Process
            if ($null -ne $snapshot.ExitCode) { $root.ExitCode = $snapshot.ExitCode }
            [void]$activeRoots.Add([int]$root.Pid)
        }
        else {
            [void](Get-LastKnownExitCode -Entry $root)
            $knownDescendant = @($script:IdentityRegistry | Where-Object { -not $_.IsRoot -and $_.RootPid -eq $root.Pid }).Count -gt 0
            if ($snapshot.State -eq "unknown" -or $null -eq $record -or $record.State -eq "unknown" -or
                (-not $knownDescendant -and $snapshot.State -ne "exited")) { Mark-CleanupUnknown -ProcessId ([int]$root.Pid) }
        }
    }
    if ($activeRoots.Count -eq 0) { return }

    # Keep the immutable root identity even when it has already exited. The
    # registry is what lets cleanup find descendants that became orphaned.
    $allIds = @(Get-DescendantIds -RootIds $activeRoots.ToArray() -Processes $treeSnapshot.Processes)
    $parentById = @{}
    foreach ($process in $treeSnapshot.Processes) { $parentById[[int]$process.Pid] = [int]$process.ParentPid }
    foreach ($id in $allIds) {
        if ($activeRoots -contains $id) { continue }
        $record = $processById[[int]$id]
        if ($null -eq $record -or $record.State -eq "unknown" -or $null -eq $record.CreationDate) {
            Mark-CleanupUnknown -ProcessId ([int]$id)
            continue
        }
        $snapshot = Get-ProcessSnapshot -ProcessId $id
        if ($snapshot.State -eq "unknown") { Mark-CleanupUnknown -ProcessId ([int]$id); continue }
        if ($snapshot.State -ne "alive") { continue }
        if (-not (Test-SameProcessIdentity -Entry ([pscustomobject]@{ StartTime = $record.CreationDate }) -Snapshot $snapshot)) {
            Mark-CleanupUnknown -ProcessId ([int]$id)
            continue
        }
        $rootPid = $null
        $cursor = [int]$id
        $walked = [System.Collections.Generic.HashSet[int]]::new()
        while ($parentById.ContainsKey($cursor) -and $walked.Add($cursor)) {
            $parent = [int]$parentById[$cursor]
            if ($activeRoots -contains $parent) { $rootPid = $parent; break }
            $cursor = $parent
        }
        if ($null -eq $rootPid) { Mark-CleanupUnknown -ProcessId ([int]$id); continue }
        $known = $false
        foreach ($entry in @($script:IdentityRegistry)) {
            if ($entry.Pid -eq $id -and
                ([datetime]$entry.StartTime).ToUniversalTime().Ticks -eq $snapshot.StartTime.ToUniversalTime().Ticks) {
                $known = $true
                $entry.Process = $snapshot.Process
                if ($null -ne $snapshot.ExitCode) { $entry.ExitCode = $snapshot.ExitCode }
                $entry.LastSeenAt = (Get-Date).ToUniversalTime()
                break
            }
        }
        if (-not $known) {
            [void](Add-Identity -ProcessId $id -StartTime $snapshot.StartTime -Label "descendant" -RootPid $rootPid -IsRoot $false -Depth 1 -Process $snapshot.Process -ExitCode $snapshot.ExitCode)
        }
    }
}

function Stop-OwnedProcessTrees {
    if ($script:Stopping) { return }
    $script:Stopping = $true

    Refresh-OwnedIdentityRegistry
    if ($script:IdentityRegistry.Count -eq 0) {
        if ($script:CleanupUnknown) {
            $script:ExitCode = 1
            Write-RuntimeEvent -Event "cleanup_unknown" -Code $script:ExitCode -Detail "a started root had no safely captured immutable identity; cleanup did not guess" -StoppedPids @() -SkippedPids @() -FailedPids @() -UnknownPids @($script:UnknownRootPids) -ChildExitCodes @{}
        }
        else {
            Write-RuntimeEvent -Event "cleanup_complete" -Detail "owned_identities=none" -StoppedPids @() -SkippedPids @() -FailedPids @() -UnknownPids @() -ChildExitCodes @{}
        }
        return
    }

    $stopped = [System.Collections.Generic.List[int]]::new()
    $skipped = [System.Collections.Generic.List[int]]::new()
    $failed = [System.Collections.Generic.List[int]]::new()
    $childExitCodes = @{}
    $identities = @($script:IdentityRegistry | Sort-Object `
        @{Expression = "IsRoot"; Descending = $false},
        @{Expression = "Depth"; Descending = $true})

    # Descendants first, then roots. Every Stop-Process is preceded by an
    # immediate PID + immutable StartTime check, so PID reuse is harmless.
    foreach ($entry in $identities) {
        $id = [int]$entry.Pid
        $current = Get-ProcessSnapshot -ProcessId $id
        if ($current.State -eq "unknown") {
            Mark-CleanupUnknown -ProcessId $id
            continue
        }
        if ($current.State -eq "exited") {
            $code = Get-LastKnownExitCode -Entry $entry
            if ($null -ne $code) { $childExitCodes[([string]$id)] = $code }
            [void]$skipped.Add($id)
            continue
        }
        if (-not (Test-SameProcessIdentity -Entry $entry -Snapshot $current)) {
            [void]$skipped.Add($id)
            continue
        }
        try {
            # Re-read immediately before this destructive operation.
            $verified = Get-ProcessSnapshot -ProcessId $id
            if ($verified.State -eq "unknown") {
                Mark-CleanupUnknown -ProcessId $id
                continue
            }
            if ($verified.State -eq "exited" -or -not (Test-SameProcessIdentity -Entry $entry -Snapshot $verified)) {
                [void]$skipped.Add($id)
                continue
            }
            Stop-Process -Id $id -Force -ErrorAction Stop
            try { [void]$verified.Process.WaitForExit(2000) } catch { }
            $after = Get-ProcessSnapshot -ProcessId $id
            if ($after.State -eq "unknown") {
                Mark-CleanupUnknown -ProcessId $id
            }
            elseif ($after.State -eq "exited" -or -not (Test-SameProcessIdentity -Entry $entry -Snapshot $after)) {
                [void]$stopped.Add($id)
            }
            else {
                [void]$failed.Add($id)
            }
        }
        catch {
            # A race with natural exit is a skip; a still-live matching process
            # is a real cleanup failure and makes the supervisor non-zero.
            $after = Get-ProcessSnapshot -ProcessId $id
            if ($after.State -eq "unknown") {
                Mark-CleanupUnknown -ProcessId $id
            }
            elseif ($after.State -eq "exited" -or -not (Test-SameProcessIdentity -Entry $entry -Snapshot $after)) {
                [void]$skipped.Add($id)
            }
            else {
                [void]$failed.Add($id)
            }
        }
        $code = Get-LastKnownExitCode -Entry $entry
        if ($null -ne $code) { $childExitCodes[([string]$id)] = $code }
    }

    $stoppedIds = @($stopped | Select-Object -Unique)
    $skippedIds = @($skipped | Select-Object -Unique)
    $failedIds = @($failed | Select-Object -Unique)
    if ($script:CleanupUnknown) {
        $script:ExitCode = 1
        Write-RuntimeEvent -Event "cleanup_unknown" -Code $script:ExitCode -Detail "root exited before a safe descendant identity was captured; the dead or reused root was excluded from numeric PID traversal" -StoppedPids $stoppedIds -SkippedPids $skippedIds -FailedPids $failedIds -UnknownPids @($script:UnknownRootPids) -ChildExitCodes $childExitCodes
        return
    }
    if ($failedIds.Count -gt 0) {
        $script:ExitCode = 1
        Write-RuntimeEvent -Event "cleanup_failed" -Code $script:ExitCode -Detail "one or more verified-owned processes could not be stopped" -StoppedPids $stoppedIds -SkippedPids $skippedIds -FailedPids $failedIds -UnknownPids @() -ChildExitCodes $childExitCodes
        return
    }
    Write-RuntimeEvent -Event "cleanup_complete" -Detail "all verified-owned live processes stopped or already exited" -StoppedPids $stoppedIds -SkippedPids $skippedIds -FailedPids $failedIds -UnknownPids @() -ChildExitCodes $childExitCodes
}

function Start-Owned {
    param(
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [string]$WorkingDirectory = $ProjectRoot
    )
    $process = $null
    $snapshot = $null
    try {
        $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList `
            -WorkingDirectory $WorkingDirectory -NoNewWindow -PassThru
        $snapshot = Get-ProcessSnapshot -ProcessId $process.Id
        if ($null -eq $snapshot) {
            # Preserve the root identity even if it exits before the first
            # refresh; descendants already recorded by the process handle can
            # still be safely considered during scoped cleanup.
            try {
                $fallbackStartTime = $process.StartTime.ToUniversalTime()
                $snapshot = [pscustomobject]@{ Id = $process.Id; StartTime = $fallbackStartTime; Process = $process; ExitCode = [int]$process.ExitCode; Alive = $false }
            }
            catch {
                $script:CleanupUnknown = $true
                if (-not $script:UnknownRootPids.Contains([int]$process.Id)) {
                    [void]$script:UnknownRootPids.Add([int]$process.Id)
                }
                throw "process exited before its immutable identity could be captured"
            }
        }
        $entry = [pscustomobject]@{ Label = $Label; Pid = $process.Id; StartTime = $snapshot.StartTime; Process = $snapshot.Process; ExitCode = $snapshot.ExitCode }
        $script:Owned.Add($entry)
        [void](Add-Identity -ProcessId $process.Id -StartTime $snapshot.StartTime -Label $Label -RootPid $process.Id -IsRoot $true -Process $snapshot.Process -ExitCode $snapshot.ExitCode)
        # Discover descendants while the root is known, before a short-lived
        # wrapper can orphan them.
        Refresh-OwnedIdentityRegistry
        Write-RuntimeEvent -Event "started" -Label $Label -ProcessId $process.Id
        return $entry
    }
    catch {
        Write-RuntimeEvent -Event "start_failed" -Label $Label -Detail $_.Exception.Message
        throw
    }
}

function Stop-OwnedReactContainer {
    if ([string]::IsNullOrWhiteSpace($script:ReactContainerName)) { return }
    $docker = Get-Command "docker.exe" -CommandType Application -ErrorAction SilentlyContinue
    if ($null -eq $docker) {
        $script:ExitCode = 1
        Write-RuntimeEvent -Event "cleanup_failed" -Label "React/Vite" -Code 1 -Detail "docker.exe is unavailable for owned Vite container cleanup"
        return
    }
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "SilentlyContinue"
    try {
        & $docker.Source rm --force $script:ReactContainerName *> $null
        $removeExit = $LASTEXITCODE
        if ($removeExit -ne 0) {
            & $docker.Source inspect $script:ReactContainerName *> $null
            $inspectExit = $LASTEXITCODE
        }
        else {
            $inspectExit = 1
        }
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($removeExit -ne 0 -and $inspectExit -eq 0) {
            $script:ExitCode = 1
            Write-RuntimeEvent -Event "cleanup_failed" -Label "React/Vite" -Code 1 -Detail "owned Vite container could not be removed"
            return
    }
    Write-RuntimeEvent -Event "container_cleanup_complete" -Label "React/Vite" -Detail $script:ReactContainerName
    $script:ReactContainerName = $null
}

function Test-OwnedAlive {
    param([Parameter(Mandatory = $true)]$Entry)
    $snapshot = Get-ProcessSnapshot -ProcessId $Entry.Pid
    if ($null -eq $snapshot -or $snapshot.State -ne "alive") {
        [void](Get-LastKnownExitCode -Entry $Entry)
        return $false
    }
    if (-not (Test-SameProcessIdentity -Entry $Entry -Snapshot $snapshot)) { return $false }
    $Entry.Process = $snapshot.Process
    if ($null -ne $snapshot.ExitCode) { $Entry.ExitCode = $snapshot.ExitCode }
    return $true
}

function Wait-HttpReady {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Label,
        [int]$Attempts = 30,
        [switch]$RequireHtmlRoot
    )
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2
            $isReady = $response.StatusCode -eq 200
            if ($isReady -and $RequireHtmlRoot) {
                $body = [string]$response.Content
                # React's root marker distinguishes the HTML app from a
                # proxy's unrelated 200 response.
                $isReady = $body -match 'id\s*=\s*["'']root["'']'
            }
            if ($isReady) {
                Write-RuntimeEvent -Event "ready" -Label $Label -Detail $Url
                return
            }
        }
        catch { }
        Start-Sleep -Seconds 1
    }
    throw "$Label did not become ready: $Url"
}

function Test-EnabledFromDotEnv {
    param([string]$Name)
    $inherited = [Environment]::GetEnvironmentVariable($Name)
    if ($null -ne $inherited) { return $inherited.Trim().ToLowerInvariant() -eq "true" }
    $dotenv = Join-Path $ProjectRoot ".env"
    if (-not (Test-Path -LiteralPath $dotenv)) { return $false }
    foreach ($line in @(Get-Content -LiteralPath $dotenv -ErrorAction SilentlyContinue)) {
        if ($line -match '^\s*([^#=]+?)\s*=\s*(.*?)\s*$') {
            if ($Matches[1].Trim() -ceq $Name) {
                $value = $Matches[2].Trim().Trim('"').Trim("'")
                return $value.Trim().ToLowerInvariant() -eq "true"
            }
        }
    }
    return $false
}

function Assert-ChildrenAlive {
    Refresh-OwnedIdentityRegistry
    foreach ($entry in @($script:Owned)) {
        if (-not (Test-OwnedAlive -Entry $entry)) {
            $code = Get-LastKnownExitCode -Entry $entry
            Write-RuntimeEvent -Event "survival_failed" -Label $entry.Label -ProcessId $entry.Pid -Code $(if ($null -ne $code) { $code } else { 1 }) -ChildExitCodes @{}
            throw "$($entry.Label) exited; stopping owned local runtime."
        }
    }
}

try {
    if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) { throw "Project root does not exist: $ProjectRoot" }
    if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw "Python executable does not exist: $PythonPath" }

    if ($DryRun) {
        Write-RuntimeEvent -Event "dry_run" -Detail "no child process started"
        exit 0
    }

    Write-RuntimeEvent -Event "supervision_started" -Detail ("api_port=" + $ApiPort + ";react_port=" + $ReactPort)
    $api = Start-Owned -Label "FastAPI" -FilePath $PythonPath -ArgumentList @(
        "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "$ApiPort"
    )
    Wait-HttpReady -Url "http://127.0.0.1:$ApiPort/health" -Label "FastAPI"
    Refresh-OwnedIdentityRegistry

    if ($env:REACT_ADMIN_RUNTIME_PROFILE -eq "artifact-runtime") {
        & $PythonPath -m scripts.run_service_monitor --react-admin-health-check
        if ($LASTEXITCODE -ne 0) { throw "artifact-runtime health probe failed with exit code $LASTEXITCODE" }
        Write-RuntimeEvent -Event "artifact_probe_passed" -Label "Runtime Monitor"
    }

    $uiRoot = Join-Path $ProjectRoot "ui_react"
    $npm = Get-Command "npm.cmd" -CommandType Application -ErrorAction SilentlyContinue
    if ($null -ne $npm) {
        $react = Start-Owned -Label "React/Vite" -FilePath $npm.Source -WorkingDirectory $uiRoot -ArgumentList @(
            "run", "dev", "--", "--host", "0.0.0.0", "--port", "$ReactPort", "--strictPort"
        )
    }
    else {
        $docker = Get-Command "docker.exe" -CommandType Application -ErrorAction SilentlyContinue
        if ($null -eq $docker) { throw "React/Vite requires host npm.cmd or docker.exe" }
        & $docker.Source run --rm -v "${uiRoot}:/app" -w "/app" "node:lts" `
            npm install --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw "Docker npm install failed with exit code $LASTEXITCODE" }
        $script:ReactContainerName = "labor-union-vite-$($script:RunId)"
        $dockerArguments = @(
            "run", "--rm", "--name", $script:ReactContainerName,
            "-e", "VITE_DEV_API_TARGET=http://host.docker.internal:$ApiPort"
        )
        if (-not [string]::IsNullOrWhiteSpace($env:VITE_ACCESS_CONTROL_PROFILE)) {
            $dockerArguments += @("-e", "VITE_ACCESS_CONTROL_PROFILE=$($env:VITE_ACCESS_CONTROL_PROFILE)")
        }
        $dockerArguments += @(
            "-v", "${uiRoot}:/app", "-w", "/app", "-p", "${ReactPort}:${ReactPort}",
            "node:lts", "npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "$ReactPort", "--strictPort"
        )
        $react = Start-Owned -Label "React/Vite" -FilePath $docker.Source -ArgumentList $dockerArguments
    }
    Wait-HttpReady -Url "http://127.0.0.1:$ReactPort/admin/" -Label "React/Vite" -RequireHtmlRoot
    Refresh-OwnedIdentityRegistry

    & $PythonPath -m scripts.launcher_preflight --profile line-worker *> $null
    $linePreflightExit = $LASTEXITCODE
    if ($linePreflightExit -eq 0) {
        $line = Start-Owned -Label "LINE Worker" -FilePath $PythonPath -ArgumentList @("-m", "scripts.run_line_worker")
    }
    else {
        Write-RuntimeEvent -Event "skipped" -Label "LINE Worker" -Detail "Skipping LINE Worker: local LINE credentials or runtime configuration are unavailable"
    }

    $monitor = Start-Owned -Label "Runtime Monitor" -FilePath $PythonPath -ArgumentList @("-m", "scripts.run_service_monitor")
    $durable = Start-Owned -Label "Durable Background Worker" -FilePath $PythonPath -ArgumentList @("-m", "scripts.run_durable_job_worker")
    $incident = Start-Owned -Label "Incident Maintenance Worker" -FilePath $PythonPath -ArgumentList @("-m", "scripts.run_incident_worker")
    if (Test-EnabledFromDotEnv -Name "KNOWLEDGE_RETRIEVAL_RUNTIME_ENABLED") {
        $knowledge = Start-Owned -Label "Knowledge Retrieval Worker" -FilePath $PythonPath -ArgumentList @("-m", "scripts.run_knowledge_worker")
    }
    else {
        Write-RuntimeEvent -Event "skipped" -Label "Knowledge Retrieval Worker" -Detail "runtime flag is not enabled"
    }

    Assert-ChildrenAlive
    Write-RuntimeEvent -Event "runtime_ready" -Detail "required and configured optional processes are alive"
    while ($true) {
        Start-Sleep -Seconds 2
        Assert-ChildrenAlive
    }
}
catch {
    if ($script:ExitCode -eq 0) { $script:ExitCode = 1 }
    Write-RuntimeEvent -Event "supervision_failed" -Code $script:ExitCode -Detail $_.Exception.Message
}
finally {
    Stop-OwnedReactContainer
    Stop-OwnedProcessTrees
}

exit $script:ExitCode
