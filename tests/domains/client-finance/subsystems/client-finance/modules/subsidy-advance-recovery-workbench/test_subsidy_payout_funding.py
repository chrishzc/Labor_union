from datetime import date

import pytest

from domains.client_finance.client_refund_reversal import (
    ClientFinanceCorrectionType,
    ClientRefundPurpose,
)
from domains.client_finance.subsidy_advance import subsidy_payout_is_advance
from subsystems.client_finance.client_refund_reversal_workflow import (
    ClientRefundReversalSelection,
)
from infrastructure.mysql.client_refund_reversal_repository import _load_subsidy_payout_funding


def _selection() -> ClientRefundReversalSelection:
    return ClientRefundReversalSelection(
        "C-1",
        ClientFinanceCorrectionType.REFUND,
        ClientRefundPurpose.SUBSIDY_RETURN,
        bank_fact_identities=("1",),
        obligation_identities=("subsidy:C-1",),
    )


def _facts(*, completed_on=date(2026, 1, 31)):
    return {
        "obligation_identity": "subsidy:C-1",
        "due_date": date(2026, 3, 15),
        "service_end_date": completed_on,
        "amount_due_ntd": 6000,
    }


def _funding(covered=(), *, paid_on=date(2026, 3, 15)):
    cursor = _Cursor(_facts(), covered)
    return _load_subsidy_payout_funding(cursor, _selection(), ({'transaction_date': paid_on},), False)[0]


def test_uncovered_period_subsidy_payout_becomes_union_advance():
    assert subsidy_payout_is_advance(_funding(), 6000) is True


def test_covered_period_payout_remains_normal_subsidy_return():
    assert subsidy_payout_is_advance(_funding(({'id': 7},)), 6000) is False


def test_ambiguous_period_coverage_never_auto_nets_a_client_payout():
    with pytest.raises(ValueError, match="subsidy_advance_settlement_ambiguous"):
        _funding(({'id': 7}, {'id': 8}))


def test_partial_legacy_allocation_requires_review_instead_of_splitting_the_payout():
    from dataclasses import replace
    with pytest.raises(ValueError, match="subsidy_advance_settlement_ambiguous"):
        subsidy_payout_is_advance(replace(_funding(), allocated_at_payment_ntd=5000), 6000)


def test_advance_before_fixed_due_date_is_blocked():
    with pytest.raises(ValueError, match="subsidy_advance_not_due"):
        subsidy_payout_is_advance(_funding(paid_on=date(2026, 3, 14)), 6000)


@pytest.mark.parametrize('completed',[None,date(2026,2,28),date(2027,1,1)])
def test_saved_official_due_date_is_not_recomputed_from_changed_service_dates(completed):
    from dataclasses import replace
    facts=replace(_funding(),completed_on=completed)
    assert subsidy_payout_is_advance(facts,6000) is True
    with pytest.raises(ValueError,match='subsidy_advance_not_due'):
        subsidy_payout_is_advance(replace(facts,paid_on=date(2026,3,14)),6000)


def test_missing_official_due_date_uses_date_reason_without_a_completion_fallback():
    from dataclasses import replace
    with pytest.raises(ValueError,match='due_date_missing'):
        subsidy_payout_is_advance(replace(_funding(),due_on=None),6000)


@pytest.mark.parametrize('covered', [False, True])
@pytest.mark.parametrize('requested', [ClientRefundPurpose.SUBSIDY_RETURN, ClientRefundPurpose.SUBSIDY_ADVANCE])
@pytest.mark.parametrize('fee', [0, 1, 30, 100])
def test_subsidy_preview_and_apply_use_gross_settlement_but_keep_actual_bank_cash(covered, requested, fee):
    from unittest.mock import Mock
    from domains.client_finance.client_refund_reversal import ClientRefundBankFact, ClientRefundObligation
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from shared_kernel.money import MoneyNTD
    from subsystems.client_finance.client_refund_reversal_workflow import (
        ClientRefundReversalWorkflow, ClientRefundReversalFacts, ClientRefundReversalApplyRequest,
    )
    selection = ClientRefundReversalSelection('C-1', ClientFinanceCorrectionType.REFUND, requested,
        bank_fact_identities=('1',), obligation_identities=('subsidy:C-1',))
    facts = ClientRefundReversalFacts(0,
        (ClientRefundBankFact('1', 'C-1', MoneyNTD(6000-fee), '2026-03-15'),),
        (ClientRefundObligation('subsidy:C-1', 'C-1', MoneyNTD(6000), 'subsidy_return'),),
        subsidy_payout=(_funding(({'id': 7},) if covered else ()),))
    repo = Mock(); repo.load.return_value = facts; repo.find_receipt.return_value = None
    unit = Mock(); unit.__enter__ = Mock(return_value=unit); unit.__exit__ = Mock(return_value=False)
    workflow = ClientRefundReversalWorkflow(repo, lambda: unit)
    preview = workflow.preview(selection, CorrelationId('synthetic-preview'))
    candidate = preview.candidate
    assert candidate.entries[0].entry_type == ('subsidy_return' if covered else 'subsidy_advance')
    assert candidate.amount.amount == candidate.entries[0].amount.amount == 6000-fee
    assert candidate.transfer_fee.amount == fee
    assert sum(a.amount.amount for a in candidate.allocations) == 6000
    request = ClientRefundReversalApplyRequest(selection, ExpectedVersion(0), preview.fingerprint,
        IdempotencyKey('subsidy-fee'), ActorContext('synthetic'), '合成手續費', CorrelationId('synthetic-apply'))
    workflow.apply(request)
    repo.append_ledger_entries.assert_called_once_with(candidate)
    repo.append_allocations.assert_called_once_with(candidate)
    unit.commit.assert_called_once()


@pytest.mark.parametrize('fee,code', [(101, 'refund_requires_exact_settlement'), (-1, 'allocation_exceeds_obligation')])
def test_subsidy_fee_outside_policy_is_same_preview_and_apply_blocker_without_writes(fee, code):
    from unittest.mock import Mock
    from domains.client_finance.client_refund_reversal import ClientRefundBankFact, ClientRefundObligation
    from shared_kernel.fingerprints import PreviewFingerprint
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from shared_kernel.money import MoneyNTD
    from subsystems.client_finance.client_refund_reversal_workflow import (
        ClientRefundReversalWorkflow, ClientRefundReversalFacts, ClientRefundReversalApplyRequest, ClientRefundReversalError,
    )
    repo = Mock(); repo.find_receipt.return_value = None
    repo.load.return_value = ClientRefundReversalFacts(0,
        (ClientRefundBankFact('1', 'C-1', MoneyNTD(6000-fee), '2026-03-15'),),
        (ClientRefundObligation('subsidy:C-1', 'C-1', MoneyNTD(6000), 'subsidy_return'),), subsidy_payout=(_funding(),))
    unit = Mock(); unit.__enter__ = Mock(return_value=unit); unit.__exit__ = Mock(return_value=False)
    workflow = ClientRefundReversalWorkflow(repo, lambda: unit)
    with pytest.raises(ClientRefundReversalError) as preview: workflow.preview(_selection(), CorrelationId('preview'))
    request = ClientRefundReversalApplyRequest(_selection(), ExpectedVersion(0), PreviewFingerprint('a'*64),
        IdempotencyKey('blocked'), ActorContext('synthetic'), '合成邊界', CorrelationId('apply'))
    with pytest.raises(ClientRefundReversalError) as apply: workflow.apply(request)
    assert preview.value.error.code == apply.value.error.code == code
    repo.append_ledger_entries.assert_not_called(); repo.append_allocations.assert_not_called(); unit.commit.assert_not_called()


@pytest.mark.parametrize('covered', [False, True])
@pytest.mark.parametrize('partial,fee', [(False, 30), (False, 100), (True, 2000)])
def test_selected_combined_subsidy_obligations_and_explicit_partial_keep_cash_and_replay(covered, partial, fee):
    from dataclasses import replace
    from unittest.mock import Mock
    from domains.client_finance.client_refund_reversal import ClientRefundBankFact, ClientRefundObligation
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from shared_kernel.money import MoneyNTD
    from subsystems.client_finance.client_refund_reversal_workflow import (
        ClientRefundReversalWorkflow, ClientRefundReversalFacts, ClientRefundReversalApplyRequest,
    )
    selection = replace(_selection(), obligation_identities=('subsidy:C-1:a', 'subsidy:C-1:b'), allow_partial_refund_recovery=partial)
    funding = replace(_funding(({'id': 7},) if covered else ()), entitled_amount_ntd=12000,
                      allocated_at_payment_ntd=12000 if covered else 0)
    repo = Mock(); repo.find_receipt.return_value = None
    repo.load.return_value = ClientRefundReversalFacts(0,
        (ClientRefundBankFact('1', 'C-1', MoneyNTD(12000-fee), '2026-03-15'),),
        tuple(ClientRefundObligation(identity, 'C-1', MoneyNTD(6000), 'subsidy_return') for identity in selection.obligation_identities),
        subsidy_payout=(funding, funding))
    unit = Mock(); unit.__enter__ = Mock(return_value=unit); unit.__exit__ = Mock(return_value=False)
    workflow = ClientRefundReversalWorkflow(repo, lambda: unit)
    preview = workflow.preview(selection, CorrelationId('combined'))
    candidate = preview.candidate
    settled = 12000-fee if partial else 12000
    assert sum(a.amount.amount for a in candidate.allocations) == settled
    assert candidate.transfer_fee.amount == (0 if partial else fee)
    assert candidate.entries[0].amount.amount == 12000-fee
    assert candidate.entries[0].entry_type == ('subsidy_return' if covered else 'subsidy_advance')
    request = ClientRefundReversalApplyRequest(selection, ExpectedVersion(0), preview.fingerprint,
        IdempotencyKey('combined'), ActorContext('synthetic'), '合成合併款／實退不足', CorrelationId('combined'))
    receipt = workflow.apply(request)
    stored = repo.save_receipt.call_args.args[1]
    repo.find_receipt.return_value = stored
    assert workflow.apply(request) == receipt
    repo.append_ledger_entries.assert_called_once_with(candidate)
    repo.append_allocations.assert_called_once_with(candidate)
    unit.commit.assert_called_once()


def test_combined_repository_retains_each_original_due_date_and_checks_each_payment_date():
    from dataclasses import replace
    rows = tuple({**_facts(), 'obligation_identity': identity} for identity in ('subsidy:C-1:a', 'subsidy:C-1:b'))
    cursor = _Cursor(rows[0], ())
    original_fetchall = cursor.fetchall
    cursor.fetchall = lambda: original_fetchall() if cursor.coverage_query else rows
    facts = _load_subsidy_payout_funding(cursor, replace(_selection(), obligation_identities=tuple(r['obligation_identity'] for r in rows)),
                                        ({'transaction_date': date(2026, 3, 15)},), True)
    assert len(facts) == 2
    assert all(f.entitled_amount_ntd == 12000 and f.due_on == date(2026, 3, 15) for f in facts)
    assert all(subsidy_payout_is_advance(f, 10000) for f in facts)


class _Cursor:
    def __init__(self, row, covered):
        self._row = row
        self._covered = covered

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def execute(self, sql, parameters):
        self.coverage_query = 'government_subsidy_period_members' in sql
        if 'government_subsidy_period_members' in sql:
            assert 'entry.paid_on<=%s' in sql
            assert 'reversal.paid_on<=%s' in sql
            assert parameters[0] == 'C-1'

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._covered if self.coverage_query else (self._row,)
