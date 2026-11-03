"""Partial union absorption/loss leave unpaid recovery open without fake cash."""
import os,runpy
import pytest
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.staff_recovery_disposition_repository import MySqlStaffRecoveryDispositionRepository,StaffRecoveryDispositionConflict
from subsystems.staff_payables.recovery_disposition import StaffRecoveryDispositionApplication,StaffRecoveryDispositionCommand
pytestmark=pytest.mark.skipif(not os.getenv('ACCOUNTING_DIFFERENCE_TEST_DB'),reason='explicit isolated local MySQL required')
base=runpy.run_path('tests/domains/payroll/subsystems/payroll/integration/test_payroll_amount_correction_mysql.py')
http=base['http'];rows=base['rows']


def test_partial_absorption_then_loss_and_replay_preserve_original_cash(http):
    case,staff,identity,_=base['seed_paid_correction'](http)
    connection=get_connection()
    try:
        application=StaffRecoveryDispositionApplication(MySqlStaffRecoveryDispositionRepository(connection),lambda:MySqlUnitOfWork(connection))
        view=application.query(case);assert len(view.items)==1
        target=view.items[0];assert target.remaining_ntd==100
        command=StaffRecoveryDispositionCommand(case,target.identity,'absorb_overpayment',50,'工會確認承擔',target.version,case+':absorb','synthetic')
        partial=application.apply(command);assert application.apply(command)==partial
        assert partial.items[0].remaining_ntd==50 and partial.items[0].noncash_ntd==50
        with pytest.raises(StaffRecoveryDispositionConflict):application.apply(StaffRecoveryDispositionCommand(case,target.identity,'loss',50,'stale',target.version,case+':stale','synthetic'))
        final=application.apply(StaffRecoveryDispositionCommand(case,target.identity,'loss',50,'確認無法收回',partial.items[0].version,case+':loss','synthetic'))
        assert final.items[0].remaining_ntd==0 and final.items[0].noncash_ntd==100 and final.items[0].status=='已作損失處理'
        assert [e.action for e in final.events]==['absorb_overpayment','loss']
        assert rows('SELECT amount_ntd FROM staff_payout_events WHERE staff_id=%s',(staff,))==({'amount_ntd':36000},)
        assert rows('SELECT allocated_amount_ntd FROM staff_payout_obligation_links WHERE obligation_identity=%s',(identity,))==({'allocated_amount_ntd':36000},)
    finally:connection.close()


def test_after_partial_absorption_actual_recovery_still_uses_the_existing_bank_writer_and_monthly_cash(http):
    from uuid import uuid4
    from datetime import date
    from api.routes.staff_payout import router
    from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting
    from infrastructure.mysql.monthly_accounting_repository import MySqlMonthlyAccountingSource
    http.app.include_router(router)
    checked=base['base']['checked'];case,staff,identity,_=base['seed_paid_correction'](http)
    connection=get_connection()
    try:
        application=StaffRecoveryDispositionApplication(MySqlStaffRecoveryDispositionRepository(connection),lambda:MySqlUnitOfWork(connection))
        item=application.query(case).items[0]
        result=application.apply(StaffRecoveryDispositionCommand(case,item.identity,'absorb_overpayment',40,'工會承擔部分',item.version,case+':absorb','synthetic'))
        account=base['complex_support']['staff_account'](staff)
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO finance_import_rows(dedup_fingerprint,format_id,transaction_date,direction,credit,debit,currency,counterparty_account,resolved_counterparty_account,bank_references,warnings,raw_payload,classification_type) VALUES(%s,'legacy','2026-11-02','incoming',30,0,'TWD',%s,%s,'{}','[]','{}','staff_payout_return')",(uuid4().hex+uuid4().hex,account,account));incoming=int(cursor.lastrowid)
        connection.commit()
        url='/api/v1/staff-payables/overpayment-recoveries'
        selection={'recovery_identity':item.identity,'finance_import_row_id':incoming,'evidence_reference':'合成來源配對'}
        preview=checked(http.post(url+'/matching/preview',json=selection))
        matching=checked(http.post(url+'/matching/apply',json={**selection,'expected_recovery_version':preview['recovery_version'],'expected_staff_payables_version':preview['staff_payables_version'],'preview_fingerprint':preview['preview_fingerprint'],'reason':'核對原追償'},headers={'Idempotency-Key':case+':matching'}))
        selected={**selection,'matching_identity':matching['matching_identity'],'matching_version':matching['matching_version']}
        preview=checked(http.post(url+'/matched/preview',json=selected))
        checked(http.post(url+'/matched/apply',json={**selected,'expected_recovery_version':preview['recovery_version'],'expected_staff_payables_version':preview['staff_payables_version'],'preview_fingerprint':preview['preview_fingerprint'],'reason':'收到部分追償'},headers={'Idempotency-Key':case+':collection'}))
        connection.rollback()
        current=application.query(case).items[0];assert current.remaining_ntd==30
        application.apply(StaffRecoveryDispositionCommand(case,item.identity,'loss',30,'確認其餘收不回',current.version,case+':loss','synthetic'))
        projected=next(i for i in query_case_staff_accounting(connection,case)[0] if i.identity==item.identity)
        assert (projected.expected_ntd,projected.actual_ntd,projected.noncash_ntd,projected.remaining_ntd)==(100,30,70,0)
        banks=MySqlMonthlyAccountingSource(connection).bank_facts(date(2026,11,1),date(2026,11,1))
        assert sum(b.amount_ntd for b in banks if b.identity==f'bank:{incoming}')==30
    finally:connection.close()
