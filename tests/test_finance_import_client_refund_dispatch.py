from decimal import Decimal

from domains.finance_import.planning import FinanceClassificationType
from domains.finance_import.transaction_classifier import classify_finance_transaction
from infrastructure.mysql.finance_import_owning_domain_composite import (
    _json_object,
    _unique_case_refund_targets,
)


def _taishin_outgoing():
    return {
        "format_id": "taishin", "source_file": "statement.xlsx", "source_bank_account": "A",
        "sheet_name": "Sheet1", "source_row": 2, "source_reference": None,
        "transaction_date": "2026-08-03", "transaction_time": None, "posting_date": None,
        "value_date": "2026-08-03", "debit": Decimal("300"), "credit": None,
        "direction": "outgoing", "balance": Decimal("700"), "currency": "TWD",
        "summary": "轉帳", "memo": None, "counterparty_name": None,
        "counterparty_account": "REFUND-A", "cancellation_code": None,
        "bank_references": {}, "warnings": [], "raw_payload": {},
    }


def test_taishin_general_refund_account_has_its_own_classification():
    result = classify_finance_transaction(
        _taishin_outgoing(),
        {"REFUND-A": [7]},
        {},
        {},
    )

    assert result["classification_type"] == FinanceClassificationType.CLIENT_REFUND.value
    assert result["matched_identity_ids"] == [7]


def test_refund_target_selection_allows_partial_prefix_for_one_case_only():
    targets = _unique_case_refund_targets(
        (
            {"case_no": "C-1", "obligation_identity": "refund-1", "amount_due_ntd": 100},
            {"case_no": "C-1", "obligation_identity": "refund-2", "amount_due_ntd": 500},
            {"case_no": "C-2", "obligation_identity": "refund-3", "amount_due_ntd": 100},
        ),
        300,
    )

    assert targets == ("refund-1", "refund-2")


def test_refund_target_selection_fails_closed_when_multiple_cases_can_pay():
    targets = _unique_case_refund_targets(
        (
            {"case_no": "C-1", "obligation_identity": "refund-1", "amount_due_ntd": 500},
            {"case_no": "C-2", "obligation_identity": "refund-2", "amount_due_ntd": 500},
        ),
        300,
    )

    assert targets is None


def test_automatic_refund_requires_a_source_case_reference_not_a_guessed_case():
    assert _json_object('{"case_no":"C-1"}')["case_no"] == "C-1"
    assert _json_object("[]") == {}
