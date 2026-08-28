"""
File: test_staff_payout_repository_recovery.py
Description: 驗證 Staff payout recovery producer 的 canonical Finance Import row identity。
"""

from __future__ import annotations

import pytest

from domains.staff_payables.reconciliation import (
    StaffOverpaymentRecoveryCandidate,
    StaffPayableStatus,
    StaffPayoutCandidate,
    StaffPayoutDifferenceMode,
    StaffPayoutEventStatus,
    StaffPayoutEventType,
    StaffPayoutLedgerEventCandidate,
)
from infrastructure.mysql.staff_payout_repository import (
    MySqlStaffPayoutRepository,
    _bank_facts_version,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.staff_payables.payout_reconciliation import (
    StaffPayoutApplyRequest,
    StaffPayoutSelection,
)


class _Cursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, params=()) -> None:
        self.calls.append((statement, tuple(params)))


class _Connection:
    def __init__(self) -> None:
        self.cursor_value = _Cursor()

    def cursor(self):
        return self.cursor_value


def _candidate(
    source_identity: str,
    *,
    source_identities: tuple[str, ...] | None = None,
) -> StaffPayoutCandidate:
    event = StaffPayoutLedgerEventCandidate(
        "payout-event:1",
        StaffPayoutEventType.PAYOUT,
        StaffPayoutEventStatus.SUCCEEDED,
        7,
        MoneyNTD(1_100),
        finance_import_fact_identity=source_identity,
    )
    recovery = StaffOverpaymentRecoveryCandidate(
        "staff-overpayment-recovery:1",
        7,
        MoneyNTD(100),
        source_identities or (source_identity,),
        ("obligation:1",),
    )
    return StaffPayoutCandidate(
        7,
        MoneyNTD(1_100),
        MoneyNTD(1_000),
        (),
        PreviewFingerprint("a" * 64),
        (event,),
        (),
        StaffPayableStatus.RECOVERY_REQUIRED,
        StaffPayoutDifferenceMode.OVERPAYMENT,
        recovery,
    )


def _repository() -> tuple[MySqlStaffPayoutRepository, _Connection]:
    connection = _Connection()
    repository = MySqlStaffPayoutRepository(connection)
    repository._event_ids["payout-event:1"] = 101
    repository.bind_apply_request(
        StaffPayoutApplyRequest(
            StaffPayoutSelection(
                StaffPayoutEventType.PAYOUT,
                ("11",),
                ("obligation:1",),
                difference_mode=StaffPayoutDifferenceMode.OVERPAYMENT,
            ),
            ExpectedVersion(0),
            ExpectedVersion(0),
            PreviewFingerprint("b" * 64),
            IdempotencyKey("recovery-write"),
            ActorContext("operator"),
            "record overpayment",
            CorrelationId("recovery-write"),
        )
    )
    return repository, connection


def test_recovery_producer_persists_canonical_finance_import_row_identity() -> None:
    repository, connection = _repository()

    repository.append_overpayment_recovery(_candidate("11"))

    recovery_params = connection.cursor_value.calls[0][1]
    assert recovery_params[4] == '["finance-import-row:11"]'


def test_recovery_producer_accepts_existing_canonical_identity() -> None:
    repository, connection = _repository()

    repository.append_overpayment_recovery(_candidate("finance-import-row:11"))

    assert connection.cursor_value.calls[0][1][4] == '["finance-import-row:11"]'


@pytest.mark.parametrize("source_identity", ("0", "-1", "bank:11", "finance-import-row:0"))
def test_recovery_producer_fails_closed_for_non_positive_or_invalid_identity(
    source_identity: str,
) -> None:
    repository, connection = _repository()

    with pytest.raises(ValueError, match="staff_overpayment_recovery_source_bank_fact_invalid"):
        repository.append_overpayment_recovery(_candidate(source_identity))

    assert connection.cursor_value.calls == []


def test_recovery_producer_fails_closed_when_canonicalization_creates_duplicates() -> None:
    repository, connection = _repository()

    with pytest.raises(ValueError, match="staff_overpayment_recovery_source_bank_fact_invalid"):
        repository.append_overpayment_recovery(
            _candidate(
                "11",
                source_identities=("11", "finance-import-row:11"),
            )
        )

    assert connection.cursor_value.calls == []


def test_bank_facts_version_is_safe_across_the_json_javascript_boundary() -> None:
    row = {
        "id": 4,
        "dedup_fingerprint": "f" * 64,
        "transaction_date": "2026-08-15",
        "debit": 12_000,
        "credit": 0,
        "direction": "outgoing",
        "currency": "TWD",
        "resolved_counterparty_account": "masked-account",
        "classification_type": "staff_payout",
        "reconciliation_status": "unmatched",
        "payout_event_id": None,
    }

    version = _bank_facts_version((row,), None)

    assert 0 <= version <= (2**53) - 1
