"""
File: test_online_script.py
Description: 驗證本機開發啟動腳本的靜態安全契約。
"""

from pathlib import Path


LAUNCHER_ROOT = Path(__file__).resolve().parents[1] / "scripts" / "launchers"
ONLINE_SCRIPT = LAUNCHER_ROOT / "start_local_development.bat"
ONLINE_SHELL_SCRIPT = LAUNCHER_ROOT / "start_local_development.sh"


def _script() -> str:
    return ONLINE_SCRIPT.read_text(encoding="utf-8")


def _shell_script() -> str:
    return ONLINE_SHELL_SCRIPT.read_text(encoding="utf-8")


def test_online_script_resolves_its_own_working_directory_and_venv():
    script = _script()

    assert 'for %%I in ("%~dp0..\\..") do set "PROJECT_ROOT=%%~fI"' in script
    assert 'cd /d "%PROJECT_ROOT%"' in script
    assert 'set "PY=%CD%\\.venv\\Scripts\\python.exe"' in script
    assert 'if not exist .venv\\Scripts\\python.exe (' in script


def test_online_script_waits_for_database_before_launching_services():
    script = _script()

    docker_start = script.index("docker-compose up -d")
    wait_for_db = script.index('"%PY%" scripts/wait_for_db.py')
    fastapi_start = script.index('"%PY%" -m uvicorn api.main:app')

    assert docker_start < wait_for_db < fastapi_start
    assert "Database connection timeout!" in script
    assert "exit /b %errorlevel%" in script


def test_online_script_is_development_only_and_uses_non_destructive_entrypoints():
    script = _script()

    assert '"%PY%" -m uvicorn api.main:app --host 0.0.0.0 --port 8000' in script
    assert 'start "React Admin UI" /D "%CD%\\ui_react" cmd /k "npm.cmd run dev -- --host 0.0.0.0 --port 5173 --strictPort"' in script
    assert "streamlit run" not in script
    assert "Local Development Startup Script" in script
    assert '"%PY%" -m scripts.validate_line_production_readiness' not in script
    assert "ONLINE_SKIP_PRODUCTION_READINESS" not in script
    assert "production_not_supported" not in script
    assert "ONLINE_APP_ENV" not in script
    assert '"%PY%" -m scripts.run_line_worker' in script
    assert '"%PY%" -m scripts.run_service_monitor' in script
    assert '"%PY%" -m scripts.run_durable_job_worker' in script
    assert '"%PY%" -m scripts.run_contract_integration_worker' not in script
    assert '"%PY%" -m scripts.run_knowledge_worker' in script
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
    assert "choose_db_port" in script
    assert "Port 3306 is busy" in script
    assert '"$PY" -m uvicorn api.main:app --host 0.0.0.0 --port 8000 &' in script
    assert '(cd ui_react && npm run dev -- --host 0.0.0.0 --port 5173 --strictPort) &' in script
    assert "streamlit run" not in script
    assert '"$PY" scripts/file_watcher.py &' not in script
    assert "scripts/init_db.py" not in script
    assert "generate_fake_data.py" not in script
