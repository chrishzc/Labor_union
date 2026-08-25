"""
File: test_line_bind_legacy_characterization.py
Description: 驗證舊 LIFF writer fail closed，且入口設定只指向 canonical 身分流程。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from line import line_bot
from subsystems.line.runtime_contracts import LineRuntimeMode


class _Cursor:
    def __init__(self) -> None:
        self.statements: list[tuple[str, object]] = []
        self.lastrowid = 1

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters=None) -> None:
        self.statements.append((" ".join(statement.split()), parameters))

    @staticmethod
    def fetchone():
        return {
            "id": 17,
            "name": "王小美",
            "case_no": "C-2026-01",
            "line_user_id": "",
        }


class _Connection:
    def __init__(self) -> None:
        self.cursor_instance = _Cursor()
        self.commits = 0

    def cursor(self, *_):
        return self.cursor_instance

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        raise AssertionError("first-time bind must not roll back")

    def close(self) -> None:
        return None


def test_legacy_first_time_bind_is_retired_in_canonical_runtime(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(line_bot, "get_db_connection", lambda: connection)
    monkeypatch.setattr(line_bot, "wake_worker", lambda: None)
    monkeypatch.setattr(
        line_bot,
        "_trusted_line_user_id",
        lambda *_: asyncio.sleep(0, result="U-client"),
    )
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(line_bot.line_bind(
            SimpleNamespace(
                name="王小美",
                phone="0912-345-678",
                line_user_id="U-untrusted",
                line_id_token="signed-token",
                force_rebind=False,
            )
        ))

    assert exc_info.value.status_code == 410
    assert exc_info.value.detail["code"] == "legacy_line_route_retired"
    assert exc_info.value.detail["replacement"] == "/api/v1/line/identity/customer/apply"
    assert connection.cursor_instance.statements == []
    assert connection.commits == 0


@pytest.mark.parametrize(
    "call_factory",
    [
        lambda: line_bot.get_line_config(),
        lambda: line_bot.post_client_info(
            SimpleNamespace(line_id_token="signed-token", line_user_id="U-untrusted")
        ),
        lambda: line_bot.get_client_info("U-untrusted"),
        lambda: line_bot.line_register(
            SimpleNamespace(
                name="王小美",
                phone="0912-345-678",
                expected_date="2026-09-01",
                service_days=10,
                address="masked-address",
                line_id_token="signed-token",
                line_user_id="U-untrusted",
            )
        ),
        lambda: line_bot.serve_bind_page(),
        lambda: line_bot.serve_register_page(),
    ],
    ids=[
        "config",
        "client-info-post",
        "client-info-get",
        "register",
        "bind-page",
        "register-page",
    ],
)
def test_all_legacy_liff_surfaces_fail_closed_in_canonical_runtime(monkeypatch, call_factory):
    monkeypatch.setattr(
        line_bot,
        "line_webhook_runtime_mode",
        lambda: LineRuntimeMode.CANONICAL,
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(call_factory())

    assert exc_info.value.status_code == 410
    assert exc_info.value.detail["code"] == "legacy_line_route_retired"
    assert exc_info.value.detail["replacement"]


def test_liff_gateway_settings_only_point_to_canonical_identity_routes():
    settings = json.loads(Path("config/liff_settings.json").read_text(encoding="utf-8"))
    actions = {
        action["id"]: action["path"]
        for action in settings["pages"]["gateway"]["actions"]
    }

    assert actions == {
        "bind_existing": "/line-identity",
        "register_new": "/line-registration",
    }
    assert all(path not in {"/bind-page", "/register-page"} for path in actions.values())
