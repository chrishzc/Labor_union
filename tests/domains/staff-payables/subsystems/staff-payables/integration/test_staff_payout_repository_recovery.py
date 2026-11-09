"""
File: test_staff_payout_repository_recovery.py
Description: 驗證銀行來源帳戶投影與 recovery producer 的 canonical Finance Import row identity。
"""

from __future__ import annotations

import pytest
from datetime import date

from domains.staff_payables.reconciliation import (
    StaffOverpaymentRecoveryCandidate,
    StaffPayableStatus,
    StaffPayoutCandidate,
    StaffPayoutDifferenceMode,
    StaffPayoutEventStatus,
    StaffPayoutEventType,
    StaffPayoutLedgerEventCandidate,
    StaffPayableFacts,
    build_staff_payout_candidate,
)
from infrastructure.mysql.staff_payout_repository import (
    MySqlStaffPayoutRepository,
    _bank_facts_version,
    _load_selected_bank_rows,
    _load_bank_accounts,
    _outgoing_bank_fact,
    _verify_taishin_memo_recipients,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.staff_payables.payout_reconciliation import (
    StaffPayoutApplyRequest,
    StaffPayoutSelection,
)


class _Cursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, params=()) -> None:
        self.calls.append((statement, tuple(params)))


@pytest.mark.parametrize('lock', [False, True])
@pytest.mark.parametrize('occurred_on,currency,code', [
    (None, 'TWD', 'bank_transaction_date_missing'),
    (date(2026, 11, 8), 'USD', 'bank_currency_not_twd'),
])
def test_staff_payout_source_reason_is_specific_for_preview_and_fresh_apply(lock, occurred_on, currency, code):
    from types import SimpleNamespace
    repository = MySqlStaffPayoutRepository(object())
    selection = SimpleNamespace(event_type=StaffPayoutEventType.PAYOUT)
    with pytest.raises(ValueError, match=code):
        repository._assemble_facts(object(), selection, 7, 0,
            ({'transaction_date': occurred_on, 'currency': currency},), (), lock)


@pytest.mark.parametrize('paid,client_remaining,subsidy_remaining', [
    ((), 18000, 12000),
    (({'format_id': 'sinopac', 'settled_ntd': 18000},), 0, 12000),
    (({'format_id': 'taishin', 'settled_ntd': 12000},), 18000, 0),
    (({'format_id': 'sinopac', 'settled_ntd': 18000}, {'format_id': 'taishin', 'settled_ntd': 12000}), 0, 0),
    (({'format_id': None, 'settled_ntd': 100},), None, None),
])
def test_funding_projection_uses_settlement_links_by_bank_including_fee_and_reopen(paid, client_remaining, subsidy_remaining):
    from infrastructure.mysql.staff_payout_repository import query_staff_funding_portions
    class Cursor(_Cursor):
        def __init__(self):
            super().__init__()
            self.responses = iter((
                ({'funding_kind': 'client', 'amount_ntd': 18000, 'due_date': date(2026, 10, 15)},
                 {'funding_kind': 'subsidy', 'amount_ntd': 12000, 'due_date': date(2026, 10, 15)}), paid))
        def fetchall(self):
            return next(self.responses)
    cursor = Cursor()
    portions = query_staff_funding_portions(cursor, 'obligation:1', lock=True)
    assert {p.funding_kind: p.remaining_ntd for p in portions} == {'client': client_remaining, 'subsidy': subsidy_remaining}
    assert 'FOR UPDATE' in cursor.calls[0][0]
    assert 'reversal_of_event_id' in cursor.calls[1][0]


class _Connection:
    def __init__(self) -> None:
        self.cursor_value = _Cursor()

    def cursor(self):
        return self.cursor_value


class _BankReadCursor(_Cursor):
    def __init__(self, source, account_owner=7):
        super().__init__()
        self.source = source
        self.account_owner = account_owner
        self.rows = []

    def execute(self, statement, params=()):
        super().execute(statement, params)
        if 'FROM finance_import_rows fir' in statement:
            self.rows = [self.source]
        elif 'FROM staff_bank_accounts' in statement:
            self.rows = ([{'account_no': '000012345678', 'staff_id': self.account_owner, 'is_primary': 1}]
                         if '000012345678' in params else [])
        elif 'FROM staff WHERE' in statement:
            self.rows = [{'id': 7, 'name': '合成月嫂甲'}, {'id': 8, 'name': '合成月嫂乙'}]
        else:
            raise AssertionError('Unexpected bank projection query')

    def fetchall(self):
        return self.rows


def _candidate_from_bank_source(source, account_owner=7):
    cursor = _BankReadCursor(source, account_owner)
    selection = StaffPayoutSelection(StaffPayoutEventType.PAYOUT, ('33',), ('obligation:1',))
    rows = _load_selected_bank_rows(cursor, selection, False)
    rows = _verify_taishin_memo_recipients(cursor, rows, False)
    accounts = _load_bank_accounts(cursor, rows, False)
    return build_staff_payout_candidate(
        (_outgoing_bank_fact(rows[0], 7, ()),),
        (StaffPayableFacts('obligation:1', 7, MoneyNTD(500)),),
        bank_accounts=accounts, require_primary_account_owner=True,
    )


def _sinopac_bank_source():
    return {'id': 33, 'format_id': 'sinopac', 'resolved_counterparty_account': '115807',
            'bank_references': {'交易參考編號': '000012345678', '備註': 'HC115807服務人員'},
            'transaction_date': date(2026, 11, 3), 'debit': 500, 'credit': None,
            'direction': 'outgoing', 'currency': 'TWD', 'classification_type': 'staff_payout',
            'reconciliation_status': 'pending', 'payout_event_id': None,
            'dedup_fingerprint': 'c' * 64}


def test_sinopac_case_suffix_is_not_used_as_staff_recipient_bank_account():
    source = _sinopac_bank_source()
    candidate = _candidate_from_bank_source(source)

    assert candidate.resulting_status is StaffPayableStatus.COMPLETED
    assert source['resolved_counterparty_account'] == '115807'
    assert source['bank_references']['交易參考編號'] == '000012345678'


def test_sinopac_recipient_account_still_rejects_another_staff_owner():
    with pytest.raises(ValueError, match='cross_staff_allocation_forbidden'):
        _candidate_from_bank_source(_sinopac_bank_source(), account_owner=8)


def test_sinopac_memo_cannot_replace_missing_recipient_account():
    source = _sinopac_bank_source()
    source['bank_references'] = {'備註': 'HC115807服務人員'}
    with pytest.raises(ValueError, match='staff_bank_account_ambiguous'):
        _candidate_from_bank_source(source)


@pytest.mark.parametrize('memo,error', [
    ('合成月嫂甲 HC115807', None),
    ('合成月嫂乙', 'cross_staff_allocation_forbidden'),
    ('HC115807', 'staff_memo_recipient_unconfirmed'),
])
def test_taishin_payout_verifies_only_original_memo_name_without_bank_account(memo, error):
    source = {**_sinopac_bank_source(), 'format_id': 'taishin', 'memo': memo,
              'resolved_counterparty_account': None, 'bank_references': {}}
    if error:
        with pytest.raises(ValueError, match=error):
            _candidate_from_bank_source(source)
    else:
        assert _candidate_from_bank_source(source).resulting_status is StaffPayableStatus.COMPLETED
    assert source['resolved_counterparty_account'] is None


def _candidate(
    source_identity: str,
    *,
    source_identities: tuple[str, ...] | None = None,
) -> StaffPayoutCandidate:
    event = StaffPayoutLedgerEventCandidate(
        "payout-event:1",
        StaffPayoutEventType.PAYOUT,
        StaffPayoutEventStatus.SUCCEEDED,
        7,
        MoneyNTD(1_100),
        finance_import_fact_identity=source_identity,
    )
    recovery = StaffOverpaymentRecoveryCandidate(
        "staff-overpayment-recovery:1",
        7,
        MoneyNTD(100),
        source_identities or (source_identity,),
        ("obligation:1",),
    )
    return StaffPayoutCandidate(
        7,
        MoneyNTD(1_100),
        MoneyNTD(1_000),
        (),
        PreviewFingerprint("a" * 64),
        (event,),
        (),
        StaffPayableStatus.RECOVERY_REQUIRED,
        StaffPayoutDifferenceMode.OVERPAYMENT,
        recovery,
    )


def _repository() -> tuple[MySqlStaffPayoutRepository, _Connection]:
    connection = _Connection()
    repository = MySqlStaffPayoutRepository(connection)
    repository._event_ids["payout-event:1"] = 101
    repository.bind_apply_request(
        StaffPayoutApplyRequest(
            StaffPayoutSelection(
                StaffPayoutEventType.PAYOUT,
                ("11",),
                ("obligation:1",),
                difference_mode=StaffPayoutDifferenceMode.OVERPAYMENT,
            ),
            ExpectedVersion(0),
            ExpectedVersion(0),
            PreviewFingerprint("b" * 64),
            IdempotencyKey("recovery-write"),
            ActorContext("operator"),
            "record overpayment",
            CorrelationId("recovery-write"),
        )
    )
    return repository, connection


def test_recovery_producer_persists_canonical_finance_import_row_identity() -> None:
    repository, connection = _repository()

    repository.append_overpayment_recovery(_candidate("11"))

    recovery_params = connection.cursor_value.calls[0][1]
    assert recovery_params[4] == '["finance-import-row:11"]'


def test_recovery_producer_accepts_existing_canonical_identity() -> None:
    repository, connection = _repository()

    repository.append_overpayment_recovery(_candidate("finance-import-row:11"))

    assert connection.cursor_value.calls[0][1][4] == '["finance-import-row:11"]'


@pytest.mark.parametrize("source_identity", ("0", "-1", "bank:11", "finance-import-row:0"))
def test_recovery_producer_fails_closed_for_non_positive_or_invalid_identity(
    source_identity: str,
) -> None:
    repository, connection = _repository()

    with pytest.raises(ValueError, match="staff_overpayment_recovery_source_bank_fact_invalid"):
        repository.append_overpayment_recovery(_candidate(source_identity))

    assert connection.cursor_value.calls == []


def test_recovery_producer_fails_closed_when_canonicalization_creates_duplicates() -> None:
    repository, connection = _repository()

    with pytest.raises(ValueError, match="staff_overpayment_recovery_source_bank_fact_invalid"):
        repository.append_overpayment_recovery(
            _candidate(
                "11",
                source_identities=("11", "finance-import-row:11"),
            )
        )

    assert connection.cursor_value.calls == []


def test_bank_facts_version_is_safe_across_the_json_javascript_boundary() -> None:
    row = {
        "id": 4,
        "dedup_fingerprint": "f" * 64,
        "transaction_date": "2026-08-15",
        "debit": 12_000,
        "credit": 0,
        "direction": "outgoing",
        "currency": "TWD",
        "resolved_counterparty_account": "masked-account",
        "classification_type": "staff_payout",
        "reconciliation_status": "unmatched",
        "payout_event_id": None,
    }

    version = _bank_facts_version((row,), None)

    assert 0 <= version <= (2**53) - 1
