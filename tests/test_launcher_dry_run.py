"""
File: test_launcher_dry_run.py
Description: 驗證各操作 launcher 的唯讀 preflight 與服務啟動前 readiness 邊界。
"""

from pathlib import Path

from scripts.launcher_preflight import inspect_profile


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
        assert 'set "DRY_RUN_EXIT=!ERRORLEVEL!"' in dry_run_block
        assert "exit /b !DRY_RUN_EXIT!" in dry_run_block


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


def test_dual_run_preflight_freezes_three_get_only_services() -> None:
    report = inspect_profile("dual-run")

    assert report["ports"] == [8000, 8501, 5173]
    assert report["startup_order"] == ["api", "streamlit", "react"]
    assert "monitor" in report["disabled"]
    assert "consumer/provider workers" in report["disabled"]
    assert report["side_effects"] == "none"


def test_windows_launcher_guards_optional_line_worker_configuration() -> None:
    source = _source("start_local_development.bat")

    assert "scripts.launcher_preflight --profile line-worker" in source
    assert "Skipping LINE Worker" in source


def test_windows_launcher_requires_current_schema_before_starting_services() -> None:
    source = _source("start_local_development.bat")
    readiness = '"%PY%" -m scripts.update_local_database --require-current'

    assert readiness in source
    assert source.index(readiness) < source.index('start "FastAPI Server"')


def test_configuration_and_scheduler_scripts_have_non_mutating_dry_run() -> None:
    configure = _source("configure_local_admin_no_auth.ps1")
    status = _source("get_durable_job_worker_task_status.ps1")
    uninstall = _source("uninstall_durable_job_worker_task.ps1")

    assert "[switch]$DryRun" in configure
    assert configure.index("if ($DryRun)") < configure.index("Set-Content")
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


def test_ngrok_launcher_routes_dry_run_before_supervision() -> None:
    source = _source("start_fastapi_ngrok.py")

    assert 'sys.argv[1:] == ["--dry-run"]' in source
    assert 'run_profile("ngrok-development")' in source
