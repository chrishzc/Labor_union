"""
File: test_client_refund_return_anomaly_detail_guard.py
Description: 驗證退款退匯 detail allowlist 與 exact reversal guard 的 fail-closed 行為。
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from api.routes.anomaly_registry import _safe_display_snapshot
from domains.anomalies.registry import default_anomaly_registry
from domains.anomalies.root_fact_projection import (
    FinanceManualReviewRootFact,
    RootFactEventOrigin,
    build_finance_manual_review_candidate,
)
from subsystems.anomalies.finance_import_anomaly_consumer import (
    _is_exact_refund_return_reversal,
    _is_exact_refund_return_row,
    _require_refund_return_reversal,
)


def test_refund_return_detail_exposes_only_registered_safe_fields() -> None:
    root_fact = FinanceManualReviewRootFact(
        source_event_identity="client-refund-return-review:12",
        source_version=12,
        origin=RootFactEventOrigin.DOMAIN_EVENT,
        occurred_at=datetime(2026, 8, 4, tzinfo=timezone.utc),
        finance_import_row_id=71,
        finance_import_batch_id=4,
        active=True,
        integrity_blocker_active=False,
        amount_delta_ntd=0,
        affected_order_identities=("C-1",),
        affected_obligation_identities=("refund-1",),
        domain_blockers=("refund_return_requires_confirmed_reversal",),
        reason_codes=("refund_return_review_recorded",),
        definition_code="CLIENTREFUND-001",
        source_identity_override="finance-import-refund-return:71:41",
        original_refund_ledger_entry_id=41,
    )
    candidate = build_finance_manual_review_candidate(
        default_anomaly_registry(), root_fact
    )
    public = _safe_display_snapshot(
        "CLIENTREFUND-001",
        default_anomaly_registry().require("CLIENTREFUND-001").display_fields,
        candidate.root_fact_snapshot,
    )

    assert [field.key for field in public.fields] == [
        "affected_obligation_identities",
        "affected_order_identities",
        "amount_delta_ntd",
        "domain_blockers",
        "finance_import_batch_id",
        "finance_import_row_id",
        "integrity_blocker_active",
        "original_refund_ledger_entry_id",
        "reason_codes",
        "root_condition_active",
    ]
    assert all(field.key not in {"recovery_bindings", "source_version"} for field in public.fields)


def test_exact_refund_return_guard_accepts_same_case_and_amount() -> None:
    assert _is_exact_refund_return_reversal(_reversal_row(), 71, 41)
    assert _is_exact_refund_return_row(
        _reversal_row(), 71, expected_amount_ntd=300
    )
    _require_refund_return_reversal(_Connection(_reversal_row()), 71, 41)


@pytest.mark.parametrize(
    "changes",
    (
        {"bank_row_id": 72},
        {"bank_direction": "outgoing"},
        {"bank_credit": Decimal("0.00")},
        {"bank_debit": Decimal("1.00")},
        {"bank_classification_type": "client_refund"},
        {"bank_reconciliation_status": "pending"},
        {"bank_transaction_date": None},
        {"bank_currency": None},
        {"bank_currency": "USD"},
        {"bank_credit": Decimal("299.00")},
    ),
)
def test_exact_refund_return_guard_rejects_invalid_canonical_row(changes) -> None:
    row = _reversal_row()
    row.update(changes)
    assert not _is_exact_refund_return_row(
        row, 71, expected_amount_ntd=row["target_amount_ntd"]
    )


@pytest.mark.parametrize(
    "changes",
    (
        {"target_entry_id": 99},
        {"target_entry_type": "receipt"},
        {"reversal_row_id": 72},
        {"target_case_no": "C-2"},
        {"reversal_case_no": "C-2"},
        {"reversal_amount_ntd": 299},
        {"reversal_target_id": 99},
        {"reversal_entry_type": "reversal"},
    ),
)
def test_exact_refund_return_guard_rejects_wrong_linkage(changes) -> None:
    row = _reversal_row()
    row.update(changes)
    assert not _is_exact_refund_return_reversal(row, 71, 41)


def test_exact_refund_return_guard_rejects_missing_read() -> None:
    connection = _Connection(None)

    with pytest.raises(ValueError, match="refund_return_reversal_not_found"):
        _require_refund_return_reversal(connection, 71, 41)


def test_exact_refund_return_guard_propagates_read_failure() -> None:
    connection = _Connection(RuntimeError("database unavailable"))

    with pytest.raises(RuntimeError, match="database unavailable"):
        _require_refund_return_reversal(connection, 71, 41)


def _reversal_row() -> dict[str, object]:
    return {
        "bank_row_id": 71,
        "bank_transaction_date": datetime(2026, 8, 5, tzinfo=timezone.utc),
        "bank_debit": Decimal("0.00"),
        "bank_credit": Decimal("300.00"),
        "bank_direction": "incoming",
        "bank_currency": "TWD",
        "bank_classification_type": "client_refund_return",
        "bank_reconciliation_status": "reconciled",
        "target_entry_id": 41,
        "target_entry_type": "refund",
        "target_case_no": "C-1",
        "target_amount_ntd": 300,
        "reversal_entry_id": 42,
        "reversal_entry_type": "refund_reversal",
        "reversal_case_no": "C-1",
        "reversal_amount_ntd": 300,
        "reversal_row_id": 71,
        "reversal_target_id": 41,
    }


class _Connection:
    def __init__(self, result):
        self.result = result

    def cursor(self):
        return _Cursor(self.result)


class _Cursor:
    def __init__(self, result):
        self.result = result

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, *_):
        if isinstance(self.result, Exception):
            raise self.result

    def fetchone(self):
        return self.result
