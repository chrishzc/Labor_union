import pytest
from domains.client_finance.difference_resolution import ClientDifferenceTarget,ClientDifferenceConflict,client_difference_options,require_client_disposition,plan_client_amount_change
from domains.client_finance.obligation_planning import (
    ClientFinanceDirection, ClientStagePlan, ExistingClientStageObligation, _build_stage_action, _stage_settled,
)
from domains.client_finance.reconciliation import PaymentStage
from shared_kernel.money import MoneyNTD


def target(kind='first',direction='receivable_from_client',remaining=100):
    return ClientDifferenceTarget('obligation',kind,direction,10000,9900,remaining)


def test_human_options_distinguish_customer_service_debt_from_overrefund_recovery():
    assert 'reduce_service_fee' in client_difference_options(target())
    options=client_difference_options(target('over_refund_correction'))
    assert 'absorb_overpayment' in options and 'loss' in options
    assert 'reduce_service_fee' not in options and 'union_bank_fee' not in options
    assert 'close_refund' not in client_difference_options(target())


@pytest.mark.parametrize('action',['loss','reduce_service_fee','union_bank_fee'])
def test_explicit_recognition_validates_amount_and_basis_instead_of_guessing_small_difference(action):
    assert require_client_disposition(target(),action,30,'人員確認')==70
    with pytest.raises(ClientDifferenceConflict):require_client_disposition(target(),action,101,'人員確認')
    with pytest.raises(ClientDifferenceConflict):require_client_disposition(target(),action,30,'')


def test_simple_close_is_only_a_whole_selected_customer_refund_and_paid_correction_is_separate():
    refund=target('refund','payable_to_client')
    assert require_client_disposition(refund,'close_refund',100,'')==0
    with pytest.raises(ClientDifferenceConflict):require_client_disposition(refund,'close_refund',50,'')
    with pytest.raises(ClientDifferenceConflict):require_client_disposition(target('salary','payable_to_client'),'close_refund',100,'')
    plan=plan_client_amount_change(target(remaining=0),9900,frozen=True)
    assert plan.separate_direction=='payable_to_client' and plan.separate_amount_ntd==100


@pytest.mark.parametrize(('frozen', 'paid', 'noncash', 'remaining', 'before', 'after', 'direction', 'amount'), (
    (False, 8000, 1000, 1000, 10000, 5000, 'payable_to_client', 3000),
    (True, 8000, 2000, 0, 10000, 5000, 'payable_to_client', 3000),
    (True, 0, 10000, 0, 10000, 5000, None, 0),
    (True, 8000, 2000, 0, 5000, 7000, 'receivable_from_client', 2000),
))
def test_stage_repricing_only_refunds_cash_and_uses_current_amount_for_later_changes(
    frozen, paid, noncash, remaining, before, after, direction, amount,
):
    source = ClientDifferenceTarget('obligation', 'first', 'receivable_from_client', before, paid, remaining, noncash)
    plan = plan_client_amount_change(source, after, frozen=frozen, cash_refund_only=True)
    assert plan.remaining_ntd == 0
    assert (plan.separate_direction, plan.separate_amount_ntd) == (direction, amount)


def test_service_shortening_preserves_manually_set_receivable_in_preview():
    stage = ClientStagePlan(PaymentStage.FIRST, (), MoneyNTD(5000), None)
    existing = ExistingClientStageObligation(
        'first', PaymentStage.FIRST, MoneyNTD(10000), MoneyNTD(8000), None, True,
        net_receipt_amount=MoneyNTD(8000), manual_amount=MoneyNTD(10000),
    )
    action = _build_stage_action('case', 'shorten', stage, existing)
    assert action.direction is ClientFinanceDirection.NO_FINANCE_CHANGE
    assert action.before_amount == action.after_amount == MoneyNTD(10000)
    assert not _stage_settled(stage, existing)
