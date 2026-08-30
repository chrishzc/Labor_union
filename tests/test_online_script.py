"""
File: test_online_script.py
Description: 驗證本機開發啟動腳本的靜態安全契約。
"""

from pathlib import Path


LAUNCHER_ROOT = Path(__file__).resolve().parents[1] / "scripts" / "launchers"
PROJECT_ROOT = LAUNCHER_ROOT.parents[1]
ONLINE_SCRIPT = LAUNCHER_ROOT / "start_local_development.bat"
ONLINE_SHELL_SCRIPT = LAUNCHER_ROOT / "start_local_development.sh"


def _script() -> str:
    return ONLINE_SCRIPT.read_text(encoding="utf-8")


def _shell_script() -> str:
    return ONLINE_SHELL_SCRIPT.read_text(encoding="utf-8")


def test_windows_launcher_is_stored_as_crlf_for_source_archives():
    attributes = (PROJECT_ROOT / ".gitattributes").read_text(encoding="utf-8")
    payload = ONLINE_SCRIPT.read_bytes()

    assert "scripts/launchers/start_local_development.bat -text" in attributes
    assert b"\r\n" in payload
    assert b"\n" not in payload.replace(b"\r\n", b"")


def test_online_script_resolves_its_own_working_directory_and_venv():
    script = _script()

    assert 'for %%I in ("%~dp0..\\..") do set "PROJECT_ROOT=%%~fI"' in script
    assert 'cd /d "%PROJECT_ROOT%"' in script
    assert 'set "PY=%CD%\\.venv\\Scripts\\python.exe"' in script
    assert 'if not exist .venv\\Scripts\\python.exe (' in script


def test_online_script_waits_for_database_before_launching_services():
    script = _script()

    docker_start = script.index("docker-compose up -d redis")
    wait_for_db = script.index('"%PY%" scripts/wait_for_db.py')
    schema_check = script.index('"%PY%" -m scripts.update_local_database --require-current')
    supervisor_start = script.index(
        'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0supervise_local_runtime.ps1"'
    )

    assert docker_start < wait_for_db < schema_check < supervisor_start
    assert "Database connection timeout!" in script
    assert "Local database schema is not current." in script


def test_online_script_is_development_only_and_uses_non_destructive_entrypoints():
    script = _script()

    assert "Starting owned Windows runtime supervision" in script
    assert "-ApiPort 8000 -ReactPort 5173" in script
    assert "supervise_local_runtime.ps1" in script
    assert 'start "React Admin UI" /D' not in script
    assert "streamlit run" not in script
    assert "Local Development Startup Script" in script
    assert '"%PY%" -m scripts.validate_line_production_readiness' not in script
    assert "ONLINE_SKIP_PRODUCTION_READINESS" not in script
    assert "production_not_supported" not in script
    assert "ONLINE_APP_ENV" not in script
    # Windows delegates all child lifecycle ownership to the supervisor.
    assert '"%PY%" -m scripts.run_line_worker' not in script
    assert '"%PY%" -m scripts.run_service_monitor' not in script
    assert '"%PY%" -m scripts.run_durable_job_worker' not in script
    assert '"%PY%" -m scripts.run_contract_integration_worker' not in script
    assert '"%PY%" -m scripts.run_knowledge_worker' not in script
    assert '"%PY%" scripts/run_line_worker.py' not in script
    assert '"%PY%" scripts/file_watcher.py' not in script
    assert '"%PY%" scripts/run_durable_job_worker.py' not in script
    assert "line.main:app" not in script
    assert "init_db" not in script.lower()
    assert "fake_data" not in script.lower()


def test_online_shell_script_uses_macos_venv_and_expected_entrypoints():
    script = _shell_script()

    assert 'SCRIPT_DIR="${BASH_SOURCE[0]%/*}"' in script
    assert 'cd "$SCRIPT_DIR/../.."' in script
    assert "[[ ! -x .venv/bin/python ]]" in script
    assert 'PY="$PWD/.venv/bin/python"' in script
    assert 'docker compose up -d redis' in script
    assert '"$PY" scripts/wait_for_db.py' in script
    assert '"$PY" -m scripts.update_local_database --require-current' in script
    api_start = script.index('start_owned "FastAPI"')
    api_ready = script.index('wait_for_http "http://127.0.0.1:8000/health"')
    react_start = script.index('(cd ui_react && exec npm run dev -- --host 0.0.0.0 --port 5173 --strictPort) &')
    react_ready = script.index('wait_for_http "http://127.0.0.1:5173/admin/"')
    assert api_start < api_ready < react_start < react_ready
    assert 'start_owned "Runtime Monitor" "$PY" -m scripts.run_service_monitor' in script
    assert 'start_owned "Durable Background Worker" "$PY" -m scripts.run_durable_job_worker' in script
    assert 'start_owned "Incident Maintenance Worker" "$PY" -m scripts.run_incident_worker' in script
    assert 'trap cleanup_owned EXIT' in script
    assert 'while true; do' in script
    assert '(cd ui_react && exec npm run dev -- --host 0.0.0.0 --port 5173 --strictPort) &' in script
    assert "streamlit run" not in script
    assert '"$PY" scripts/file_watcher.py &' not in script
    assert "scripts/init_db.py" not in script
    assert "generate_fake_data.py" not in script
