"""Static contracts for the owned Windows runtime supervisor."""

from pathlib import Path
import json
import os
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[7]
SUPERVISOR = ROOT / "scripts" / "launchers" / "supervise_local_runtime.ps1"
WINDOWS_LAUNCHER = ROOT / "scripts" / "launchers" / "start_local_development.bat"


def test_supervisor_owns_one_process_scoped_internal_service_key() -> None:
    supervisor = SUPERVISOR.read_text(encoding="utf-8")
    launcher = WINDOWS_LAUNCHER.read_text(encoding="utf-8")

    initialize = supervisor.index("function Initialize-InternalServiceSharedKey")
    process_scope = supervisor.index("[EnvironmentVariableTarget]::Process", initialize)
    dotenv_lookup = supervisor.index('Join-Path $ProjectRoot ".env"', process_scope)
    assignment = supervisor.index("$env:INTERNAL_SERVICE_SHARED_KEY", dotenv_lookup)
    supervision_start = supervisor.index(
        'Write-RuntimeEvent -Event "supervision_started"'
    )

    assert initialize < process_scope < dotenv_lookup < assignment < supervision_start
    assert ":ENSURE_INTERNAL_SERVICE_KEY" not in launcher
    assert "INTERNAL_SERVICE_SHARED_KEY=%%K" not in launcher


def test_private_auth_handshake_precedes_every_worker() -> None:
    supervisor = SUPERVISOR.read_text(encoding="utf-8")

    api_ready = supervisor.index(
        'Wait-HttpReady -Url "http://127.0.0.1:$ApiPort/health" -Label "FastAPI"'
    )
    auth_check = supervisor.index("Assert-PrivateApiAuthentication", api_ready)
    react_start = supervisor.index('Start-Owned -Label "React/Vite"', auth_check)
    line_start = supervisor.index('Start-Owned -Label "LINE Worker"', auth_check)

    assert api_ready < auth_check < react_start < line_start


def test_windows_launcher_keeps_supervision_failure_visible() -> None:
    launcher = WINDOWS_LAUNCHER.read_text(encoding="utf-8")

    failure = launcher.index(
        "[Error] Local runtime supervision stopped with exit code"
    )
    pause = launcher.index("pause", failure)
    failure_exit = launcher.index("exit /b !SUPERVISOR_EXIT!", failure)

    assert failure < pause < failure_exit


@pytest.mark.skipif(os.name != "nt", reason="Windows CIM process identity")
def test_real_cim_dates_match_native_identity_without_weakening_stop_checks() -> None:
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    script = r'''
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:SUPERVISOR_TEST_PATH, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Supervisor syntax error' }
$functions = $ast.FindAll({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst]}, $false)
foreach ($function in $functions) { Invoke-Expression $function.Extent.Text }
$native = (Get-Process -Id $PID).StartTime.ToUniversalTime()
$tree = Get-ProcessTreeSnapshot
$record = @($tree.Processes | Where-Object { $_.Pid -eq $PID })[0]
if ($record.State -ne 'known') { throw 'Real CIM DateTime was not captured' }
if (-not (Test-CimCreationTime $record.CreationDate $native)) { throw 'CIM/native precision mismatch' }
$cim = [datetime]::new($native.Ticks - ($native.Ticks % 10), [DateTimeKind]::Utc)
if (-not (Test-CimCreationTime $cim $cim.AddTicks(7))) { throw 'Sub-microsecond precision lost' }
if (Test-CimCreationTime $cim $cim.AddTicks(10)) { throw 'Different CIM timestamp accepted' }
if (Test-SameProcessIdentity ([pscustomobject]@{StartTime=$cim}) ([pscustomobject]@{StartTime=$cim.AddTicks(7)})) { throw 'Native stop check was weakened' }
Write-Output 'PASS'
'''
    result = subprocess.run(
        [str(powershell), "-NoProfile", "-Command", script],
        env={**os.environ, "SUPERVISOR_TEST_PATH": str(SUPERVISOR)},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "PASS"


@pytest.mark.skipif(os.name != "nt", reason="Windows launcher branching")
@pytest.mark.parametrize("profile,host_npm", [
    ("local_bypass", False), ("local_bypass", True),
    ("local_auth", False), ("local_auth", True),
])
def test_real_react_launch_branch_uses_gateway_only_for_no_npm_bypass(
    tmp_path: Path, profile: str, host_npm: bool,
) -> None:
    fake_docker = tmp_path / "docker_stub.ps1"
    fake_docker.write_text(
        "if ($args[0] -eq 'port') { Write-Output '127.0.0.1:55173' }\n"
        "$global:LASTEXITCODE = 0\n", encoding="utf-8",
    )
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    script = r'''
$ErrorActionPreference = 'Stop'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:SUPERVISOR_TEST_PATH, [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw 'Supervisor syntax error' }
foreach ($function in $ast.FindAll({param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst]}, $false)) {
    Invoke-Expression $function.Extent.Text
}
$script:calls = [System.Collections.Generic.List[object]]::new()
$ProjectRoot = 'D:\test project'
$PythonPath = 'test-python.exe'
$ApiPort = 8000; $ReactPort = 5173; $script:RunId = 'test-owned'
function Get-Command {
    param($Name, $CommandType, $ErrorAction)
    if ($Name -eq 'npm.cmd' -and $env:HOST_NPM_TEST -eq '1') { return [pscustomobject]@{Source='test-npm.cmd'} }
    if ($Name -eq 'docker.exe') { return [pscustomobject]@{Source=$env:DOCKER_STUB_TEST_PATH} }
    return $null
}
function Start-Owned {
    param($Label, $FilePath, [string[]]$ArgumentList, $WorkingDirectory)
    $script:calls.Add([pscustomobject]@{Kind='start';Label=$Label;Arguments=$ArgumentList})
    return [pscustomobject]@{Label=$Label}
}
function Wait-HttpReady {
    param($Url, $Label, [switch]$RequireHtmlRoot)
    $script:calls.Add([pscustomobject]@{Kind='ready';Label=$Label;Url=$Url})
}
function Test-OwnedAlive { param($Entry); return $true }
function Start-Sleep { throw 'Unexpected port-discovery retry' }
$source = $ast.Extent.Text
$start = $source.IndexOf('    $uiRoot = Join-Path')
$end = $source.IndexOf('    Refresh-OwnedIdentityRegistry', $start)
Invoke-Expression $source.Substring($start, $end - $start)
ConvertTo-Json -InputObject @($script:calls) -Depth 5 -Compress
'''
    result = subprocess.run(
        [str(powershell), "-NoProfile", "-Command", script],
        env={**os.environ, "SUPERVISOR_TEST_PATH": str(SUPERVISOR),
             "DOCKER_STUB_TEST_PATH": str(fake_docker), "HOST_NPM_TEST": "1" if host_npm else "0",
             "ACCESS_CONTROL_PROFILE": profile, "VITE_ACCESS_CONTROL_PROFILE": profile},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    calls = json.loads(result.stdout)
    starts = [call for call in calls if call["Kind"] == "start"]
    needs_gateway = profile == "local_bypass" and not host_npm
    assert [call["Label"] for call in starts] == (
        ["React/Vite", "Local React Gateway"] if needs_gateway else ["React/Vite"]
    )
    if host_npm:
        assert starts[0]["Arguments"] == [
            "run", "dev", "--", "--host", "127.0.0.1", "--port", "5173", "--strictPort",
        ]
    else:
        arguments = starts[0]["Arguments"]
        assert arguments[arguments.index("-p") + 1] == (
            "127.0.0.1::5173" if needs_gateway else "127.0.0.1:5173:5173"
        )
        assert ("VITE_DEV_API_TARGET=http://host.docker.internal:8000" in arguments) == (not needs_gateway)
    if needs_gateway:
        assert starts[1]["Arguments"] == [
            "-m", "scripts.launchers.local_react_gateway", "--listen-port", "5173",
            "--api-port", "8000", "--vite-port", "55173",
        ]
        assert calls[1] == {"Kind": "ready", "Label": "Docker React/Vite", "Url": "http://127.0.0.1:55173/admin/"}
    assert calls[-1] == {"Kind": "ready", "Label": "React/Vite", "Url": "http://127.0.0.1:5173/admin/"}
