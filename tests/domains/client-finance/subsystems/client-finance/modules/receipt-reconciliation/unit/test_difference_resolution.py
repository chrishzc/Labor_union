import pytest
from domains.client_finance.difference_resolution import ClientDifferenceTarget,ClientDifferenceConflict,client_difference_options,require_client_disposition,plan_client_amount_change


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
