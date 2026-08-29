"""
File: test_external_staff_completion_port.py
Description: 驗證 borrowed staff completion adapter 的 commitment、deposit、LINE reminder 與失敗關閉。
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest

from domains.contract_signing.external_signing import (
    ExternalSigningSessionFacts,
    ExternalSigningState,
    StaffSigningReportTarget,
)
from infrastructure.db import external_staff_completion_port as module
from infrastructure.db.external_staff_completion_port import (
    MySqlExternalStaffCompletionPort,
)
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.contract_signing.external_signing_contracts import (
    ExternalReporterSubjectType,
    RecordExternalStaffSigningReport,
    VerifiedReporterBindingSnapshot,
)


def test_existing_commitment_replays_and_borrowed_adapter_never_commits(monkeypatch) -> None:
    connection = FakeConnection()
    captured = _install_success_dependencies(monkeypatch)
    port = MySqlExternalStaffCompletionPort(connection)

    first = port.establish_prerequisites(_command(), _facts(), 2)
    second = port.establish_prerequisites(_command(), _facts(), 2)

    assert first.commitment_id == second.commitment_id == 44
    assert all("INSERT INTO precontract_service_commitments" not in sql for sql, _ in connection.executions)
    assert connection.commit_calls == 0
    assert connection.rollback_calls == 0
    assert len(captured["deliveries"]) == 2


def test_client_reminder_contains_no_url_and_uses_durable_source(monkeypatch) -> None:
    connection = FakeConnection()
    captured = _install_success_dependencies(monkeypatch)

    MySqlExternalStaffCompletionPort(connection).establish_prerequisites(
        _command(), _facts(), 2
    )

    request = captured["deliveries"][0]
    payload = json.loads(request.payload_json)
    assert "http" not in payload["text"].lower()
    assert "url" not in payload["text"].lower()
    assert request.source_aggregate_type == "contract_external_signing_session"
    assert request.source_aggregate_identity == _facts().session_id


def test_deposit_uses_a_deterministic_derived_key(monkeypatch) -> None:
    connection = FakeConnection()
    captured = _install_success_dependencies(monkeypatch)
    command = _command()

    MySqlExternalStaffCompletionPort(connection).establish_prerequisites(
        command, _facts(), 2
    )

    finance_command = captured["finance_commands"][0]
    expected = module._derived_key(command.idempotency_key, "deposit")
    assert finance_command.idempotency_key == expected
    assert finance_command.idempotency_key != command.idempotency_key
    assert finance_command.source_event_family == "precontract-commitment"
    assert finance_command.source_event_id == 44


def test_missing_order_fails_before_deposit_or_delivery(monkeypatch) -> None:
    connection = FakeConnection(order=None)
    captured = _install_success_dependencies(monkeypatch)

    with pytest.raises(RuntimeError, match="order_missing"):
        MySqlExternalStaffCompletionPort(connection).establish_prerequisites(
            _command(), _facts(), 2
        )

    assert captured["finance_commands"] == []
    assert captured["deliveries"] == []


def test_unbound_client_fails_before_deposit_or_delivery(monkeypatch) -> None:
    connection = FakeConnection(binding=None)
    captured = _install_success_dependencies(monkeypatch)

    with pytest.raises(ValueError, match="recipient_unbound"):
        MySqlExternalStaffCompletionPort(connection).establish_prerequisites(
            _command(), _facts(), 2
        )

    assert captured["finance_commands"] == []
    assert captured["deliveries"] == []


def test_existing_commitment_identity_mismatch_fails_closed(monkeypatch) -> None:
    connection = FakeConnection(
        commitment={"id": 44, "case_no": "OTHER", "matching_plan_id": 9}
    )
    captured = _install_success_dependencies(monkeypatch)

    with pytest.raises(RuntimeError, match="identity_conflict"):
        MySqlExternalStaffCompletionPort(connection).establish_prerequisites(
            _command(), _facts(), 2
        )

    assert captured["finance_commands"] == []
    assert captured["deliveries"] == []


def test_plan_case_mismatch_fails_before_commitment_or_reminder(monkeypatch) -> None:
    connection = FakeConnection(plan={"case_no": "OTHER"})
    captured = _install_success_dependencies(monkeypatch)

    with pytest.raises(RuntimeError, match="plan_identity_conflict"):
        MySqlExternalStaffCompletionPort(connection).establish_prerequisites(
            _command(), _facts(), 2
        )

    assert not any(sql.startswith("INSERT") for sql, _ in connection.executions)
    assert captured["finance_commands"] == []
    assert captured["deliveries"] == []


def _install_success_dependencies(monkeypatch):
    captured = {"finance_commands": [], "deliveries": []}
    monkeypatch.setattr(module, "select_order", lambda cursor, case_no, lock: {"case_no": case_no})
    monkeypatch.setattr(module, "load_contract_client_finance_facts", lambda cursor, order, lock: object())
    monkeypatch.setattr(module, "build_precontract_deposit_candidate", lambda facts, identity: SimpleNamespace(mutates=True))
    monkeypatch.setattr(module, "precontract_deposit_terms_impact", lambda candidate: "deposit-impact")
    monkeypatch.setattr(module, "persist_client_finance_terms_impact", lambda cursor, command: captured["finance_commands"].append(command))

    class DeliveryRepository:
        def __init__(self, connection):
            self.connection = connection

        def enqueue(self, request):
            captured["deliveries"].append(request)
            return SimpleNamespace(task_id=SimpleNamespace(value=77))

    monkeypatch.setattr(module, "MySqlLineDeliveryTaskRepository", DeliveryRepository)
    return captured


class FakeCursor:
    def __init__(self, connection) -> None:
        self.connection = connection
        self.lastrowid = 88
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, parameters=()):
        self.connection.executions.append((statement, parameters))
        if "FROM precontract_service_commitments" in statement:
            self._row = self.connection.commitment
        elif "FROM caregiver_matching_plans" in statement:
            self._row = self.connection.plan
        elif "SELECT client_id FROM orders" in statement:
            self._row = self.connection.order
        elif "FROM line_identity_bindings" in statement:
            self._row = self.connection.binding
        else:
            self._row = None

    def fetchone(self):
        return self._row

    def fetchall(self):
        return ()


class FakeConnection:
    def __init__(
        self, *, plan="default", commitment="default", order="default", binding="default"
    ) -> None:
        self.plan = {"case_no": "CASE-001"} if plan == "default" else plan
        self.commitment = (
            {"id": 44, "case_no": "CASE-001", "matching_plan_id": 9}
            if commitment == "default"
            else commitment
        )
        self.order = {"client_id": 301} if order == "default" else order
        self.binding = (
            {
                "line_user_id": "U-client",
                "binding_status": "bound",
                "subject_type": "customer",
                "subject_reference": "301",
            }
            if binding == "default"
            else binding
        )
        self.executions = []
        self.commit_calls = 0
        self.rollback_calls = 0

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1


def _facts() -> ExternalSigningSessionFacts:
    return ExternalSigningSessionFacts(
        "ces_1234567890abcdef1234567890abcdef",
        "CASE-001",
        9,
        "a" * 64,
        (
            StaffSigningReportTarget(11, "501", 101),
            StaffSigningReportTarget(12, "502", 102),
        ),
        (11,),
        "301",
        201,
        None,
        False,
        ExternalSigningState.STAFF_REPORTING,
        1,
    )


def _command() -> RecordExternalStaffSigningReport:
    return RecordExternalStaffSigningReport(
        _facts().session_id,
        "CASE-001",
        9,
        12,
        102,
        VerifiedReporterBindingSnapshot(
            "U-staff",
            ExternalReporterSubjectType.STAFF,
            "502",
            ExpectedVersion(3),
        ),
        "line-event-staff-002",
        "b" * 64,
        datetime(2026, 8, 26, 10, tzinfo=timezone.utc),
        ExpectedVersion(1),
        ActorContext("line_user_id:U-staff"),
        IdempotencyKey("external-report:staff:002"),
        CorrelationId("corr-staff-002"),
    )
