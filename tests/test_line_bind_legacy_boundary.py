"""#251 retirement supersedes #226's characterization of the legacy writer.

The old payload remains decodable, but neither rollback nor force_rebind permits
binding, token verification, a transaction, or a canonical command bridge.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from line import line_bot
from shared_kernel.writer_inventory import scan_production_writers
from subsystems.line.runtime_contracts import LineRuntimeMode
from subsystems.line.runtime_cutover import LineRuntimeCutoverError, resolve_line_runtime_selection

REPLACEMENT = "/api/v1/line/identity/customer/apply"
PAYLOAD = {"name": "合成客戶", "phone": "synthetic-phone", "line_user_id": "U-synthetic"}


@pytest.fixture
def effects(monkeypatch):
    probes = {
        "get_db_connection": Mock(side_effect=AssertionError("LINE_BIND_MUTATION_STILL_REACHABLE")),
        "_trusted_line_user_id": AsyncMock(side_effect=AssertionError("unexpected token verification")),
        "bind_client": Mock(side_effect=AssertionError("unexpected canonical bridge")),
        "wake_worker": Mock(side_effect=AssertionError("unexpected worker wakeup")),
    }
    for name, probe in probes.items():
        monkeypatch.setattr(line_bot, name, probe)
    yield probes
    for probe in probes.values():
        probe.assert_not_called()


def test_legacy_bind_no_db_acquisition(monkeypatch, effects):
    """Original failure: allowed legacy reaches DB acquisition before retirement."""
    monkeypatch.setattr(line_bot, "line_webhook_runtime_mode", lambda: LineRuntimeMode.LEGACY)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(line_bot.line_bind(line_bot.LineBindPayload(**PAYLOAD)))
    assert caught.value.status_code == 410
    assert caught.value.detail["code"] == "legacy_line_route_retired"
    assert caught.value.detail["replacement"] == REPLACEMENT


@pytest.mark.parametrize("environment,mode,rollback", [
    ("development", "canonical", "false"),
    ("development", "legacy", "false"),
    ("production", "canonical", "false"),
    ("production", "legacy", "true"),
    ("production", "legacy", "false"),
])
@pytest.mark.parametrize("extra", [{}, {"force_rebind": True}, {"line_id_token": "synthetic-invalid-token"}])
def test_bind_retired_in_every_runtime(monkeypatch, effects, environment, mode, rollback, extra):
    configuration = {"APP_ENV": environment, "LINE_WEBHOOK_RUNTIME_MODE": mode,
                     "LINE_WORKER_RUNTIME_MODE": mode, "LINE_LEGACY_ROLLBACK_MODE": rollback}
    for key, value in configuration.items():
        monkeypatch.setenv(key, value)
    # Prove the actual runtime policy separately; retirement does not alter it.
    if environment == "production" and mode == "legacy" and rollback == "false":
        with pytest.raises(LineRuntimeCutoverError, match="rollback"):
            resolve_line_runtime_selection(configuration)
    else:
        assert resolve_line_runtime_selection(configuration).webhook_mode.value == mode
    app = FastAPI()
    app.include_router(line_bot.router)
    with TestClient(app) as client:
        response = client.post("/api/line/bind", json={**PAYLOAD, **extra})
    assert response.status_code == 410
    detail = response.json()["detail"]
    assert set(detail) == {"code", "message", "replacement"}
    assert detail["code"] == "legacy_line_route_retired"
    assert detail["replacement"] == REPLACEMENT
    assert isinstance(detail["message"], str) and detail["message"]


@pytest.mark.parametrize("database_available", [True, False])
def test_retirement_never_starts_success_or_failure_transaction(monkeypatch, database_available):
    connection = Mock()
    acquire = Mock(return_value=connection) if database_available else Mock(side_effect=RuntimeError("synthetic database unavailable"))
    monkeypatch.setattr(line_bot, "get_db_connection", acquire)
    monkeypatch.setattr(line_bot, "line_webhook_runtime_mode", lambda: LineRuntimeMode.LEGACY)
    with pytest.raises(HTTPException) as caught:
        asyncio.run(line_bot.line_bind(line_bot.LineBindPayload(**PAYLOAD, force_rebind=True)))
    assert caught.value.status_code == 410
    acquire.assert_not_called()
    assert connection.mock_calls == []  # Zero SQL, commit, rollback and close: no transaction acquired.


def test_retirement_does_not_disable_other_legacy_surfaces(monkeypatch):
    monkeypatch.setattr(line_bot, "line_webhook_runtime_mode", lambda: LineRuntimeMode.LEGACY)
    assert line_bot._require_legacy_line_surface("/unrelated") is None
    monkeypatch.setattr(line_bot, "line_webhook_runtime_mode", lambda: LineRuntimeMode.CANONICAL)
    with pytest.raises(HTTPException) as caught:
        line_bot._require_legacy_line_surface("/unrelated")
    assert caught.value.status_code == 410


def test_retired_bind_has_no_production_writer_finding():
    root = Path(__file__).resolve().parents[1]
    findings = scan_production_writers(root, ("line",))
    assert not [item for item in findings if item.relative_path == "line/line_bot.py" and item.symbol == "line_bind"]
