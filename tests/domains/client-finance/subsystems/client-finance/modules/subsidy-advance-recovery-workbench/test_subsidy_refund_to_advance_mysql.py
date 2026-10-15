"""Opt-in MySQL evidence: customer refund -> advance register -> recovery.

Only a newly created lu_test_subsidy_advance_<uuid> database is mutated.
"""
import json
import os
import re
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.getenv('LU_TEST_ADVANCE_MYSQL') != '1', reason='opt-in isolated MySQL acceptance')


@pytest.fixture
def mysql_connection():
    import pymysql
    from dotenv import dotenv_values
    cfg = {**dotenv_values(Path(__file__).resolve().parents[7] / '.env'), **os.environ}
    assert cfg.get('APP_ENV') == 'development'
    assert cfg.get('DB_HOST') in {'localhost', '127.0.0.1', '::1'}
    connection = pymysql.connect(host=cfg['DB_HOST'], port=int(cfg.get('DB_PORT') or 3306),
                                 user=cfg['DB_USER'], password=cfg.get('DB_PASSWORD') or '',
                                 cursorclass=pymysql.cursors.DictCursor, charset='utf8mb4')
    name = 'lu_test_subsidy_advance_' + uuid.uuid4().hex
    assert re.fullmatch(r'lu_test_subsidy_advance_[a-f0-9]{32}', name)
    try:
        with connection.cursor() as cursor:
            cursor.execute(f'CREATE DATABASE `{name}` CHARACTER SET utf8mb4')
        connection.select_db(name)
        with connection.cursor() as cursor:
            for statement in _SCHEMA:
                cursor.execute(statement)
            for statement in _SEED:
                cursor.execute(statement)
        connection.commit()
        yield connection
    finally:
        connection.rollback()
        with connection.cursor() as cursor:
            cursor.execute(f'DROP DATABASE IF EXISTS `{name}`')
        connection.close()


def api_client(connection):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.routes.client_refund_reversal import router as payout_router
    from api.routes.subsidy_advance_settlement import router as recovery_router
    from api.routes.client_payments import router as history_router
    from api.dependencies.admin_auth import require_admin, require_system_admin
    from api.dependencies.client_payments import get_client_finance_query_application
    from subsystems.client_finance.client_payments_query import ClientFinanceQueryApplication
    from infrastructure.mysql.client_payments_query_repository import MySqlClientFinanceQueryRepository
    from api.dependencies.client_refund_reversal import ClientRefundReversalApplication, get_client_refund_reversal_application
    from api.dependencies.subsidy_advance_settlement import get_advance_settlement_application
    from infrastructure.mysql.client_refund_reversal_repository import MySqlClientRefundReversalRepository
    from infrastructure.mysql.subsidy_advance_settlement_repository import MySqlAdvanceSettlementRepository
    from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
    from subsystems.client_finance.client_refund_reversal_workflow import ClientRefundReversalWorkflow
    from subsystems.client_finance.subsidy_advance_settlement import AdvanceSettlementApplication
    from subsystems.access.authentication_session import AdminPrincipal
    repo = MySqlClientRefundReversalRepository(connection)
    payout = ClientRefundReversalApplication(repo, ClientRefundReversalWorkflow(repo, lambda: MySqlUnitOfWork(connection)))
    recovery = AdvanceSettlementApplication(MySqlAdvanceSettlementRepository(connection), lambda: MySqlUnitOfWork(connection))
    api = FastAPI()
    api.include_router(payout_router)
    api.include_router(recovery_router)
    api.include_router(history_router)
    api.dependency_overrides[require_system_admin] = lambda: AdminPrincipal(1, 'test-admin', '測試管理員', 'system_admin')
    api.dependency_overrides[require_admin] = api.dependency_overrides[require_system_admin]
    api.dependency_overrides[get_client_finance_query_application] = lambda: ClientFinanceQueryApplication(MySqlClientFinanceQueryRepository(connection))
    api.dependency_overrides[get_client_refund_reversal_application] = lambda: payout
    api.dependency_overrides[get_advance_settlement_application] = lambda: recovery
    return TestClient(api)


PAYOUT = '/api/v1/orders/TEST-ADVANCE-001/client-finance/subsidy-return'
REGISTER = '/api/v1/client-finance/subsidy-advance-recoveries'
SELECTION = {'finance_import_row_ids': [1], 'obligation_identities': ['test:subsidy-return'], 'allow_partial_refund_recovery': False}
HEADERS = {'Idempotency-Key': 'test:subsidy-payout', 'X-Correlation-ID': 'test-advance-chain'}


def add_government_receipt(connection, occurred_on='2026-04-01', amount=12000):
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO government_subsidy_transactions (id,claim_batch_id,transaction_status,occurred_at) VALUES (40,2,'succeeded',%s)", (occurred_on,))
        cursor.execute("INSERT INTO government_subsidy_allocations (id,transaction_id,claim_item_id,claim_batch_id,allocation_type,allocated_amount) VALUES (30,40,20,2,'receipt',%s)", (amount,))
        payload = {'kind': 'receipt', 'transaction_id': 40, 'batch_id': 2, 'allocations': [{'claim_item_id': 20, 'case_no': 'TEST-ADVANCE-001', 'amount_ntd': amount}]}
        cursor.execute("INSERT INTO government_subsidy_outbox (id,transaction_id,intent_type,payload_snapshot) VALUES (50,40,'government_subsidy_receipt_allocated',%s)", (json.dumps(payload),))
        cursor.execute('UPDATE government_subsidy_batch_accounts SET aggregate_version=aggregate_version+1 WHERE batch_id=2')
    connection.commit()


def preview_and_pay(client):
    response = client.post(PAYOUT + '/preview', json=SELECTION)
    assert response.status_code == 200, response.text
    preview = response.json()['data']
    body = {**SELECTION, 'expected_account_version': preview['account_version'],
            'preview_fingerprint': preview['preview_fingerprint'], 'reason': '核對實際退款銀行證據'}
    response = client.post(PAYOUT + '/apply', json=body, headers=HEADERS)
    assert response.status_code == 200, response.text
    return preview, body, response.json()


@pytest.mark.parametrize('timing', ['unfunded', 'government_paid_after_customer', 'government_paid_before_customer'])
def test_actual_refund_api_register_and_recovery_without_second_payout(mysql_connection, timing):
    connection = mysql_connection
    client = api_client(connection)
    if timing != 'unfunded':
        add_government_receipt(connection, '2026-04-01' if timing.endswith('after_customer') else '2026-03-01')
    assert client.get(REGISTER).json()['data']['rows'] == []
    preview, body, receipt = preview_and_pay(client)
    expected = 'subsidy_return' if timing.endswith('before_customer') else 'subsidy_advance'
    assert preview['candidate']['entries'][0]['entry_type'] == expected
    assert client.post(PAYOUT + '/apply', json=body, headers=HEADERS).json() == receipt
    history = client.get('/api/v1/client-payments/TEST-ADVANCE-001')
    assert history.status_code == 200, history.text
    assert [entry['entry_type'] for entry in history.json()['data']['ledger_entries']] == [expected]
    assert history.json()['data']['ledger_entries'][0]['amount_ntd'] == 12000
    rows = client.get(REGISTER).json()['data']['rows']
    if expected == 'subsidy_return':
        assert rows == []
        return
    assert len(rows) == 1
    assert rows[0]['status'] == ('waiting_receipt' if timing == 'unfunded' else 'ready')
    if timing == 'unfunded':
        add_government_receipt(connection)
    rows = client.get(REGISTER).json()['data']['rows']
    assert rows[0]['status'] == 'ready'
    advance_id = rows[0]['advance_id']
    response = client.post(f'{REGISTER}/{advance_id}/preview', json={})
    assert response.status_code == 200, response.text
    preview = response.json()['data']
    body = {'expected_account_version': preview['account_version'], 'expected_batch_version': preview['batch_version'],
            'preview_fingerprint': preview['preview_fingerprint'], 'reason': '政府入款回收原墊款'}
    response = client.post(f'{REGISTER}/{advance_id}/apply', json=body, headers={'Idempotency-Key': 'test:advance-recovery'})
    assert response.status_code == 200, response.text
    assert client.get(REGISTER).json()['data']['rows'][0]['status'] == 'recovered'
    assert len(client.get('/api/v1/client-payments/TEST-ADVANCE-001').json()['data']['ledger_entries']) == 1
    assert client.post(f'{REGISTER}/{advance_id}/apply', json=body, headers={'Idempotency-Key': 'test:advance-recovery'}).json() == response.json()
    with connection.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) count FROM client_ledger_entries')
        assert cursor.fetchone()['count'] == 1  # recovery never creates another customer payout
        cursor.execute('SELECT status,amount_due_ntd FROM client_obligations')
        assert cursor.fetchone() == {'status': 'settled', 'amount_due_ntd': 0}


def test_government_change_after_preview_conflicts_without_customer_payout(mysql_connection):
    client = api_client(mysql_connection)
    preview = client.post(PAYOUT + '/preview', json=SELECTION).json()['data']
    add_government_receipt(mysql_connection)
    body = {**SELECTION, 'expected_account_version': preview['account_version'],
            'preview_fingerprint': preview['preview_fingerprint'], 'reason': '核對退款'}
    response = client.post(PAYOUT + '/apply', json=body, headers=HEADERS)
    assert response.status_code == 409, response.text
    assert client.get(REGISTER).json()['data']['rows'] == []


def test_advance_reversal_reopens_customer_payable(mysql_connection):
    client = api_client(mysql_connection)
    preview_and_pay(client)
    reversal = '/api/v1/orders/TEST-ADVANCE-001/client-finance/reversal'
    selection = {'ledger_entry_ids': [1], 'occurred_on': '2026-03-16'}
    response = client.post(reversal + '/preview', json=selection)
    assert response.status_code == 200, response.text
    preview = response.json()['data']
    body = {**selection, 'expected_account_version': preview['account_version'],
            'preview_fingerprint': preview['preview_fingerprint'], 'reason': '銀行退款退匯'}
    response = client.post(reversal + '/apply', json=body, headers={**HEADERS, 'Idempotency-Key': 'test:advance-reversal'})
    assert response.status_code == 200, response.text
    with mysql_connection.cursor() as cursor:
        cursor.execute('SELECT direction,status,amount_due_ntd FROM client_obligations')
        assert cursor.fetchone() == {'direction': 'payable_to_client', 'status': 'open', 'amount_due_ntd': 12000}
    assert client.get(REGISTER).json()['data']['rows'][0]['status'] == 'review_required'


@pytest.mark.parametrize('issue', ['missing_link', 'partial_government_payment', 'paid_before_due'])
def test_unconfirmed_funding_never_posts_as_an_ordinary_refund(mysql_connection, issue):
    connection = mysql_connection
    if issue == 'partial_government_payment':
        add_government_receipt(connection, '2026-03-01', 6000)
    else:
        with connection.cursor() as cursor:
            if issue == 'missing_link':
                cursor.execute('DELETE FROM client_subsidy_return_claim_item_links')
            else:
                cursor.execute("UPDATE finance_import_rows SET transaction_date='2026-03-14'")
        connection.commit()
    response = api_client(connection).post(PAYOUT + '/preview', json=SELECTION)
    assert response.status_code == 409, response.text
    with connection.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) count FROM client_ledger_entries')
        assert cursor.fetchone()['count'] == 0


def test_bank_import_uses_same_advance_rule_and_keeps_outer_commit_owner(mysql_connection):
    from types import SimpleNamespace
    from domains.finance_import.planning import CanonicalFinanceImportRow, FinanceClassificationType, FinanceImportDisposition
    from infrastructure.mysql.finance_import_owning_domain_composite import MySqlFinanceImportOwningDomainComposite
    from shared_kernel.fingerprints import PreviewFingerprint
    from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
    from shared_kernel.money import MoneyNTD
    candidate = CanonicalFinanceImportRow('finance-import-row:1', 1, MoneyNTD(12000),
                                         FinanceClassificationType.CLIENT_SUBSIDY_RETURN,
                                         FinanceImportDisposition.CREATE, PreviewFingerprint('a' * 64),
                                         target_identities=('test:subsidy-return',))
    composite = MySqlFinanceImportOwningDomainComposite(mysql_connection)
    composite.bind_request(SimpleNamespace(idempotency_key=IdempotencyKey('test:import-advance'),
                                          actor=ActorContext('test-admin'), reason='核對銀行退款',
                                          correlation_id=CorrelationId('test-import-advance')))
    mysql_connection.begin()
    outcome = composite.post(candidate)
    assert outcome.outcome.value == 'reconciled'
    with mysql_connection.cursor() as cursor:
        cursor.execute('SELECT entry_type FROM client_ledger_entries')
        assert cursor.fetchone()['entry_type'] == 'subsidy_advance'
    mysql_connection.rollback()
    with mysql_connection.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) count FROM client_ledger_entries')
        assert cursor.fetchone()['count'] == 0


_SCHEMA = [
    'CREATE TABLE clients (id BIGINT PRIMARY KEY,name VARCHAR(100))',
    'CREATE TABLE orders (case_no VARCHAR(50) PRIMARY KEY,client_id BIGINT,actual_end_date DATE)',
    'CREATE TABLE client_finance_accounts (case_no VARCHAR(50) PRIMARY KEY,aggregate_version BIGINT NOT NULL)',
    'CREATE TABLE client_obligations (obligation_identity VARCHAR(191) PRIMARY KEY,case_no VARCHAR(50),obligation_type VARCHAR(30),direction VARCHAR(30),status VARCHAR(30),amount_due_ntd BIGINT,due_date DATE,projection_version BIGINT)',
    'CREATE TABLE client_refund_recipient_snapshots (refund_obligation_identity VARCHAR(191),bank_account VARCHAR(100))',
    'CREATE TABLE finance_import_rows (id BIGINT PRIMARY KEY,transaction_date DATE,debit DECIMAL(15,2),credit DECIMAL(15,2),direction VARCHAR(20),currency VARCHAR(10),classification_type VARCHAR(40),reconciliation_status VARCHAR(30),counterparty_account VARCHAR(100),bank_references JSON,reconciliation_reference VARCHAR(191),reconciled_at DATETIME)',
    'CREATE TABLE finance_import_classification_events (id BIGINT PRIMARY KEY,finance_import_row_id BIGINT,classification_type VARCHAR(40))',
    'CREATE TABLE client_ledger_entries (id BIGINT AUTO_INCREMENT PRIMARY KEY,case_no VARCHAR(50),finance_import_row_id BIGINT,entry_type VARCHAR(40),amount_ntd BIGINT,occurred_on DATE,reconciliation_reference VARCHAR(191),reversal_of_entry_id BIGINT,idempotency_key VARCHAR(191) UNIQUE,actor VARCHAR(100),reason VARCHAR(500),created_at DATETIME DEFAULT CURRENT_TIMESTAMP)',
    'CREATE TABLE client_ledger_obligation_allocations (id BIGINT AUTO_INCREMENT PRIMARY KEY,ledger_entry_id BIGINT,obligation_identity VARCHAR(191),amount_ntd BIGINT,allocation_ordinal INT)',
    'CREATE TABLE client_refund_reversal_apply_receipts (idempotency_key VARCHAR(191) PRIMARY KEY,correction_type VARCHAR(30),command_fingerprint CHAR(64),preview_fingerprint CHAR(64),case_no VARCHAR(50),resulting_account_version BIGINT,result_snapshot JSON)',
    'CREATE TABLE client_finance_apply_receipts (idempotency_key VARCHAR(191) PRIMARY KEY,command_fingerprint CHAR(64),preview_fingerprint CHAR(64),case_no VARCHAR(50),resulting_account_version BIGINT,result_snapshot JSON)',
    'CREATE TABLE client_finance_outbox (id BIGINT AUTO_INCREMENT PRIMARY KEY,case_no VARCHAR(50),intent_type VARCHAR(80),intent_key VARCHAR(191) UNIQUE,payload_snapshot JSON)',
    'CREATE TABLE client_subsidy_return_claim_item_links (id BIGINT AUTO_INCREMENT PRIMARY KEY,obligation_identity VARCHAR(191),claim_item_id BIGINT,entitled_amount_ntd BIGINT)',
    'CREATE TABLE subsidy_claim_batch_items (id BIGINT PRIMARY KEY,case_no VARCHAR(50),batch_id BIGINT,approved_amount BIGINT)',
    'CREATE TABLE government_subsidy_batch_accounts (batch_id BIGINT PRIMARY KEY,aggregate_version BIGINT)',
    'CREATE TABLE government_subsidy_transactions (id BIGINT PRIMARY KEY,claim_batch_id BIGINT,transaction_status VARCHAR(30),occurred_at DATETIME)',
    'CREATE TABLE government_subsidy_allocations (id BIGINT PRIMARY KEY,transaction_id BIGINT,claim_item_id BIGINT,claim_batch_id BIGINT,allocation_type VARCHAR(30),allocated_amount BIGINT,reversal_of_allocation_id BIGINT)',
    'CREATE TABLE government_subsidy_outbox (id BIGINT PRIMARY KEY,transaction_id BIGINT,intent_type VARCHAR(80),payload_snapshot JSON)',
    'CREATE TABLE client_subsidy_advance_recoveries (id BIGINT AUTO_INCREMENT PRIMARY KEY,case_no VARCHAR(50),advance_ledger_entry_id BIGINT UNIQUE,government_allocation_id BIGINT,recovered_amount_ntd BIGINT,source_outbox_id BIGINT)',
]
_SEED = [
    "INSERT INTO clients VALUES (1,'測試客戶')",
    "INSERT INTO orders VALUES ('TEST-ADVANCE-001',1,'2026-01-20')",
    "INSERT INTO client_finance_accounts VALUES ('TEST-ADVANCE-001',0)",
    "INSERT INTO client_obligations VALUES ('test:subsidy-return','TEST-ADVANCE-001','subsidy_return','payable_to_client','open',12000,'2026-03-15',0)",
    "INSERT INTO client_refund_recipient_snapshots VALUES ('test:subsidy-return','TEST-RECIPIENT')",
    "INSERT INTO finance_import_rows (id,transaction_date,debit,credit,direction,currency,classification_type,reconciliation_status,counterparty_account) VALUES (1,'2026-03-15',12000,0,'outgoing','TWD','client_subsidy_return','pending','TEST-RECIPIENT')",
    "INSERT INTO client_subsidy_return_claim_item_links VALUES (1,'test:subsidy-return',20,12000)",
    "INSERT INTO subsidy_claim_batch_items VALUES (20,'TEST-ADVANCE-001',2,12000)",
    'INSERT INTO government_subsidy_batch_accounts VALUES (2,0)',
]
