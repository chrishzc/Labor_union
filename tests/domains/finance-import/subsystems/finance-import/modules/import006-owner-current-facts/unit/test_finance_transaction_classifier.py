from decimal import Decimal

import pytest

from domains.finance_import.transaction_classifier import classify_finance_transaction
from domains.finance_import.cancellation_code import extract_sinopac_memo_case_suffix


@pytest.mark.parametrize(("memo", "expected"), [
    ("HC115001服務人員", "115001"),
    ("A115001服務人員", "115001"),
    ("HC115001退款", "115001"),
    ("B015001付款", "015001"),
    ("HC115001／A115001", "115001"),
    ("HC115001／HC115002", None),
    ("HC11500", None),
    ("HC1150010", None),
    ("20261029", None),
    ("沒有案件尾碼", None),
    (None, None),
    ("ＨＣ１１５００１服務人員", "115001"),
    ("新竹市月子照顧服務人員職業工會 HC115001 轉帳時間 143022", "115001"),
    ("客戶退款 虛擬帳號99781699115001轉出", "115001"),
    ("115001月嫂薪資", "115001"),
    ("轉入0007510007056900 115001", "115001"),
])
def test_sinopac_memo_has_one_complete_six_digit_case_suffix(memo, expected):
    assert extract_sinopac_memo_case_suffix(memo) == expected


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


@pytest.mark.parametrize("identities,resolved", [([7], True), ([7, 8], False), ([], False)])
def test_staff_incoming_retains_unique_bank_binding_for_explicit_recovery_matching(identities, resolved):
    account = "88888888880007"
    result = classify_finance_transaction(
        _row(bank_references={"交易參考編號": account}), {}, {account: identities})
    assert result["classification_type"] == "non_business_review"
    assert result["resolved_counterparty_account"] == (account if resolved else None)
    assert result["matched_identity_ids"] == ([7] if resolved else [])


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


def test_taishin_government_return_is_available_for_human_period_selection():
    row = _row(format_id="taishin", direction="outgoing", credit=None,
               debit=Decimal("50"), memo="新竹市政府 多撥退回", counterparty_account=None)
    before = dict(row)
    result = classify_finance_transaction(row, {}, {})
    assert result["classification_type"] == "government_subsidy"
    assert result["matched_identity_ids"] == []
    assert result["reason"] == "taishin_government_return_memo"
    assert row == before


@pytest.mark.parametrize("owner", ["client", "staff", "subsidy_return"])
def test_taishin_government_memo_cannot_override_another_confirmed_recipient(owner):
    row = _row(format_id="taishin", direction="outgoing", credit=None,
               debit=Decimal("50"), memo="新竹市政府 多撥退回", counterparty_account="SYNTHETIC-001")
    accounts = {"SYNTHETIC-001": [7]}
    result = classify_finance_transaction(row,
        accounts if owner == "client" else {}, accounts if owner == "staff" else {},
        client_subsidy_return_accounts=accounts if owner == "subsidy_return" else {})
    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "counterparty_identity_type_conflict"


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


def test_sinopac_outgoing_memo_classifies_staff_salary():
    row = _row(
        format_id="sinopac",
        direction="outgoing",
        debit=Decimal("12000"),
        credit=None,
        memo="新竹市月子照顧服務人員職業工會 HC115001 服務人員薪資 轉帳時間 143022",
        bank_references={"交易參考編號": None},
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        staff_case_suffixes={"115001": [7]},
        client_refund_case_suffixes={},
    )
    assert result["classification_type"] == "staff_salary"
    assert result["matched_identity_ids"] == [7]


def test_taishin_outgoing_scenario_a_exact_match():
    row = _row(
        format_id="taishin",
        direction="outgoing",
        transaction_date="2026-10-15",
        debit=Decimal("10000"),
        credit=None,
        memo="林小美退款",
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_client_names=("林小美",),
        taishin_client_refund_candidates=(
            {
                "client_id": 101,
                "name": "林小美",
                "case_no": "115001",
                "obligation_identity": "refund:115001",
                "amount_due_ntd": 10000,
                "due_date": "2026-10-15",
            },
        ),
    )
    assert result["classification_type"] == "client_refund"
    assert result["matched_identity_ids"] == [101]
    assert result["reason"] == "taishin_unique_client_refund_name_and_month_matched"


def test_taishin_outgoing_scenario_b1_amount_mismatch_enters_review():
    row = _row(
        format_id="taishin",
        direction="outgoing",
        transaction_date="2026-10-14",
        debit=Decimal("9800"),  # 少付超過 100 元（差額 200 元），進入待核對
        credit=None,
        memo="林小美退款",
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_client_names=("林小美",),
        taishin_client_refund_candidates=(
            {
                "client_id": 101,
                "name": "林小美",
                "case_no": "115001",
                "obligation_identity": "refund:115001",
                "amount_due_ntd": 10000,
                "due_date": "2026-10-15",
            },
        ),
    )
    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "taishin_client_refund_amount_mismatch"


def test_taishin_outgoing_scenario_b1_transfer_fee_within_100_matches():
    row = _row(
        format_id="taishin",
        direction="outgoing",
        transaction_date="2026-10-14",
        debit=Decimal("9970"),  # 跨行手續費 30 元（<= 100 元），四階段配對成功
        credit=None,
        memo="林小美退款",
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_client_names=("林小美",),
        taishin_client_refund_candidates=(
            {
                "client_id": 101,
                "name": "林小美",
                "case_no": "115001",
                "obligation_identity": "refund:115001",
                "amount_due_ntd": 10000,
                "due_date": "2026-10-15",
            },
        ),
    )
    assert result["classification_type"] == "client_refund"
    assert result["matched_identity_ids"] == [101]
    assert result["reason"] == "taishin_unique_client_refund_name_month_fee_matched"


def test_taishin_same_name_clients_require_independent_identity_evidence():
    row = _row(
        format_id="taishin",
        direction="outgoing",
        transaction_date="2026-10-16",
        debit=Decimal("5000"),
        credit=None,
        memo="陳小芬",
    )
    # 即使月份和金額只符合其中一筆，仍須有證據辨識同名客戶。
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_client_names=("陳小芬",),
        taishin_client_refund_candidates=(
            {
                "client_id": 201,
                "name": "陳小芬",
                "case_no": "115002",
                "amount_due_ntd": 3000,
                "due_date": "2026-09-15",
            },
            {
                "client_id": 202,
                "name": "陳小芬",
                "case_no": "115003",
                "amount_due_ntd": 5000,
                "due_date": "2026-10-15",
            },
        ),
    )
    assert result["classification_type"] == "non_business_review"
    assert result["matched_identity_ids"] == []
    assert result["reason"] == "outgoing_client_refund_name_ambiguous"


def test_taishin_outgoing_scenario_b3_month_mismatch_enters_review():
    row = _row(
        format_id="taishin",
        direction="outgoing",
        transaction_date="2026-11-01",  # 11月出款，但應退款為 10 月
        debit=Decimal("10000"),
        credit=None,
        memo="林小美",
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_client_names=("林小美",),
        taishin_client_refund_candidates=(
            {
                "client_id": 101,
                "name": "林小美",
                "case_no": "115001",
                "amount_due_ntd": 10000,
                "due_date": "2026-10-15",
            },
        ),
    )
    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "taishin_client_refund_month_no_match"


def test_taishin_outgoing_longest_prefix_match():
    # 測試名冊中同時有 "王明" 與 "王明星"，備註為 "王明星退款" 應精確匹配 "王明星"
    row = _row(
        format_id="taishin",
        direction="outgoing",
        transaction_date="2026-10-15",
        debit=Decimal("2000"),
        credit=None,
        memo="王明星退款",
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_client_names=("王明", "王明星"),
        taishin_client_refund_candidates=(
            {
                "client_id": 301,
                "name": "王明星",
                "case_no": "115005",
                "amount_due_ntd": 2000,
                "due_date": "2026-10-15",
            },
        ),
    )
    assert result["classification_type"] == "client_refund"
    assert result["matched_identity_ids"] == [301]


def test_sinopac_outgoing_staff_payout_four_stage_fee_zero():
    # 永豐支出：月嫂姓名 + 同月份 + 差額 0 元（同行免手續費）
    row = _row(
        format_id="sinopac",
        direction="outgoing",
        transaction_date="2026-10-20",
        debit=Decimal("12000"),
        credit=None,
        memo="薪資-張美美",
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_staff_names=("張美美",),
        staff_payout_candidates=(
            {
                "staff_id": 88,
                "name": "張美美",
                "case_no": "115088",
                "obligation_identity": "staff-obl-88",
                "amount_due_ntd": 12000,
                "due_date": "2026-10-15",
            },
        ),
    )
    assert result["classification_type"] == "staff_salary"
    assert result["matched_identity_ids"] == [88]
    assert result["reason"] == "unique_staff_payout_name_and_month_matched"


def test_sinopac_outgoing_staff_payout_four_stage_fee_30():
    # 永豐支出：月嫂姓名 + 同月份 + 差額 30 元（跨行手續費 30 元由月嫂負擔）
    row = _row(
        format_id="sinopac",
        direction="outgoing",
        transaction_date="2026-10-20",
        debit=Decimal("11970"),  # 應付 12000，實付 11970，手續費 30
        credit=None,
        memo="張美美月嫂薪資",
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_staff_names=("張美美",),
        staff_payout_candidates=(
            {
                "staff_id": 88,
                "name": "張美美",
                "case_no": "115088",
                "obligation_identity": "staff-obl-88",
                "amount_due_ntd": 12000,
                "due_date": "2026-10-15",
            },
        ),
    )
    assert result["classification_type"] == "staff_salary"
    assert result["matched_identity_ids"] == [88]
    assert result["reason"] == "unique_staff_payout_name_month_fee_matched"


def test_taishin_outgoing_staff_payout_four_stage_fee_100():
    # 台新支出：月嫂姓名 + 同月份 + 差額 100 元（手續費上限 100 元）
    row = _row(
        format_id="taishin",
        direction="outgoing",
        transaction_date="2026-10-20",
        debit=Decimal("19900"),  # 應付 20000，實付 19900，手續費 100
        credit=None,
        memo="張美美",
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_staff_names=("張美美",),
        staff_payout_candidates=(
            {
                "staff_id": 88,
                "name": "張美美",
                "case_no": "115088",
                "obligation_identity": "staff-obl-88",
                "amount_due_ntd": 20000,
                "due_date": "2026-10-15",
            },
        ),
    )
    assert result["classification_type"] == "staff_salary"
    assert result["matched_identity_ids"] == [88]
    assert result["reason"] == "unique_staff_payout_name_month_fee_matched"


def test_taishin_outgoing_staff_payout_fee_over_100_enters_review():
    # 台新支出：少付 101 元（差額 101 元超過 100 元手續費上限），進入 review
    row = _row(
        format_id="taishin",
        direction="outgoing",
        transaction_date="2026-10-20",
        debit=Decimal("19899"),  # 差額 101 元
        credit=None,
        memo="張美美",
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_staff_names=("張美美",),
        staff_payout_candidates=(
            {
                "staff_id": 88,
                "name": "張美美",
                "case_no": "115088",
                "obligation_identity": "staff-obl-88",
                "amount_due_ntd": 20000,
                "due_date": "2026-10-15",
            },
        ),
    )
    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "outgoing_staff_payout_amount_mismatch"


def test_taishin_outgoing_staff_payout_overpayment_enters_review():
    # 台新支出：實付 12030 大於應付 12000（超付），進入 review
    row = _row(
        format_id="taishin",
        direction="outgoing",
        transaction_date="2026-10-20",
        debit=Decimal("12030"),
        credit=None,
        memo="張美美",
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_staff_names=("張美美",),
        staff_payout_candidates=(
            {
                "staff_id": 88,
                "name": "張美美",
                "case_no": "115088",
                "obligation_identity": "staff-obl-88",
                "amount_due_ntd": 12000,
                "due_date": "2026-10-15",
            },
        ),
    )
    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "outgoing_staff_payout_amount_mismatch"


def test_taishin_outgoing_staff_payout_month_mismatch_enters_review():
    # 交易日 10 月 vs 應付月份 11 月，月份不合進入 review
    row = _row(
        format_id="taishin",
        direction="outgoing",
        transaction_date="2026-10-20",
        debit=Decimal("11970"),
        credit=None,
        memo="張美美",
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_staff_names=("張美美",),
        staff_payout_candidates=(
            {
                "staff_id": 88,
                "name": "張美美",
                "case_no": "115088",
                "obligation_identity": "staff-obl-88",
                "amount_due_ntd": 12000,
                "due_date": "2026-11-15",
            },
        ),
    )
    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "outgoing_staff_payout_month_no_match"
    assert result["reason"] == "sinopac_unique_staff_case_suffix_in_memo"


def test_sinopac_outgoing_memo_classifies_client_refund():
    row = _row(
        format_id="sinopac",
        direction="outgoing",
        debit=Decimal("3000"),
        credit=None,
        memo="客戶退款 虛擬帳號99781699115001轉出",
        bank_references={"交易參考編號": None},
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        staff_case_suffixes={},
        client_refund_case_suffixes={"115001": [4]},
    )
    assert result["classification_type"] == "client_refund"
    assert result["matched_identity_ids"] == [4]
    assert result["reason"] == "sinopac_unique_client_refund_case_suffix_in_memo"


def test_sinopac_outgoing_memo_disambiguates_by_keywords():
    row_staff = _row(
        format_id="sinopac",
        direction="outgoing",
        debit=Decimal("12000"),
        credit=None,
        memo="HC115001月嫂薪資",
        bank_references={"交易參考編號": None},
    )
    res_staff = classify_finance_transaction(
        row_staff,
        client_refund_accounts={},
        staff_accounts={},
        staff_case_suffixes={"115001": [7]},
        client_refund_case_suffixes={"115001": [4]},
    )
    assert res_staff["classification_type"] == "staff_salary"
    assert res_staff["matched_identity_ids"] == [7]

    row_refund = _row(
        format_id="sinopac",
        direction="outgoing",
        debit=Decimal("3000"),
        credit=None,
        memo="HC115001客戶退款",
        bank_references={"交易參考編號": None},
    )
    res_refund = classify_finance_transaction(
        row_refund,
        client_refund_accounts={},
        staff_accounts={},
        staff_case_suffixes={"115001": [7]},
        client_refund_case_suffixes={"115001": [4]},
    )
    assert res_refund["classification_type"] == "client_refund"
    assert res_refund["matched_identity_ids"] == [4]


def test_sinopac_outgoing_fullwidth_memo():
    row = _row(
        format_id="sinopac",
        direction="outgoing",
        debit=Decimal("12000"),
        credit=None,
        memo="ＨＣ１１５００１服務人員薪資",
        bank_references={"交易參考編號": None},
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        staff_case_suffixes={"115001": [7]},
        client_refund_case_suffixes={},
    )
    assert result["classification_type"] == "staff_salary"
    assert result["matched_identity_ids"] == [7]


def test_taishin_outgoing_scenario_a_exact_match():
    row = _row(
        format_id="taishin",
        direction="outgoing",
        transaction_date="2026-10-15",
        debit=Decimal("10000"),
        credit=None,
        memo="林小美退款",
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_client_names=("林小美",),
        taishin_client_refund_candidates=(
            {
                "client_id": 101,
                "name": "林小美",
                "case_no": "115001",
                "obligation_identity": "refund:115001",
                "amount_due_ntd": 10000,
                "due_date": "2026-10-15",
            },
        ),
    )
    assert result["classification_type"] == "client_refund"
    assert result["matched_identity_ids"] == [101]
    assert result["reason"] == "taishin_unique_client_refund_name_and_month_matched"


def test_taishin_outgoing_scenario_b1_amount_mismatch_enters_review():
    row = _row(
        format_id="taishin",
        direction="outgoing",
        transaction_date="2026-10-14",
        debit=Decimal("9800"),  # 少付超過 100 元（差額 200 元），進入待核對
        credit=None,
        memo="林小美退款",
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_client_names=("林小美",),
        taishin_client_refund_candidates=(
            {
                "client_id": 101,
                "name": "林小美",
                "case_no": "115001",
                "obligation_identity": "refund:115001",
                "amount_due_ntd": 10000,
                "due_date": "2026-10-15",
            },
        ),
    )
    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "taishin_client_refund_amount_mismatch"


def test_taishin_outgoing_scenario_b1_transfer_fee_within_100_matches():
    row = _row(
        format_id="taishin",
        direction="outgoing",
        transaction_date="2026-10-14",
        debit=Decimal("9970"),  # 跨行手續費 30 元（<= 100 元），四階段配對成功
        credit=None,
        memo="林小美退款",
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_client_names=("林小美",),
        taishin_client_refund_candidates=(
            {
                "client_id": 101,
                "name": "林小美",
                "case_no": "115001",
                "obligation_identity": "refund:115001",
                "amount_due_ntd": 10000,
                "due_date": "2026-10-15",
            },
        ),
    )
    assert result["classification_type"] == "client_refund"
    assert result["matched_identity_ids"] == [101]
    assert result["reason"] == "taishin_unique_client_refund_name_month_fee_matched"


def test_taishin_same_name_clients_require_independent_identity_evidence():
    row = _row(
        format_id="taishin",
        direction="outgoing",
        transaction_date="2026-10-16",
        debit=Decimal("5000"),
        credit=None,
        memo="陳小芬",
    )
    # 即使月份和金額只符合其中一筆，仍須有證據辨識同名客戶。
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_client_names=("陳小芬",),
        taishin_client_refund_candidates=(
            {
                "client_id": 201,
                "name": "陳小芬",
                "case_no": "115002",
                "amount_due_ntd": 3000,
                "due_date": "2026-09-15",
            },
            {
                "client_id": 202,
                "name": "陳小芬",
                "case_no": "115003",
                "amount_due_ntd": 5000,
                "due_date": "2026-10-15",
            },
        ),
    )
    assert result["classification_type"] == "non_business_review"
    assert result["matched_identity_ids"] == []
    assert result["reason"] == "outgoing_client_refund_name_ambiguous"


def test_taishin_outgoing_scenario_b3_month_mismatch_enters_review():
    row = _row(
        format_id="taishin",
        direction="outgoing",
        transaction_date="2026-11-01",  # 11月出款，但應退款為 10 月
        debit=Decimal("10000"),
        credit=None,
        memo="林小美",
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_client_names=("林小美",),
        taishin_client_refund_candidates=(
            {
                "client_id": 101,
                "name": "林小美",
                "case_no": "115001",
                "amount_due_ntd": 10000,
                "due_date": "2026-10-15",
            },
        ),
    )
    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "taishin_client_refund_month_no_match"


def test_taishin_outgoing_longest_prefix_match():
    # 測試名冊中同時有 "王明" 與 "王明星"，備註為 "王明星退款" 應精確匹配 "王明星"
    row = _row(
        format_id="taishin",
        direction="outgoing",
        transaction_date="2026-10-15",
        debit=Decimal("2000"),
        credit=None,
        memo="王明星退款",
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_client_names=("王明", "王明星"),
        taishin_client_refund_candidates=(
            {
                "client_id": 301,
                "name": "王明星",
                "case_no": "115005",
                "amount_due_ntd": 2000,
                "due_date": "2026-10-15",
            },
        ),
    )
    assert result["classification_type"] == "client_refund"
    assert result["matched_identity_ids"] == [301]


def test_sinopac_outgoing_staff_payout_four_stage_fee_zero():
    # 永豐支出：月嫂姓名 + 同月份 + 差額 0 元（同行免手續費）
    row = _row(
        format_id="sinopac",
        direction="outgoing",
        transaction_date="2026-10-20",
        debit=Decimal("12000"),
        credit=None,
        memo="薪資-張美美",
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_staff_names=("張美美",),
        staff_payout_candidates=(
            {
                "staff_id": 88,
                "name": "張美美",
                "case_no": "115088",
                "obligation_identity": "staff-obl-88",
                "amount_due_ntd": 12000,
                "due_date": "2026-10-15",
            },
        ),
    )
    assert result["classification_type"] == "staff_salary"
    assert result["matched_identity_ids"] == [88]
    assert result["reason"] == "unique_staff_payout_name_and_month_matched"


def test_sinopac_outgoing_staff_payout_four_stage_fee_30():
    # 永豐支出：月嫂姓名 + 同月份 + 差額 30 元（跨行手續費 30 元由月嫂負擔）
    row = _row(
        format_id="sinopac",
        direction="outgoing",
        transaction_date="2026-10-20",
        debit=Decimal("11970"),  # 應付 12000，實付 11970，手續費 30
        credit=None,
        memo="張美美月嫂薪資",
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_staff_names=("張美美",),
        staff_payout_candidates=(
            {
                "staff_id": 88,
                "name": "張美美",
                "case_no": "115088",
                "obligation_identity": "staff-obl-88",
                "amount_due_ntd": 12000,
                "due_date": "2026-10-15",
            },
        ),
    )
    assert result["classification_type"] == "staff_salary"
    assert result["matched_identity_ids"] == [88]
    assert result["reason"] == "unique_staff_payout_name_month_fee_matched"


def test_taishin_outgoing_staff_payout_four_stage_fee_100():
    # 台新支出：月嫂姓名 + 同月份 + 差額 100 元（手續費上限 100 元）
    row = _row(
        format_id="taishin",
        direction="outgoing",
        transaction_date="2026-10-20",
        debit=Decimal("19900"),  # 應付 20000，實付 19900，手續費 100
        credit=None,
        memo="張美美",
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_staff_names=("張美美",),
        staff_payout_candidates=(
            {
                "staff_id": 88,
                "name": "張美美",
                "case_no": "115088",
                "obligation_identity": "staff-obl-88",
                "amount_due_ntd": 20000,
                "due_date": "2026-10-15",
            },
        ),
    )
    assert result["classification_type"] == "staff_salary"
    assert result["matched_identity_ids"] == [88]
    assert result["reason"] == "unique_staff_payout_name_month_fee_matched"


def test_taishin_outgoing_staff_payout_fee_over_100_enters_review():
    # 台新支出：少付 101 元（差額 101 元超過 100 元手續費上限），進入 review
    row = _row(
        format_id="taishin",
        direction="outgoing",
        transaction_date="2026-10-20",
        debit=Decimal("19899"),  # 差額 101 元
        credit=None,
        memo="張美美",
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_staff_names=("張美美",),
        staff_payout_candidates=(
            {
                "staff_id": 88,
                "name": "張美美",
                "case_no": "115088",
                "obligation_identity": "staff-obl-88",
                "amount_due_ntd": 20000,
                "due_date": "2026-10-15",
            },
        ),
    )
    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "outgoing_staff_payout_amount_mismatch"


def test_taishin_outgoing_staff_payout_overpayment_enters_review():
    # 台新支出：實付 12030 大於應付 12000（超付），進入 review
    row = _row(
        format_id="taishin",
        direction="outgoing",
        transaction_date="2026-10-20",
        debit=Decimal("12030"),
        credit=None,
        memo="張美美",
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_staff_names=("張美美",),
        staff_payout_candidates=(
            {
                "staff_id": 88,
                "name": "張美美",
                "case_no": "115088",
                "obligation_identity": "staff-obl-88",
                "amount_due_ntd": 12000,
                "due_date": "2026-10-15",
            },
        ),
    )
    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "outgoing_staff_payout_amount_mismatch"


def test_taishin_outgoing_staff_payout_month_mismatch_enters_review():
    # 交易日 10 月 vs 應付月份 11 月，月份不合進入 review
    row = _row(
        format_id="taishin",
        direction="outgoing",
        transaction_date="2026-10-20",
        debit=Decimal("11970"),
        credit=None,
        memo="張美美",
    )
    result = classify_finance_transaction(
        row,
        client_refund_accounts={},
        staff_accounts={},
        all_staff_names=("張美美",),
        staff_payout_candidates=(
            {
                "staff_id": 88,
                "name": "張美美",
                "case_no": "115088",
                "obligation_identity": "staff-obl-88",
                "amount_due_ntd": 12000,
                "due_date": "2026-11-15",
            },
        ),
    )
    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "outgoing_staff_payout_month_no_match"
