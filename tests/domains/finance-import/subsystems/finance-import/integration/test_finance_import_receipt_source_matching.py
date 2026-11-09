from decimal import Decimal

from domains.finance_import.planning import (
    CanonicalFinanceImportRow,
    FinanceClassificationType,
    FinanceImportDisposition,
    defer_overlapping_client_receipts,
)
from domains.finance_import.transaction_classifier import classify_finance_transaction
from infrastructure.mysql.client_receipt_reconciliation_repository import (
    _bank_row_is_eligible,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.money import MoneyNTD


def test_name_account_and_amount_cannot_replace_the_complete_virtual_account():
    result = classify_finance_transaction(
        _incoming_row(),
        {},
        {},
        client_receipt_candidates=(
            {"client_id": 7, "name": "王小美", "account": "001234", "open_amounts": (3000,)},
        ),
    )

    assert result == {
        "classification_type": "non_business_review",
        "matched_identity_ids": [],
        "resolved_counterparty_account": None,
        "reason": "sinopac_invalid_or_missing_virtual_account",
    }


def test_multiple_name_account_candidates_do_not_create_a_receipt_path():
    result = classify_finance_transaction(
        _incoming_row(),
        {},
        {},
        client_receipt_candidates=(
            {"client_id": 7, "name": "王小美", "account": "001234", "open_amounts": (3000,)},
            {"client_id": 8, "name": "王小美", "account": "001234", "open_amounts": (3000,)},
        ),
    )

    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "sinopac_invalid_or_missing_virtual_account"


def test_complete_virtual_account_takes_priority_over_unrelated_name_account_candidates():
    row = {**_incoming_row(), 'bank_references': {'銷帳編號': '99781699115001'}}
    result = classify_finance_transaction(row, {}, {}, known_virtual_accounts=frozenset({'99781699115001'}),
        client_receipt_candidates=({'client_id': 99, 'name': '王小美', 'account': '001234', 'open_amounts': (3000,)},))
    assert result['classification_type'] == 'client_receipt'
    assert result['matched_identity_ids'] == []
    assert result['reason'] == 'sinopac_valid_virtual_account'


def test_two_full_payments_for_one_period_require_combined_overage_review_not_duplicate_review():
    first, second = defer_overlapping_client_receipts(
        (_resolved_row("finance-import-row:11"), _resolved_row("finance-import-row:12"))
    )

    assert first.disposition is FinanceImportDisposition.BUSINESS_PENDING
    assert second.disposition is FinanceImportDisposition.BUSINESS_PENDING
    assert first.client_receipt_review.reason == second.client_receipt_review.reason == "client_receipt_overpaid"
    assert first.evidence == second.evidence == ("sinopac_valid_virtual_account",)
    assert second.available_actions == ("resolve_owning_domain_target",)


def test_combined_review_retains_all_original_rows_and_unrelated_targets():
    rows = defer_overlapping_client_receipts(
        (
            _resolved_row("finance-import-row:11", "deposit:C-1"),
            _resolved_row("finance-import-row:12", "deposit:C-1"),
            _resolved_row("finance-import-row:13", "deposit:C-2"),
        )
    )

    assert tuple(row.row_identity for row in rows) == (
        "finance-import-row:11",
        "finance-import-row:12",
        "finance-import-row:13",
    )
    assert tuple(row.disposition for row in rows) == (
        FinanceImportDisposition.BUSINESS_PENDING,
        FinanceImportDisposition.BUSINESS_PENDING,
        FinanceImportDisposition.CREATE,
    )


def test_partial_and_topup_for_one_period_keep_both_sources_without_a_duplicate_flag():
    from dataclasses import replace
    from domains.finance_import.planning import ClientReceiptReviewDiagnostic
    rows = tuple(replace(_resolved_row(f'finance-import-row:{i}'), amount=MoneyNTD(amount),
                         disposition=FinanceImportDisposition.BUSINESS_PENDING,
                         client_receipt_review=ClientReceiptReviewDiagnostic('client_receipt_underpaid'))
                 for i, amount in ((11,9000),(12,1000)))
    result = defer_overlapping_client_receipts(rows)
    assert result == rows
    assert sum(row.amount.amount for row in result) == 10000
    assert all('suspected_duplicate_business_match' not in row.evidence for row in result)


def test_old_client_identity_without_a_virtual_account_or_selected_obligation_is_ineligible():
    row = {
        "format_id": "legacy",
        "direction": "incoming",
        "debit": 0,
        "credit": 3000,
        "classification_type": "client_receipt",
        "authoritative_classification_type": "client_receipt",
        "authoritative_reason": "unrecognized_historical_reason",
        "authoritative_target_identities": ["client:7"],
        "selected_client_id": 7,
        "reconciliation_status": "pending",
        "transaction_date": "2026-08-04",
        "ledger_entry_id": None,
        "currency": "TWD",
        "cancellation_code": None,
        "bank_references": {},
    }

    assert _bank_row_is_eligible(row, "115000007") is False


def test_other_client_identity_cannot_cross_the_selected_client_boundary():
    row = {
        "format_id": "legacy",
        "direction": "incoming",
        "debit": 0,
        "credit": 3000,
        "classification_type": "client_receipt",
        "authoritative_classification_type": "client_receipt",
        "authoritative_reason": "unrecognized_historical_reason",
        "authoritative_target_identities": ["client:8"],
        "selected_client_id": 7,
        "reconciliation_status": "pending",
        "transaction_date": "2026-08-04",
        "ledger_entry_id": None,
        "currency": "TWD",
        "cancellation_code": None,
        "bank_references": {},
    }

    assert _bank_row_is_eligible(row, "115000007") is False


def _incoming_row():
    return {
        "format_id": "sinopac",
        "source_file": "fixture.xlsx",
        "source_bank_account": "123",
        "sheet_name": "Sheet1",
        "source_row": 2,
        "source_reference": None,
        "transaction_date": "2026-08-04",
        "transaction_time": "09:00:00",
        "posting_date": "2026-08-04",
        "value_date": "2026-08-04",
        "direction": "incoming",
        "credit": Decimal("3000"),
        "debit": Decimal("0"),
        "balance": Decimal("5000"),
        "currency": "TWD",
        "counterparty_name": "王小美",
        "counterparty_account": "001234",
        "memo": "月嫂服務款",
        "summary": "網路轉帳",
        "cancellation_code": None,
        "bank_references": {},
        "warnings": [],
        "raw_payload": {},
    }


def _resolved_row(row_identity, target="deposit:C-1"):
    return CanonicalFinanceImportRow(
        row_identity,
        1,
        MoneyNTD(3000),
        FinanceClassificationType.CLIENT_RECEIPT,
        FinanceImportDisposition.CREATE,
        PreviewFingerprint("a" * 64),
        (target,),
        ("sinopac_valid_virtual_account",),
        ("preview_apply",),
    )
