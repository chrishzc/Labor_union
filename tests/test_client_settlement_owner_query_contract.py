"""
File: test_client_settlement_owner_query_contract.py
Description: 驗證客戶退款與補助退還查詢只暴露 owner 可用的精確出款候選。
"""

from datetime import date

from api.schemas.client_refund_reversal import ClientRefundReversalQueryView
from domains.client_finance.client_refund_reversal import ClientRefundPurpose
from domains.client_finance.client_refund_reversal import (
    ClientRefundBankFact,
    ClientRefundObligation,
    build_client_refund_candidate,
)
from infrastructure.mysql.client_refund_reversal_repository import (
    _load_refund_obligation_rows,
    _query_outgoing_bank_facts,
)
from shared_kernel.money import MoneyNTD


def _bank_row(row_id: int, classification: str, account: str) -> dict[str, object]:
    return {
        "id": row_id,
        "transaction_date": date(2026, 8, 27),
        "debit": 1200,
        "credit": 0,
        "direction": "outgoing",
        "currency": "TWD",
        "reconciliation_status": "pending",
        "resolved_counterparty_account": account,
        "effective_classification_type": classification,
        "ledger_entry_id": None,
    }


def _obligation(identity: str, kind: str, account: str) -> dict[str, object]:
    return {
        "obligation_identity": identity,
        "obligation_type": kind,
        "amount_due_ntd": 1200,
        "due_date": date(2026, 8, 1),
        "bank_account": account,
    }


def test_outgoing_candidates_are_purpose_and_recipient_bound() -> None:
    rows = (
        _bank_row(11, "client_refund", "refund-account"),
        _bank_row(12, "client_subsidy_return", "subsidy-account"),
    )
    refund = _query_outgoing_bank_facts(
        rows,
        (_obligation("refund:C-1", "refund", "refund-account"),),
        ClientRefundPurpose.CUSTOMER_REFUND,
    )
    subsidy = _query_outgoing_bank_facts(
        rows,
        (_obligation("subsidy:C-1", "subsidy_return", "subsidy-account"),),
        ClientRefundPurpose.SUBSIDY_RETURN,
    )

    assert [item["finance_import_row_id"] for item in refund] == [11]
    assert refund[0]["eligible_obligation_identities"] == ("refund:C-1",)
    assert [item["finance_import_row_id"] for item in subsidy] == [12]
    assert subsidy[0]["eligible_obligation_identities"] == ("subsidy:C-1",)


def test_outgoing_candidate_without_exact_recipient_is_not_exposed() -> None:
    facts = _query_outgoing_bank_facts(
        (_bank_row(13, "client_refund", "different-account"),),
        (_obligation("refund:C-2", "refund", "expected-account"),),
        ClientRefundPurpose.CUSTOMER_REFUND,
    )
    assert facts == ()


def test_refund_query_http_contract_keeps_refund_and_subsidy_return_separate() -> None:
    view = ClientRefundReversalQueryView.model_validate(
        {
            "case_no": "C-3",
            "account_version": 4,
            "refund_obligations": [
                {
                    "obligation_identity": "refund:C-3",
                    "obligation_type": "refund",
                    "amount_due_ntd": 1200,
                    "due_date": "2026-08-01",
                }
            ],
            "subsidy_return_obligations": [
                {
                    "obligation_identity": "subsidy:C-3",
                    "obligation_type": "subsidy_return",
                    "amount_due_ntd": 2400,
                    "due_date": "2026-08-02",
                }
            ],
            "refund_bank_facts": [],
            "subsidy_return_bank_facts": [],
            "reversal_targets": [],
            "refund_return_targets": [],
        }
    )
    assert view.refund_obligations[0].obligation_type == "refund"
    assert view.subsidy_return_obligations[0].obligation_type == "subsidy_return"


def test_customer_refund_branch_can_exactly_settle_payable_adjustment() -> None:
    candidate = build_client_refund_candidate(
        "C-4",
        (
            ClientRefundBankFact(
                "21", "C-4", MoneyNTD(1200), "2026-08-27"
            ),
        ),
        (
            ClientRefundObligation(
                "adjustment:C-4", "C-4", MoneyNTD(1200), "adjustment"
            ),
        ),
        ClientRefundPurpose.CUSTOMER_REFUND,
    )
    assert candidate.affected_obligations == ("adjustment:C-4",)
    assert candidate.amount.amount == 1200


def test_customer_refund_loader_includes_adjustment_but_not_subsidy_return() -> None:
    class Cursor:
        def __init__(self) -> None:
            self.sql = ""
            self.parameters: tuple[object, ...] = ()

        def execute(self, sql, parameters) -> None:
            self.sql = sql
            self.parameters = tuple(parameters)

        def fetchall(self):
            return ()

    selection = type(
        "Selection",
        (),
        {
            "obligation_identities": ("adjustment:C-5",),
            "case_no": "C-5",
            "refund_purpose": ClientRefundPurpose.CUSTOMER_REFUND,
        },
    )()
    cursor = Cursor()

    _load_refund_obligation_rows(cursor, selection, False)

    assert "obligation.obligation_type IN (%s,%s)" in cursor.sql
    assert cursor.parameters[-2:] == ("adjustment", "refund")
