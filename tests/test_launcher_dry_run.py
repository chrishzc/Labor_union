"""Focused checks for the current FastAPI + React local launchers."""

from pathlib import Path

from scripts.launcher_preflight import PROFILE_REQUIREMENTS, inspect_profile


ROOT = Path(__file__).resolve().parents[1]
LAUNCHERS = ROOT / "scripts" / "launchers"


def _source(name: str) -> str:
    return (LAUNCHERS / name).read_text(encoding="utf-8")


def test_preflight_profiles_are_read_only_and_streamlit_free() -> None:
    assert set(PROFILE_REQUIREMENTS) == {
        "artifact-runtime",
        "dual-run",
        "local-windows",
        "local-unix",
        "admin-no-auth",
        "database-update",
        "database-reset",
        "line-worker",
    }
    for profile in PROFILE_REQUIREMENTS:
        report = inspect_profile(profile)
        assert report["side_effects"] == "none"
    assert "streamlit" not in repr(PROFILE_REQUIREMENTS).lower()
    assert "ui/app.py" not in repr(PROFILE_REQUIREMENTS)


def test_dual_run_is_exactly_fastapi_and_react() -> None:
    report = inspect_profile("dual-run")

    assert report["ports"] == [8000, 5173]
    assert report["startup_order"] == ["api", "react"]
    assert report["planned_commands"] == [
        "python -m uvicorn api.main:app --host 127.0.0.1 --port 8000",
        "npm run dev -- --host 127.0.0.1 --port 5173 --strictPort",
    ]
    assert set(report["health_predicates"]) == {"api", "react", "proxy"}
    assert "streamlit" not in repr(report).lower()


def test_local_launchers_use_current_preflight_and_never_start_streamlit() -> None:
    expected_profiles = {
        "start_local_development.bat": "local-windows",
        "start_local_development.sh": "local-unix",
    }
    for name, profile in expected_profiles.items():
        source = _source(name)
        assert "--dry-run" in source
        assert f"--profile {profile}" in source
        assert "--profile dual-run" in source
        assert "--profile artifact-runtime" in source
        assert "api.main:app" in source
        assert "5173" in source
        assert "streamlit" not in source.lower()
        assert "ui/app.py" not in source
        assert "8501" not in source


def test_windows_supervisor_owns_current_processes_and_scoped_cleanup() -> None:
    source = _source("supervise_local_runtime.ps1")

    assert "api.main:app" in source
    assert '"node:lts", "npm", "run", "dev"' in source
    assert "scripts.run_service_monitor" in source
    assert "scripts.run_durable_job_worker" in source
    assert "scripts.run_incident_worker" in source
    assert "/health" in source
    assert "/admin/" in source
    assert "Refresh-OwnedIdentityRegistry" in source
    assert "Stop-OwnedReactContainer" in source
    assert '"cleanup_failed"' in source
    assert '"cleanup_complete"' in source
    assert "streamlit" not in source.lower()


def test_unix_launcher_requires_current_schema_and_cleans_owned_processes() -> None:
    source = _source("start_local_development.sh")
    readiness = '"$PY" -m scripts.update_local_database --require-current'

    assert source.index(readiness) < source.index("api.main:app")
    assert "npm run dev" in source
    assert "trap cleanup_owned EXIT" in source
    assert 'kill -TERM -- "-$pid"' in source
    assert 'require_owned_process "Runtime Monitor"' in source
    assert 'require_owned_process "Durable Background Worker"' in source
    assert 'require_owned_process "Incident Maintenance Worker"' in source
    assert "streamlit" not in source.lower()


def test_database_launchers_keep_dry_run_before_mutation() -> None:
    for name, profile in (
        ("update_local_database.bat", "database-update"),
        ("reset_DB.bat", "database-reset"),
    ):
        source = _source(name)
        assert "--dry-run" in source
        assert f"--profile {profile}" in source


def test_no_auth_wrappers_only_set_local_profile_and_delegate() -> None:
    windows = _source("start_local_development_no_auth.bat")
    unix = _source("start_local_development_no_auth.sh")

    assert 'set "ACCESS_CONTROL_PROFILE=local_bypass"' in windows
    assert 'call "%~dp0start_local_development.bat"' in windows
    assert "export ACCESS_CONTROL_PROFILE=local_bypass" in unix
    assert 'exec "$SCRIPT_DIR/start_local_development.sh" "$@"' in unix
    assert "streamlit" not in (windows + unix).lower()
