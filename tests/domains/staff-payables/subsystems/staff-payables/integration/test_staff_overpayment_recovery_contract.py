"""
File: test_staff_overpayment_recovery_contract.py
Description: 驗證 Staff recovery evidence、strict Query 與零寫入邊界。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.staff_payout import get_staff_overpayment_recovery_matching_application
from api.main import app
from domains.staff_payables.overpayment_recovery import (
    StaffOverpaymentRecovery,
    StaffOverpaymentRecoveryStatus,
    StaffRecoveryIncomingBankFact,
)
from infrastructure.mysql.staff_overpayment_recovery_repository import (
    MySqlStaffOverpaymentRecoveryRepository,
)
from shared_kernel.errors import ErrorCategory
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.staff_payables.overpayment_recovery import (
    StaffOverpaymentRecoveryAction,
    StaffOverpaymentRecoveryApplyRequest,
    StaffOverpaymentRecoveryFacts,
    StaffOverpaymentRecoveryError,
    StaffOverpaymentRecoverySelection,
    StaffOverpaymentRecoveryWorkflow,
)
from subsystems.staff_payables.overpayment_recovery_query import (
    StaffOverpaymentRecoveryQueryView,
)


def _recovery(amount: int = 1_000, version: int = 4) -> StaffOverpaymentRecovery:
    return StaffOverpaymentRecovery(
        "staff-overpayment-recovery:1",
        7,
        MoneyNTD(amount),
        StaffOverpaymentRecoveryStatus.OPEN,
        version,
    )


def _incoming(amount: int = 1_000, staff_id: int = 7) -> StaffRecoveryIncomingBankFact:
    return StaffRecoveryIncomingBankFact(
        "finance-import-row:11",
        staff_id,
        MoneyNTD(amount),
        "2026-08-11",
        True,
    )


class _UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        return None


class _Repository:
    def __init__(self, facts):
        self.facts = facts
        self.receipt = None
        self.persisted = []

    def load(self, _selection, *, for_update):
        self.persisted.append(("load", for_update))
        return self.facts

    def find_receipt(self, _key):
        return self.receipt

    def persist(self, _request, preview, receipt, fingerprint):
        self.persisted.append(("persist", preview.candidate.bank_fact_identity))
        from subsystems.staff_payables.overpayment_recovery import (
            StoredStaffOverpaymentRecoveryReceipt,
        )

        self.receipt = StoredStaffOverpaymentRecoveryReceipt(fingerprint, receipt)


def test_same_key_evidence_change_is_idempotency_conflict() -> None:
    selection = StaffOverpaymentRecoverySelection(
        "staff-overpayment-recovery:1", StaffOverpaymentRecoveryAction.COLLECT,
        "finance-import-row:11",
        matching_identity="staff-recovery-match:1", matching_version=1,
    )
    repository = _Repository(StaffOverpaymentRecoveryFacts(_recovery(), 9, _incoming()))
    workflow = StaffOverpaymentRecoveryWorkflow(repository, _UnitOfWork)
    preview = workflow.preview(selection, CorrelationId("preview"), "evidence-a")
    request = StaffOverpaymentRecoveryApplyRequest(
        selection, ExpectedVersion(4), ExpectedVersion(9), preview.fingerprint,
        IdempotencyKey("same-key"), ActorContext("operator"), "reason",
        CorrelationId("apply"), "evidence-a",
    )
    workflow.apply(request)

    changed = StaffOverpaymentRecoveryApplyRequest(
        selection, ExpectedVersion(4), ExpectedVersion(9), preview.fingerprint,
        IdempotencyKey("same-key"), ActorContext("operator"), "reason",
        CorrelationId("apply"), "evidence-b",
    )
    with pytest.raises(StaffOverpaymentRecoveryError) as raised:
        workflow.apply(changed)
    assert raised.value.error.category is ErrorCategory.IDEMPOTENCY_MISMATCH


def test_missing_matching_evidence_is_http_422_without_workflow_call() -> None:
    class _MustNotRun:
        def preview(self, *_args, **_kwargs):
            raise AssertionError("missing evidence must fail before workflow")

    app.dependency_overrides[require_system_admin] = lambda: object()
    app.dependency_overrides[get_staff_overpayment_recovery_matching_application] = lambda: _MustNotRun()
    try:
        response = TestClient(app).post(
            "/api/v1/staff-payables/overpayment-recoveries/matching/preview",
            json={"recovery_identity": "r", "finance_import_row_id": 1},
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 422


class _Cursor:
    def __init__(self, owner: int = 7) -> None:
        self.owner = owner
        self.statements: list[str] = []
        self._result: object = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement: str, _params=()) -> None:
        self.statements.append(statement)
        assert statement.lstrip().upper().startswith("SELECT")
        if "FROM staff_overpayment_recoveries" in statement:
            self._result = {
                "recovery_identity": "recovery-1",
                "staff_id": self.owner,
                "remaining_amount_ntd": 500,
                "status": "open",
                "aggregate_version": 2,
                "source_bank_fact_identities": '["finance-import-row:11"]',
                "source_payout_event_ids": '["payout-event:9"]',
                "source_obligation_identities": '["obligation:3"]',
            }
        elif "FROM staff_payable_accounts" in statement:
            self._result = {"aggregate_version": 8}
        else:
            self._result = [{
                "matching_identity": "matching-1",
                "staff_id": self.owner,
                "matching_version": 1,
                "finance_import_row_id": 11,
            }]

    def fetchone(self):
        result = self._result
        if isinstance(result, list):
            return result[0] if result else None
        return result

    def fetchall(self):
        return self._result if isinstance(self._result, list) else []


class _Connection:
    def __init__(self, owner: int = 7) -> None:
        self.cursor_value = _Cursor(owner)

    def cursor(self):
        return self.cursor_value


def test_query_is_redacted_and_zero_write() -> None:
    connection = _Connection()
    result = MySqlStaffOverpaymentRecoveryRepository(connection).query_recovery(7, "recovery-1")
    assert result.remaining_amount_ntd == 500
    assert result.matchings[0].matching_identity == "matching-1"
    assert all(value.startswith("redacted:") for value in result.source_bank_fact_references)
    assert result.matchings[0].finance_import_row_identity.startswith("redacted:")
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in connection.cursor_value.statements)


def test_query_owner_mismatch_fails_closed() -> None:
    with pytest.raises(ValueError, match="staff_overpayment_recovery_owner_mismatch"):
        MySqlStaffOverpaymentRecoveryRepository(_Connection(owner=9)).query_recovery(7, "recovery-1")


@pytest.mark.parametrize(
    ("status", "remaining"),
    (("open", 0), ("partially_recovered", 0), ("recovered", 1), ("adjusted", 1)),
)
def test_query_rejects_status_remaining_contradiction(status, remaining) -> None:
    with pytest.raises(ValueError, match="staff_overpayment_recovery_query_invalid"):
        StaffOverpaymentRecoveryQueryView(
            7, "recovery-1", remaining, status, 2, 8, (), (), (), (),
        )
