"""
File: test_external_staff_completion_port.py
Description: 驗證 borrowed staff completion adapter 的 commitment、deposit 與失敗關閉。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
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
from domains.scheduling.assignment_plan import StaffOccupancyFact
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
    assert captured["finance_commands"]


@pytest.mark.parametrize("scenario, expected", [
    ("free", ()), ("own_case", ()), ("outside_interval", ()),
    ("other_assignment", ("signing_staff_occupancy_conflict",)),
    ("unavailable", ("signing_staff_occupancy_conflict",)),
])
def test_signing_checks_current_occupancy_before_handoff_without_writing(monkeypatch, scenario, expected):
    segments = [
        {"id": 11, "staff_id": 501, "assigned_start_date": date(2026, 8, 26), "assigned_end_date": date(2026, 8, 27)},
        {"id": 12, "staff_id": 502, "assigned_start_date": date(2026, 8, 28), "assigned_end_date": date(2026, 8, 29)},
    ]
    statements = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, params):
            self.sql = sql
            statements.append(sql)
        def fetchall(self):
            if "FROM caregiver_matching_plan_segments" in self.sql:
                return segments
            assert "WHERE status='effective'" in self.sql
            return [{"id": 1, "staff_id": 501, "start_date": date(2026, 8, 27), "end_date": None}] if scenario == "unavailable" else []
    connection = SimpleNamespace(cursor=Cursor)
    def no_confirmed_dates(*args, **kwargs):
        raise ValueError("current confirmed service dates are required")
    monkeypatch.setattr(module, "_with_current_confirmed_service_dates", no_confirmed_dates)
    monkeypatch.setattr(module, "_commitment_service_days", lambda *_: tuple((segment, segment["assigned_start_date"]) for segment in segments))
    day = date(2026, 8, 25) if scenario == "outside_interval" else date(2026, 8, 27)
    occupancy = () if scenario in {"free", "unavailable"} else (
        StaffOccupancyFact(501, day, "CASE-001" if scenario == "own_case" else "OTHER-CASE"),
    )
    monkeypatch.setattr(module, "load_occupancy_snapshot", lambda *args, **kwargs: (occupancy, ()))
    assert MySqlExternalStaffCompletionPort(connection).signing_blockers(_facts()) == expected
    assert statements and all(sql.startswith("SELECT ") for sql in statements)


@pytest.mark.parametrize("scenario, expected", [
    ("current_conflict", ("signing_staff_occupancy_conflict",)),
    ("old_dates_free", ()),
    ("invalid_current_dates", ("signing_service_dates_unavailable",)),
])
def test_signing_uses_current_confirmed_dates_instead_of_original_plan(monkeypatch, scenario, expected):
    statements = []

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, sql, params):
            self.sql = sql
            statements.append(sql)
        def fetchone(self):
            assert "FROM confirmed_service_date_versions" in self.sql
            return {"id": 7, "service_day_count": 2, "service_days": 3 if scenario == "invalid_current_dates" else 2}
        def fetchall(self):
            if "FROM caregiver_matching_plan_segments" in self.sql:
                return [{"id": 11, "staff_id": 501, "assigned_start_date": date(2026, 8, 26), "assigned_end_date": date(2026, 8, 27)}]
            if "FROM confirmed_service_date_days" in self.sql:
                return [{"service_date": date(2026, 9, 1)}, {"service_date": date(2026, 9, 2)}]
            assert "WHERE status='effective'" in self.sql
            return []

    def no_planned_date_fallback(*_):
        pytest.fail("current confirmed dates must remain authoritative")

    monkeypatch.setattr(module, "_commitment_service_days", no_planned_date_fallback)
    occupancy_date = date(2026, 9, 1) if scenario == "current_conflict" else date(2026, 8, 26)
    monkeypatch.setattr(module, "load_occupancy_snapshot", lambda *args, **kwargs: (
        (StaffOccupancyFact(501, occupancy_date, "OTHER-CASE"),), (),
    ))
    facts = _facts()
    facts = replace(facts, staff_targets=facts.staff_targets[:1], reported_staff_segment_ids=())
    assert MySqlExternalStaffCompletionPort(SimpleNamespace(cursor=Cursor)).signing_blockers(facts) == expected
    assert all(sql.startswith("SELECT ") for sql in statements)


@pytest.mark.parametrize("for_update", [False, True])
def test_existing_commitment_lookup_is_case_and_plan_scoped_without_business_writes(for_update):
    connection = FakeConnection()
    port = MySqlExternalStaffCompletionPort(connection)
    assert port.existing_commitment(_facts(), for_update=for_update) == 44
    [(statement, parameters)] = connection.executions
    assert parameters == ("CASE-001", 9)
    assert statement.endswith(" FOR UPDATE") is for_update
    assert statement.startswith("SELECT ")
    assert connection.commit_calls == connection.rollback_calls == 0


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


def test_unbound_client_does_not_block_commitment_or_deposit(monkeypatch) -> None:
    connection = FakeConnection(binding=None)
    captured = _install_success_dependencies(monkeypatch)

    result = MySqlExternalStaffCompletionPort(connection).establish_prerequisites(
        _command(), _facts(), 2
    )

    assert result == module.StaffCompletionPrerequisites(44)
    assert len(captured["finance_commands"]) == 1
    assert not any("line_identity_bindings" in sql for sql, _ in connection.executions)


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


def test_plan_case_mismatch_fails_before_commitment(monkeypatch) -> None:
    connection = FakeConnection(plan={"case_no": "OTHER"})
    captured = _install_success_dependencies(monkeypatch)

    with pytest.raises(RuntimeError, match="plan_identity_conflict"):
        MySqlExternalStaffCompletionPort(connection).establish_prerequisites(
            _command(), _facts(), 2
        )

    assert not any(sql.startswith("INSERT") for sql, _ in connection.executions)
    assert captured["finance_commands"] == []


def _install_success_dependencies(monkeypatch):
    captured = {"finance_commands": []}
    monkeypatch.setattr(module, "select_order", lambda cursor, case_no, lock: {"case_no": case_no})
    monkeypatch.setattr(module, "load_contract_client_finance_facts", lambda cursor, order, lock: object())
    monkeypatch.setattr(module, "build_precontract_deposit_candidate", lambda facts, identity: SimpleNamespace(mutates=True))
    monkeypatch.setattr(module, "precontract_deposit_terms_impact", lambda candidate: "deposit-impact")
    monkeypatch.setattr(module, "persist_client_finance_terms_impact", lambda cursor, command: captured["finance_commands"].append(command))

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
        elif "FROM line_identity_role_bindings" in statement:
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
