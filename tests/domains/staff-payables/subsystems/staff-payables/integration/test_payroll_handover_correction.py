from types import SimpleNamespace

import pytest

from domains.staff_payables.reconciliation import StaffPayableStatus
from infrastructure.mysql.staff_payout_repository import _load_obligation_rows, _projection_rows, _projection_status
from infrastructure.mysql.staff_payable_payroll_correction import MySqlStaffPayablePayrollCorrectionRepository
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.staff_payables.payroll_correction import PayrollCorrectionSettlement, StaffPayablesPayrollCorrectionApplication


class Projection:
    def __init__(self, *, fail=False):
        self.calls = []
        self.fail = fail

    def refresh_payroll_correction(self, settlement):
        self.calls.append(settlement)
        if self.fail:
            raise ValueError("staff_payables_correction_stale")


class Recovery:
    def __init__(self):
        self.calls = []

    def create_from_payroll_correction(self, request):
        self.calls.append(request)


def settlement(*, paid=2000, recovery=0):
    return PayrollCorrectionSettlement("CASE", "original", "staff-handover:delta", 7,
        MoneyNTD(5800), MoneyNTD(paid), MoneyNTD(recovery))


def context():
    return SimpleNamespace(idempotency_key=IdempotencyKey("handover-1"), actor=ActorContext("operator"),
                           reason="", correlation_id=CorrelationId("handover-1"))


def test_partial_payment_only_refreshes_projection_and_never_creates_recovery():
    projection, recovery = Projection(), Recovery()
    StaffPayablesPayrollCorrectionApplication(projection, recovery).apply(settlement(), context())
    assert len(projection.calls) == 1
    assert recovery.calls == []


def test_actual_overpayment_delegates_exact_correction_source_with_stable_child_identity():
    projection, recovery = Projection(), Recovery()
    owner = StaffPayablesPayrollCorrectionApplication(projection, recovery)
    owner.apply(settlement(paid=8000, recovery=2200), context())
    owner.apply(settlement(paid=8000, recovery=2200), context())
    first, second = recovery.calls
    assert first.idempotency_key == second.idempotency_key
    assert first.source.correction_identity == "staff-handover:delta"
    assert first.source.obligation_identity == "original"
    assert first.source.amount == MoneyNTD(2200)
    assert first.reason == ""


def test_stale_projection_never_creates_recovery():
    recovery = Recovery()
    owner = StaffPayablesPayrollCorrectionApplication(Projection(fail=True), recovery)
    with pytest.raises(ValueError, match="staff_payables_correction_stale"):
        owner.apply(settlement(paid=8000, recovery=2200), context())
    assert recovery.calls == []


class Cursor:
    rowcount = 1

    def __init__(self, *, paid=2000):
        self.calls = []
        self.paid = paid

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self.calls.append((sql, params))

    def fetchone(self):
        return {"aggregate_version": 4}

    def fetchall(self):
        return ({"obligation_identity": "original", "staff_id": 7, "obligation_amount_ntd": 5800,
                 "net_paid_ntd": self.paid, "current_event_id": 12},)


def test_projection_refresh_uses_effective_entitlement_and_actual_payment_without_mutating_payroll_roots():
    cursor = Cursor()
    repository = MySqlStaffPayablePayrollCorrectionRepository(SimpleNamespace(cursor=lambda: cursor))
    repository.refresh_payroll_correction(settlement())
    upsert = next(params for sql, params in cursor.calls if "INSERT INTO staff_payable_projections" in sql)
    assert upsert[:6] == ("original", 7, 5800, 2000, 3800, "partially_paid")
    assert not any("UPDATE staff_obligations" in sql for sql, _ in cursor.calls)
    assert not any("staff_payout_events" in sql and sql.startswith("INSERT") for sql, _ in cursor.calls)
    assert not hasattr(repository, "commit")


def test_effective_amount_is_shared_by_selected_payout_and_projection_rebuild_and_corrections_cannot_be_selected():
    cursor = Cursor()
    _load_obligation_rows(cursor, ("original",), lock=True)
    _projection_rows(cursor, ("original",))
    for sql, _ in cursor.calls:
        assert "handover_delta.source_obligation_identity=obligations.obligation_identity" in sql
        assert "handover_delta.case_no=obligations.case_no" in sql
        assert "handover_delta.staff_id=obligations.staff_id" in sql
    assert "obligation_identity NOT LIKE 'staff-handover:%%'" in cursor.calls[0][0]
    assert _projection_status({"obligation_amount_ntd": 5800, "net_paid_ntd": 8000}) is StaffPayableStatus.ANOMALY
