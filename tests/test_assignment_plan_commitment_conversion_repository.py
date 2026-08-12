from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pytest

import infrastructure.mysql.assignment_plan_repository as assignment_repository
from domains.scheduling.commitment_execution import CommitmentExecutionMismatch
from infrastructure.mysql.assignment_plan_repository import MySqlAssignmentPlanRepository
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, IdempotencyKey


class _Connection:
    def __init__(self) -> None:
        self.cursor_instance = _Cursor()

    @contextmanager
    def cursor(self):
        yield self.cursor_instance


class _Cursor:
    def __init__(self) -> None:
        self.statements: list[str] = []
        self._rows: list[dict[str, object]] = []

    def execute(self, statement, _parameters=()) -> None:
        self.statements.append(statement)
        if "FROM precontract_service_commitments commitment" in statement:
            self._rows = [{"id": 11, "matching_plan_id": 5, "terminal_event_id": None}]
        elif "FROM precontract_service_commitment_days" in statement:
            self._rows = [{"staff_id": 9, "service_date": date(2030, 1, 1)}]
        elif "FROM caregiver_availability_locks" in statement:
            self._rows = [{"plan_id": 5}]

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


def test_commitment_mismatch_stops_before_execution_persistence(monkeypatch):
    connection = _Connection()
    repository = MySqlAssignmentPlanRepository(connection)
    monkeypatch.setattr(
        assignment_repository,
        "persist_scheduling_replacement",
        lambda *_: pytest.fail("execution persistence must not run on commitment mismatch"),
    )

    with pytest.raises(CommitmentExecutionMismatch):
        repository.replace_scheduling_generation(_candidate(), _context())

    assert all(not statement.lstrip().upper().startswith(("INSERT", "UPDATE")) for statement in connection.cursor_instance.statements)


def _candidate():
    return SimpleNamespace(
        case_no="CASE-1",
        assignments=(SimpleNamespace(staff_id=7, service_dates=(date(2030, 1, 1),)),),
    )


def _context():
    fingerprint = PreviewFingerprint("a" * 64)
    return SimpleNamespace(
        expected_order_version=1,
        command_fingerprint=fingerprint,
        preview_fingerprint=fingerprint,
        idempotency_key=IdempotencyKey("wp56-conversion-mismatch"),
        actor=SimpleNamespace(actor_id="wp56-test"),
        reason="verify mismatch rollback",
        correlation_id=CorrelationId("wp56-conversion-mismatch"),
        waiting_lock_ids=(17,),
    )
