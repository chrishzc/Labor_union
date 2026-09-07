"""T11-2: real source-only review, typed query, formal Apply and replay readback.

Requires an explicitly bootstrapped disposable lu_test_* database. No provider calls.
"""
from __future__ import annotations

from argparse import Namespace
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

import pandas as pd
import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap

DATABASE = os.getenv('LABOR_UNION_TEST_MYSQL_DATABASE')
pytestmark = pytest.mark.skipif(not DATABASE, reason='requires disposable MySQL')


def _arguments() -> Namespace:
    return Namespace(
        host=os.environ['LABOR_UNION_TEST_MYSQL_HOST'],
        port=int(os.environ['LABOR_UNION_TEST_MYSQL_PORT']),
        user=os.environ['LABOR_UNION_TEST_MYSQL_USER'],
        password=os.environ['LABOR_UNION_TEST_MYSQL_PASSWORD'],
        database=DATABASE,
        confirm_database=DATABASE,
    )


@pytest.fixture(autouse=True)
def _use_explicit_disposable_database(monkeypatch):
    settings = {
        'DB_HOST': os.environ['LABOR_UNION_TEST_MYSQL_HOST'],
        'DB_PORT': os.environ['LABOR_UNION_TEST_MYSQL_PORT'],
        'DB_USER': os.environ['LABOR_UNION_TEST_MYSQL_USER'],
        'DB_PASSWORD': os.environ['LABOR_UNION_TEST_MYSQL_PASSWORD'],
        'DB_DATABASE': DATABASE,
    }
    for name, value in settings.items():
        monkeypatch.setenv(name, value)
    from infrastructure.mysql import mysql_adapter
    monkeypatch.setattr(mysql_adapter, 'DB_CONFIG', {
        'host': settings['DB_HOST'], 'port': int(settings['DB_PORT']),
        'user': settings['DB_USER'], 'password': settings['DB_PASSWORD'],
        'database': settings['DB_DATABASE'], 'charset': 'utf8mb4',
    })


def _counts():
    from infrastructure.mysql.mysql_adapter import get_connection
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT DATABASE() AS name')
            assert cursor.fetchone()['name'] == DATABASE
            tables = ('finance_import_rows', 'finance_import_occurrences',
                      'finance_import_source_reviews', 'finance_import_source_review_occurrences',
                      'finance_import_dispatch_events', 'finance_import_reconciliation_receipts',
                      'finance_import_apply_receipts', 'client_ledger_entries', 'staff_payout_events')
            result = {}
            for table in tables:
                cursor.execute(f'SELECT COUNT(*) AS n FROM {table}')
                result[table] = int(cursor.fetchone()['n'])
            return result
    finally:
        connection.close()


def _seed_deposit(case_no, token):
    from infrastructure.mysql.mysql_adapter import get_connection
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO clients(case_no,name) VALUES (%s,%s)', (case_no, 'T11 synthetic client'))
            client_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO orders(case_no,client_id,status) VALUES (%s,%s,'服務中')", (case_no, client_id))
            identity = f'deposit:{case_no}'
            cursor.execute("INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,after_due_date,source_event_identity,expected_account_version,idempotency_key,actor,reason) VALUES (%s,%s,'deposit','receivable_from_client','established',0,300,'2026-09-01',%s,0,%s,'t11-test','isolated synthetic deposit')", (identity, case_no, token, token))
            event_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,amount_due_ntd,due_date,status,current_event_id,projection_version) VALUES (%s,%s,'deposit','receivable_from_client',300,'2026-09-01','open',%s,0)", (identity, case_no, event_id))
        connection.commit()
    finally:
        connection.close()


def test_t11_source_review_query_apply_and_replay(tmp_path):
    bootstrap(_arguments())
    assert DATABASE and DATABASE.startswith('lu_test_') and os.environ['DB_DATABASE'] == DATABASE
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.dependencies.admin_auth import require_admin
    from api.dependencies.finance_import import build_finance_import_application
    from api.routes.finance_import import router
    from infrastructure.mysql.finance_import_owning_domain_composite import MySqlFinanceImportOwningDomainComposite
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.access.authentication_session import AdminPrincipal
    from subsystems.finance_import.import_workflow import FinanceImportApplyRequest

    token = uuid4().hex
    # Unique canonical virtual-account case in this disposable schema, not production data.
    sequence = int(token[:6], 16) % 1000
    year = 200 + int(token[6:10], 16) % 700
    case_no = f'{year:03d}{sequence:06d}'
    _seed_deposit(case_no, token)
    workbook = tmp_path / 't11-source-review.xlsx'
    headers = ['帳號', '交易日', '計息日', '入帳日', '摘要', '幣別', '支出', '存入', '餘額', '銷帳編號', '交易參考編號', '', '更正註記', '存摺備註']
    account = 'LU-TEST-SOURCE'
    pd.DataFrame([headers,
        [account, '2026/09/01 09:08:07', '2026/09/01', '2026/09/01', '轉帳', 'TWD', None, 300, 9000, f'99781699{year:03d}{sequence:03d}', token, 'synthetic', None, 'fixture'],
        [account, '2026/09/02 09:08:07', '2026/09/02', '2026/09/02', '轉帳', 'TWD', None, 300.5, 9300.5, None, token+'-review', 'synthetic invalid amount', None, 'fixture'],
    ]).to_excel(workbook, sheet_name='來源', index=False, header=False)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(1, 't11-test', 'Synthetic', 'admin')
    before = _counts()
    headers_http = {'Idempotency-Key': f't11-ingest:{token}', 'X-Correlation-ID': f't11:{token}'}
    with TestClient(app) as client:
        def ingest(key):
            return client.post('/api/v1/finance-import/workbooks/ingest', headers={**headers_http, 'Idempotency-Key': key}, files={'workbook': (workbook.name, workbook.read_bytes(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
        intake = ingest(headers_http['Idempotency-Key'])
        assert intake.status_code == 200, intake.text
        data = intake.json()['data']
        assert (data['source_row_count'], data['canonical_created_count'], data['source_warning_count']) == (2, 1, 1)
        batch = data['batch_identity']
        url = f'/api/v1/finance-import/batches/{batch}'
        preview = client.post('/api/v1/finance-import/batches/preview', json={'batch_identity': batch}, headers=headers_http)
        assert preview.status_code == 200, preview.text
        assert preview.json()['data']['counts']['ready_dispatch'] == 1
        assert preview.json()['data']['apply_allowed'] is True
        staged = _counts()
        manifest = client.get(url+'/manifest')
        assert manifest.status_code == 200, manifest.text
        assert manifest.json()['data']['review_count'] == 1, 'T11_2_SOURCE_REVIEW_OCCURRENCE_NOT_IN_QUERY'
        reviews = client.get(url+'/review-rows')
        assert reviews.status_code == 200, reviews.text
        page = reviews.json()['data']
        assert page['batch_identity'] == batch and page['items'] == []
        assert len(page['source_reviews']) == 1
        source = page['source_reviews'][0]
        assert source['source_sheet'] == '來源' and source['source_row'] == 3
        assert 'invalid:transaction_amount' in source['issue_codes']
        assert set(source) == {'review_id', 'review_identity', 'source_sheet', 'source_row', 'issue_codes', 'created_at'}
        assert client.get(url+'/review-rows').json() == reviews.json()
        assert _counts() == staged, 'query must not create any bank/owner fact'
        connection = get_connection()
        try:
            application = build_finance_import_application(connection, MySqlFinanceImportOwningDomainComposite(connection))
            plan = application.preview_batch(batch, CorrelationId('t11-preview'))
            request = FinanceImportApplyRequest(batch, ExpectedVersion(plan.batch_version), plan.fingerprint, IdempotencyKey('t11-apply:'+token), ActorContext('t11-test'), 'synthetic batch acceptance', CorrelationId('t11-apply'))
            receipt = application.apply_batch(request)
            assert receipt.reconciled_count == 1
            applied = _counts()
            assert application.apply_batch(request) == receipt
            assert _counts() == applied
        finally:
            connection.close()
        assert applied['finance_import_dispatch_events'] == staged['finance_import_dispatch_events'] + 1
        assert applied['finance_import_reconciliation_receipts'] == staged['finance_import_reconciliation_receipts'] + 1
        assert applied['client_ledger_entries'] == before['client_ledger_entries'] + 1
        assert applied['staff_payout_events'] == before['staff_payout_events']  # This batch contains no staff payout.
        assert client.get(url+'/review-rows').json() == reviews.json()
        replay = ingest(headers_http['Idempotency-Key'])
        reselect = ingest(headers_http['Idempotency-Key'])
        assert replay.status_code == reselect.status_code == 200
        assert replay.json()['data']['batch_identity'] == reselect.json()['data']['batch_identity'] == batch
        assert _counts() == applied, 'replay/same-key reselect must not duplicate dispatch, receipts, payout or review occurrences'
        assert client.get(url+'/manifest').json()['data']['review_count'] == 1
        # Exact API response crosses the real typed client and page, without DB credentials in the UI process.
        exchange = tmp_path/'review-exchange.json'
        exchange.write_text(json.dumps({'ingestion': intake.json(), 'preview': preview.json(), 'manifest': manifest.json(), 'reviews': reviews.json()}), encoding='utf-8')
        root = Path(__file__).resolve().parents[1]
        ui_report = tmp_path/'typed-ui-report.json'
        result = subprocess.run(['npm', '--prefix', str(root/'ui_react'), 'test', '--', 'src/tests/finance_source_review_list.test.tsx', '-t', 'same-run source-review', '--reporter=json', '--outputFile', str(ui_report)], cwd=root, env={'PATH': os.environ['PATH'], 'HOME': str(tmp_path), 'CI': 'true', 'FI_REVIEW_EXCHANGE': str(exchange)}, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout[-5000:]+result.stderr[-5000:]
        report = json.loads(ui_report.read_text(encoding='utf-8'))
        assert report.get('numPassedTests') == 1 and report.get('numFailedTests') == 0, report
        print('T11_2_READBACK', json.dumps({'before': before, 'staged': staged, 'applied_and_replayed': applied, 'source_review_count': 1, 'typed_ui': 'passed'}, sort_keys=True))
