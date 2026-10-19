"""Protect automatic startup's storage and service isolation boundaries."""
from pathlib import Path

import pytest
import yaml

from scripts import nas_appliance


def test_automatic_initializer_refuses_partial_data_without_changing_it(tmp_path, monkeypatch):
    for name in ("SETTINGS", "DATA", "SERVER_TLS", "MYSQL_SECRETS", "BOOTSTRAP"):
        folder = tmp_path / name
        folder.mkdir()
        monkeypatch.setattr(nas_appliance, name, folder)
    existing = nas_appliance.DATA / "preserve-user-file"
    existing.write_text("existing", encoding="utf-8")
    with pytest.raises(ValueError, match="refusing to overwrite"):
        nas_appliance.initialize()
    assert existing.read_text() == "existing"
    assert list(nas_appliance.SETTINGS.iterdir()) == []


def test_single_project_scopes_database_secrets_and_never_publishes_container_ports():
    root = Path(__file__).resolve().parents[7]
    config = yaml.safe_load((root / "deployment/nas-test/compose.web-setup.yaml").read_text(encoding="utf-8"))
    assert set(config["services"]) == {"initialize", "db", "redis", "api"}
    assert all("ports" not in service for service in config["services"].values())
    assert config["services"]["initialize"]["network_mode"] == "none"
    assert config["services"]["db"]["depends_on"]["initialize"]["condition"] == "service_completed_successfully"
    assert config["services"]["api"]["depends_on"]["db"]["condition"] == "service_healthy"
    mounts = config["services"]["api"]["volumes"]
    assert not any(name.startswith(("mysql-secrets:", "server-tls:")) for name in mounts)
    environment = config["services"]["api"]["environment"]
    assert not {"NAS_SETUP_KEY", "NAS_PUBLIC_ORIGIN", "API_CONCURRENCY"}.intersection(environment)


def test_api_start_does_not_require_installation_parameters_or_limit_concurrency(monkeypatch):
    calls = []
    monkeypatch.setattr(nas_appliance, "dotenv_values", lambda _: {})
    monkeypatch.setattr(nas_appliance, "_trusted_proxies", lambda: "127.0.0.1")
    monkeypatch.setattr(nas_appliance, "_drop_privileges", lambda: None)
    monkeypatch.setattr(nas_appliance.nas_test_runtime, "require_login_mode", lambda: None)
    monkeypatch.setattr(nas_appliance.nas_test_runtime, "verify_schema", lambda: None)
    monkeypatch.setattr(nas_appliance.os, "execvp", lambda executable, args: calls.append(args))
    monkeypatch.delenv("NAS_SETUP_KEY", raising=False)
    monkeypatch.delenv("NAS_PUBLIC_ORIGIN", raising=False)
    nas_appliance.serve()
    assert calls[0][0:4] == ["python", "-m", "uvicorn", "api.routes.nas_setup:create_app"]
    assert "--limit-concurrency" not in calls[0]


def test_line_startup_only_needs_no_identity_or_network(monkeypatch):
    calls = []
    monkeypatch.setattr(nas_appliance, "_drop_privileges", lambda: None)
    monkeypatch.setattr(nas_appliance.os, "execvp", lambda executable, args: calls.append(args))
    # Missing settings prove this check never stages credentials or starts a cycle.
    monkeypatch.setattr(nas_appliance, "SETTINGS", Path("nonexistent-test-settings"))
    nas_appliance.line_check()
    assert calls == [["python", "-m", "scripts.run_line_worker", "--help"]]
    root = Path(__file__).resolve().parents[7]
    config = yaml.safe_load((root / "deployment/nas-test/line-check.web-setup.yaml").read_text(encoding="utf-8"))
    service = config["services"]["line-check"]
    assert service["network_mode"] == "none" and "volumes" not in service
