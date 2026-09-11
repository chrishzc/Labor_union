"""Static contracts for the owned Windows runtime supervisor."""

from pathlib import Path


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
