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


@pytest.mark.parametrize('amounts,cash,due,reason', [
    ((6000,7000),5000,'2026-10-15','staff_payout_amount_mismatch'),
    ((12000,),12000,None,'due_date_missing'),
    ((12000,12000),12000,'2026-10-15','outgoing_staff_payout_multiple_fee_matches'),
    ((6000,6000),12000,'2026-10-15','unique_staff_payout_name_month_fee_matched'),
])
def test_sinopac_staff_failure_categories_follow_actual_matching_step(amounts,cash,due,reason):
    from domains.finance_import.transaction_classifier import _classify_outgoing_by_name_month_fee
    name='合成服務甲'
    source=_row(direction='outgoing',debit=Decimal(cash),credit=None,memo=name,transaction_date='2026-10-20')
    candidates=tuple(dict(staff_id=7,name=name,case_no='SYNTHETIC',due_date=due,amount_due_ntd=amount) for amount in amounts)
    result=_classify_outgoing_by_name_month_fee(source,[name],candidates,[],())
    assert result['reason']==reason
    assert result['matched_identity_ids']==[7]


@pytest.mark.parametrize('amounts,cash,due,trans,currency,reason', [
    ((12000,),12000,'2026-10-15',None,'TWD','bank_transaction_date_missing'),
    ((12000,),12000,'2026-10-15','2026-10-20','USD','bank_currency_not_twd'),
    ((12000,),12000,None,'2026-10-20','TWD','due_date_missing'),
    ((12000,),12000,'2026-09-15','2026-10-20','TWD','outgoing_staff_payout_month_no_match'),
    ((6000,7000),5000,'2026-10-15','2026-10-20','TWD','staff_payout_amount_mismatch'),
    ((12000,12000),12000,'2026-10-15','2026-10-20','TWD','outgoing_staff_payout_multiple_fee_matches'),
    ((7000,5000),11900,'2026-10-15','2026-10-20','TWD','unique_staff_payout_name_month_fee_matched'),
])
def test_taishin_staff_classification_reports_the_actual_step(amounts,cash,due,trans,currency,reason):
    name='合成月嫂甲'
    source=_row(format_id='taishin',direction='outgoing',debit=Decimal(cash),credit=None,memo=name,transaction_date=trans,currency=currency)
    candidates=tuple(dict(staff_id=7,name=name,case_no='SYNTHETIC',due_date=due,amount_due_ntd=amount) for amount in amounts)
    result=classify_finance_transaction(source,{}, {}, {},all_staff_names=(name,),staff_payout_candidates=candidates)
    assert result['reason']==reason and result['matched_identity_ids']==[7]


@pytest.mark.parametrize('amounts,cash,due,transaction_date,reason', [
    ((12000,),12000,'2026-10-15',None,'bank_transaction_date_missing'),
    ((12000,),12000,None,'2026-10-20','due_date_missing'),
    ((12000,),12000,'2026-09-15','2026-10-20','outgoing_client_refund_month_no_match'),
    ((6000,7000),5000,'2026-10-15','2026-10-20','outgoing_client_refund_amount_mismatch'),
    ((12000,12000),12000,'2026-10-15','2026-10-20','outgoing_client_refund_multiple_fee_matches'),
    ((6000,6000),12000,'2026-10-15','2026-10-20','unique_client_refund_name_month_fee_matched'),
    ((6000,6000),11900,'2026-10-15','2026-10-20','unique_client_refund_name_month_fee_matched'),
])
def test_sinopac_refund_failure_is_not_inferred_from_raw_candidate_count(amounts,cash,due,transaction_date,reason):
    from domains.finance_import.transaction_classifier import _classify_outgoing_by_name_month_fee
    name='合成退款客戶'
    source=_row(direction='outgoing',debit=Decimal(cash),credit=None,memo=name,transaction_date=transaction_date)
    candidates=tuple(dict(client_id=7,name=name,case_no='SYNTHETIC',obligation_type='refund',due_date=due,amount_due_ntd=amount) for amount in amounts)
    result=_classify_outgoing_by_name_month_fee(source,(),(),(name,),candidates)
    assert result['reason']==reason
    assert result['matched_identity_ids']==[7]


def test_sinopac_shared_name_requires_case_evidence_even_with_reference_account():
    name='合成服務甲'
    candidates=tuple(dict(staff_id=staff,name=name,case_no='SYNTHETIC',due_date='2026-10-15',amount_due_ntd=12000) for staff in (7,8))
    source=_row(direction='outgoing',debit=Decimal(12000),credit=None,memo=name,transaction_date='2026-10-20',
                bank_references={'交易參考編號':'0000007001'})
    result=classify_finance_transaction(source,{}, {'0000007001':[7]},all_staff_names=[name,name],staff_payout_candidates=candidates)
    assert result['classification_type']=='non_business_review'
    assert result['reason']=='outgoing_staff_payout_name_ambiguous'
    unresolved=classify_finance_transaction(source,{}, {},all_staff_names=[name,name],staff_payout_candidates=candidates)
    assert unresolved['classification_type']=='non_business_review'
    assert unresolved['reason']=='outgoing_staff_payout_name_ambiguous'


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


@pytest.mark.parametrize(("memo", "expected"), [
    ("115001", "non_business_review"),
    ("115001其他文字", "non_business_review"),
    ("115001 115002", "non_business_review"),
    ("合成客戶退款", "non_business_review"),
    ("合成人員甲", "staff_salary"),
    ("合成人員甲客戶退款", "staff_salary"),
    ("合成人員甲115001", "staff_salary"),
    ("合成人員甲115999", "staff_salary"),
    ("合成人員甲115001 115002", "staff_salary"),
    ("115001月嫂薪資", "non_business_review"),
    ("月嫂薪資", "non_business_review"),
    (None, "non_business_review"),
])
def test_taishin_case_suffix_waits_for_manual_scheme_and_name_only_staff_path_remains(memo, expected):
    row = _row(format_id="taishin", direction="outgoing", debit=Decimal("100"), credit=None,
               memo=memo, counterparty_name="合成人員甲", counterparty_account="A")
    result = classify_finance_transaction(row, {"A": [7]}, {"A": [9]},
        all_staff_names=("合成人員甲",),
        staff_payout_candidates=({"staff_id": 9, "name": "合成人員甲", "amount_due_ntd": 100,
                                  "due_date": row["transaction_date"]},),
        all_client_names=("合成客戶",), known_case_suffixes=frozenset({"115001", "115002"}))
    assert result["classification_type"] == expected
    assert result["matched_identity_ids"] == ([9] if expected == "staff_salary" else [])
    assert result["resolved_counterparty_account"] == ("A" if expected == "staff_salary" else None)


def test_taishin_memo_name_shared_by_two_staff_is_not_admitted():
    row = _row(format_id="taishin", direction="outgoing", debit=Decimal("100"), credit=None,
               memo="合成月嫂補助款")
    result = classify_finance_transaction(row, {}, {}, all_staff_names=("合成月嫂", "合成月嫂"),
        staff_payout_candidates=({"staff_id": 9, "name": "合成月嫂", "amount_due_ntd": 100,
                                  "due_date": row["transaction_date"]},))
    assert result["classification_type"] == "non_business_review"
    assert result["reason"] == "outgoing_staff_payout_name_ambiguous"


@pytest.mark.parametrize("suffix", ["", "HC115001", "ＨＣ１１５００１"])
def test_taishin_identifies_memo_staff_name_before_checking_open_payables(suffix):
    row = _row(format_id="taishin", direction="outgoing", debit=Decimal("100"), credit=None,
               memo="合成人員甲" + suffix)
    result = classify_finance_transaction(row, {}, {}, all_staff_names=("合成人員甲",),
                                          staff_name_identities={"合成人員甲": (9,)})
    assert result["classification_type"] == "staff_legacy_subsidy"
    assert result["matched_identity_ids"] == [9]
    assert result["reason"] == "taishin_staff_subsidy_identity_pending_preflight"


@pytest.mark.parametrize('memo,kind', [('HC115001雇主補助款','client_subsidy_return'),
    ('ＨＣ１１５００１客戶補助返還','client_subsidy_return'), ('HC115001','non_business_review')])
def test_taishin_customer_purpose_can_precede_manual_scheme_and_refund(memo,kind):
    result=classify_finance_transaction(_row(format_id='taishin',direction='outgoing',debit=Decimal(11970),credit=None,memo=memo),
        {},{},client_case_suffixes={'115001':[17]},known_case_suffixes=frozenset({'115001'}))
    assert result['classification_type']==kind
    assert result['matched_identity_ids']==([17] if kind=='client_subsidy_return' else [])


def test_taishin_duplicate_staff_names_cannot_be_disambiguated_by_unpaid_amount():
    result=classify_finance_transaction(_row(format_id='taishin',direction='outgoing',debit=Decimal(12000),credit=None,memo='合成人員甲補助款'),
        {},{},all_staff_names=('合成人員甲','合成人員甲'),staff_name_identities={'合成人員甲':(9,10)},
        staff_payout_candidates=({'staff_id':9,'name':'合成人員甲','amount_due_ntd':12000,'case_no':'115001','due_date':'2026-07-13'},))
    assert result['classification_type']=='non_business_review'


@pytest.mark.parametrize('named_ids,kind', [((17,), 'client_subsidy_return'),
    ((18,), 'non_business_review'), ((17,18), 'client_subsidy_return')])
@pytest.mark.parametrize('memo', ['HC115001合成家長補助返還', '合成家長 ＨＣ１１５００１ GB,轉入0000000000000003'])
def test_taishin_named_customer_subsidy_uses_the_same_unique_case_identity(named_ids,kind,memo):
    result=classify_finance_transaction(_row(format_id='taishin',direction='outgoing',
        debit=Decimal(11970),credit=None,memo=memo), {},{},
        client_case_suffixes={'115001':[17]},known_case_suffixes=frozenset({'115001'}),
        client_name_identities={'合成家長':named_ids})
    assert result['classification_type']==kind


@pytest.mark.parametrize('memo, ids, kind', [
    ('合成家長 GB,轉入0000000000000003', (17,), 'client_subsidy_return'),
    ('合成家長 GB,轉入0000000000000003', (17, 18), 'client_subsidy_return'),
    ('合成家長 HC115001 HC115002', (17,), 'non_business_review'),
    ('合成家長 HC115099', (17,), 'non_business_review'),
])
def test_taishin_customer_name_without_a_case_reference(memo, ids, kind):
    row = _row(format_id='taishin', direction='outgoing', debit=Decimal(11970), credit=None, memo=memo)
    result = classify_finance_transaction(row, {}, {}, client_name_identities={'合成家長': ids},
        known_case_suffixes=frozenset({'115001'}))
    assert result['classification_type'] == kind
    assert result['matched_identity_ids'] == (list(ids) if kind == 'client_subsidy_return' else [])


@pytest.mark.parametrize('format_id,reference_key',[('sinopac','交易參考編號'),('legacy','transaction_reference')])
def test_sinopac_staff_case_is_resolved_without_checking_the_reference_account(format_id,reference_key):
    row=_row(format_id=format_id,direction='outgoing',debit=Decimal(12000),credit=None,memo='HC115001服務人員',
        bank_references={reference_key:'123456789012'})
    result=classify_finance_transaction(row,{}, {'123456789012':[10]},staff_case_suffixes={'115001':[9]})
    assert result['classification_type']=='staff_salary'
    assert result['matched_identity_ids']==[9]
    assert result['reason']=='sinopac_unique_staff_case_suffix_in_memo'


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
    assert result["classification_type"] == "staff_salary"
    assert result["reason"] == "staff_payout_amount_mismatch"
    assert result["matched_identity_ids"] == [88]


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
    assert result["classification_type"] == "staff_salary"
    assert result["reason"] == "staff_payout_amount_mismatch"
    assert result["matched_identity_ids"] == [88]


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
    assert result["classification_type"] == "staff_salary"
    assert result["reason"] == "outgoing_staff_payout_month_no_match"
    assert result["matched_identity_ids"] == [88]
