"""Frozen period, short/excess cash, explicit loss, correction and original status."""
import os,runpy
from datetime import date
from uuid import uuid4
import pytest
pytestmark=pytest.mark.skipif(not os.getenv('SUBSIDY_PERIOD_TEST_DB'),reason='explicit isolated local MySQL required')
base=runpy.run_path('tests/domains/government-subsidy/subsystems/government-subsidy/integration/test_period_reconciliation_mysql.py')
http=base['http'];seed_case=base['seed_case'];query=base['query'];checked=base['checked'];bank=base['bank'];rows=base['rows']


def apply(http,view,action,*,identity='',amount=None,source=None,handling='',reason='',key=None):
    return http.post('/api/v1/government-subsidy/periods/differences',json={**view['period'],'action':action,'identity':identity,'amount_ntd':amount,'bank_row_id':source,'handling':handling,'reason':reason,'expected_version':view['version'],'key':key or uuid4().hex})


def test_first_partial_freezes_members_and_original_settlement_is_independent_of_later_corrections(http):
    year=int(rows('SELECT COALESCE(MAX(YEAR(end_date)),2080)+1 y FROM orders')[0]['y']);case=seed_case(http,year,1,days=20);view=query(http,'month',year,1);assert view['total_ntd']==12000
    source=bank(11900,date(2026,10,1));key=uuid4().hex
    assert apply(http,view,'initial_receipt',source=source).status_code==409
    initial=checked(apply(http,view,'initial_receipt',source=source,handling='partial',key=key))
    assert checked(apply(http,view,'initial_receipt',source=source,handling='partial',key=key))==initial
    original=initial['balances'][0];assert original['expected_ntd']==12000 and original['received_ntd']==11900 and original['remaining_ntd']==100
    assert initial['coverage'][0]['settled'] is False
    corrected=checked(apply(http,initial,'manual_amount',identity=case,amount=12100,reason='核對後更正'))
    assert corrected['recorded_lines'][0]['amount_ntd']==12000
    correction=next(b for b in corrected['balances'] if b['kind']=='correction');assert correction['expected_ntd']==100
    assert apply(http,initial,'loss',identity=original['identity'],amount=100,reason='stale').status_code==409
    settled=checked(apply(http,corrected,'loss',identity=original['identity'],amount=100,reason='工會確認收不回'))
    assert settled['coverage'][0]['settled'] is True
    case_view=checked(http.get('/api/v1/government-subsidy/periods/cases/'+case));assert case_view['coverage'][0]['settled'] is True
    assert next(b for b in settled['balances'] if b['kind']=='correction')['remaining_ntd']==100
    paid=checked(apply(http,settled,'receipt',identity=correction['identity'],source=bank(100,date(2026,11,1))))
    assert next(b for b in paid['balances'] if b['identity']==correction['identity'])['settled'] is True
    adopted=checked(apply(http,paid,'adopt_calculation',identity=case,reason='恢復最新計算'))
    assert adopted['amount_controls'][0]['mode']=='automatic'
    assert any(b['direction']=='payable' and b['expected_ntd']==100 for b in adopted['balances'])
    assert rows('SELECT amount_ntd FROM government_subsidy_period_members WHERE receipt_id=%s AND case_no=%s',(original['root_receipt_id'],case))[0]['amount_ntd']==12000
    assert rows('SELECT credit FROM finance_import_rows WHERE id=%s',(source,))[0]['credit']==11900
    assert query(http,'quarter',year,1)['can_reconcile'] is False


def test_excess_is_pending_refund_until_actual_outgoing_bank_fact_and_cannot_be_silently_waived(http):
    year=int(rows('SELECT COALESCE(MAX(YEAR(end_date)),2080)+1 y FROM orders')[0]['y']);seed_case(http,year,1,days=20);view=query(http,'month',year,1)
    source=bank(12100,date(2026,11,1))
    assert apply(http,view,'initial_receipt',source=source,handling='partial').status_code==409
    excess=checked(apply(http,view,'initial_receipt',source=source,handling='refund_excess'))
    balance=excess['balances'][0];assert balance['refund_due_ntd']==100 and excess['coverage'][0]['settled'] is False
    assert apply(http,excess,'loss',identity=balance['identity'],amount=100,reason='不能用損失免退').status_code==409
    assert apply(http,excess,'refund',identity=balance['identity'],source=bank(-101,date(2026,11,2))).status_code==409
    settled=checked(apply(http,excess,'refund',identity=balance['identity'],source=bank(-100,date(2026,11,2))))
    assert settled['balances'][0]['refund_due_ntd']==0 and settled['coverage'][0]['settled'] is True
    assert len(settled['coverage'])==1 and len(settled['operations'])==2
    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.monthly_accounting_repository import MySqlMonthlyAccountingSource
    connection=get_connection()
    try:
        facts=MySqlMonthlyAccountingSource(connection).bank_facts(date(2026,11,1),date(2026,11,1))
        assert any(f.amount_ntd==12100 and f.direction=='in' for f in facts)
        assert any(f.amount_ntd==100 and f.direction=='out' for f in facts)
    finally:connection.close()
