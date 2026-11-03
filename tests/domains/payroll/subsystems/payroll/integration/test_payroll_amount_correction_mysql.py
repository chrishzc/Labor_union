"""Payroll modes consume fresh formula and preserve already-paid evidence."""
import os,runpy
from uuid import uuid4
import pytest
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.payroll_amount_correction_repository import MySqlPayrollAmountRepository
from subsystems.payroll.amount_correction import PayrollAmountApplication,PayrollAmountCommand

pytestmark=pytest.mark.skipif(not os.getenv('ACCOUNTING_DIFFERENCE_TEST_DB'),reason='explicit isolated local MySQL required')
base=runpy.run_path('tests/domains/government-subsidy/subsystems/government-subsidy/integration/test_period_reconciliation_mysql.py')
http=base['http'];complex_support=base['support'];rows=base['rows'];write=base['write']


def seed(http):
    case='118'+str(rows('SELECT COUNT(*) n FROM orders')[0]['n']+1).zfill(6)
    staff=complex_support['seed_case'](http,case)
    return case,staff


def app(connection):return PayrollAmountApplication(MySqlPayrollAmountRepository(connection),lambda:MySqlUnitOfWork(connection))


def test_manual_source_update_then_adopt_restores_automatic_and_funding_schedule(http):
    # http is a real intake/bank API fixture; every target is synthetic lu_test_*.
    case,staff=seed(http);connection=get_connection()
    try:
        application=app(connection);before=application.query(case);item=next(i for i in before.items if i.party.endswith(' A'))
        cmd=PayrollAmountCommand(case,item.identity,'manual_amount',35000,'核對後更正',before.version,case+':manual','synthetic')
        manual=application.apply(cmd);assert application.apply(cmd)==manual
        assignment=int(item.identity.rsplit(':',1)[-1])
        write("INSERT INTO payroll_special_pay_events(assignment_id,service_date,event_type,source_event_identity,actor,reason,idempotency_key) VALUES(%s,'2026-10-01','double_pay',%s,'synthetic','來源更新',%s)",(assignment,case+':double1',case+':double1'))
        _rebuild(connection,case,'source1')
        current=application.query(case);item=next(i for i in current.items if i.identity==item.identity)
        assert item.mode=='manual' and item.effective_ntd==35000 and item.computed_ntd==38400
        cash=base['checked'](http.get('/api/v1/finance-reports/accounts-payable/cash-requirements'));assert next(r for r in cash['rows'] if r['case_no']==case and r['staff_id']==staff[0])['unpaid_amount_ntd']==35000
        adopted=application.apply(PayrollAmountCommand(case,item.identity,'adopt_calculation',None,'採用新計算',current.version,case+':auto','synthetic'))
        write("INSERT INTO payroll_special_pay_events(assignment_id,service_date,event_type,source_event_identity,actor,reason,idempotency_key) VALUES(%s,'2026-10-02','double_pay',%s,'synthetic','來源再次更新',%s)",(assignment,case+':double2',case+':double2'))
        _rebuild(connection,case,'source2')
        final=next(i for i in application.query(case).items if i.identity==item.identity)
        assert final.mode=='automatic' and final.effective_ntd==40800 and final.computed_ntd==40800
        cash=base['checked'](http.get('/api/v1/finance-reports/accounts-payable/cash-requirements'));assert next(r for r in cash['rows'] if r['case_no']==case and r['staff_id']==staff[0])['unpaid_amount_ntd']==40800
    finally:connection.close()


def _rebuild(connection,case,key):
    from api.dependencies.payroll_rebuild import build_payroll_rebuild_application
    from subsystems.payroll.rebuild_workflow import PayrollRebuildRequest
    from shared_kernel.identities import ActorContext,ExpectedVersion,IdempotencyKey,CorrelationId
    owner=build_payroll_rebuild_application(connection);preview=owner.preview(case)
    owner.apply(PayrollRebuildRequest(case,ExpectedVersion(preview.payroll_version),preview.fingerprint,IdempotencyKey(case+':'+key),ActorContext('synthetic'),'來源重算',CorrelationId(case)))


def seed_paid_correction(http):
    case,staff=seed(http)
    complex_support['bank'](http,case,36000,1,account=complex_support['staff_account'](staff[0]))
    connection=get_connection()
    try:
        application=app(connection);before=application.query(case);item=next(i for i in before.items if i.party.endswith(' A'))
        result=application.apply(PayrollAmountCommand(case,item.identity,'manual_amount',35900,'更正已核銷薪資',before.version,case+':paid-correction','synthetic'))
        return case,staff[0],item.identity,result
    finally:connection.close()


def test_paid_amount_correction_creates_independent_recovery_and_keeps_original_bank_and_links(http):
    case,staff,identity,result=seed_paid_correction(http)
    assert next(i for i in result.items if i.identity==identity).effective_ntd==35900
    recovery=rows('SELECT original_amount_ntd,remaining_amount_ntd FROM staff_overpayment_recoveries WHERE staff_id=%s',(staff,))
    assert recovery==({'original_amount_ntd':100,'remaining_amount_ntd':100},)
    assert rows('SELECT o.amount_due_ntd,p.net_paid_ntd FROM staff_obligations o JOIN staff_payable_projections p ON p.obligation_identity=o.obligation_identity WHERE o.obligation_identity=%s',(identity,))==({'amount_due_ntd':36000,'net_paid_ntd':36000},)


def test_same_person_terms_successor_carries_manual_mode_without_duplicate_payables(http):
    from types import SimpleNamespace
    from infrastructure.mysql.payroll_rebuild_repository import MySqlPayrollRebuildRepository
    from infrastructure.mysql.payroll_terms_writer import persist_payroll_terms_impact
    from infrastructure.mysql.payroll_adjustment_repository import MySqlPayrollAdjustmentRepository
    from domains.payroll.calculation import build_case_payroll_candidate
    from subsystems.payroll.terms_impact import PayrollTermsAction,PayrollTermsActionKind,StaffObligationKind,StaffObligationDirection,PayrollTermsImpactCandidate
    from subsystems.orders.terms_workflow import PayrollImpactPersistenceCommand
    from shared_kernel.money import MoneyNTD
    from shared_kernel.fingerprints import fingerprint_payload
    from shared_kernel.identities import IdempotencyKey,ActorContext,CorrelationId
    case,staff=seed(http);connection=get_connection()
    try:
        owner=app(connection);before=owner.query(case);item=next(i for i in before.items if i.party.endswith(' A'))
        manual=owner.apply(PayrollAmountCommand(case,item.identity,'manual_amount',35000,'人工值需保留',before.version,case+':manual','synthetic'))
        old=rows('SELECT * FROM staff_obligations WHERE obligation_identity=%s',(item.identity,))[0]
        facts=MySqlPayrollRebuildRepository(connection).load(case,for_update=False)
        payroll=build_case_payroll_candidate(facts.service_facts,facts.rate_snapshots,facts.terms,facts.adjustments)
        key=f'assignment:{old["assignment_id"]}';new_identity='payroll-source-successor:'+uuid4().hex
        actions=(PayrollTermsAction(PayrollTermsActionKind.CLOSE_UNPAID,item.identity,None,old['assignment_id'],None,staff[0],StaffObligationKind.SERVICE_PAY,StaffObligationDirection.PAYABLE_TO_STAFF,MoneyNTD(36000),old['due_date']),
            PayrollTermsAction(PayrollTermsActionKind.ESTABLISH,new_identity,None,old['assignment_id'],key,staff[0],StaffObligationKind.SERVICE_PAY,StaffObligationDirection.PAYABLE_TO_STAFF,MoneyNTD(36000),old['due_date']))
        candidate=PayrollTermsImpactCandidate(case,manual.version,manual.version+1,payroll,(),actions,(),fingerprint_payload({'source':case}),rate_source_assignments=((key,old['assignment_id']),))
        command=PayrollImpactPersistenceCommand(candidate,SimpleNamespace(assignment_id_by_candidate_key={key:old['assignment_id']}),IdempotencyKey(case+':source-successor'),ActorContext('synthetic'),'同人員來源更新',CorrelationId(case),1,reuse_existing_assignments=True)
        with MySqlUnitOfWork(connection) as work:
            with connection.cursor() as cursor:persist_payroll_terms_impact(cursor,command)
            work.commit()
        view=owner.query(case);changed=next(i for i in view.items if i.identity==new_identity)
        assert changed.mode=='manual' and changed.effective_ntd==35000 and changed.computed_ntd==36000
        assert all(i.identity!=item.identity for i in view.items)
        payroll_query=MySqlPayrollAdjustmentRepository(connection).query_case_payroll(case)
        assert next(i for i in payroll_query['obligations'] if i['obligation_identity']==new_identity)['amount_due_ntd']==35000
        assert rows("SELECT COUNT(*) n FROM staff_obligations WHERE case_no=%s AND staff_id=%s AND status='open'",(case,staff[0]))[0]['n']==1
    finally:connection.close()
