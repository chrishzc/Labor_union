from decimal import Decimal

import pytest

from services.finance_transaction_classifier import classify_finance_transaction


def _row(**overrides):
    row = {
        "format_id": "sinopac",
        "source_file": "statement.xlsx",
        "source_bank_account": "001",
        "sheet_name": "transactions",
        "source_row": 4,
        "source_reference": None,
        "transaction_date": "2026-07-13",
        "transaction_time": "13:31:00",
        "posting_date": "2026-07-13",
        "value_date": "2026-07-13",
        "debit": None,
        "credit": Decimal("100"),
        "direction": "incoming",
        "balance": Decimal("1000"),
        "currency": "TWD",
        "summary": "transfer",
        "memo": None,
        "counterparty_name": None,
        "counterparty_account": None,
        "cancellation_code": None,
        "bank_references": {"銷帳編號": "99781699115001"},
        "warnings": [],
        "raw_payload": {"銷帳編號": "99781699115001"},
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize("format_id", ["sinopac", "legacy"])
def test_sinopac_incoming_requires_exact_client_virtual_account(format_id):
    result = classify_finance_transaction(_row(format_id=format_id), {}, {})

    assert result == {
        "classification_type": "client_receipt",
        "matched_identity_ids": [],
        "resolved_counterparty_account": None,
        "reason": "sinopac_valid_virtual_account",
    }


@pytest.mark.parametrize(
    "virtual_account",
    [
        "99781600115001",
        "99781699１１５００１",
    ],
)
def test_sinopac_incoming_with_invalid_virtual_account_requires_review(virtual_account):
    result = classify_finance_transaction(
        _row(bank_references={"銷帳編號": virtual_account}), {}, {}
    )

    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "sinopac_invalid_or_missing_virtual_account"


def test_taishin_incoming_only_classifies_government_keyword():
    government = classify_finance_transaction(
        _row(format_id="taishin", memo="新竹市政府補助撥款"), {}, {}
    )
    other = classify_finance_transaction(
        _row(format_id="taishin", memo="其他存入"), {}, {}
    )

    assert government["classification_type"] == "government_subsidy"
    assert other["classification_type"] == "non_business_review"


def test_taishin_outgoing_exactly_one_client_match_is_subsidy_return():
    result = classify_finance_transaction(
        _row(
            format_id="taishin",
            direction="outgoing",
            debit=Decimal("100"),
            credit=None,
            counterparty_account="C001",
        ),
        {"C001": [7]},
        {},
    )

    assert result["classification_type"] == "client_subsidy_return"
    assert result["matched_identity_ids"] == [7]
    assert result["resolved_counterparty_account"] == "C001"


def test_taishin_outgoing_exactly_one_staff_match_is_legacy_subsidy():
    result = classify_finance_transaction(
        _row(
            format_id="taishin",
            direction="outgoing",
            debit=Decimal("100"),
            credit=None,
            counterparty_account="S001",
        ),
        {},
        {"S001": [9]},
    )

    assert result["classification_type"] == "staff_legacy_subsidy"
    assert result["matched_identity_ids"] == [9]
    assert result["resolved_counterparty_account"] == "S001"


@pytest.mark.parametrize(
    ("client_accounts", "staff_accounts", "reason"),
    [
        ({}, {}, "counterparty_account_no_match"),
        ({"A": [1, 2]}, {}, "counterparty_account_multiple_matches"),
        ({"A": [1]}, {"A": [2]}, "counterparty_identity_type_conflict"),
    ],
)
def test_taishin_outgoing_zero_multiple_or_cross_type_matches_require_review(
    client_accounts, staff_accounts, reason
):
    result = classify_finance_transaction(
        _row(
            format_id="taishin",
            direction="outgoing",
            debit=Decimal("100"),
            credit=None,
            counterparty_account="A",
        ),
        client_accounts,
        staff_accounts,
    )

    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == reason


def test_sinopac_outgoing_without_confirmed_account_never_guesses_from_name():
    result = classify_finance_transaction(
        _row(
            direction="outgoing",
            debit=Decimal("100"),
            credit=None,
            counterparty_name="服務人員甲",
            counterparty_account=None,
        ),
        {},
        {"S001": [9]},
    )

    assert result == {
        "classification_type": "non_business_review",
        "matched_identity_ids": [],
        "resolved_counterparty_account": None,
        "reason": "sinopac_staff_account_no_match",
    }


def test_sinopac_outgoing_requires_one_exact_staff_account():
    result = classify_finance_transaction(
        _row(
            direction="outgoing",
            debit=Decimal("100"),
            credit=None,
            memo="salary transfer to S001",
            counterparty_account="S001",
        ),
        {},
        {"S001": [9]},
    )

    assert result["classification_type"] == "staff_salary"
    assert result["matched_identity_ids"] == [9]
    assert result["resolved_counterparty_account"] == "S001"


def test_sinopac_outgoing_uses_passbook_memo_only_when_memo_has_no_match():
    result = classify_finance_transaction(
        _row(
            direction="outgoing",
            debit=Decimal("100"),
            credit=None,
            memo="monthly salary",
            bank_references={"存摺備註": "transfer S001"},
        ),
        {},
        {"S001": [9]},
    )

    assert result == {
        "classification_type": "staff_salary",
        "matched_identity_ids": [9],
        "resolved_counterparty_account": "S001",
        "reason": "sinopac_unique_staff_account_in_passbook_memo",
    }


def test_sinopac_outgoing_does_not_mix_primary_and_backup_candidates():
    result = classify_finance_transaction(
        _row(
            direction="outgoing",
            debit=Decimal("100"),
            credit=None,
            memo="transfer S001",
            bank_references={"存摺備註": "transfer S002"},
        ),
        {},
        {"S001": [9], "S002": [10]},
    )

    assert result["classification_type"] == "staff_salary"
    assert result["matched_identity_ids"] == [9]
    assert result["resolved_counterparty_account"] == "S001"


def test_sinopac_one_staff_with_multiple_registered_accounts_can_match_one():
    result = classify_finance_transaction(
        _row(
            direction="outgoing",
            debit=Decimal("100"),
            credit=None,
            memo="transfer S002",
        ),
        {},
        {"S001": [9], "S002": [9, 9]},
    )

    assert result["classification_type"] == "staff_salary"
    assert result["matched_identity_ids"] == [9]


def test_sinopac_multiple_accounts_for_same_staff_still_require_review():
    result = classify_finance_transaction(
        _row(
            direction="outgoing",
            debit=Decimal("100"),
            credit=None,
            memo="transfer S001 and S002",
        ),
        {},
        {"S001": [9], "S002": [9]},
    )

    assert result == {
        "classification_type": "non_business_review",
        "matched_identity_ids": [],
        "resolved_counterparty_account": None,
        "reason": "sinopac_multiple_staff_accounts_matched",
    }


def test_sinopac_numeric_account_must_not_be_embedded_in_a_longer_number():
    result = classify_finance_transaction(
        _row(
            direction="outgoing",
            debit=Decimal("100"),
            credit=None,
            memo="transfer 91234567890",
        ),
        {},
        {"1234567890": [9]},
    )

    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "sinopac_staff_account_no_match"


def test_sinopac_alphanumeric_account_must_not_be_embedded_in_a_longer_token():
    result = classify_finance_transaction(
        _row(
            direction="outgoing",
            debit=Decimal("100"),
            credit=None,
            memo="transfer XS0019",
        ),
        {},
        {"S001": [9]},
    )

    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "sinopac_staff_account_no_match"


@pytest.mark.parametrize(
    ("memo", "staff_accounts", "reason"),
    [
        (
            "transfer S001 and S002",
            {"S001": [9], "S002": [10]},
            "sinopac_multiple_staff_accounts_matched",
        ),
        (
            "transfer S001",
            {"S001": [9, 10]},
            "sinopac_staff_account_identity_ambiguous",
        ),
        (
            "transfer unknown",
            {"S001": [9]},
            "sinopac_staff_account_no_match",
        ),
    ],
)
def test_sinopac_outgoing_ambiguous_or_missing_matches_require_review(
    memo, staff_accounts, reason
):
    result = classify_finance_transaction(
        _row(
            direction="outgoing",
            debit=Decimal("100"),
            credit=None,
            memo=memo,
        ),
        {},
        staff_accounts,
    )

    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == reason


def test_unknown_direction_requires_review():
    result = classify_finance_transaction(
        _row(direction="unknown", debit=None, credit=None), {}, {}
    )

    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "direction_unknown"
