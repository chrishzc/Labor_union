# Frontend-only maintenance. Loaded by the owned runtime supervisor; no DB setup.
$controllerHash = [Security.Cryptography.SHA256]::Create()
try {
    $script:FrontendControllerDigest = [BitConverter]::ToString($controllerHash.ComputeHash([IO.File]::ReadAllBytes($PSCommandPath))) + ':' +
        [BitConverter]::ToString($controllerHash.ComputeHash([IO.File]::ReadAllBytes((Join-Path $PSScriptRoot 'supervise_local_runtime.ps1'))))
}
finally { $controllerHash.Dispose() }

function Get-FrontendControlDirectory {
    return Join-Path $ProjectRoot "scratch\windows-remote\frontend-control"
}

function Write-FrontendControlJson {
    param([string]$Path, $Value)
    $temporary = "$Path.$([guid]::NewGuid().ToString('N')).tmp"
    [IO.File]::WriteAllText($temporary, ($Value | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    if (Test-Path -LiteralPath $Path) { [IO.File]::Replace($temporary, $Path, [System.Management.Automation.Language.NullString]::Value) }
    else { [IO.File]::Move($temporary, $Path) }
}

function Assert-FrontendArtifact {
    param([string]$ArtifactPath)
    $canonical = [IO.Path]::GetFullPath($ArtifactPath)
    $allowed = [IO.Path]::GetFullPath((Join-Path $ProjectRoot 'scratch\windows-remote')) + [IO.Path]::DirectorySeparatorChar
    if (-not $canonical.StartsWith($allowed, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Frontend artifact must be under scratch/windows-remote.'
    }
    $code = "import json,sys; from pathlib import Path; from infrastructure.runtime.react_admin_artifact import validate_react_admin_artifact; a=validate_react_admin_artifact(Path(sys.argv[1]),workspace_root=Path.cwd()); print(json.dumps(a.health_attestation('current')))"
    $result = & $PythonPath -c $code $canonical
    if ($LASTEXITCODE -ne 0) { throw 'Frontend artifact validation failed; current frontend was not replaced.' }
    return [pscustomobject]@{ Path = $canonical; Identity = ($result | ConvertFrom-Json) }
}

function Publish-FrontendControlState {
    param([string]$RuntimeStatus = 'ready')
    $directory = Get-FrontendControlDirectory
    [void][IO.Directory]::CreateDirectory($directory)
    $roots = @($script:Owned | ForEach-Object {
        [ordered]@{ label = $_.Label; pid = $_.Pid; start_time = $_.StartTime.ToUniversalTime().ToString('o') }
    })
    Write-FrontendControlJson (Join-Path $directory 'state.json') ([ordered]@{
        contract = 'windows-frontend-control/v1'; run_id = $script:RunId
        controller_digest = $script:FrontendControllerDigest
        supervisor_pid = $PID; supervisor_start_time = (Get-Process -Id $PID).StartTime.ToUniversalTime().ToString('o')
        project_root = $ProjectRoot; api_port = $ApiPort; react_port = $ReactPort
        artifact_path = $env:WINDOWS_REMOTE_ARTIFACT_DIR; roots = $roots
        runtime_status = $RuntimeStatus
        cleanup_confirmed = ($script:CleanupSucceeded -eq $true)
    })
}

function Stop-RemoteFrontendChild {
    param($Entry)
    if ($Entry.Label -ne 'Remote React') { throw 'Only the registered remote frontend may be replaced.' }
    Refresh-OwnedIdentityRegistry
    # Stop the Python launcher before its listener child: otherwise the launcher
    # can exit between the descendant stop and the next native identity read.
    $identities = @($script:IdentityRegistry | Where-Object { $_.RootPid -eq $Entry.Pid } | Sort-Object @{Expression='IsRoot';Descending=$true})
    foreach ($identity in $identities) {
        $snapshot = Get-ProcessSnapshot $identity.Pid
        if ($snapshot.State -eq 'exited') { continue }
        if ($snapshot.State -eq 'unknown' -and $null -ne $snapshot.Process) {
            # A console-owned Python child can exit with its launcher. Reading
            # StartTime then fails, but the native handle can still prove exit.
            try { if ($snapshot.Process.HasExited) { continue } } catch { }
        }
        if ($snapshot.State -ne 'alive' -or -not (Test-SameProcessIdentity $identity $snapshot)) {
            throw "Frontend process identity changed (pid=$($identity.Pid), state=$($snapshot.State)); no unverified process was stopped."
        }
        # Kill via the verified process handle, never an unqualified process tree.
        $snapshot.Process.Kill()
        if (-not $snapshot.Process.WaitForExit(5000)) { throw 'Frontend process did not stop.' }
    }
    foreach ($identity in $identities) { [void]$script:IdentityRegistry.Remove($identity) }
    [void]$script:Owned.Remove($Entry)
}

function Start-RemoteFrontendChild {
    param([string]$ArtifactPath)
    $env:WINDOWS_REMOTE_ARTIFACT_DIR = $ArtifactPath
    $env:WINDOWS_REMOTE_API_PORT = "$ApiPort"
    $env:ACCESS_CONTROL_PROFILE = 'production'
    $env:ENABLE_ADMIN_AUTH = 'true'
    $entry = Start-Owned -Label 'Remote React' -FilePath $PythonPath -ArgumentList @(
        '-m', 'uvicorn', 'scripts.windows_remote_runtime:create_app', '--factory',
        '--host', '127.0.0.1', '--port', "$ReactPort", '--no-proxy-headers'
    )
    Wait-HttpReady -Url "http://127.0.0.1:$ReactPort/test/" -Label 'Remote React' -RequireHtmlRoot -OwnedEntry $entry
    $expected = Get-Content -Raw -LiteralPath (Join-Path $ArtifactPath 'artifact-manifest.json') | ConvertFrom-Json
    $actual = (Invoke-WebRequest -Uri "http://127.0.0.1:$ReactPort/test/artifact-manifest.json" -UseBasicParsing -TimeoutSec 5).Content | ConvertFrom-Json
    if ($actual.artifact_digest -ne $expected.artifact_digest) { throw 'Frontend readback did not match the requested artifact.' }
    return $entry
}

function Invoke-RemoteFrontendRestart {
    param([string]$ArtifactPath)
    $validated = Assert-FrontendArtifact $ArtifactPath
    $previous = $env:WINDOWS_REMOTE_ARTIFACT_DIR
    $frontend = @($script:Owned | Where-Object { $_.Label -eq 'Remote React' })
    if ($frontend.Count -ne 1) { throw 'Exactly one owned remote frontend is required.' }
    try {
        Stop-RemoteFrontendChild $frontend[0]
        [void](Start-RemoteFrontendChild $validated.Path)
        Publish-FrontendControlState
        return @{ status = 'updated'; artifact = $validated.Identity }
    }
    catch {
        $errorText = $_.Exception.Message
        try {
            foreach ($entry in @($script:Owned | Where-Object { $_.Label -eq 'Remote React' })) { Stop-RemoteFrontendChild $entry }
            [void](Start-RemoteFrontendChild $previous)
            Publish-FrontendControlState
            return @{ status = 'rolled_back'; error = $errorText }
        }
        catch {
            # Keep supervising unrelated children even if both frontend starts failed.
            foreach ($entry in @($script:Owned | Where-Object { $_.Label -eq 'Remote React' })) {
                try { Stop-RemoteFrontendChild $entry } catch { }
            }
            return @{ status = 'failed'; error = $errorText; rollback_error = $_.Exception.Message }
        }
    }
}

function Receive-FrontendControlRequest {
    $directory = Get-FrontendControlDirectory
    $path = Join-Path $directory 'request.json'
    if (-not (Test-Path -LiteralPath $path)) { return }
    try { $request = Get-Content -Raw -LiteralPath $path | ConvertFrom-Json } catch { return }
    if ($request.id -notmatch '^[0-9a-f]{32}$' -or $request.id -eq $script:LastFrontendRequest) { return }
    $script:LastFrontendRequest = $request.id
    try {
        if ($request.run_id -ne $script:RunId -or $request.operation -notin @('restart_frontend', 'stop_runtime')) {
            throw 'Frontend request does not belong to this supervisor.'
        }
        if ($request.operation -eq 'stop_runtime') {
            $script:StopRequested = $true
            Publish-FrontendControlState -RuntimeStatus 'stopping'
            $result = @{ status = 'stopping' }
        }
        else { $result = Invoke-RemoteFrontendRestart $request.artifact_path }
    }
    catch { $result = @{ status = 'rejected'; error = $_.Exception.Message } }
    $result.id = $request.id
    Write-FrontendControlJson (Join-Path $directory ($request.id + '.response.json')) $result
    Write-RuntimeEvent -Event 'frontend_update' -Label 'Remote React' -Detail $result.status
}

function Submit-RuntimeStop {
    # Share the existing run-bound maintenance channel and ownership checks.
    $directory = Get-FrontendControlDirectory
    [void][IO.Directory]::CreateDirectory($directory)
    $lock = [IO.File]::Open((Join-Path $directory 'update.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    try {
        $state = Get-FrontendUpdateSupervisor
        $owner = Get-ProcessSnapshot ([int]$state.supervisor_pid)
        if ($owner.State -ne 'alive' -or -not (Test-SameProcessIdentity ([pscustomobject]@{StartTime=[datetime]$state.supervisor_start_time}) $owner)) {
            throw 'Supervisor identity changed; no stop request was sent.'
        }
        Write-FrontendControlJson (Join-Path $directory 'request.json') @{
            id=[guid]::NewGuid().ToString('N');run_id=$state.run_id;operation='stop_runtime'
        }
        if (-not $owner.Process.WaitForExit(180000)) { throw 'Runtime stop is still pending; do not start another host.' }
        $finished = Get-Content -Raw -LiteralPath (Join-Path $directory 'state.json') | ConvertFrom-Json
        if ($finished.run_id -ne $state.run_id -or $finished.runtime_status -ne 'stopped') {
            throw 'Runtime cleanup was not confirmed; do not start another host.'
        }
        Write-Host '[Ready] Owned API, frontend, workers and Tunnel stopped. Database and Redis preserved.'
    }
    finally { $lock.Dispose() }
}

function Assert-LegacyRuntimeRoot {
    param($Root, [int]$LegacyPid)
    $snapshot = Get-ProcessSnapshot ([int]$Root.pid)
    if ($snapshot.State -ne 'alive' -or -not (Test-SameProcessIdentity ([pscustomobject]@{StartTime=[datetime]$Root.start_time}) $snapshot)) {
        throw 'A runtime child identity changed; adoption stopped.'
    }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($Root.pid)" -ErrorAction Stop
    $roles = @{
        'FastAPI' = 'uvicorn api.main:app'; 'Remote React' = 'uvicorn scripts.windows_remote_runtime:create_app'
        'LINE Worker' = '-m scripts.run_line_worker'; 'Runtime Monitor' = '-m scripts.run_service_monitor'
        'Durable Background Worker' = '-m scripts.run_durable_job_worker'
        'Incident Maintenance Worker' = '-m scripts.run_incident_worker'
        'Knowledge Retrieval Worker' = '-m scripts.run_knowledge_worker'; 'Cloudflare Tunnel' = '--token-file'
    }
    if (-not $roles.ContainsKey([string]$Root.label) -or $process.ParentProcessId -ne $LegacyPid -or
        -not $process.CommandLine.Contains($roles[[string]$Root.label])) { throw 'Unexpected runtime child; adoption stopped.' }
    return [pscustomobject]@{Label=$Root.label; Pid=[int]$Root.pid; StartTime=$snapshot.StartTime; Process=$snapshot.Process; ExitCode=$null}
}

function Initialize-AdoptedRemoteRuntime {
    param([string]$StatePath)
    # Until the legacy supervisor exits, failure must never clean up its children.
    $script:SkipRuntimeCleanup = $true
    $state = Get-Content -Raw -LiteralPath $StatePath | ConvertFrom-Json
    if ($state.contract -ne 'windows-frontend-adoption/v1' -or $state.project_root -ne $ProjectRoot -or
        $state.api_port -ne $ApiPort -or $state.react_port -ne $ReactPort) { throw 'Adoption binding mismatch.' }
    [void](Assert-FrontendArtifact $state.artifact_path)
    $roots = @($state.roots | ForEach-Object { Assert-LegacyRuntimeRoot $_ ([int]$state.legacy.pid) })
    $labels = @($roots.Label)
    if ($roots.Count -lt 2 -or @($labels | Select-Object -Unique).Count -ne $roots.Count -or
        $labels -notcontains 'FastAPI' -or $labels -notcontains 'Remote React') { throw 'Incomplete runtime adoption.' }
    $legacy = Get-ProcessSnapshot ([int]$state.legacy.pid)
    if ($legacy.State -ne 'alive' -or -not (Test-SameProcessIdentity ([pscustomobject]@{StartTime=[datetime]$state.legacy.start_time}) $legacy)) { throw 'Legacy supervisor identity changed.' }
    Write-FrontendControlJson ($StatePath + '.ready.json') @{pid=$PID; start_time=(Get-Process -Id $PID).StartTime.ToUniversalTime().ToString('o')}
    if (-not $legacy.Process.WaitForExit(30000)) { throw 'Legacy supervisor handoff was not committed.' }
    foreach ($root in $state.roots) { [void](Assert-LegacyRuntimeRoot $root ([int]$state.legacy.pid)) }
    foreach ($entry in $roots) {
        $script:Owned.Add($entry)
        [void](Add-Identity -ProcessId $entry.Pid -StartTime $entry.StartTime -Label $entry.Label -RootPid $entry.Pid -IsRoot $true -Process $entry.Process)
    }
    $env:WINDOWS_REMOTE_ARTIFACT_DIR = $state.artifact_path
    $script:SkipRuntimeCleanup = $false
    Refresh-OwnedIdentityRegistry
    Write-RuntimeEvent -Event 'runtime_adopted' -Detail 'existing runtime children preserved; no DB or worker startup'
}

function Get-FrontendUpdateSupervisor {
    $directory = Get-FrontendControlDirectory
    $statePath = Join-Path $directory 'state.json'
    if (Test-Path -LiteralPath $statePath) {
        $state = Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json
        $snapshot = Get-ProcessSnapshot ([int]$state.supervisor_pid)
        if ($state.contract -eq 'windows-frontend-control/v1' -and $state.project_root -eq $ProjectRoot -and
            $state.api_port -eq $ApiPort -and $state.react_port -eq $ReactPort -and
            $snapshot.State -eq 'alive' -and (Test-SameProcessIdentity ([pscustomobject]@{StartTime=[datetime]$state.supervisor_start_time}) $snapshot)) {
            if ($state.controller_digest -eq $script:FrontendControllerDigest) { return $state }
            # A live supervisor can still have older function definitions loaded
            # after source files change. Upgrade that verified owner by handoff.
        }
        else { throw 'Frontend control state is stale; refusing to guess a runtime owner.' }
    }
    # One-time upgrade of the already-running legacy supervisor. Only its own
    # direct, role-checked children are eligible; no service is restarted here.
    $listener = @(Get-NetTCPConnection -State Listen -LocalPort $ReactPort -ErrorAction Stop | Where-Object LocalAddress -eq '127.0.0.1')
    if ($listener.Count -ne 1) { throw 'Expected one loopback frontend listener.' }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener[0].OwningProcess)"
    $legacy = $null
    for ($depth=0; $depth -lt 4 -and $process; $depth++) {
        if ($process.CommandLine -like '*supervise_local_runtime.ps1*' -and $process.CommandLine.Contains($ProjectRoot)) { $legacy=$process; break }
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($process.ParentProcessId)"
    }
    if (-not $legacy) { throw 'No project-owned legacy supervisor was found.' }
    $roles = @{
        'uvicorn api.main:app'='FastAPI'; 'uvicorn scripts.windows_remote_runtime:create_app'='Remote React'
        '-m scripts.run_line_worker'='LINE Worker'; '-m scripts.run_service_monitor'='Runtime Monitor'
        '-m scripts.run_durable_job_worker'='Durable Background Worker'; '-m scripts.run_incident_worker'='Incident Maintenance Worker'
        '-m scripts.run_knowledge_worker'='Knowledge Retrieval Worker'; '--token-file'='Cloudflare Tunnel'
    }
    $roots = @()
    foreach ($child in @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$($legacy.ProcessId)")) {
        $label = @($roles.Keys | Where-Object { $child.CommandLine -and $child.CommandLine.Contains($_) })
        if ($label.Count -ne 1) { throw 'Unknown legacy child; no supervisor was stopped.' }
        $snapshot = Get-ProcessSnapshot ([int]$child.ProcessId)
        if ($snapshot.State -ne 'alive') { throw 'Legacy child is not verifiably alive.' }
        $roots += @{label=$roles[$label[0]]; pid=[int]$child.ProcessId; start_time=$snapshot.StartTime.ToUniversalTime().ToString('o')}
    }
    $current = (Invoke-WebRequest -Uri "http://127.0.0.1:$ReactPort/test/artifact-manifest.json" -UseBasicParsing -TimeoutSec 5).Content | ConvertFrom-Json
    $artifact = @(Get-ChildItem -LiteralPath (Join-Path $ProjectRoot 'scratch\windows-remote') -Directory -Filter 'artifact-*' | Where-Object {
        $manifest = Join-Path $_.FullName 'artifact-manifest.json'
        (Test-Path -LiteralPath $manifest) -and (Get-Content -Raw -LiteralPath $manifest | ConvertFrom-Json).artifact_digest -eq $current.artifact_digest
    } | Select-Object -First 1)
    if ($artifact.Count -ne 1) { throw 'The current rollback artifact was not found.' }
    $legacySnapshot = Get-ProcessSnapshot ([int]$legacy.ProcessId)
    $adoptionPath = Join-Path $directory ('adoption-' + [guid]::NewGuid().ToString('N') + '.json')
    Write-FrontendControlJson $adoptionPath @{
        contract='windows-frontend-adoption/v1'; project_root=$ProjectRoot; api_port=$ApiPort; react_port=$ReactPort
        legacy=@{pid=[int]$legacy.ProcessId; start_time=$legacySnapshot.StartTime.ToUniversalTime().ToString('o')}
        roots=$roots; artifact_path=$artifact[0].FullName
    }
    $supervisorPath = Join-Path $ProjectRoot 'scripts\launchers\supervise_local_runtime.ps1'
    $command = "& '" + $supervisorPath.Replace("'", "''") + "' -ProjectRoot '" + $ProjectRoot.Replace("'", "''") +
        "' -PythonPath '" + $PythonPath.Replace("'", "''") + "' -ApiPort $ApiPort -ReactPort $ReactPort -AdoptFrontendState '" +
        $adoptionPath.Replace("'", "''") + "' *> '" + ($adoptionPath+'.stdout.log').Replace("'", "''") + "'"
    # ShellExecute detaches the lifetime and inherited pipe handles from this
    # short-lived updater; stream redirection occurs inside the new PowerShell.
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = Join-Path $PSHOME 'powershell.exe'
    $start.Arguments = '-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "' + $command + '"'
    $start.WorkingDirectory = $ProjectRoot
    $start.UseShellExecute = $true
    $start.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    $replacement = [Diagnostics.Process]::Start($start)
    $readyPath = $adoptionPath + '.ready.json'
    for ($attempt=0; $attempt -lt 120 -and -not (Test-Path -LiteralPath $readyPath); $attempt++) {
        if ($replacement.HasExited) { throw 'Replacement supervisor rejected handoff; current runtime was retained.' }
        Start-Sleep -Milliseconds 250
    }
    if (-not (Test-Path -LiteralPath $readyPath)) { throw 'Replacement supervisor did not become ready; current runtime was retained.' }
    $ready = Get-Content -Raw -LiteralPath $readyPath | ConvertFrom-Json
    if ($ready.pid -ne $replacement.Id -or ([datetime]$ready.start_time).ToUniversalTime().Ticks -ne $replacement.StartTime.ToUniversalTime().Ticks) { throw 'Replacement supervisor identity mismatch.' }
    $verified = Get-ProcessSnapshot ([int]$legacy.ProcessId)
    if ($verified.State -ne 'alive' -or -not (Test-SameProcessIdentity ([pscustomobject]@{StartTime=$legacySnapshot.StartTime}) $verified)) { throw 'Legacy supervisor changed before handoff.' }
    # Terminate only this verified PowerShell process. Its children remain alive;
    # the prepared replacement assumes their existing PID/start-time identities.
    $verified.Process.Kill()
    [void]$verified.Process.WaitForExit(5000)
    for ($attempt=0; $attempt -lt 120; $attempt++) {
        if (Test-Path -LiteralPath $statePath) {
            $state = Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json
            if ($state.supervisor_pid -eq $replacement.Id) { return $state }
        }
        if ($replacement.HasExited) { throw "Supervisor handoff needs recovery from $adoptionPath; preserved children were not intentionally stopped." }
        Start-Sleep -Milliseconds 250
    }
    throw 'Supervisor handoff acknowledgement timed out.'
}

function Submit-FrontendUpdate {
    param([string]$ArtifactPath)
    $validated = Assert-FrontendArtifact $ArtifactPath
    $directory = Get-FrontendControlDirectory
    [void][IO.Directory]::CreateDirectory($directory)
    $lock = [IO.File]::Open((Join-Path $directory 'update.lock'), [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    try {
        $state = Get-FrontendUpdateSupervisor
        $id = [guid]::NewGuid().ToString('N')
        Write-FrontendControlJson (Join-Path $directory 'request.json') @{id=$id;run_id=$state.run_id;operation='restart_frontend';artifact_path=$validated.Path}
        $responsePath = Join-Path $directory ($id + '.response.json')
        for ($attempt=0; $attempt -lt 480; $attempt++) {
            if (Test-Path -LiteralPath $responsePath) {
                $response = Get-Content -Raw -LiteralPath $responsePath | ConvertFrom-Json
                if ($response.id -ne $id) { throw 'Frontend response identity mismatch.' }
                if ($response.status -ne 'updated') { throw "Frontend update $($response.status): $($response.error)" }
                Write-Host "[Ready] Frontend updated on 127.0.0.1:$ReactPort; API, workers and Tunnel were not restarted."
                return
            }
            Start-Sleep -Milliseconds 250
        }
        throw 'Frontend update acknowledgement timed out; inspect the matching request before retrying.'
    }
    finally { $lock.Dispose() }
}
