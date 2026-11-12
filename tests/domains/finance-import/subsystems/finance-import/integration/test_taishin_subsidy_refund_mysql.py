"""Opt-in current R台 acceptance against an explicitly provisioned isolated MySQL.

Uses the actual workbook importer, correction owner writers and source claims.
The caller provisions a fresh canonical lu_test_* schema; no schema reset/drop.
"""
from datetime import date
from dataclasses import replace
import json
import os
from pathlib import Path
from runpy import run_path
from uuid import uuid4

import pandas as pd
import pymysql
import pytest

pytestmark = pytest.mark.skipif(os.getenv('RTA_MYSQL_RETEST') != '1', reason='requires explicit isolated current MySQL acceptance')


@pytest.fixture
def connection(monkeypatch):
    assert os.getenv('APP_ENV') == 'development'
    host = os.environ['LABOR_UNION_TEST_MYSQL_HOST']
    database = os.environ['LABOR_UNION_TEST_MYSQL_DATABASE']
    assert host in {'localhost', '127.0.0.1'} and database.startswith('lu_test_')
    config = dict(host=host, port=int(os.environ['LABOR_UNION_TEST_MYSQL_PORT']),
                  user=os.environ['LABOR_UNION_TEST_MYSQL_USER'], password=os.environ['LABOR_UNION_TEST_MYSQL_PASSWORD'],
                  database=database, charset='utf8mb4', autocommit=False)
    from infrastructure.mysql import mysql_adapter
    monkeypatch.setattr(mysql_adapter, 'DB_CONFIG', config)
    conn = pymysql.connect(**config, cursorclass=pymysql.cursors.DictCursor)
    with conn.cursor() as cursor:
        cursor.execute('SELECT DATABASE() db,@@hostname server')
        identity = cursor.fetchone()
        assert identity['db'] == database and identity['server']
    conn.rollback()
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()


def _seed(connection, amounts, missing_due):
    from subsystems.client_finance.virtual_account_resolution import build_client_virtual_account

    seed = run_path(str(Path(__file__).with_name('test_subsidy_confirmation_mysql.py')))['seed']
    case, _, _ = seed(connection, False, 'advance', subsidy=sum(amounts), actual_end=date(2026, 8, 31))
    with connection.cursor() as cursor:
        identities = tuple(f'subsidy:{case}:{i}' for i in range(len(amounts)))
        for identity, amount in zip(identities, amounts):
            due = None if missing_due else date(2026, 10, 15)
            cursor.execute("INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,after_due_date,source_event_identity,expected_account_version,idempotency_key,actor,reason) VALUES (%s,%s,'subsidy_return','payable_to_client','established',0,%s,%s,%s,0,%s,'rta-mysql','Synthetic original official due date')", (identity, case, amount, due, identity, identity))
            cursor.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,amount_due_ntd,due_date,status,current_event_id,projection_version) VALUES (%s,%s,'subsidy_return','payable_to_client',%s,%s,'open',%s,0)", (identity, case, amount, due, cursor.lastrowid))
    connection.commit()
    return case, build_client_virtual_account(case)[-6:], identities


def _snapshot(connection, case):
    with connection.cursor() as cursor:
        result = {}
        for table in ('client_ledger_entries', 'client_obligation_events', 'client_finance_outbox',
                      'client_refund_reversal_apply_receipts', 'client_over_refund_recoveries'):
            cursor.execute(f'SELECT COUNT(*) n FROM {table} WHERE case_no=%s', (case,))
            result[table] = cursor.fetchone()['n']
        cursor.execute("SELECT obligation_identity,amount_due_ntd,due_date,status FROM client_obligations WHERE case_no=%s AND obligation_type='subsidy_return' ORDER BY obligation_identity", (case,))
        result['obligations'] = list(cursor.fetchall())
        cursor.execute("SELECT allocation.obligation_identity,allocation.amount_ntd FROM client_ledger_obligation_allocations allocation JOIN client_ledger_entries entry ON entry.id=allocation.ledger_entry_id WHERE entry.case_no=%s AND entry.entry_type<>'receipt' ORDER BY allocation.obligation_identity", (case,))
        result['allocations'] = list(cursor.fetchall())
        cursor.execute('SELECT amount_due_ntd,status FROM client_over_refund_recoveries WHERE case_no=%s', (case,))
        result['recoveries'] = list(cursor.fetchall())
        cursor.execute("SELECT entry_type,amount_ntd FROM client_ledger_entries WHERE case_no=%s AND entry_type<>'receipt'", (case,))
        result['ledger'] = list(cursor.fetchall())
        return result


@pytest.mark.parametrize('amounts,cash,mode,missing_due', [
    ((6000,),6000,'exact',False), ((6000,),5970,'exact',False),
    ((2500,3500),5900,'exact',False), ((6000,),6030,'overage',False),
    ((2500,3500),6030,'overage',False), ((6000,6000),6000,'choose_second',False),
    ((6000,),6000,'exact',True),
])
def test_current_rta_mysql_preview_apply_replay(connection, tmp_path, amounts, cash, mode, missing_due):
    from api.dependencies.finance_import import build_finance_import_application
    from domains.finance_import.correction import FinanceImportCorrectionSelection
    from domains.finance_import.planning import FinanceClassificationType
    from infrastructure.mysql.finance_import_owning_domain_composite import MySqlFinanceImportOwningDomainComposite
    from infrastructure.mysql.mysql_adapter import get_connection
    from scripts.imports.finance_statement_normalizer import normalize_workbook
    from shared_kernel.fingerprints import PreviewFingerprint
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.finance_import.correction_workflow import FinanceImportCorrectionApplyRequest, FinanceImportCorrectionWorkflowError
    from subsystems.finance_import.ingestion import ingest_finance_workbook

    case, suffix, identities = _seed(connection, amounts, missing_due)
    workbook = tmp_path / f'{case}.xlsx'
    pd.DataFrame([['說明'], ['序號','交易日期','交易時間','帳務日期','摘要','支出金額','存入金額','帳戶餘額','備註'],
                  ['0001','2026/10/15','09:01:00','2026/10/15','轉出',str(cash),'','90000',f'HC{suffix}']]).to_excel(workbook,index=False,header=False)
    actor = ActorContext('rta-mysql'); correlation = CorrelationId(f'rta:{case}')
    ingested = ingest_finance_workbook(str(workbook), IdempotencyKey(f'{case}:import'), actor,
                                     connection_factory=get_connection, normalizer=normalize_workbook)
    assert ingested.canonical_created_count == 1
    with connection.cursor() as cursor:
        cursor.execute('SELECT id,debit,counterparty_account FROM finance_import_rows WHERE batch_id=%s', (int(ingested.batch_identity.split(':')[-1]),))
        bank = cursor.fetchone()
        assert bank['debit'] == cash and bank['counterparty_account'] is None
        cursor.execute('SELECT COUNT(*) n FROM client_refund_recipient_snapshots WHERE case_no=%s', (case,))
        assert cursor.fetchone()['n'] == 0
        cursor.execute('SELECT client_id FROM orders WHERE case_no=%s', (case,))
        client_id = cursor.fetchone()['client_id']
    app = build_finance_import_application(connection, MySqlFinanceImportOwningDomainComposite(connection))
    plan = app.preview_batch(ingested.batch_identity, correlation)
    expected = 'due_date_missing' if missing_due else 'outgoing_client_refund_multiple_fee_matches' if mode == 'choose_second' else 'outgoing_client_refund_amount_mismatch' if mode == 'overage' else None
    assert plan.rows[0].pending_reason == expected
    if expected is None:
        from domains.finance_import.planning import FinanceImportDisposition
        old_reason_frame = replace(plan.rows[0], disposition=FinanceImportDisposition.BUSINESS_PENDING,
            target_identities=(f'client:{client_id}',), pending_reason='due_date_missing', subsidy_preflight=None)
        refreshed = MySqlFinanceImportOwningDomainComposite(connection).resolve(old_reason_frame)
        assert refreshed.disposition is FinanceImportDisposition.CREATE and refreshed.pending_reason is None
    selected = (identities[1],) if mode == 'choose_second' else identities
    selection = FinanceImportCorrectionSelection(f"finance-import-row:{bank['id']}", FinanceClassificationType.CLIENT_SUBSIDY_RETURN,
        selected, 'Synthetic current subsidy refund', (f'{case}:source',), allow_refund_overage_recovery=mode == 'overage')
    before = _snapshot(connection, case)
    if missing_due:
        with pytest.raises(FinanceImportCorrectionWorkflowError) as rejected:
            app.preview_correction(selection, correlation)
        assert rejected.value.error.code == 'due_date_missing'
        current = app.correction_workflow._repository.load(selection, for_update=False)
        rejected_request = FinanceImportCorrectionApplyRequest(selection, ExpectedVersion(current.batch_version),
            ExpectedVersion(current.canonical_fact_version), ExpectedVersion(current.alert_version), PreviewFingerprint('f'*64),
            IdempotencyKey(f'{case}:blocked'), actor, correlation)
        with pytest.raises(FinanceImportCorrectionWorkflowError) as applied:
            app.correct_and_post(rejected_request)
        assert applied.value.error.code == rejected.value.error.code
        assert _snapshot(connection, case) == before
        evidence = os.getenv('RTA_MYSQL_EVIDENCE_DIR')
        if evidence:
            folder=Path(evidence);folder.mkdir(parents=True,exist_ok=True)
            (folder/f'{case}.json').write_text(json.dumps({'case':case,'before':before,'after':before,
                'preview_and_apply_blocker':'due_date_missing','writes':'none'},default=str,indent=2),encoding='utf-8')
        return
    checked = app.preview_correction(selection, correlation)
    assert _snapshot(connection, case) == before
    due_total = sum(amounts[1:2]) if mode == 'choose_second' else sum(amounts)
    assert checked.candidate.refund_preview.transfer_fee.amount == max(0, due_total-cash)
    assert checked.candidate.refund_preview.remaining_amount.amount == 0
    request = FinanceImportCorrectionApplyRequest(selection, ExpectedVersion(checked.batch_version), ExpectedVersion(checked.canonical_fact_version),
        ExpectedVersion(checked.alert_version), checked.fingerprint, IdempotencyKey(f'{case}:apply'), actor, correlation)
    first = app.correct_and_post(request)
    after = _snapshot(connection, case)
    assert app.correct_and_post(request) == first and _snapshot(connection, case) == after
    assert after['ledger'] == [{'entry_type':'subsidy_advance','amount_ntd':cash}]
    assert after['client_refund_reversal_apply_receipts'] == 1
    assert sum(item['amount_ntd'] for item in after['allocations']) == due_total
    assert all(item['due_date'] == date(2026,10,15) for item in after['obligations'])
    assert all(item['amount_due_ntd'] == 0 for item in after['obligations'] if item['obligation_identity'] in selected)
    assert after['recoveries'] == ([{'amount_due_ntd':cash-due_total,'status':'open'}] if mode == 'overage' else [])
    reimported = ingest_finance_workbook(str(workbook), IdempotencyKey(f'{case}:reimport'), actor,
                                      connection_factory=get_connection, normalizer=normalize_workbook)
    assert reimported.canonical_created_count == 0 and reimported.duplicate_occurrence_count == 1
    connection.rollback()  # Refresh the read transaction after the other ingestion connection.
    assert _snapshot(connection, case) == after
    evidence = os.getenv('RTA_MYSQL_EVIDENCE_DIR')
    if evidence:
        folder = Path(evidence); folder.mkdir(parents=True,exist_ok=True)
        (folder/f'{case}.json').write_text(json.dumps({'database':os.environ['LABOR_UNION_TEST_MYSQL_DATABASE'], 'case':case,
            'mode':mode,'before':before,'after':after,'receipt':str(first),'replay':'passed','reimport':'passed'},default=str,ensure_ascii=False,indent=2),encoding='utf-8')
