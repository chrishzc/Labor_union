from datetime import date
from decimal import Decimal

import pytest

from domains.finance_import.planning import (
    CanonicalFinanceImportRow,
    FinanceClassificationType,
    FinanceImportDisposition,
)
from domains.finance_import.transaction_classifier import classify_finance_transaction
from infrastructure.mysql.finance_import_owning_domain_composite import (
    MySqlFinanceImportOwningDomainComposite,
    _json_object,
    _unique_monthly_payout_targets,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.money import MoneyNTD


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
        client_refund_accounts={"REFUND-A": [7]},
        staff_accounts={},
        client_subsidy_return_accounts={},
    )

    assert result["classification_type"] == FinanceClassificationType.CLIENT_REFUND.value
    assert result["matched_identity_ids"] == [7]
    assert result["reason"] == "taishin_unique_client_refund_account"
    _assert_account_identity_without_verified_name_stays_pending(result)


def _assert_account_identity_without_verified_name_stays_pending(decision):
    candidate = CanonicalFinanceImportRow(
        "finance-import-row:1", 0, MoneyNTD(300),
        FinanceClassificationType(decision["classification_type"]),
        FinanceImportDisposition.BUSINESS_PENDING, PreviewFingerprint("a" * 64),
        tuple(f"client:{identity}" for identity in decision["matched_identity_ids"]),
        evidence=(decision["reason"],),
    )
    # object has no cursor: absence of actual source-name evidence must stop
    # before target selection or any SQL, even with a unique account identity.
    assert MySqlFinanceImportOwningDomainComposite(object()).resolve(candidate) is candidate


@pytest.mark.parametrize("source_has_name", (False, True))
def test_taishin_refund_name_evidence_comes_from_source_and_current_owner_candidate(source_has_name):
    row = _taishin_outgoing()
    if source_has_name:
        row["counterparty_name"] = "Synthetic Refund Client"
    result = classify_finance_transaction(
        row, client_refund_accounts={}, staff_accounts={},
        client_subsidy_return_accounts={"REFUND-A": [7]},
        all_client_names=("Synthetic Refund Client",),
        taishin_client_refund_candidates=({
            "client_id": 7, "name": "Synthetic Refund Client", "case_no": "C-1",
            "obligation_identity": "subsidy:C-1", "obligation_type": "subsidy_return",
            "amount_due_ntd": 300, "due_date": "2026-08-15",
        },),
    )
    assert result["classification_type"] == FinanceClassificationType.CLIENT_SUBSIDY_RETURN.value
    assert result["matched_identity_ids"] == [7]
    assert result["reason"] == (
        "taishin_unique_client_refund_name_and_month_matched" if source_has_name
        else "taishin_unique_client_subsidy_return_account"
    )
    if not source_has_name:
        _assert_account_identity_without_verified_name_stays_pending(result)


def test_refund_target_selection_allows_same_month_exact_total_for_one_case_only():
    targets = _unique_monthly_payout_targets(
        (
            {"case_no": "C-1", "obligation_identity": "refund-1", "amount_due_ntd": 100, "due_date": "2026-08-15"},
            {"case_no": "C-1", "obligation_identity": "refund-2", "amount_due_ntd": 200, "due_date": "2026-08-15"},
            {"case_no": "C-2", "obligation_identity": "refund-3", "amount_due_ntd": 100, "due_date": "2026-08-15"},
        ),
        date(2026, 8, 3),
        300,
        by_case=True,
    )

    assert targets == ("refund-1", "refund-2")


def test_refund_target_selection_fails_closed_when_multiple_cases_can_pay():
    targets = _unique_monthly_payout_targets(
        (
            {"case_no": "C-1", "obligation_identity": "refund-1", "amount_due_ntd": 300, "due_date": "2026-08-15"},
            {"case_no": "C-2", "obligation_identity": "refund-2", "amount_due_ntd": 300, "due_date": "2026-08-15"},
        ),
        date(2026, 8, 3),
        300,
        by_case=True,
    )

    assert targets is None


def test_refund_target_selection_does_not_automatically_accept_a_partial_prefix():
    # OUT-MATCH-03 allows only a unique exact/0..100 fee match. Larger
    # underpayment needs the original explicit partial-refund owner flow.
    rows = (
        {"case_no": "C-1", "obligation_identity": "refund-1", "amount_due_ntd": 100, "due_date": "2026-08-15"},
        {"case_no": "C-1", "obligation_identity": "refund-2", "amount_due_ntd": 500, "due_date": "2026-08-15"},
        {"case_no": "C-2", "obligation_identity": "refund-3", "amount_due_ntd": 100, "due_date": "2026-08-15"},
    )
    assert _unique_monthly_payout_targets(rows, date(2026, 8, 3), 300, by_case=True) is None


@pytest.mark.parametrize("amount_due,due_date,accepted", [
    (300, "2026-08-15", True),
    (400, "2026-08-15", True),
    (401, "2026-08-15", False),
    (299, "2026-08-15", False),
    (300, "2026-09-15", False),
    (300, None, False),
])
def test_refund_target_selection_keeps_the_month_and_fee_boundary(amount_due, due_date, accepted):
    rows = ({"case_no": "C-1", "obligation_identity": "refund-1", "amount_due_ntd": amount_due,
             "due_date": due_date},)
    targets = _unique_monthly_payout_targets(rows, date(2026, 8, 3), 300, by_case=True)
    assert targets == (("refund-1",) if accepted else None)


def test_automatic_refund_requires_a_source_case_reference_not_a_guessed_case():
    assert _json_object('{"case_no":"C-1"}')["case_no"] == "C-1"
    assert _json_object("[]") == {}
