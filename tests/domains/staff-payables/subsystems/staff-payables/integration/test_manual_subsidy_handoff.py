"""HANDOFF-A02..07: manual precedence, exact remaining balances and item-local blockers."""
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import pytest

from domains.staff_payables.subsidy_handoff import SubsidyHandoffFacts, decide_subsidy_handoff
from domains.staff_payables.reconciliation import StaffPayableStatus
from infrastructure.mysql.accounts_payable_export_sources import (
    MySqlClientRefundExportSource, _staff_fact, _staff_payment_route,
)
from subsystems.staff_payables.accounts_payable_export import aggregate_accounts_payable_rows
from subsystems.staff_payables.cash_requirements_query import (
    CashRefundFact, CashRequirementCase, query_cash_requirements,
)


def handoff(**changes):
    return decide_subsidy_handoff(replace(SubsidyHandoffFacts(
        'advance', 'unknown', False, '訂單完成', 30000, 12000, 30000,
        30000, 0, 0, 0, 0, False), **changes))


def staff_row(portion='subsidy', **changes):
    return dict(obligation_identity='staff:case:1', case_no='CASE', staff_id=1,
        recipient_name='測試月嫂', amount_due_ntd=30000, export_amount_ntd=12000,
        due_date=date(2026, 11, 15), payout_status='partially_paid', primary_account_count=1,
        bank_code='0040000', account_no='000001', installment_funding=portion, **changes)


@pytest.mark.parametrize('automatic', ['unknown', 'waiting', 'split', 'direct'])
def test_last_manual_choice_wins_over_unknown_different_or_conflicted_automatic_result_without_government_cash(automatic):
    result = handoff(historical_scheme=automatic, historical_conflict=True)
    assert result.scheme == 'advance' and result.client_subsidy_reason is None


def test_old_direct_arrangement_never_fills_an_unsaved_new_plan_and_historical_case_keeps_its_original_scheme():
    pending = handoff(manual_scheme=None, historical_scheme='direct')
    assert pending.scheme == 'unknown' and '尚未人工保存' in pending.client_subsidy_reason
    old = handoff(manual_scheme=None, historical_scheme='advance', order_status='歷史訂單－服務完成')
    assert old.scheme == 'advance' and not old.manual and not old.requires_manual_plan


def test_early_manual_choice_blocks_only_subsidy_portion_until_formal_service_end():
    decision = handoff(manual_scheme='split', order_status='服務中', customer_amount_ntd=18000)
    subsidy = _staff_fact(_staff_payment_route(staff_row(), decision))
    normal = _staff_fact(_staff_payment_route(staff_row('client'), decision))
    assert subsidy.status is StaffPayableStatus.ANOMALY
    assert normal.status is StaffPayableStatus.PARTIALLY_PAID and normal.outgoing_bank == '31'


def test_split_routes_only_formal_remaining_subsidy_within_total_and_never_pays_subsidy_again_after_staff_received_total():
    decision = handoff(manual_scheme='split', customer_amount_ntd=18000, customer_paid_ntd=18000, staff_paid_ntd=18000)
    remaining = _staff_fact(_staff_payment_route(staff_row(), decision))
    assert remaining.amount.amount == 12000 and remaining.outgoing_bank == '633'
    assert 18000 + sum(item.amount.amount for item in aggregate_accounts_payable_rows((remaining,), ())) == 30000
    exhausted = _staff_fact(_staff_payment_route(staff_row(), handoff(manual_scheme='split', staff_paid_ntd=30000)))
    assert exhausted.status is StaffPayableStatus.ANOMALY
    assert aggregate_accounts_payable_rows((exhausted,), ()) == ()


@pytest.mark.parametrize('paid', [None, 0, 18000])
def test_advance_choice_without_real_customer_advance_cannot_authorize_a_refund(paid):
    assert '墊款依據不足' in handoff(customer_paid_ntd=paid).client_subsidy_reason


def test_split_existing_customer_subsidy_refund_is_a_local_conflict_not_a_reassignment():
    decision = handoff(manual_scheme='split', has_customer_subsidy_payable=True)
    affected = _staff_payment_route(staff_row(), decision)
    normal = _staff_payment_route(staff_row('client'), decision)
    assert '既有客戶補助退款矛盾' in affected['funding_reason']
    assert normal['payout_status'] == 'partially_paid' and normal['due_date'] == date(2026, 11, 15)


class Cursor:
    def __init__(self, rows): self.rows, self.statements = rows, []
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, sql, parameters):
        assert sql.lstrip().startswith('SELECT')
        self.statements.append((sql, parameters))
    def fetchall(self): return self.rows


class Connection:
    def __init__(self, rows): self.reader = Cursor(rows)
    def cursor(self): return self.reader


@pytest.mark.parametrize('scheme,payable', [('advance', True), ('split', False), ('direct', False)])
def test_existing_refund_uses_manual_purpose_and_remains_read_only_with_its_formed_date_and_balance(scheme, payable):
    rows = ({'obligation_identity':'refund:1', 'case_no':'CASE', 'obligation_type':'subsidy_return',
        'recipient_name':'測試客戶', 'amount_due_ntd':8000, 'net_refunded_ntd':4000,
        'due_date':date(2026, 10, 15), 'refund_bank_code':'0040000', 'refund_account_no':'000001'},
        {'obligation_identity':'normal:1', 'case_no':'CASE', 'obligation_type':'refund',
        'recipient_name':'測試客戶', 'amount_due_ntd':500, 'net_refunded_ntd':0,
        'due_date':date(2026, 10, 15), 'refund_bank_code':'0040000', 'refund_account_no':'000001'})
    original = tuple(dict(row) for row in rows)
    connection = Connection(rows)
    facts = MySqlClientRefundExportSource(connection, case_query=lambda _: handoff(manual_scheme=scheme)).load(date(2026,11,15))
    assert facts[0].payable is payable and facts[0].amount.amount == 8000
    assert facts[0].payment_date == date(2026,10,15) and facts[1].payable
    assert rows == original
    exported = aggregate_accounts_payable_rows((), facts)
    assert sum(item.amount.amount for item in exported) == 8500 if payable else sum(item.amount.amount for item in exported) == 500


def cash_case(**changes):
    return replace(CashRequirementCase('CASE','測試客戶','訂單完成',True,date(2026,10,31),
        '一般市民',None,None,None,True,False,(),(), subsidy_ntd=12000,
        manual_plan_required=True, service_completed=True), **changes)


def cash_rows(case):
    return query_cash_requirements(SimpleNamespace(query_cases=lambda *_:(case,))).rows


def test_missing_manual_plan_and_missing_formal_refund_remain_pending_without_fabricating_payee_or_payable():
    missing = cash_rows(cash_case())
    assert len(missing) == 1 and missing[0].recipient_name is None
    assert missing[0].unpaid_amount_ntd is None and '尚未人工保存' in missing[0].pending_reasons[0]
    after_choice = cash_rows(cash_case(manual_subsidy_plan=True, confirmed_scheme='advance'))
    assert after_choice[0].certainty == 'estimated'
    assert '尚未建立正式補助退款應付' in ' '.join(after_choice[0].pending_reasons)
    assert cash_rows(cash_case(manual_subsidy_plan=True, confirmed_scheme='direct')) == ()
    assert cash_rows(cash_case(service_completed=False)) == ()


def test_confirmed_refund_conflict_remains_visible_while_normal_refund_is_unaffected():
    case = cash_case(manual_subsidy_plan=True, confirmed_scheme='direct', has_subsidy_return=True,
        subsidy_refund_reason='既有補助退款與人工安排不符', refunds=(
            CashRefundFact('subsidy','client_subsidy_return',8000,date(2026,10,15),'客戶',True),
            CashRefundFact('normal','client_refund',500,date(2026,10,15),'客戶',True)))
    rows = cash_rows(case)
    assert rows[0].pending_reasons == ('既有補助退款與人工安排不符',)
    assert rows[1].pending_reasons == ()
    assert [item.unpaid_amount_ntd for item in rows] == [8000,500]


def test_manual_plan_cannot_convert_a_full_subsidy_obligation_into_customer_advance_or_extra_salary():
    decision=handoff(manual_scheme='advance',total_ntd=12000,subsidy_ntd=12000,
        customer_amount_ntd=0,customer_paid_ntd=0)
    assert '免自備' in decision.staff_subsidy_reason and '免自備' in decision.client_subsidy_reason
    assert _staff_fact(_staff_payment_route(staff_row(),decision)).status is StaffPayableStatus.ANOMALY


@pytest.mark.parametrize('changes', [dict(full_subsidy_order=True),dict(funding_conflict=True)])
def test_manual_selection_cannot_mask_a_formal_full_subsidy_or_amount_source_conflict(changes):
    decision=handoff(**changes)
    assert decision.staff_subsidy_reason is not None and decision.client_subsidy_reason is not None
    ordinary=_staff_fact(_staff_payment_route(staff_row('client'),decision))
    assert ordinary.status is (StaffPayableStatus.ANOMALY if decision.full_subsidy else StaffPayableStatus.PARTIALLY_PAID)


def test_handoff_keeps_an_excess_formal_refund_pending_instead_of_silently_exporting_the_old_amount():
    from domains.staff_payables.subsidy_handoff import subsidy_refund_amount_reason
    assert subsidy_refund_amount_reason(12000,8000,4000) is None
    rows=cash_rows(cash_case(manual_subsidy_plan=True,confirmed_scheme='advance',has_subsidy_return=True,
        refunds=(CashRefundFact('excess','client_subsidy_return',13000,date(2026,10,15),'客戶',True),)))
    assert rows[0].unpaid_amount_ntd==13000 and '超出本案補助' in rows[0].pending_reasons[0]
    assert handoff(manual_scheme='split',staff_subsidy_paid_ntd=13000).staff_subsidy_reason
    assert handoff(manual_scheme='split',full_subsidy_order=True,customer_amount_ntd=0,
        customer_paid_ntd=0,total_ntd=12000,subsidy_ntd=0).staff_subsidy_reason


@pytest.mark.parametrize('scheme',['advance','direct','split'])
def test_a_manual_choice_does_not_convert_incompatible_formed_customer_charges_or_receipts(scheme):
    if scheme=='split':
        result=handoff(manual_scheme=scheme,customer_amount_ntd=30000,customer_paid_ntd=30000)
        assert '分別入款安排不符' in result.staff_subsidy_reason
    else:
        result=handoff(manual_scheme=scheme,customer_amount_ntd=18000,customer_paid_ntd=18000)
        assert result.client_subsidy_reason is not None


@pytest.mark.parametrize('scheme',['unknown','waiting','advance'])
def test_historical_formal_refund_without_a_new_plan_keeps_its_original_legal_source_eligibility(scheme):
    result=handoff(manual_scheme=None,historical_scheme=scheme,order_status='歷史訂單－服務完成')
    assert not result.requires_manual_plan and result.client_subsidy_reason is None


def test_historical_source_conflict_is_not_relaxed_by_the_new_manual_handoff():
    result=handoff(manual_scheme=None,historical_scheme='unknown',historical_conflict=True,order_status='歷史訂單－服務完成')
    assert _staff_fact(_staff_payment_route(staff_row('client'),result)).status is StaffPayableStatus.ANOMALY
