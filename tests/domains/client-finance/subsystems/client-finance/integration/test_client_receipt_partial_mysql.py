"""Real owner Apply: partial cash, remaining balance, replay and later completion."""
from argparse import Namespace
import hashlib
import json
import os

import pymysql
import pytest

from api.dependencies.client_receipt_reconciliation import ClientReceiptReconciliationApplication
from domains.client_finance.reconciliation import PaymentStage
from infrastructure.mysql.client_receipt_reconciliation_repository import MySqlClientReceiptReconciliationRepository, ClientReceiptMySqlUnitOfWork
from infrastructure.mysql.client_payments_query_repository import query_case_accounting
from scripts.bootstrap_disposable_mysql_schema import bootstrap
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.client_finance.reconciliation_workflow import ClientReconciliationWorkflow, ClientReconciliationApplyRequest, ReconciliationSelection, ClientReconciliationError
from functools import partial
from infrastructure.mysql.accounting_workspace_repository import MySqlAccountingWorkspaceState
from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting
from infrastructure.mysql.monthly_accounting_repository import MySqlMonthlyAccountingSource
from subsystems.finance_import.accounting_workspace import AccountingWorkspace, AccountingConflict
from subsystems.finance_import.monthly_accounting import MonthlyAccountingQuery

pytestmark = pytest.mark.skipif(not os.getenv('LABOR_UNION_TEST_MYSQL_DATABASE'), reason='requires an explicitly configured disposable lu_test_* database')


def test_partial_cash_then_topup_preserves_sources_and_only_completes_deposit_at_the_end():
    host=os.environ['LABOR_UNION_TEST_MYSQL_HOST']
    assert host in {'localhost','127.0.0.1'} and os.getenv('APP_ENV')=='development'
    database=os.environ['LABOR_UNION_TEST_MYSQL_DATABASE']+'_receipt_partial'
    args=Namespace(host=host,port=int(os.environ['LABOR_UNION_TEST_MYSQL_PORT']),user=os.environ['LABOR_UNION_TEST_MYSQL_USER'],password=os.environ['LABOR_UNION_TEST_MYSQL_PASSWORD'],database=database,confirm_database=database)
    bootstrap(args)  # Refuses existing targets; never resets a database.
    connection=pymysql.connect(host=host,port=args.port,user=args.user,password=args.password,database=database,charset='utf8mb4',cursorclass=pymysql.cursors.DictCursor,autocommit=False)
    case='ACCT-PARTIAL-1';obligation='accounting-partial:deposit'
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO clients(case_no,name) VALUES (%s,'Synthetic Client')",(case,))
            cursor.execute("INSERT INTO orders(case_no,client_id,status) VALUES (%s,%s,'洽談中')",(case,cursor.lastrowid))
            cursor.execute("INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES (%s,0)",(case,))
            cursor.execute("INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,after_due_date,source_event_identity,expected_account_version,idempotency_key,actor,reason) VALUES (%s,%s,'deposit','receivable_from_client','established',0,10000,'2026-10-01','synthetic',0,'synthetic-obligation','synthetic','fixture')",(obligation,case))
            event=cursor.lastrowid
            cursor.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,amount_due_ntd,due_date,status,current_event_id,projection_version) VALUES (%s,%s,'deposit','receivable_from_client',10000,'2026-10-01','open',%s,0)",(obligation,case,event))
            cursor.execute("INSERT INTO finance_import_batches(format_id,sheet_name,header_row,row_count) VALUES ('sinopac','synthetic',1,2)")
            batch=cursor.lastrowid
            banks=[]
            for index,amount in enumerate((9000,1000)):
                cursor.execute("INSERT INTO finance_import_rows(dedup_fingerprint,batch_id,format_id,transaction_date,credit,direction,bank_references,warnings,raw_payload,classification_type) VALUES (%s,%s,'sinopac','2026-10-02',%s,'incoming',%s,'[]','{}','client_receipt')",(hashlib.sha256(f'partial-{index}'.encode()).hexdigest(),batch,amount,'{}'))
                banks.append(str(cursor.lastrowid))
                cursor.execute("INSERT INTO finance_import_classification_events(batch_id,finance_import_row_id,classification_version,canonical_fact_version,classification_type,disposition,decision_facts_fingerprint,target_identities,evidence,available_actions,actor,reason) VALUES (%s,%s,1,1,'client_receipt','manual_review',%s,%s,'[]','[]','synthetic','synthetic confirmed case')",(batch,int(banks[-1]),'a'*64,json.dumps([obligation])))
        connection.commit()
        repository=MySqlClientReceiptReconciliationRepository(connection)
        app=ClientReceiptReconciliationApplication(repository,ClientReconciliationWorkflow(repository,lambda:ClientReceiptMySqlUnitOfWork(connection)))
        selection=ReconciliationSelection(case,PaymentStage.DEPOSIT,(banks[0],),(obligation,),allow_partial_receipt=True)
        preview=app.preview(selection)
        first=ClientReconciliationApplyRequest(selection,ExpectedVersion(0),preview.fingerprint,IdempotencyKey('partial-9000'),ActorContext('synthetic'),'餘額續收',CorrelationId('partial-9000'))
        assert app.apply(first).status.value=='partial'
        assert app.apply(first).account_version==1
        with connection.cursor() as cursor:
            cursor.execute('SELECT amount_due_ntd,status FROM client_obligations WHERE obligation_identity=%s',(obligation,))
            assert cursor.fetchone()=={'amount_due_ntd':1000,'status':'open'}
            cursor.execute("SELECT COUNT(*) n FROM client_finance_outbox WHERE case_no=%s AND intent_type='orders_deposit_reconciled'",(case,))
            assert cursor.fetchone()['n']==0
        items,_=query_case_accounting(connection,case)
        assert (items[0].expected_ntd,items[0].actual_ntd,items[0].remaining_ntd)==(10000,9000,1000)
        selection=ReconciliationSelection(case,PaymentStage.DEPOSIT,(banks[1],),(obligation,))
        preview=app.preview(selection)
        stale=ClientReconciliationApplyRequest(selection,ExpectedVersion(0),preview.fingerprint,IdempotencyKey('stale'),ActorContext('synthetic'),'',CorrelationId('stale'))
        with pytest.raises(ClientReconciliationError):app.apply(stale)
        final=ClientReconciliationApplyRequest(selection,ExpectedVersion(1),preview.fingerprint,IdempotencyKey('topup-1000'),ActorContext('synthetic'),'補足餘額',CorrelationId('topup-1000'))
        assert app.apply(final).status.value=='exact'
        assert app.apply(final).account_version==2
        items,_=query_case_accounting(connection,case)
        assert (items[0].expected_ntd,items[0].actual_ntd,items[0].remaining_ntd)==(10000,10000,0)
        with connection.cursor() as cursor:
            cursor.execute('SELECT contracted_amount_ntd,allocated_net_amount_ntd FROM client_deposit_settlement_projection WHERE case_no=%s',(case,))
            assert cursor.fetchone()=={'contracted_amount_ntd':10000,'allocated_net_amount_ntd':10000}
            cursor.execute('SELECT amount_ntd FROM client_ledger_entries WHERE case_no=%s ORDER BY id',(case,))
            assert [row['amount_ntd'] for row in cursor.fetchall()]==[9000,1000]
        for overage in (False, True):
            mixed_case='ACCT-MIXED-'+str(int(overage))
            identities,mixed_banks=_seed_mixed_case(connection,mixed_case,overage)
            mixed=ReconciliationSelection(mixed_case,None,tuple(sorted(mixed_banks)),tuple(sorted(identities)),allow_overage_disposition=overage)
            assert {str(row['finance_import_row_id']) for row in app.query(mixed_case)['bank_facts']}==set(mixed_banks)
            if not overage:
                with connection.cursor() as cursor:
                    cursor.execute("INSERT INTO finance_import_integrity_events(batch_id,finance_import_row_id,issue_code,active,evidence_snapshot,source_event_identity) SELECT batch_id,id,'synthetic_hold',1,'{}','synthetic-hold' FROM finance_import_rows WHERE id=%s",(int(mixed_banks[0]),))
                connection.commit()
                assert {str(row['finance_import_row_id']) for row in app.query(mixed_case)['bank_facts']}=={mixed_banks[1]}
                with pytest.raises(ValueError):app.preview(mixed)
                with connection.cursor() as cursor:
                    cursor.execute("INSERT INTO finance_import_integrity_events(batch_id,finance_import_row_id,issue_code,active,evidence_snapshot,source_event_identity) SELECT batch_id,id,'synthetic_hold',0,'{}','synthetic-hold-cleared' FROM finance_import_rows WHERE id=%s",(int(mixed_banks[0]),))
                connection.commit()
            mixed_preview=app.preview(mixed)
            assert mixed_preview.candidate.status.value==('overage' if overage else 'exact')
            assert mixed_preview.candidate.payment_stage is None
            mixed_request=ClientReconciliationApplyRequest(mixed,ExpectedVersion(0),mixed_preview.fingerprint,IdempotencyKey(mixed_case),ActorContext('synthetic'),'同案多筆合計核銷',CorrelationId(mixed_case))
            receipt=app.apply(mixed_request)
            assert receipt.ledger_entry_count==2 and app.apply(mixed_request)==receipt
            with connection.cursor() as cursor:
                cursor.execute('SELECT COUNT(*) n FROM client_obligations WHERE case_no=%s AND direction=\'receivable_from_client\' AND amount_due_ntd>0',(mixed_case,))
                assert cursor.fetchone()['n']==0
                cursor.execute("SELECT COALESCE(SUM(amount_due_ntd),0) amount FROM client_obligations WHERE case_no=%s AND obligation_type='refund'",(mixed_case,))
                assert cursor.fetchone()['amount']==(100 if overage else 0)
                if overage:
                    cursor.execute("SELECT case_no,bank_code,bank_account FROM client_refund_recipient_snapshots WHERE case_no=%s",(mixed_case,))
                    assert cursor.fetchall()==[{'case_no':mixed_case,'bank_code':'000','bank_account':'SYNTHETIC-ACCOUNT'}]
                cursor.execute('SELECT contracted_amount_ntd,allocated_net_amount_ntd FROM client_deposit_settlement_projection WHERE case_no=%s',(mixed_case,))
                assert cursor.fetchone()=={'contracted_amount_ntd':5000,'allocated_net_amount_ntd':5000}
        historical='ACCT-HISTORY'
        identities,historical_banks=_seed_mixed_case(connection,historical,False,partial_only=True)
        selected=ReconciliationSelection(historical,None,tuple(sorted(historical_banks)),tuple(sorted(identities)),allow_partial_receipt=True)
        preview=app.preview(selected)
        app.apply(ClientReconciliationApplyRequest(selected,ExpectedVersion(0),preview.fingerprint,IdempotencyKey('history-cash'),ActorContext('synthetic'),'歷史實收',CorrelationId('history-cash')))
        source=MySqlMonthlyAccountingSource(connection)
        workspace=AccountingWorkspace(MySqlAccountingWorkspaceState(connection),partial(query_case_accounting,connection),partial(query_case_staff_accounting,connection),source.case_bank_facts)
        monthly=MonthlyAccountingQuery(source,partial(workspace.query,include_sources=False))
        before=workspace.query(historical)
        report_before=monthly.query('2026-10','2026-10','all')
        versions={item.identity:item.version for item in (*before.client_items,*before.staff_items)}
        with pytest.raises(AccountingConflict):workspace.mark_historical(historical,'歷史原因無法查明',{},'history-marker','synthetic')
        marker=workspace.mark_historical(historical,'歷史原因無法查明',versions,'history-marker','synthetic')
        assert workspace.mark_historical(historical,'歷史原因無法查明',versions,'history-marker','synthetic')==marker
        assert sum(item.remaining_ntd for item in marker.amounts)==1000
        after=workspace.query(historical)
        assert after.client_items==before.client_items and after.bank_facts==before.bank_facts
        report_after=monthly.query('2026-10','2026-10','all')
        assert historical in report_after.excluded_cases
        assert report_before.rows[0].expected_in_ntd-report_after.rows[0].expected_in_ntd==10000
        assert report_before.rows[0].cash_in_ntd-report_after.rows[0].cash_in_ntd==9000
        with connection.cursor() as cursor:
            cursor.execute('SELECT status FROM orders WHERE case_no=%s',(historical,))
            assert cursor.fetchone()['status']=='洽談中'
    finally:connection.close()


def _seed_mixed_case(connection, case, overage, *, partial_only=False, stage_amounts=(5000, 5000), bank_amounts=None):
    identities=[case+':deposit',case+':first'];banks=[]
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO clients(case_no,name) VALUES (%s,'Synthetic Client')",(case,))
        cursor.execute("INSERT INTO orders(case_no,client_id,status) VALUES (%s,%s,'洽談中')",(case,cursor.lastrowid))
        # Source query numbers are provenance, never case identities.  An
        # unbound lookalike must not supply another source's refund account.
        cursor.execute("INSERT INTO beclass_records(query_no,refund_bank_code,refund_account_no) VALUES (%s,'999','WRONG-SYNTHETIC-ACCOUNT')",(case,))
        cursor.execute("INSERT INTO beclass_records(query_no,bound_case_no,refund_bank_code,refund_account_no) VALUES (%s,%s,'000','SYNTHETIC-ACCOUNT')",('source:'+case,case))
        cursor.execute("INSERT INTO client_finance_accounts(case_no) VALUES (%s)",(case,))
        for index,stage in enumerate(('deposit','first')):
            amount = stage_amounts[index]
            cursor.execute("INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,after_due_date,source_event_identity,expected_account_version,idempotency_key,actor,reason) VALUES (%s,%s,%s,'receivable_from_client','established',0,%s,%s,'synthetic',0,%s,'synthetic','fixture')",(identities[index],case,stage,amount,'2026-10-0'+str(index+1),identities[index]))
            event=cursor.lastrowid
            cursor.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,amount_due_ntd,due_date,status,current_event_id,projection_version) VALUES (%s,%s,%s,'receivable_from_client',%s,%s,'open',%s,0)",(identities[index],case,stage,amount,'2026-10-0'+str(index+1),event))
        cursor.execute("INSERT INTO finance_import_batches(format_id,sheet_name,header_row,row_count) VALUES ('sinopac','synthetic',1,2)")
        batch=cursor.lastrowid
        if bank_amounts is None:
            bank_amounts = (9000,) if partial_only else (9000, 1100 if overage else 1000)
        for index,amount in enumerate(bank_amounts):
            cursor.execute("INSERT INTO finance_import_rows(dedup_fingerprint,batch_id,format_id,transaction_date,credit,direction,bank_references,warnings,raw_payload,classification_type) VALUES (%s,%s,'sinopac','2026-10-02',%s,'incoming','{}','[]','{}','client_receipt')",(hashlib.sha256(f'{case}-{index}'.encode()).hexdigest(),batch,amount))
            banks.append(str(cursor.lastrowid))
            cursor.execute("INSERT INTO finance_import_classification_events(batch_id,finance_import_row_id,classification_version,canonical_fact_version,classification_type,disposition,decision_facts_fingerprint,target_identities,evidence,available_actions,actor,reason) VALUES (%s,%s,1,1,'client_receipt','manual_review',%s,%s,'[]','[]','synthetic','synthetic case confirmed')",(batch,int(banks[-1]),'a'*64,json.dumps(identities)))
    connection.commit()
    return identities,banks
