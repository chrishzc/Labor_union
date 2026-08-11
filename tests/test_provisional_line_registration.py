"""Regression coverage for the typed provisional LINE registration owner."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from domains.case_import.provisional_registration import (
    ProvisionalRegistrationIntent,
    build_provisional_registration_candidate,
)
from infrastructure.mysql.provisional_registration_repository import (
    MySqlProvisionalRegistrationRepository,
    ProvisionalRegistrationMySqlUnitOfWork,
)
from line import line_bot
from subsystems.case_import.provisional_registration_application import (
    ProvisionalRegistrationApplication,
    ProvisionalRegistrationConflictError,
    ProvisionalRegistrationReceipt,
)


def _intent(*, name="王小美"):
    return ProvisionalRegistrationIntent(
        line_user_id="U-registration",
        name=name,
        phone="0912-345-678",
        expected_date="2026-10-01",
        service_days=26,
        address="台北市中山區",
        gender="女",
        email="client@example.test",
        birth_date="1990-01-01",
        tel=None,
        ext=None,
        city="台北市",
        zip_code="104",
        id_number="A123456789",
        liff_config_revision="revision-1",
        survey_details={"餐點": "一般"},
    )


class _Cursor:
    def __init__(self, record):
        self.record = record
        self.statements = []
        self.lastrowid = 0
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters=None):
        normalized = " ".join(statement.split())
        self.statements.append((normalized, parameters))
        if normalized.startswith("INSERT INTO clients"):
            self.lastrowid = 17
        elif normalized.startswith("INSERT INTO beclass_records"):
            self.lastrowid = 23
        elif normalized.startswith("INSERT INTO provisional_registration_conflicts"):
            self.lastrowid = 29

    def fetchone(self):
        return self.record


class _Connection:
    def __init__(self, record):
        self.cursor_instance = _Cursor(record)
        self.commits = 0
        self.rollbacks = 0
        self.begins = 0

    def begin(self):
        self.begins += 1

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _application(connection):
    return ProvisionalRegistrationApplication(
        MySqlProvisionalRegistrationRepository(connection),
        lambda: ProvisionalRegistrationMySqlUnitOfWork(connection),
    )


def test_first_submission_writes_only_provisional_roots_and_one_task():
    connection = _Connection(
        {
            "id": 5,
            "payload_fingerprint": "",
            "client_id": None,
            "beclass_record_id": None,
        }
    )
    candidate_fingerprint = build_provisional_registration_candidate(
        _intent()
    ).payload_fingerprint.value
    connection.cursor_instance.record["payload_fingerprint"] = candidate_fingerprint

    receipt = _application(connection).apply(_intent())

    statements = [statement for statement, _ in connection.cursor_instance.statements]
    assert receipt == ProvisionalRegistrationReceipt(5, 17, 23, "王小美", False, True)
    assert connection.commits == 1
    assert any(statement.startswith("INSERT INTO clients") for statement in statements)
    assert any(statement.startswith("INSERT INTO beclass_records") for statement in statements)
    assert any("INSERT INTO line_delivery_tasks" in statement for statement in statements)
    assert not any("INSERT INTO orders" in statement for statement in statements)


def test_exact_replay_returns_original_receipt_without_duplicate_write():
    candidate_fingerprint = build_provisional_registration_candidate(
        _intent()
    ).payload_fingerprint.value
    connection = _Connection(
        {"id": 5, "payload_fingerprint": candidate_fingerprint, "client_id": 17, "beclass_record_id": 23}
    )

    receipt = _application(connection).apply(_intent())

    statements = [statement for statement, _ in connection.cursor_instance.statements]
    assert receipt.replayed is True
    assert receipt.worker_wakeup_required is False
    assert not any(statement.startswith("INSERT INTO clients") for statement in statements)
    assert not any(statement.startswith("INSERT INTO beclass_records") for statement in statements)
    assert not any("INSERT INTO line_delivery_tasks" in statement for statement in statements)


def test_different_payload_creates_one_admin_conflict_and_returns_conflict():
    connection = _Connection(
        {"id": 5, "payload_fingerprint": "0" * 64, "client_id": 17, "beclass_record_id": 23}
    )

    with pytest.raises(ProvisionalRegistrationConflictError, match="registration_conflict"):
        _application(connection).apply(_intent())

    statements = [statement for statement, _ in connection.cursor_instance.statements]
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert any("INSERT INTO provisional_registration_conflicts" in statement for statement in statements)


def test_legacy_liff_route_delegates_to_typed_owner(monkeypatch):
    captured = []
    receipt = ProvisionalRegistrationReceipt(5, 17, 23, "王小美", False, True)
    application = SimpleNamespace(apply=lambda intent: captured.append(intent) or receipt)
    connection = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(line_bot, "get_db_connection", lambda: connection)
    monkeypatch.setattr(line_bot, "wake_worker", lambda: None)
    monkeypatch.setattr(line_bot, "_require_legacy_line_surface", lambda _: None)
    monkeypatch.setattr(line_bot, "build_provisional_registration_application", lambda _: application)
    monkeypatch.setattr(
        line_bot,
        "_trusted_line_user_id",
        lambda *_: asyncio.sleep(0, result="U-registration"),
    )

    result = asyncio.run(line_bot.line_register(_payload()))

    assert result == {
        "status": "success", "client_id": 17, "client_name": "王小美", "case_no": None, "replayed": False,
    }
    assert captured[0].line_user_id == "U-registration"


def _payload():
    return line_bot.LineRegisterPayload(
        name="王小美", phone="0912-345-678", expected_date="2026-10-01",
        service_days=26, address="台北市中山區", survey_details={"餐點": "一般"},
    )
