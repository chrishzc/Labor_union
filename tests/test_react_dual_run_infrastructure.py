"""
File: test_react_dual_run_infrastructure.py
Description: 驗證 Phase 5B FastAPI＋React、relative API 與 owned cleanup 的靜態契約。
"""

from pathlib import Path

from scripts import smoke_local_development_launcher as smoke
from scripts.launcher_preflight import inspect_profile


ROOT = Path(__file__).resolve().parents[1]


def test_dual_run_contract_has_exact_services_and_loopback_ports() -> None:
    report = inspect_profile("dual-run")
    commands = smoke._service_commands()

    assert tuple(commands) == ("api", "react")
    assert report["ports"] == [8000, 5173]
    assert all("127.0.0.1" in " ".join(command) for command in commands.values())
    assert report["startup_order"] == ["api", "react"]


def test_smoke_never_composes_monitor_workers_or_provider() -> None:
    source = (ROOT / "scripts/smoke_local_development_launcher.py").read_text(
        encoding="utf-8"
    )
    commands = smoke._service_commands()

    assert set(commands) == {"api", "react"}
    assert "scripts.run_service_monitor" not in source
    assert "scripts.run_line_worker" not in source
    assert "scripts.run_durable_job_worker" not in source
    assert "docker-compose" not in source


def test_react_readiness_and_proxy_are_not_reduced_to_open_ports() -> None:
    source = (ROOT / "scripts/smoke_local_development_launcher.py").read_text(
        encoding="utf-8"
    )

    assert "id=\"root\"" in source
    assert (
        "http://127.0.0.1:5173/api/v1/system/status/performance-snapshot"
        in source
    )
    assert "_require_free_port" in source
    assert "taskkill" in source


def test_legacy_browser_client_has_no_absolute_backend_origin() -> None:
    source = (ROOT / "ui_react/src/api/client.ts").read_text(encoding="utf-8")

    assert "const API_BASE_URL = '/api'" in source
    assert "localhost:8000" not in source
    assert "127.0.0.1:8000" not in source
