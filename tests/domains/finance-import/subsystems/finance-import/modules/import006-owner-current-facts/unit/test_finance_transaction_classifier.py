from decimal import Decimal

import pytest

from domains.finance_import.transaction_classifier import classify_finance_transaction


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


@pytest.mark.parametrize(
    "overrides",
    [
        {"transaction_date": "not-a-date"},
        {"debit": "NOT_DECIMAL"},
        {"unexpected": "not-canonical"},
    ],
)
def test_malformed_normalized_row_is_rejected_by_canonical_validator(overrides):
    with pytest.raises(ValueError, match="normalized row validation failed"):
        classify_finance_transaction(_row(**overrides), {}, {})


@pytest.mark.parametrize(
    "overrides",
    [
        {
            "format_id": "sinopac",
            "cancellation_code": None,
            "bank_references": {"銷帳編號": "99781699115001"},
        },
        {
            "format_id": "legacy",
            "cancellation_code": "99781699115001",
            "bank_references": {},
        },
    ],
)
def test_incoming_uses_projected_client_virtual_account(overrides):
    result = classify_finance_transaction(_row(**overrides), {}, {})

    assert result == {
        "classification_type": "client_receipt",
        "matched_identity_ids": [],
        "resolved_counterparty_account": None,
        "reason": "sinopac_valid_virtual_account",
    }


def test_legacy_incoming_does_not_use_raw_bank_reference_fallback():
    result = classify_finance_transaction(
        _row(
            format_id="legacy",
            cancellation_code=None,
            bank_references={"銷帳編號": "99781699115001"},
        ),
        {},
        {},
    )

    assert result == {
        "classification_type": "non_business_review",
        "matched_identity_ids": [],
        "resolved_counterparty_account": None,
        "reason": "sinopac_invalid_or_missing_virtual_account",
    }


def test_sinopac_incoming_uses_cancellation_reference_instead_of_correction_marker():
    result = classify_finance_transaction(
        _row(
            cancellation_code="99781699115002",
            bank_references={"銷帳編號": "99781699115001測試甲"},
        ),
        {},
        {},
    )

    assert result["classification_type"] == "client_receipt"
    assert result["resolved_counterparty_account"] is None


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
        ({}, {"A": [1, 2]}, "counterparty_account_multiple_matches"),
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


def test_taishin_outgoing_never_matches_identity_by_name():
    result = classify_finance_transaction(
        _row(
            format_id="taishin",
            direction="outgoing",
            debit=Decimal("100"),
            credit=None,
            counterparty_name="服務人員甲",
            counterparty_account=None,
        ),
        {"服務人員甲": [7]},
        {"服務人員甲": [9]},
    )

    assert result == {
        "classification_type": "non_business_review",
        "matched_identity_ids": [],
        "resolved_counterparty_account": None,
        "reason": "counterparty_account_missing",
    }


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


def test_legacy_outgoing_requires_one_exact_staff_account():
    result = classify_finance_transaction(
        _row(
            format_id="legacy",
            direction="outgoing",
            debit=Decimal("100"),
            credit=None,
            memo="salary transfer to 001234567890",
            counterparty_account="001234567890",
            bank_references={"transaction_reference": "001234567890"},
        ),
        {},
        {"001234567890": [9]},
    )

    assert result["classification_type"] == "staff_salary"
    assert result["matched_identity_ids"] == [9]
    assert result["resolved_counterparty_account"] == "001234567890"


def test_legacy_outgoing_does_not_use_passbook_memo_as_account_source():
    result = classify_finance_transaction(
        _row(
            format_id="legacy",
            direction="outgoing",
            debit=Decimal("100"),
            credit=None,
            memo="monthly salary",
            bank_references={"存摺備註": "transfer 001234567890"},
        ),
        {},
        {"001234567890": [9]},
    )

    assert result == {
        "classification_type": "non_business_review",
        "matched_identity_ids": [],
        "resolved_counterparty_account": None,
        "reason": "sinopac_staff_account_no_match",
    }


def test_legacy_outgoing_uses_reference_despite_conflicting_memos():
    result = classify_finance_transaction(
        _row(
            format_id="legacy",
            direction="outgoing",
            debit=Decimal("100"),
            credit=None,
            memo="transfer 001234567890",
            bank_references={"transaction_reference": "001234567890", "存摺備註": "transfer 009876543210"},
        ),
        {},
        {"001234567890": [9], "009876543210": [10]},
    )

    assert result["classification_type"] == "staff_salary"
    assert result["matched_identity_ids"] == [9]
    assert result["resolved_counterparty_account"] == "001234567890"


def test_legacy_one_staff_with_multiple_registered_accounts_can_match_one():
    result = classify_finance_transaction(
        _row(
            format_id="legacy",
            direction="outgoing",
            debit=Decimal("100"),
            credit=None,
            memo="transfer 009876543210",
            bank_references={"transaction_reference": "009876543210"},
        ),
        {},
        {"001234567890": [9], "009876543210": [9, 9]},
    )

    assert result["classification_type"] == "staff_salary"
    assert result["matched_identity_ids"] == [9]


def test_legacy_multiple_accounts_for_same_staff_still_require_review():
    result = classify_finance_transaction(
        _row(
            format_id="legacy",
            direction="outgoing",
            debit=Decimal("100"),
            credit=None,
            memo="transfer 001234567890 and 009876543210",
            bank_references={"transaction_reference": "001234567890 and 009876543210"},
        ),
        {},
        {"001234567890": [9], "009876543210": [9]},
    )

    assert result == {
        "classification_type": "non_business_review",
        "matched_identity_ids": [],
        "resolved_counterparty_account": None,
        "reason": "sinopac_staff_account_no_match",
    }


def test_legacy_numeric_account_must_not_be_embedded_in_a_longer_number():
    result = classify_finance_transaction(
        _row(
            format_id="legacy",
            direction="outgoing",
            debit=Decimal("100"),
            credit=None,
            memo="transfer 91234567890",
            bank_references={"transaction_reference": "91234567890"},
        ),
        {},
        {"1234567890": [9]},
    )

    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "sinopac_staff_account_no_match"


def test_legacy_alphanumeric_account_must_not_be_embedded_in_a_longer_token():
    result = classify_finance_transaction(
        _row(
            format_id="legacy",
            direction="outgoing",
            debit=Decimal("100"),
            credit=None,
            memo="transfer X0012345678909",
            bank_references={"transaction_reference": "X0012345678909"},
        ),
        {},
        {"001234567890": [9]},
    )

    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "sinopac_staff_account_no_match"


@pytest.mark.parametrize(
    ("reference", "staff_accounts", "reason"),
    [
        (
            "001234567890 and 009876543210",
            {"001234567890": [9], "009876543210": [10]},
            "sinopac_staff_account_no_match",
        ),
        (
            "001234567890",
            {"001234567890": [9, 10]},
            "sinopac_staff_account_identity_ambiguous",
        ),
        (
            "transfer unknown",
            {"001234567890": [9]},
            "sinopac_staff_account_no_match",
        ),
    ],
)
def test_legacy_outgoing_ambiguous_or_missing_matches_require_review(
    reference, staff_accounts, reason
):
    result = classify_finance_transaction(
        _row(
            format_id="legacy",
            direction="outgoing",
            debit=Decimal("100"),
            credit=None,
            bank_references={"transaction_reference": reference},
        ),
        {},
        staff_accounts,
    )

    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == reason


def test_unknown_direction_requires_review():
    result = classify_finance_transaction(
        _row(
            direction="unknown",
            debit=None,
            credit=None,
            warnings=["direction_missing"],
        ),
        {},
        {},
    )

    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "direction_unknown"
