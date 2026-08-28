"""
File: test_launcher_dry_run.py
Description: 驗證各操作 launcher 的唯讀 preflight 與服務啟動前 readiness 邊界。
"""

from pathlib import Path

from scripts.launcher_preflight import PROFILE_REQUIREMENTS, inspect_profile


ROOT = Path(__file__).resolve().parents[1]
LAUNCHERS = ROOT / "scripts" / "launchers"


def _source(name: str) -> str:
    return (LAUNCHERS / name).read_text(encoding="utf-8")


def test_profiles_report_no_side_effects() -> None:
    for profile in ("artifact-runtime", "dual-run", "local-windows", "local-unix", "admin-no-auth", "database-update", "database-reset", "ngrok-development", "line-worker"):
        assert inspect_profile(profile)["side_effects"] == "none"


def test_batch_and_shell_launchers_route_dry_run_to_preflight() -> None:
    expected_profiles = {
        "start_local_development.bat": "local-windows",
        "start_local_development.sh": "local-unix",
        "update_local_database.bat": "database-update",
        "reset_DB.bat": "database-reset",
    }
    for name, profile in expected_profiles.items():
        source = _source(name)
        assert "--dry-run" in source
        assert f"--profile {profile}" in source
        if name.startswith("start_local_development"):
            assert "--profile dual-run" in source
        else:
            assert "--profile dual-run" not in source


def test_batch_dry_run_propagates_a_blocked_preflight() -> None:
    for name in (
        "start_local_development.bat",
        "update_local_database.bat",
        "reset_DB.bat",
    ):
        dry_run_block = _source(name).split('=="--dry-run"', maxsplit=1)[1]
        captures_exit = 'set "DRY_RUN_EXIT=!ERRORLEVEL!"' in dry_run_block
        assert (
            captures_exit and "exit /b !DRY_RUN_EXIT!" in dry_run_block
        ) or "exit /b !ERRORLEVEL!" in dry_run_block


def test_windows_launcher_exposes_controlled_smoke_test() -> None:
    source = _source("start_local_development.bat")

    assert 'if /I "%~1"=="--smoke-test" goto :SMOKE_TEST' in source
    smoke_block = source.rsplit("\n:SMOKE_TEST", maxsplit=1)[1]
    assert "scripts.smoke_local_development_launcher" in smoke_block
    assert "docker-compose up -d" not in smoke_block
    assert "scripts/wait_for_db.py" not in smoke_block
    assert "scripts.update_local_database" not in smoke_block
    assert "exit /b !ERRORLEVEL!" in smoke_block


def test_launchers_gate_artifact_runtime_before_children_and_probe_after_api() -> None:
    for name in ("start_local_development.bat", "start_local_development.sh"):
        source = _source(name)
        assert "--profile artifact-runtime" in source
        assert "--react-admin-health-check" in source
        assert "--artifact-runtime-smoke" in source
        assert source.index("--profile artifact-runtime") < source.index("api.main:app")


def test_dual_run_preflight_freezes_api_and_react_get_only_services() -> None:
    report = inspect_profile("dual-run")

    assert report["ports"] == [8000, 5173]
    assert report["startup_order"] == ["api", "react"]
    assert all("streamlit" not in command for command in report["planned_commands"])
    assert "streamlit" not in report["health_predicates"]
    assert "streamlit" in report["disabled"]
    assert "monitor" in report["disabled"]
    assert "consumer/provider workers" in report["disabled"]
    assert report["side_effects"] == "none"


def test_windows_launcher_guards_optional_line_worker_configuration() -> None:
    source = _source("start_local_development.bat") + _source("supervise_local_runtime.ps1")

    assert "scripts.launcher_preflight --profile line-worker" in source
    assert "Skipping LINE Worker" in source


def test_windows_launcher_reuses_existing_mysql_container_without_recreate() -> None:
    source = _source("start_local_development.bat")

    assert 'docker inspect --format "{{.State.Running}}" "!MYSQL_CONTAINER!"' in source
    assert 'docker start "!MYSQL_CONTAINER!"' in source
    assert "docker-compose up -d redis" in source
    assert "docker-compose up -d db" in source
    assert "\ndocker-compose up -d\n" not in source


def test_windows_launcher_requires_current_schema_before_starting_services() -> None:
    source = _source("start_local_development.bat")
    readiness = '"%PY%" -m scripts.update_local_database --require-current'

    assert readiness in source
    assert source.index(readiness) < source.index("supervise_local_runtime.ps1")


def test_windows_launcher_delegates_runtime_ownership_after_current_gate() -> None:
    source = _source("start_local_development.bat")
    supervisor = _source("supervise_local_runtime.ps1")
    readiness = '"%PY%" -m scripts.update_local_database --require-current'

    assert "supervise_local_runtime.ps1" in source
    assert source.index(readiness) < source.index("supervise_local_runtime.ps1")
    assert "-ApiPort 8000 -ReactPort 5173" in source
    assert 'start "FastAPI Server" cmd' not in source
    assert "cmd /k" not in source
    assert "Start-Process" in supervisor
    assert "finally" in supervisor


def test_windows_supervisor_has_readiness_survival_and_scoped_cleanup_contract() -> None:
    source = _source("supervise_local_runtime.ps1")

    assert source.isascii()  # Windows PowerShell 5.1 treats UTF-8 without BOM as ANSI.
    assert "<#" in source and "#>" in source
    assert "<##" not in source and "##>" not in source
    assert "Invoke-WebRequest" in source
    assert "/health" in source
    assert "/admin/" in source
    assert "Get-CimInstance -ClassName Win32_Process" in source
    assert "Stop-Process -Id $id -Force" in source
    assert 'Get-Command "npm.cmd" -CommandType Application' in source
    assert 'Get-Command "docker.exe" -CommandType Application' in source
    assert '"VITE_DEV_API_TARGET=http://host.docker.internal:$ApiPort"' in source
    assert '"node:lts", "npm", "run", "dev"' in source
    assert '"--rm", "--name", $script:ReactContainerName' in source
    assert 'dockerArguments += @("-e", "VITE_ACCESS_CONTROL_PROFILE=' in source
    assert 'Stop-OwnedReactContainer' in source
    assert 'rm --force $script:ReactContainerName' in source
    assert '"-it"' not in source
    assert "Get-DescendantIds -RootIds $activeRoots.ToArray() -Processes $treeSnapshot.Processes" in source
    assert 'event = "runtime_ready"' in source or '"runtime_ready"' in source
    assert '"survival_failed"' in source
    assert '"cleanup_complete"' in source
    for module in (
        "api.main:app",
        "scripts.run_service_monitor",
        "scripts.run_durable_job_worker",
        "scripts.run_incident_worker",
    ):
        assert module in source


def test_windows_supervisor_preserves_optional_worker_and_profile_semantics() -> None:
    source = _source("supervise_local_runtime.ps1")

    assert "REACT_ADMIN_RUNTIME_PROFILE" in source
    assert "--react-admin-health-check" in source
    assert "--profile line-worker" in source
    assert "RUNTIME_EVENT" in source  # optional workers emit structured skipped events
    assert "KNOWLEDGE_RETRIEVAL_RUNTIME_ENABLED" in source
    assert '"LINE Worker"' in source
    assert '"Knowledge Retrieval Worker"' in source


def test_windows_supervisor_registry_is_immutable_and_refreshes_orphan_descendants() -> None:
    source = _source("supervise_local_runtime.ps1")

    assert "IdentityRegistry" in source
    assert "StartTime" in source
    assert "Process = $process" in source
    assert "ExitCode = $exitCode" in source
    assert "Refresh-OwnedIdentityRegistry" in source
    assert "Keep the immutable root identity" in source
    assert "immediate PID + immutable StartTime check" in source


def test_windows_supervisor_never_discovers_from_dead_or_reused_root_pid() -> None:
    source = _source("supervise_local_runtime.ps1")

    assert "activeRoots" in source
    assert "Get-ProcessTreeSnapshot" in source
    assert "CreationDate" in source
    assert "sameCreation" in source
    assert "treeSnapshot.Processes" in source
    assert source.count("Get-CimInstance -ClassName Win32_Process") == 1
    assert "record.CreationDate" in source
    assert "Test-SameProcessIdentity -Entry $root -Snapshot $snapshot" in source
    assert "Get-DescendantIds -RootIds $activeRoots.ToArray() -Processes $treeSnapshot.Processes" in source
    assert "$roots = @($script:Owned" not in source
    assert "if ($activeRoots.Count -eq 0) { return }" in source
    assert "CleanupUnknown" in source
    assert "UnknownRootPids" in source
    assert '"cleanup_unknown"' in source


def test_windows_supervisor_cleanup_reports_failures_without_false_completion() -> None:
    source = _source("supervise_local_runtime.ps1")

    assert '"cleanup_failed"' in source
    assert "failed_pids" in source
    assert "stopped_pids" in source
    assert "skipped_pids" in source
    assert "if ($failedIds.Count -gt 0)" in source
    assert source.index('"cleanup_failed"') < source.rindex('"cleanup_complete"')
    assert "child_exit_codes" in source
    assert 'State = "unknown"' in source
    assert 'if ($notFound) { "exited" } else { "unknown" }' in source
    assert 'if ($current.State -eq "unknown")' in source
    assert 'if ($current.State -eq "exited")' in source


def test_no_auth_configuration_writes_atomic_utf8_without_bom() -> None:
    source = _source("configure_local_admin_no_auth.ps1")

    assert "UTF8Encoding]::new($false)" in source
    assert "WriteAllText($temporaryEnvFile" in source
    assert "File]::Replace($temporaryEnvFile, $envFile" in source
    assert "File]::Move($temporaryEnvFile, $envFile)" in source
    assert "Remove-Item -LiteralPath $temporaryEnvFile" in source


def test_windows_supervisor_reacts_only_to_html_root_and_normalizes_true_flags() -> None:
    source = _source("supervise_local_runtime.ps1")

    assert "RequireHtmlRoot" in source
    assert "response.Content" in source
    assert "id\\s*=\\s*[\"'']root[\"'']" in source
    assert "Trim().ToLowerInvariant() -eq \"true\"" in source


def test_unix_launcher_requires_current_schema_and_guards_optional_workers() -> None:
    source = _source("start_local_development.sh")
    readiness = (
        '"$PY" -m scripts.update_local_database --require-current '
        '--database-port "$DB_PORT"'
    )

    assert readiness in source
    assert source.index(readiness) < source.index("api.main:app")
    assert source.index("--profile line-worker") < source.index("scripts.run_line_worker")
    assert source.index("KNOWLEDGE_RETRIEVAL_RUNTIME_ENABLED=true") < source.index(
        "scripts.run_knowledge_worker"
    )


def test_windows_launcher_does_not_claim_an_unstarted_file_watcher() -> None:
    assert "File Watcher: Monitoring" not in _source("start_local_development.bat")


def test_configuration_and_scheduler_scripts_have_non_mutating_dry_run() -> None:
    configure = _source("configure_local_admin_no_auth.ps1")
    status = _source("get_durable_job_worker_task_status.ps1")
    uninstall = _source("uninstall_durable_job_worker_task.ps1")

    assert "[switch]$DryRun" in configure
    assert configure.index("if ($DryRun)") < configure.index("WriteAllText")
    assert "no task was queried" in status
    assert "no task was queried or removed" in uninstall


def test_no_auth_configuration_persists_backend_bypass_profile() -> None:
    configure = _source("configure_local_admin_no_auth.ps1")

    assert 'ACCESS_CONTROL_PROFILE = "local_bypass"' in configure
    assert 'ACCESS_CONTROL_PROFILE=$($desired[' in configure


def test_composed_no_auth_launcher_dry_runs_both_steps() -> None:
    source = _source("start_local_development_no_auth.bat")

    assert "configure_local_admin_no_auth.ps1\" -DryRun" in source
    assert "start_local_development.bat\" --dry-run" in source
    assert 'set "ACCESS_CONTROL_PROFILE=local_bypass"' in source
    assert 'set "VITE_ACCESS_CONTROL_PROFILE=local_bypass"' in source
    assert source.index('set "VITE_ACCESS_CONTROL_PROFILE=local_bypass"') < source.index(
        'call "%~dp0start_local_development.bat"'
    )


def test_unix_no_auth_launcher_only_sets_profile_and_delegates() -> None:
    source = _source("start_local_development_no_auth.sh")

    assert "export APP_ENV=development" in source
    assert "export ACCESS_CONTROL_PROFILE=local_bypass" in source
    assert "export ENABLE_ADMIN_AUTH=false" in source
    assert "export VITE_ACCESS_CONTROL_PROFILE=local_bypass" in source
    assert 'exec "$SCRIPT_DIR/start_local_development.sh" "$@"' in source
    assert "scripts.update_local_database" not in source
    assert "api.main:app" not in source
    assert "npm run dev" not in source


def test_unix_launcher_uses_configured_database_port_and_owned_cleanup() -> None:
    source = _source("start_local_development.sh")
    assert 'export DB_PORT="${DB_PORT:-3306}"' in source
    assert "choose_db_port" not in source
    assert "lsof" not in PROFILE_REQUIREMENTS["local-unix"]["commands"]
    assert 'scripts/wait_for_db.py --port' not in source
    assert "trap cleanup_owned EXIT" in source
    assert "trap 'exit 130' INT" in source
    assert "trap 'exit 143' TERM" in source
    assert 'kill -TERM -- "-$pid"' in source
    assert 'require_owned_process "Runtime Monitor"' in source
    assert 'require_owned_process "Durable Background Worker"' in source
    assert 'require_owned_process "Incident Maintenance Worker"' in source


def test_unix_launcher_reuses_existing_mysql_container_without_recreate() -> None:
    source = _source("start_local_development.sh")

    assert 'docker inspect --format "{{.State.Running}}" "$MYSQL_CONTAINER"' in source
    assert 'docker start "$MYSQL_CONTAINER"' in source
    assert "docker compose up -d db" in source
    assert "docker compose up -d redis" in source
    assert "\ndocker compose up -d\n" not in source


def test_unix_no_auth_launcher_delegates_to_current_gate_before_children() -> None:
    wrapper = _source("start_local_development_no_auth.sh")
    canonical = _source("start_local_development.sh")
    readiness = (
        '"$PY" -m scripts.update_local_database --require-current '
        '--database-port "$DB_PORT"'
    )

    assert 'exec "$SCRIPT_DIR/start_local_development.sh" "$@"' in wrapper
    assert canonical.index(readiness) < canonical.index("api.main:app")


def test_ngrok_launcher_routes_dry_run_before_supervision() -> None:
    source = _source("start_fastapi_ngrok.py")

    assert 'sys.argv[1:] == ["--dry-run"]' in source
    assert 'run_profile("ngrok-development")' in source
