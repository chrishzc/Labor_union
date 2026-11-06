"""
File: test_finance_import_ingestion.py
Description: 驗證銀行對帳單匯入重播、分類事件唯一性與無關流水匯入前丟棄規則。
"""
import json
from decimal import Decimal

import pytest

from domains.finance_import.ingestion import InitialClassificationFacts
from shared_kernel.identities import ActorContext, IdempotencyKey
from subsystems.finance_import.ingestion import (
    _append_missing_classifications,
    _command_fingerprint,
    _filter_admitted_business_rows,
    _find_replay,
    _integer_tuple,
    _unique_rows,
)


class _Cursor:
    def __init__(self, row=None) -> None:
        self.row = row
        self.calls = []

    def execute(self, statement, params) -> None:
        self.calls.append((statement, params))

    def fetchone(self):
        return self.row


def test_replay_rehydrates_receipt_when_command_fingerprint_matches() -> None:
    actor = ActorContext("admin")
    digest = "a" * 64
    fingerprint = _command_fingerprint(digest, actor)
    cursor = _Cursor(
        {
            "command_fingerprint": fingerprint,
            "result_snapshot": json.dumps(
                {
                    "batch_identity": "finance-import-batch:7",
                    "source_content_digest": digest,
                    "source_row_count": 2,
                    "canonical_created_count": 1,
                    "duplicate_occurrence_count": 1,
                }
            ),
        }
    )

    receipt = _find_replay(cursor, IdempotencyKey("same-workbook"), fingerprint)

    assert receipt.batch_identity == "finance-import-batch:7"
    assert "FOR UPDATE" in cursor.calls[0][0]


def test_replay_rejects_idempotency_key_with_different_command() -> None:
    cursor = _Cursor({"command_fingerprint": "other", "result_snapshot": "{}"})

    with pytest.raises(ValueError, match="idempotency_conflict"):
        _find_replay(cursor, IdempotencyKey("same-workbook"), "expected")


def test_unique_rows_prefers_inserted_row_and_stable_identity_order() -> None:
    rows = _unique_rows(
        [
            {"row_id": 2, "result": "skipped_existing"},
            {"row_id": 1, "result": "skipped_existing"},
            {"row_id": 2, "result": "inserted"},
        ]
    )

    assert rows == (
        {"row_id": 1, "result": "skipped_existing"},
        {"row_id": 2, "result": "inserted"},
    )


@pytest.mark.parametrize("value", ["[3,2,3]", [3, 2, 3]])
def test_identity_ids_are_positive_unique_sorted_integers(value) -> None:
    assert _integer_tuple(value) == (2, 3)


@pytest.mark.parametrize("value", ["{}", [0]])
def test_identity_ids_reject_non_array_or_nonpositive_values(value) -> None:
    with pytest.raises(ValueError, match="matched_identity_ids"):
        _integer_tuple(value)


def test_duplicate_staged_row_still_creates_only_one_canonical_event(monkeypatch) -> None:
    cursor = _Cursor()
    monkeypatch.setattr(
        "subsystems.finance_import.ingestion._classification_exists",
        lambda *_arguments: False,
    )
    monkeypatch.setattr(
        "subsystems.finance_import.ingestion._load_initial_facts",
        lambda *_arguments: InitialClassificationFacts(
            4, "non_business_review", (), "source_requires_review"
        ),
    )
    monkeypatch.setattr(
        "subsystems.finance_import.ingestion.build_initial_classification",
        lambda _facts: object(),
    )
    inserted = []
    monkeypatch.setattr(
        "subsystems.finance_import.ingestion._insert_initial_classification",
        lambda *_arguments: inserted.append("event"),
    )
    monkeypatch.setattr(
        "subsystems.finance_import.ingestion._append_classification_outbox",
        lambda *_arguments: None,
    )

    created = _append_missing_classifications(
        cursor,
        7,
        [
            {"row_id": 4, "result": "skipped_existing"},
            {"row_id": 4, "result": "inserted"},
        ],
        ActorContext("admin"),
    )

    assert created == 1
    assert inserted == ["event"]


def _normalized_row(**overrides) -> dict[str, object]:
    base: dict[str, object] = {
        "format_id": "taishin",
        "source_file": "taishin.xlsx",
        "source_bank_account": "000000000001",
        "sheet_name": "交易明細查詢",
        "source_row": 2,
        "source_reference": None,
        "transaction_date": "2026-10-15",
        "transaction_time": "09:00:00",
        "posting_date": "2026-10-15",
        "value_date": None,
        "debit": None,
        "credit": Decimal("10000"),
        "direction": "incoming",
        "balance": Decimal("80000"),
        "currency": "TWD",
        "summary": "轉帳",
        "memo": "借款",
        "counterparty_name": None,
        "counterparty_account": None,
        "cancellation_code": None,
        "bank_references": {"sequence": "0001"},
        "warnings": [],
        "raw_payload": {"memo": "借款"},
    }
    base.update(overrides)
    return base


def test_filter_admitted_business_rows_discards_loan_and_unmatched_rows() -> None:
    identity_maps = {
        "client_refund_accounts": {},
        "staff_accounts": {"001234567890": [12]},
        "client_subsidy_return_accounts": {},
        "client_receipt_candidates": (),
        "staff_case_suffixes": {},
        "client_refund_case_suffixes": {},
        "all_client_names": (),
        "taishin_client_refund_candidates": (),
        "all_staff_names": ("王月嫂",),
        "staff_payout_candidates": (),
        "known_virtual_accounts": frozenset({"99781699115001"}),
        "known_case_suffixes": frozenset({"115001"}),
    }
    normalized = {
        "format_id": "taishin",
        "sheet_name": "交易明細查詢",
        "header_row": 2,
        "source_row_count": 5,
        "normalized_rows": [
            _normalized_row(
                source_row=2,
                credit=Decimal("50000"),
                memo="借款",
                bank_references={"sequence": "0001"},
            ),
            _normalized_row(
                source_row=3,
                credit=Decimal("18000"),
                memo="新竹市政府補助入款",
                bank_references={"sequence": "0002"},
            ),
            _normalized_row(
                source_row=4,
                direction="outgoing",
                debit=Decimal("12000"),
                credit=None,
                memo="月嫂薪資",
                bank_references={"sequence": "0003"},
            ),
            _normalized_row(
                format_id="sinopac",
                source_row=5,
                credit=Decimal("6000"),
                memo="虛擬帳號入帳",
                cancellation_code="99781699999999",
                bank_references={"銷帳編號": "99781699999999"},
            ),
            _normalized_row(
                format_id="sinopac",
                source_row=6,
                credit=Decimal("6000"),
                memo="虛擬帳號入帳",
                cancellation_code="99781699115001",
                bank_references={"銷帳編號": "99781699115001"},
            ),
        ],
    }

    admitted = _filter_admitted_business_rows(normalized, identity_maps)

    assert admitted["source_row_count"] == 2
    assert admitted["source_file"] == "taishin.xlsx"
    assert [row["memo"] for row in admitted["normalized_rows"]] == [
        "新竹市政府補助入款",
        "虛擬帳號入帳",
    ]
    assert admitted["normalized_rows"][1]["cancellation_code"] == "99781699115001"


@pytest.mark.parametrize("bank", ["sinopac", "taishin"])
@pytest.mark.parametrize("amount", [11899, 12001])
def test_known_same_month_payout_difference_is_admitted(bank, amount):
    row = _normalized_row(
        format_id=bank,
        transaction_date="2026-10-15",
        direction="outgoing",
        debit=Decimal(amount),
        credit=None,
        counterparty_name="Synthetic Staff",
        bank_references={},
    )
    identity_maps = {
        "staff_payout_candidates": ({
            "staff_id": 12,
            "name": "Synthetic Staff",
            "due_date": "2026-10-20",
            "amount_due_ntd": 12000,
        },),
    }
    admitted = _filter_admitted_business_rows({"normalized_rows": [row]}, identity_maps)

    assert admitted["normalized_rows"] == [row]


def test_filter_admitted_business_rows_preserves_source_file_when_all_rows_discarded() -> None:
    normalized = {
        "format_id": "taishin",
        "sheet_name": "交易明細查詢",
        "header_row": 2,
        "source_row_count": 1,
        "normalized_rows": [
            _normalized_row(
                source_file="only-loan.xlsx",
                credit=Decimal("10000"),
                memo="借款",
            )
        ],
    }

    admitted = _filter_admitted_business_rows(normalized, {})

    assert admitted["source_row_count"] == 0
    assert admitted["normalized_rows"] == []
    assert admitted["source_file"] == "only-loan.xlsx"
