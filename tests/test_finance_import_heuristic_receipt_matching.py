from decimal import Decimal

from domains.finance_import.planning import (
    CanonicalFinanceImportRow,
    FinanceClassificationType,
    FinanceImportDisposition,
    mark_suspected_duplicate_client_receipts,
)
from domains.finance_import.transaction_classifier import classify_finance_transaction
from infrastructure.mysql.client_receipt_reconciliation_repository import (
    _bank_row_is_eligible,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.money import MoneyNTD


def test_name_account_and_amount_build_one_client_receipt_candidate_without_virtual_account():
    result = classify_finance_transaction(
        _incoming_row(),
        {},
        {},
        client_receipt_candidates=(
            {"client_id": 7, "name": "王小美", "account": "001234", "open_amounts": (3000,)},
        ),
    )

    assert result == {
        "classification_type": "client_receipt",
        "matched_identity_ids": [7],
        "resolved_counterparty_account": None,
        "reason": "client_receipt_heuristic:name+account+amount",
    }


def test_two_equally_plausible_clients_require_review_instead_of_auto_settlement():
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
    assert result["reason"] == "client_receipt_heuristic_ambiguous"


def test_second_different_bank_row_for_the_same_obligation_stays_pending():
    first, second = mark_suspected_duplicate_client_receipts(
        (_resolved_row("finance-import-row:11"), _resolved_row("finance-import-row:12"))
    )

    assert first.disposition is FinanceImportDisposition.CREATE
    assert second.disposition is FinanceImportDisposition.BUSINESS_PENDING
    assert second.evidence[-1] == "suspected_duplicate_business_match"
    assert second.available_actions == ("review_suspected_duplicate_business_match",)


def test_unique_heuristic_candidate_can_enter_the_canonical_receipt_workflow():
    row = {
        "format_id": "legacy",
        "direction": "incoming",
        "debit": 0,
        "credit": 3000,
        "classification_type": "client_receipt",
        "authoritative_classification_type": "client_receipt",
        "authoritative_reason": "client_receipt_heuristic:name+amount",
        "authoritative_target_identities": ["client:7"],
        "selected_client_id": 7,
        "reconciliation_status": "pending",
        "transaction_date": "2026-08-04",
        "ledger_entry_id": None,
        "currency": "TWD",
        "cancellation_code": None,
        "bank_references": {},
    }

    assert _bank_row_is_eligible(row, "115000007") is True


def test_heuristic_candidate_cannot_cross_the_selected_client_boundary():
    row = {
        "format_id": "legacy",
        "direction": "incoming",
        "debit": 0,
        "credit": 3000,
        "classification_type": "client_receipt",
        "authoritative_classification_type": "client_receipt",
        "authoritative_reason": "client_receipt_heuristic:name+amount",
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


def _resolved_row(row_identity):
    return CanonicalFinanceImportRow(
        row_identity,
        1,
        MoneyNTD(3000),
        FinanceClassificationType.CLIENT_RECEIPT,
        FinanceImportDisposition.CREATE,
        PreviewFingerprint("a" * 64),
        ("deposit:C-1",),
        ("client_receipt_heuristic:name+amount",),
        ("preview_apply",),
    )
