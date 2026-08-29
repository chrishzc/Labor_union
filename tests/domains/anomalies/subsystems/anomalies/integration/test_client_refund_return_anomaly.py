"""
File: test_client_refund_return_anomaly.py
Description: 驗證客戶退款退匯異常的安全詳情、實際流水綁定與精確解除門禁。
"""

from datetime import datetime, timezone
from decimal import Decimal

from domains.anomalies.registry import default_anomaly_registry
from domains.anomalies.root_fact_projection import (
    FinanceManualReviewRootFact,
    RootFactEventOrigin,
    build_finance_manual_review_candidate,
)
from subsystems.anomalies.finance_import_anomaly_consumer import _root_facts


def test_confirmed_refund_return_review_creates_a_distinct_blocking_anomaly() -> None:
    root_fact = _review_root_fact()

    candidate = build_finance_manual_review_candidate(
        default_anomaly_registry(),
        root_fact,
    )

    assert candidate.desired.definition_code == "CLIENTREFUND-001"
    assert candidate.desired.active is True
    assert candidate.desired.fingerprint_values == {
        "finance_import_row_id": "71",
        "original_refund_ledger_entry_id": "41",
    }
    action = candidate.available_actions[0]
    assert action.action_key == "classify_client_refund_return"
    assert action.form_schema_key == "finance_import.correction.v1"
    assert action.source_bindings == {
        "finance_import_row_identity": "finance-import-row:71",
        "source_version": 12,
    }
    assert candidate.occurrence is not None


def test_refund_return_review_event_requires_a_confirmed_ledger_link() -> None:
    event = {
        "id": 9,
        "intent_type": "refund_return_review_recorded",
        "created_at": datetime(2026, 8, 4, tzinfo=timezone.utc),
    }
    payload = {
        "source_event_identity": "client-refund-return-review:12",
        "source_version": 12,
        "row_identity": "finance-import-row:71",
        "batch_identity": "finance-import-batch:4",
        "original_refund_ledger_entry_id": 41,
        "affected_order_identities": ["C-1"],
        "affected_obligation_identities": ["refund-1"],
        "bank_memo": "candidate evidence may be reviewed before this command",
    }

    root_fact = _root_facts(None, event | {"payload_snapshot": payload})[0]

    assert root_fact.definition_code == "CLIENTREFUND-001"
    assert root_fact.source_identity == "finance-import-refund-return:71:41"
    assert root_fact.original_refund_ledger_entry_id == 41
    assert root_fact.reason_codes == ("refund_return_review_recorded",)


def test_refund_return_resolution_requires_the_exact_formal_reversal():
    event = {
        "id": 13,
        "intent_type": "manual_correction_completed",
        "created_at": datetime(2026, 8, 5, tzinfo=timezone.utc),
        "payload_snapshot": {
            "row_identity": "finance-import-row:71",
            "batch_identity": "finance-import-batch:4",
            "classification_type": "client_refund_return",
            "refund_ledger_entry_identity": "client-ledger-entry:41",
        },
    }

    root_facts = _root_facts(_ReversalConnection(), event)

    assert root_facts[-1].definition_code == "CLIENTREFUND-001"
    assert root_facts[-1].active is False
    assert root_facts[-1].source_identity == "finance-import-refund-return:71:41"


def _review_root_fact() -> FinanceManualReviewRootFact:
    return FinanceManualReviewRootFact(
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


class _ReversalConnection:
    def cursor(self):
        return _ReversalCursor()


class _ReversalCursor:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, _sql, _params):
        return None

    def fetchone(self):
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
