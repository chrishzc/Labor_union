"""Static acceptance coverage for the production startup batch script."""

from pathlib import Path


ONLINE_SCRIPT = Path(__file__).resolve().parents[1] / "online.bat"


def _script() -> str:
    return ONLINE_SCRIPT.read_text(encoding="utf-8")


def test_online_script_resolves_its_own_working_directory_and_venv():
    script = _script()

    assert 'cd /d "%~dp0"' in script
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


def test_online_script_uses_expected_service_entrypoints_without_initializing_data():
    script = _script()

    assert '"%PY%" -m uvicorn api.main:app --host 0.0.0.0 --port 8000' in script
    assert '"%PY%" -m streamlit run ui/app.py --server.address 0.0.0.0 --server.port 8501' in script
    assert '"%PY%" scripts/file_watcher.py' in script
    assert "line.main:app" not in script
    assert "init_db" not in script.lower()
    assert "fake_data" not in script.lower()
