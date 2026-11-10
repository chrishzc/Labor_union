"""HANDOFF-A02..07: manual precedence, exact remaining balances and item-local blockers."""
from dataclasses import replace
from contextlib import nullcontext
from copy import deepcopy
from datetime import date, datetime, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from domains.staff_payables.subsidy_handoff import SubsidyHandoffFacts, decide_subsidy_handoff
from domains.staff_payables.reconciliation import StaffPayableStatus
from infrastructure.mysql.accounts_payable_export_sources import (
    MySqlClientRefundExportSource, MySqlStaffPayableExportSource, _staff_fact, _staff_payment_route,
)
from subsystems.staff_payables.accounts_payable_export import (
    AccountsPayableExportWorkflow, ArchivedWorkbook, aggregate_accounts_payable_rows,
)
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
    assert pending.scheme == 'unknown' and '尚未正式確認' in pending.client_subsidy_reason
    old = handoff(manual_scheme=None, historical_scheme='advance', order_status='歷史訂單－服務完成')
    assert old.scheme == 'advance' and not old.manual and not old.confirmation_required


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


@pytest.mark.parametrize('status', ['訂單完成', '歷史訂單－服務完成'])
def test_bank_confirmed_scheme_hands_off_to_the_original_cash_and_export_queries(status):
    advance = handoff(order_status=status, confirmation_source='bank')
    assert advance.confirmed and not advance.manual and advance.client_subsidy_reason is None
    rows = cash_rows(cash_case(confirmed_subsidy_plan=advance.confirmed,
        confirmed_scheme=advance.scheme, confirmation_required=advance.confirmation_required,
        subsidy_refund_reason=advance.client_subsidy_reason))
    assert len(rows) == 1 and rows[0].unpaid_amount_ntd == 12000
    assert not any('尚未正式確認' in reason for reason in rows[0].pending_reasons)
    split = handoff(order_status=status, confirmation_source='bank', manual_scheme='split',
        customer_amount_ntd=18000, customer_paid_ntd=18000, staff_paid_ntd=18000)
    payable = _staff_fact(_staff_payment_route(staff_row(), split))
    assert split.confirmed and not split.manual and payable.outgoing_bank == '633'
    assert payable.amount.amount == 12000 and payable.status is StaffPayableStatus.PARTIALLY_PAID


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
        confirmation_required=True, service_completed=True), **changes)


def cash_rows(case):
    return query_cash_requirements(SimpleNamespace(query_cases=lambda *_:(case,))).rows


def test_missing_manual_plan_and_missing_formal_refund_remain_pending_without_fabricating_payee_or_payable():
    missing = cash_rows(cash_case())
    assert len(missing) == 1 and missing[0].recipient_name is None
    assert missing[0].unpaid_amount_ntd is None and '尚未正式確認' in missing[0].pending_reasons[0]
    after_choice = cash_rows(cash_case(confirmed_subsidy_plan=True, confirmed_scheme='advance'))
    assert after_choice[0].certainty == 'estimated'
    assert '尚未建立正式補助退款應付' in ' '.join(after_choice[0].pending_reasons)
    assert cash_rows(cash_case(confirmed_subsidy_plan=True, confirmed_scheme='direct')) == ()
    assert cash_rows(cash_case(service_completed=False)) == ()


def test_confirmed_refund_conflict_remains_visible_while_normal_refund_is_unaffected():
    case = cash_case(confirmed_subsidy_plan=True, confirmed_scheme='direct', has_subsidy_return=True,
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
    rows=cash_rows(cash_case(confirmed_subsidy_plan=True,confirmed_scheme='advance',has_subsidy_return=True,
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
    assert not result.confirmation_required and result.client_subsidy_reason is None


def test_historical_source_conflict_is_not_relaxed_by_the_new_manual_handoff():
    result=handoff(manual_scheme=None,historical_scheme='unknown',historical_conflict=True,order_status='歷史訂單－服務完成')
    assert _staff_fact(_staff_payment_route(staff_row('client'),result)).status is StaffPayableStatus.ANOMALY


def full_handoff(**changes):
    facts = dict(manual_scheme=None, total_ntd=30000, subsidy_ntd=30000,
        customer_amount_ntd=0, customer_paid_ntd=0, staff_paid_ntd=18000,
        staff_subsidy_paid_ntd=18000, full_subsidy_order=True)
    facts.update(changes)
    return handoff(**facts)


@pytest.mark.parametrize('government_paid', [None, 0])
@pytest.mark.parametrize('customer_paid', [None, 0])
def test_formal_full_subsidy_needs_no_manual_plan_or_cash_receipt_to_export_remaining_payable(
    government_paid, customer_paid,
):
    decision = full_handoff(government_received_ntd=government_paid, customer_paid_ntd=customer_paid)

    assert decision.scheme == 'split' and decision.full_subsidy
    assert not decision.manual and not decision.confirmation_required
    assert decision.staff_subsidy_reason is None
    assert decision.client_subsidy_reason is not None
    rows = aggregate_accounts_payable_rows((_staff_fact(_staff_payment_route(staff_row(), decision)),), ())
    assert len(rows) == 1 and rows[0].outgoing_bank == '633'
    assert rows[0].amount.amount == 12000
    assert 18000 + rows[0].amount.amount == 30000
    assert cash_rows(cash_case(confirmed_scheme=decision.scheme, subsidy_ntd=decision.subsidy_ntd,
        confirmed_subsidy_plan=decision.confirmed, confirmation_required=decision.confirmation_required,
        subsidy_refund_reason=decision.client_subsidy_reason)) == ()


@pytest.mark.parametrize('changes', [
    dict(full_subsidy_order=False), dict(total_ntd=None), dict(subsidy_ntd=None),
    dict(customer_amount_ntd=None), dict(total_ntd=0, subsidy_ntd=0),
    dict(subsidy_ntd=12000), dict(customer_amount_ntd=1), dict(customer_paid_ntd=1),
    dict(funding_conflict=True), dict(historical_conflict=True), dict(order_status='服務中'),
    dict(staff_paid_ntd=30000), dict(staff_subsidy_paid_ntd=30001),
    dict(has_customer_subsidy_payable=True), dict(customer_subsidy_paid_ntd=1),
])
def test_automatic_full_subsidy_keeps_missing_conflicting_or_exhausted_sources_blocked(changes):
    decision = full_handoff(**changes)
    fact = _staff_fact(_staff_payment_route(staff_row(), decision))

    assert decision.staff_subsidy_reason is not None
    if changes.get('full_subsidy_order') is not False:
        assert '尚未正式確認' not in decision.staff_subsidy_reason
    assert fact.status is StaffPayableStatus.ANOMALY
    assert aggregate_accounts_payable_rows((fact,), ()) == ()


@pytest.mark.parametrize('paid', [0, 18000, 30000])
def test_full_subsidy_handoff_and_original_readers_feed_the_same_list_and_excel_without_financial_writes(
    monkeypatch, paid,
):
    from infrastructure.mysql import accounting_workspace_repository as workspace_repository

    target_date = date(2026, 11, 15)
    case = SimpleNamespace(
        funding=SimpleNamespace(full_subsidy=True, total_ntd=30000),
        staff_receivable_ntd=30000, subsidy_ntd=30000, customer_amount_ntd=0, customer_paid_ntd=0,
        subsidy_plan=None, scheme='split', scheme_conflict=False,
        cash_by_flow={'C': 0, 'G': 0, 'PS': 0, 'PT': paid, 'RS': 0, 'RT': 0},
        staff_items=(SimpleNamespace(direction='payable', summary_included=True, actual_ntd=paid),),
    )
    full_row = {**staff_row(), 'export_amount_ntd': 30000 - paid,
                'funding_root_total':30000, 'funding_settled_total':paid,
                'payout_status': 'partially_paid' if paid else 'payable'}
    ordinary = {**staff_row('client'), 'obligation_identity': 'staff:other:1', 'case_no': 'OTHER',
                'staff_id': 2, 'recipient_name': '一般月嫂', 'amount_due_ntd': 5000,
                'export_amount_ntd': 5000, 'payout_status': 'payable'}
    ordinary.update(funding_root_total=5000,funding_settled_total=0)
    staff_rows = (ordinary,) if paid == 30000 else (full_row, ordinary)
    refunds = ({'obligation_identity': 'normal:1', 'case_no': 'CASE', 'obligation_type': 'refund',
        'recipient_name': '一般退款', 'amount_due_ntd': 500, 'net_refunded_ntd': 0,
        'due_date': target_date, 'refund_bank_code': '0040000', 'refund_account_no': '000001'},)
    before = deepcopy((case, staff_rows, refunds))

    class ReadOnlyCursor(Cursor):
        def execute(self, sql, parameters):
            super().execute(sql, parameters)
            if 'AS has_customer_subsidy_payable' in sql:
                self.rows = ({'status': '訂單完成', 'has_customer_subsidy_payable': 0},)
            elif 'FROM client_obligations' in sql:
                self.rows = refunds
            else:
                self.rows = staff_rows

        def fetchone(self):
            return self.rows[0] if self.rows else None

    connection = SimpleNamespace(reader=ReadOnlyCursor(()))
    connection.cursor = lambda: connection.reader
    def workspace(actual):
        assert actual is connection
        return SimpleNamespace(query=lambda case_no: case)

    monkeypatch.setattr(workspace_repository, 'build_accounting_workspace', workspace)
    from subsystems.staff_payables.case_accounting_query import StaffFundingPortion
    monkeypatch.setattr('infrastructure.mysql.staff_payout_repository.query_staff_funding_portions',
        lambda cursor, identity, **kwargs: (
            StaffFundingPortion('subsidy',30000,target_date,paid,30000-paid),) if identity=='staff:case:1'
            else (StaffFundingPortion('client',5000,target_date,0,5000),))

    def case_query(case_no):
        if case_no == 'OTHER':
            return handoff()
        return workspace_repository.query_subsidy_payable_handoff(connection, case_no)

    archived = []

    def save(year, filename, content, digest):
        archived.append(content)
        return ArchivedWorkbook(filename, digest)

    workflow = AccountsPayableExportWorkflow(
        MySqlStaffPayableExportSource(connection, case_query=case_query),
        MySqlClientRefundExportSource(connection, case_query=case_query),
        SimpleNamespace(save=save), nullcontext,
        lambda: datetime(2026, 11, 1, tzinfo=timezone.utc),
    )
    listed = workflow.query(target_date)
    receipt = workflow.export(target_date)
    sheet = load_workbook(BytesIO(receipt.workbook_bytes)).active
    exported = tuple(sheet.iter_rows(min_row=3, values_only=True))

    full_rows = [row for row in listed if row.outgoing_bank == '633']
    assert len(full_rows) == int(paid < 30000)
    assert paid + sum(row.amount.amount for row in full_rows) == 30000
    assert sorted(row.amount.amount for row in listed if row.outgoing_bank == '31') == [500, 5000]
    assert receipt.row_count == len(listed) == len(exported)
    assert sorted((row[1], row[5]) for row in exported) == sorted(
        ('台新銀行' if row.outgoing_bank == '633' else '永豐銀行', row.amount.amount) for row in listed)
    assert archived == [receipt.workbook_bytes]
    assert (case, staff_rows, refunds) == before
