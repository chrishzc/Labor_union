"""Real owner noncash/mode transactions; no user data or external effects."""
import os,runpy
from uuid import uuid4
from types import SimpleNamespace
import pymysql,pytest
from infrastructure.mysql.client_difference_repository import MySqlClientDifferenceRepository,persist_controlled_client_stage
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from subsystems.client_finance.difference_resolution import ClientDifferenceApplication,ClientDifferenceCommand
from infrastructure.mysql.client_payments_query_repository import query_case_accounting
from domains.client_finance.difference_resolution import ClientDifferenceConflict
from domains.client_finance.reconciliation import PaymentStage
from shared_kernel.identities import ActorContext,ExpectedVersion,IdempotencyKey,CorrelationId
from shared_kernel.money import MoneyNTD

pytestmark=pytest.mark.skipif(not os.getenv('ACCOUNTING_DIFFERENCE_TEST_DB'),reason='explicit isolated local MySQL required')
support=runpy.run_path('tests/domains/client-finance/subsystems/client-finance/integration/test_client_receipt_partial_mysql.py')
government_support=runpy.run_path('tests/domains/government-subsidy/subsystems/government-subsidy/integration/test_period_reconciliation_mysql.py')
http=government_support['http']


@pytest.fixture
def connection():
    from infrastructure.mysql.mysql_adapter import DB_CONFIG
    assert DB_CONFIG['host'] in {'localhost','127.0.0.1'} and DB_CONFIG['database'].startswith('lu_test_')
    conn=pymysql.connect(**DB_CONFIG,cursorclass=pymysql.cursors.DictCursor,autocommit=False)
    try:yield conn
    finally:conn.close()


def _app(conn):return ClientDifferenceApplication(MySqlClientDifferenceRepository(conn),lambda:MySqlUnitOfWork(conn))


def _cash(conn,case,*,overage=False,partial=False):
    identities,banks=support['_seed_mixed_case'](conn,case,overage,partial_only=partial)
    repository=support['MySqlClientReceiptReconciliationRepository'](conn)
    app=support['ClientReceiptReconciliationApplication'](repository,support['ClientReconciliationWorkflow'](repository,lambda:support['ClientReceiptMySqlUnitOfWork'](conn)))
    selection=support['ReconciliationSelection'](case,None,tuple(sorted(banks)),tuple(sorted(identities)),allow_partial_receipt=partial,allow_overage_disposition=overage)
    preview=app.preview(selection)
    app.apply(support['ClientReconciliationApplyRequest'](selection,ExpectedVersion(0),preview.fingerprint,IdempotencyKey(case+':cash'),ActorContext('synthetic'),'已核對',CorrelationId(case)))
    return identities,banks


@pytest.mark.parametrize('action',['loss','reduce_service_fee','union_bank_fee'])
def test_noncash_preserves_original_cash_and_month_while_clearing_only_selected_remainder(connection,action):
    case='DIFF-'+action+'-'+uuid4().hex[:6];identities,banks=_cash(connection,case,partial=True)
    app=_app(connection);before=app.query(case);item=next(i for i in before.items if i.remaining_ntd)
    command=ClientDifferenceCommand(case,item.identity,action,1000,'人員核對處理依據',before.version,case+':difference','synthetic')
    after=app.apply(command);assert app.apply(command)==after
    target=next(i for i in after.items if i.identity==item.identity)
    assert (target.expected_ntd,target.actual_ntd,target.noncash_ntd,target.remaining_ntd)==(5000,4000,1000,0)
    if action=='reduce_service_fee':assert target.service_reduction_ntd==1000 and target.effective_charge_ntd==4000
    items,_=query_case_accounting(connection,case);projection=next(i for i in items if i.identity==item.identity)
    assert (projection.expected_ntd,projection.actual_ntd,projection.noncash_ntd,projection.remaining_ntd)==(5000,4000,1000,0)
    with connection.cursor() as cursor:
        cursor.execute('SELECT credit,transaction_date FROM finance_import_rows WHERE id=%s',(banks[0],));row=cursor.fetchone()
        assert int(row['credit'])==9000 and str(row['transaction_date'])=='2026-10-02'
        cursor.execute('SELECT confirmed_on FROM client_finance_noncash_events WHERE operation_key=%s',(command.key,))
        from infrastructure.mysql.client_difference_repository import _today
        assert cursor.fetchone()['confirmed_on']==_today()
        cursor.execute('SELECT COUNT(*) n FROM staff_obligations WHERE case_no=%s',(case,));assert cursor.fetchone()['n']==0
    with pytest.raises(ClientDifferenceConflict):app.apply(ClientDifferenceCommand(case,item.identity,action,1000,'changed',before.version,command.key,'synthetic'))
    # Re-reading the same source must not resurrect the recognized remainder.
    _source(connection,case,item.identity,5000,after.version)
    assert next(i for i in app.query(case).items if i.identity==item.identity).remaining_ntd==0


def _source(conn,case,identity,computed,version):
    stage=PaymentStage.FIRST
    with MySqlUnitOfWork(conn) as work:
        with conn.cursor() as cursor:
            cursor.execute('SELECT due_date FROM client_obligations WHERE obligation_identity=%s',(identity,));due=cursor.fetchone()['due_date']
            command=SimpleNamespace(candidate=SimpleNamespace(case_no=case,expected_account_version=version,resulting_account_version=version+1),idempotency_key=IdempotencyKey(f'{case}:source:{computed}'),actor=ActorContext('synthetic'),reason='來源更新')
            assert persist_controlled_client_stage(cursor,command,SimpleNamespace(payment_stage=stage,amount=MoneyNTD(computed),due_date=due))
            cursor.execute('UPDATE client_finance_accounts SET aggregate_version=aggregate_version+1 WHERE case_no=%s',(case,))
        work.commit()


def test_manual_value_survives_source_then_adopt_restores_automatic_updates(connection):
    case='DIFF-MODE-'+uuid4().hex[:6];identities,_=support['_seed_mixed_case'](connection,case,False,partial_only=True)
    app=_app(connection);identity=identities[1]
    before=app.query(case)
    changed=app.apply(ClientDifferenceCommand(case,identity,'manual_amount',4900,'核對後更正',before.version,case+':mode-manual','synthetic'))
    _source(connection,case,identity,5100,changed.version)
    current=app.query(case);item=next(i for i in current.items if i.identity==identity)
    assert (item.mode,item.effective_ntd,item.computed_ntd,item.remaining_ntd)==('manual',4900,5100,4900)
    adopted=app.apply(ClientDifferenceCommand(case,identity,'adopt_calculation',None,'採用目前計算',current.version,case+':mode-auto','synthetic'))
    _source(connection,case,identity,5200,adopted.version)
    item=next(i for i in app.query(case).items if i.identity==identity)
    assert (item.mode,item.effective_ntd,item.computed_ntd,item.remaining_ntd)==('automatic',5200,5200,5200)


def test_settled_correction_adds_refund_without_rewriting_source_and_simple_close_has_no_extra_audit(connection):
    case='DIFF-SETTLED-'+uuid4().hex[:6];identities,_=_cash(connection,case)
    app=_app(connection);before=app.query(case)
    result=app.apply(ClientDifferenceCommand(case,identities[1],'manual_amount',4900,'更正計算結果',before.version,case+':settled-correction','synthetic'))
    original=next(i for i in result.items if i.identity==identities[1]);refund=next(i for i in result.items if i.direction=='payable_to_client')
    assert original.actual_ntd==5000 and original.expected_ntd==5000 and refund.remaining_ntd==100
    count=len(result.events)
    command=ClientDifferenceCommand(case,refund.identity,'close_refund',None,'',result.version,case+':refund-close-no-audit','synthetic')
    closed=app.apply(command);assert app.apply(command)==closed
    assert len(closed.events)==count
    closed_refund=next(i for i in closed.items if i.identity==refund.identity)
    assert closed_refund.expected_ntd==100 and closed_refund.actual_ntd==0 and closed_refund.remaining_ntd==0
    with connection.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) n FROM client_ledger_entries WHERE case_no=%s',(case,));assert cursor.fetchone()['n']==2
        cursor.execute('SELECT COUNT(*) n FROM client_finance_noncash_events WHERE operation_key=%s',(command.key,));assert cursor.fetchone()['n']==0


def test_customer_overrefund_recovery_can_be_partly_absorbed_and_partly_recorded_as_loss(connection,http):
    case='DIFF-REFUND-'+uuid4().hex[:6];_cash(connection,case,overage=True)
    application=_app(connection);before=application.query(case)
    refund=next(i for i in before.items if i.direction=='payable_to_client')
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO finance_import_rows(dedup_fingerprint,format_id,transaction_date,direction,credit,debit,currency,counterparty_account,bank_references,warnings,raw_payload,classification_type) VALUES(%s,'legacy','2026-11-02','outgoing',0,200,'TWD','SYNTHETIC-ACCOUNT','{}','[]','{}','client_refund')",(uuid4().hex+uuid4().hex,))
        source=int(cursor.lastrowid)
    connection.commit()
    body={'finance_import_row_ids':[source],'obligation_identities':[refund.identity]}
    url=f'/api/v1/orders/{case}/client-finance/refund-overage'
    checked=government_support['checked'];preview=checked(http.post(url+'/preview',json=body))
    checked(http.post(url+'/apply',json={**body,'expected_account_version':preview['account_version'],'preview_fingerprint':preview['preview_fingerprint'],'reason':'核對超付並另列追償'},headers={'Idempotency-Key':case+':refund'}))
    # End the readonly connection snapshot before observing another API UoW.
    connection.rollback()
    view=application.query(case);recovery=next(i for i in view.items if i.kind=='over_refund_recovery')
    assert recovery.remaining_ntd==100
    absorbed=application.apply(ClientDifferenceCommand(case,recovery.identity,'absorb_overpayment',40,'工會確認承擔',view.version,case+':absorb','synthetic'))
    assert next(i for i in absorbed.items if i.identity==recovery.identity).remaining_ntd==60
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO finance_import_rows(dedup_fingerprint,format_id,transaction_date,direction,credit,debit,currency,bank_references,warnings,raw_payload,classification_type) VALUES(%s,'legacy','2026-11-02','incoming',30,0,'TWD','{}','[]','{}','client_receipt')",(uuid4().hex+uuid4().hex,));incoming=int(cursor.lastrowid)
    connection.commit()
    recovery_url=f'/api/v1/orders/{case}/client-finance/refund-overage-recovery'
    selection={'recovery_identity':recovery.identity,'finance_import_row_id':incoming,'evidence_reference':'合成追償配對'}
    preview=checked(http.post(recovery_url+'/matching/preview',json=selection))
    matching=checked(http.post(recovery_url+'/matching/apply',json={**selection,'expected_recovery_version':preview['recovery_version'],'expected_account_version':preview['account_version'],'preview_fingerprint':preview['preview_fingerprint'],'reason':'核對原追償'},headers={'Idempotency-Key':case+':matching'}))
    selected={**selection,'matching_identity':matching['matching_identity'],'matching_version':matching['matching_version']}
    preview=checked(http.post(recovery_url+'/matched/preview',json=selected))
    checked(http.post(recovery_url+'/matched/apply',json={**selected,'expected_recovery_version':preview['recovery_version'],'expected_account_version':preview['account_version'],'preview_fingerprint':preview['preview_fingerprint'],'reason':'收到部分追償'},headers={'Idempotency-Key':case+':collection'}))
    connection.rollback()
    collected=application.query(case)
    final=application.apply(ClientDifferenceCommand(case,recovery.identity,'loss',30,'確認剩餘收不回',collected.version,case+':loss','synthetic'))
    recovery=next(i for i in final.items if i.identity==recovery.identity)
    assert (recovery.remaining_ntd,recovery.noncash_ntd,recovery.actual_ntd)==(0,70,30)
    refund=next(i for i in final.items if i.identity==refund.identity)
    assert refund.actual_ntd==200 and refund.expected_ntd==100
    with connection.cursor() as cursor:
        cursor.execute('SELECT debit FROM finance_import_rows WHERE id=%s',(source,));assert int(cursor.fetchone()['debit'])==200
        cursor.execute('SELECT COUNT(*) n FROM client_ledger_entries WHERE case_no=%s',(case,));assert cursor.fetchone()['n']==4
    items,_=query_case_accounting(connection,case)
    item=next(i for i in items if i.identity==recovery.identity)
    assert (item.expected_ntd,item.actual_ntd,item.noncash_ntd,item.remaining_ntd)==(100,30,70,0)


def test_repeated_correction_recalculates_unpaid_difference_without_creating_a_false_refund_and_collection(connection):
    case='DIFF-REPEAT-'+uuid4().hex[:6];identities,_=_cash(connection,case)
    owner=_app(connection);before=owner.query(case)
    lowered=owner.apply(ClientDifferenceCommand(case,identities[1],'manual_amount',4900,'第一次更正',before.version,case+':lower','synthetic'))
    raised=owner.apply(ClientDifferenceCommand(case,identities[1],'manual_amount',5100,'重新核對更正',lowered.version,case+':raise','synthetic'))
    assert not any(i.direction=='payable_to_client' and i.remaining_ntd for i in raised.items)
    assert sum(i.remaining_ntd for i in raised.items if i.direction=='receivable_from_client')==100
    assert next(i for i in raised.items if i.identity==identities[1]).actual_ntd==5000


def test_partial_cash_then_lower_calculation_preserves_allocated_principal_and_only_adds_actual_excess_refund(connection):
    from infrastructure.mysql.order_terms_read_model import _select_client_obligations,_client_obligation
    case='DIFF-PARTIAL-CORRECT-'+uuid4().hex[:6];identities,_=_cash(connection,case,partial=True)
    owner=_app(connection);before=owner.query(case)
    corrected=owner.apply(ClientDifferenceCommand(case,identities[1],'manual_amount',3900,'核對部分收款後更正',before.version,case+':correct','synthetic'))
    assert sum(i.remaining_ntd for i in corrected.items if i.direction=='payable_to_client')==100
    assert next(i for i in corrected.items if i.identity==identities[1]).actual_ntd==4000
    with connection.cursor() as cursor:
        source=next(r for r in _select_client_obligations(cursor,case,False) if r['obligation_identity']==identities[1])
        fact=_client_obligation(source)
        assert fact.net_settled_amount==fact.contracted_amount==MoneyNTD(4000)
