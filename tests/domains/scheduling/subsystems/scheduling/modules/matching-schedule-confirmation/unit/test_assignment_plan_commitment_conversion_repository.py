from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import pytest

import infrastructure.mysql.assignment_plan_repository as assignment_repository
from domains.scheduling.commitment_execution import CommitmentExecutionMismatch, ExecutionServiceDay
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
        self.commitment_days = [{"staff_id": 9, "service_date": date(2030, 1, 1)}]

    def execute(self, statement, _parameters=()) -> None:
        self.statements.append(statement)
        if "FROM precontract_service_commitments commitment" in statement:
            self._rows = [{"id": 11, "matching_plan_id": 5, "terminal_event_id": None}]
        elif "FROM precontract_service_commitment_days" in statement:
            self._rows = self.commitment_days
        elif "FROM caregiver_availability_locks" in statement:
            self._rows = [{"plan_id": 5}]
        elif "FROM scheduling_service_start_requests" in statement:
            self._rows = [{"id": 90, "staff_id": 7, "selected_candidate_id": None,
                           "execution_dates": [{"staff_id": 7, "dates": ["2030-01-01"]}],
                           "confirmed_version_id": 42}]

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


def test_office_preview_requires_reason_when_signed_allocation_changes():
    cursor = _Cursor()
    days = tuple(date(2030, 1, day) for day in (1, 2, 3))
    cursor.commitment_days = [{"staff_id": staff_id, "service_date": day} for staff_id, day in zip((7, 8, 8), days)]
    execution_days = tuple(ExecutionServiceDay(staff_id, day) for staff_id, day in zip((7, 8, 7), days))
    reason = ""

    def execution_reader(*_args, **_kwargs):
        return {"substitutions": {}, "office_reallocation_reason": reason}, execution_days

    def verify(days):
        return assignment_repository._require_exact_commitment_days(
            cursor, "CASE-1", days, (17,), lock=False, execution_reader=execution_reader, office_preview=True,
        )

    with pytest.raises(ValueError, match="office_schedule_reallocation_reason_required"):
        verify(execution_days)
    reason = "已協調"
    assert verify(execution_days) == 11
    assert all("FOR UPDATE" not in statement for statement in cursor.statements)


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
