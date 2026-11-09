"""Real owner writes: corrected terms -> current bank candidates -> original-source receipt."""
from argparse import Namespace
from dataclasses import replace
from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import runpy
from uuid import uuid4

import pymysql
import pytest

_fixture = runpy.run_path(str(Path(__file__).with_name('test_order_terms_empty_service_time_disposable_mysql.py')))
_seed, _seed_effective_assignment, _CASE_NO = (_fixture[name] for name in ('_seed', '_seed_effective_assignment', '_CASE_NO'))
from infrastructure.mysql import mysql_adapter
from infrastructure.mysql.order_terms_repository import MySqlOrderTermsRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.client_receipt_reconciliation_repository import MySqlClientReceiptReconciliationRepository
from infrastructure.mysql.accounting_workspace_repository import build_accounting_workspace
from infrastructure.mysql.case_staff_accounting_repository import query_case_staff_accounting
from infrastructure.mysql.case_manual_supplement_repository import MySqlCaseManualSupplementRepository
from subsystems.finance_import.case_manual_supplement import CaseManualSupplementService
from api.dependencies.client_receipt_reconciliation import ClientReceiptReconciliationApplication
from subsystems.client_finance.reconciliation_workflow import (
    ClientReconciliationWorkflow, ClientReconciliationApplyRequest, ReconciliationSelection,
)
from subsystems.finance_import.query import FinanceImportQueryService
from subsystems.orders.terms_workflow import OrderTermsWorkflow, OrderTermsApplyRequest, TermsWorkflowError
from shared_kernel.clock import FixedBusinessClock, TAIPEI_TIME_ZONE
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.money import MoneyNTD
from scripts.bootstrap_disposable_mysql_schema import bootstrap

pytestmark = pytest.mark.skipif(os.getenv('ACCOUNTING_SYNC_MYSQL') != '1', reason='opt-in localhost acceptance')


@pytest.fixture
def connection():
    config = mysql_adapter._database_config_from_environment()
    assert config['host'] in {'127.0.0.1', 'localhost'}
    assert os.getenv('APP_ENV', 'development') == 'development'
    name = 'lu_test_accounting_sync_' + uuid4().hex[:12]
    bootstrap(Namespace(**{key: config[key] for key in ('host', 'port', 'user', 'password')},
                        database=name, confirm_database=name))
    connection = pymysql.connect(**{**config, 'database': name, 'charset':'utf8mb4',
                                    'cursorclass':pymysql.cursors.DictCursor, 'autocommit':False})
    try:
        from infrastructure.mysql.nas_mutations import ensure_nas_procedures
        ensure_nas_procedures(connection)
        _seed(connection)
        _seed_effective_assignment(connection)
        yield connection
    finally:
        connection.rollback()
        connection.close()
        assert name.startswith('lu_test_accounting_sync_')
        server = pymysql.connect(**{key: value for key, value in config.items() if key != 'database'})
        try:
            with server.cursor() as cursor:
                cursor.execute(f'DROP DATABASE `{name}`')
        finally:
            server.close()


def terms_workflow(connection):
    return OrderTermsWorkflow(MySqlOrderTermsRepository(connection), lambda: MySqlUnitOfWork(connection),
        FixedBusinessClock(datetime(2026, 11, 9, 12, tzinfo=TAIPEI_TIME_ZONE)))


def change_fee(connection, amount, key, *, closed=False, apply=True):
    workflow = terms_workflow(connection)
    current = MySqlOrderTermsRepository(connection).load_for_query(_CASE_NO).registry.order.terms
    candidate = replace(current, floor_fee=MoneyNTD(amount))
    preview = workflow.preview(_CASE_NO, candidate, floor_fee_correction=closed)
    request = OrderTermsApplyRequest(_CASE_NO, candidate, ExpectedVersion(preview.order_version),
        ExpectedVersion(preview.scheduling_version), ExpectedVersion(preview.client_finance_version),
        ExpectedVersion(preview.payroll_version), preview.fingerprint, IdempotencyKey(key),
        ActorContext('synthetic-accounting'), '補正漏填樓層費', CorrelationId(key), floor_fee_correction=closed)
    return workflow.apply(request) if apply else request


def bank_source(connection, amount, targets):
    with connection.cursor() as cursor:
        cursor.execute("INSERT IGNORE INTO client_legacy_virtual_accounts(case_no,virtual_account,source_content_digest,source_row,created_by) VALUES (%s,'99781699115999',%s,2,'synthetic')", (_CASE_NO, 'b'*64))
        cursor.execute("INSERT INTO finance_import_batches(format_id,sheet_name,header_row,row_count) VALUES ('sinopac','synthetic sync',1,1)")
        batch = cursor.lastrowid
        cursor.execute("INSERT INTO finance_import_rows(dedup_fingerprint,batch_id,format_id,transaction_date,credit,direction,cancellation_code,bank_references,warnings,raw_payload,classification_type) VALUES (%s,%s,'sinopac','2026-10-02',%s,'incoming','99781699115999',%s,'[]','{}','client_receipt')",
                       (hashlib.sha256(uuid4().bytes).hexdigest(), batch, amount, json.dumps({'銷帳編號':'99781699115999'})))
        row = cursor.lastrowid
        cursor.execute("INSERT INTO finance_import_classification_events(batch_id,finance_import_row_id,classification_version,canonical_fact_version,classification_type,disposition,decision_facts_fingerprint,target_identities,evidence,available_actions,actor,reason) VALUES (%s,%s,1,1,'client_receipt','manual_review',%s,%s,'[]','[]','synthetic','confirmed original case source')",
                       (batch, row, 'a'*64, json.dumps(targets)))
    connection.commit()
    return row


def receipt_application(connection):
    repository = MySqlClientReceiptReconciliationRepository(connection)
    return ClientReceiptReconciliationApplication(repository, ClientReconciliationWorkflow(repository, lambda: MySqlUnitOfWork(connection)))


def receive(connection, row, targets, key):
    app = receipt_application(connection)
    selection = ReconciliationSelection(_CASE_NO, None, (str(row),), tuple(targets))
    preview = app.preview(selection)
    assert preview.candidate.status.value == 'exact'
    request = ClientReconciliationApplyRequest(selection, ExpectedVersion(preview.account_version),
        preview.fingerprint, IdempotencyKey(key), ActorContext('synthetic-accounting'),
        '核銷原銀行流水', CorrelationId(key))
    receipt = app.apply(request)
    assert app.apply(request) == receipt
    return receipt


def bank_candidate(connection, row):
    connection.commit()
    page = FinanceImportQueryService(connection).bank_transactions(bank=None, direction=None, status='all',
        start=None, end=None, search='', limit=50, before_row_id=None, row_id=row)
    assert len(page['items']) == 1
    assert page['items'][0]['row_id'] == row
    return page['items'][0]


def cash_snapshot(connection):
    with connection.cursor() as cursor:
        result = {}
        for table in ('client_ledger_entries', 'client_ledger_obligation_allocations', 'staff_payout_events', 'staff_payout_obligation_links'):
            cursor.execute(f'SELECT * FROM {table} ORDER BY id')
            result[table] = cursor.fetchall()
        return result


def close_service(connection):
    with connection.cursor() as cursor:
        cursor.execute("UPDATE orders SET status='訂單完成',actual_start_date='2026-10-01',actual_end_date='2026-10-05',staff_payment_due_date='2026-11-15' WHERE case_no=%s", (_CASE_NO,))
        cursor.execute("INSERT INTO order_lifecycle_state_events(case_no,trigger_event,before_status,after_status,actor,business_date,expected_version,idempotency_key,facts_snapshot) SELECT case_no,'synthetic_completion','服務中','訂單完成','synthetic','2026-10-06',lifecycle_version,'synthetic-completion','{}' FROM orders WHERE case_no=%s", (_CASE_NO,))
        cursor.execute("INSERT INTO order_service_data_locks(case_no,lifecycle_event_id,client_settlement_fingerprint,created_by) VALUES (%s,%s,%s,'synthetic')", (_CASE_NO, cursor.lastrowid, 'a'*64))
    connection.commit()


def test_closed_fee_preserves_receipt_and_reconciles_original_waiting_bank_source(connection):
    change_fee(connection, 1000, 'initial-terms')
    items = receipt_application(connection).query(_CASE_NO)['obligations']
    targets = [item['obligation_identity'] for item in items]
    initial = bank_source(connection, sum(int(item['amount_due_ntd']) for item in items), targets)
    receive(connection, initial, targets, 'initial-receipt')
    waiting = bank_source(connection, 1500, targets)
    close_service(connection)
    staff_items, _ = query_case_staff_accounting(connection, _CASE_NO)
    assert staff_items
    with MySqlUnitOfWork(connection) as unit:
        staff_item = next(item for item in staff_items if item.direction == 'payable')
        CaseManualSupplementService(MySqlCaseManualSupplementRepository(connection)).execute(
            case_no=_CASE_NO, bank='sinopac', direction='staff_salary', target_item=staff_item.identity,
            amount_ntd=staff_item.expected_ntd, transaction_date='2026-11-15', reason='合成原付款',
            idempotency_key='original-staff-payout', actor='synthetic-accounting')
        unit.commit()
    cash = cash_snapshot(connection)
    assert cash['staff_payout_events']
    before = MySqlOrderTermsRepository(connection).load_for_query(_CASE_NO)
    request = change_fee(connection, 2500, 'closed-fee', closed=True, apply=False)
    class FailingRepository(MySqlOrderTermsRepository):
        def persist_payroll_impact(self, command):
            super().persist_payroll_impact(command)
            raise RuntimeError('synthetic failure before outer commit')
    failure = OrderTermsWorkflow(FailingRepository(connection), lambda: MySqlUnitOfWork(connection),
        FixedBusinessClock(datetime(2026, 11, 9, 12, tzinfo=TAIPEI_TIME_ZONE)))
    with pytest.raises(RuntimeError, match='synthetic failure'):
        failure.apply(request)
    assert MySqlOrderTermsRepository(connection).load_for_query(_CASE_NO) == before
    assert cash_snapshot(connection) == cash
    workflow = terms_workflow(connection)
    receipt = workflow.apply(request)
    assert workflow.apply(request) == receipt
    assert cash_snapshot(connection) == cash
    after = MySqlOrderTermsRepository(connection).load_for_query(_CASE_NO)
    assert before.assignments == after.assignments
    assert before.registry.scheduling_version == after.registry.scheduling_version
    assert after.registry.order.service_data_locked
    assert after.registry.order.terms.floor_fee.amount == 2500
    with connection.cursor() as cursor:
        cursor.execute('SELECT status,actual_end_date FROM orders WHERE case_no=%s', (_CASE_NO,))
        assert cursor.fetchone() == {'status': '訂單完成', 'actual_end_date': date(2026, 10, 5)}
    candidate = bank_candidate(connection, waiting)
    assert candidate['reconciliation_target'] is not None, candidate
    new_targets = candidate['reconciliation_target']['obligation_identities']
    assert new_targets and set(new_targets) != set(targets)
    receive(connection, waiting, new_targets, 'corrected-receipt')
    assert bank_candidate(connection, waiting)['status'] == 'posted'
    assert bank_candidate(connection, initial)['status'] == 'posted'
    assert build_accounting_workspace(connection).query(_CASE_NO).received_ntd == sum(int(item['amount_due_ntd']) for item in items) + 1500
    change_fee(connection, 3000, 'closed-fee-second', closed=True)
    assert sum(item['amount_due_ntd'] for item in receipt_application(connection).query(_CASE_NO)['obligations']) == 500
    with pytest.raises(TermsWorkflowError):
        workflow.apply(replace(request, proposed_terms=replace(request.proposed_terms, floor_fee=MoneyNTD(3000))))


def test_case_pricing_recalculates_terms_and_reconciles_waiting_original_source(connection):
    from decimal import Decimal
    from domains.client_finance.pricing_policy import CasePricingTerms, HourlyRates, IdentityRule
    from infrastructure.mysql.pricing_configuration_repository import MySqlPricingConfigurationRepository
    from subsystems.client_finance.pricing_configuration import PricingConfigurationApplication
    change_fee(connection, 1000, 'terms-before-pricing')
    initial = receipt_application(connection).query(_CASE_NO)['obligations']
    waiting = bank_source(connection, 19000, [item['obligation_identity'] for item in initial])
    application = PricingConfigurationApplication(MySqlPricingConfigurationRepository(connection), lambda: MySqlUnitOfWork(connection))
    facts, _ = application.query_case(_CASE_NO)
    terms = CasePricingTerms('一般市民', IdentityRule.CITIZEN, Decimal(0), HourlyRates(350,450), HourlyRates(350,450))
    revision = application.apply_case(_CASE_NO, terms, facts.revision, None, 'synthetic-accounting', '個案費率更正', 'pricing-change')
    assert application.apply_case(_CASE_NO, terms, facts.revision, None, 'synthetic-accounting', '個案費率更正', 'pricing-change') == revision
    current = receipt_application(connection).query(_CASE_NO)['obligations']
    assert sum(item['amount_due_ntd'] for item in current) == 19000
    target = bank_candidate(connection, waiting)['reconciliation_target']
    assert target is not None
    receive(connection, waiting, target['obligation_identities'], 'pricing-receipt')
    assert bank_candidate(connection, waiting)['status'] == 'posted'


def test_early_service_end_replaces_bank_candidates_and_receives_original_source(connection):
    from domains.orders.cancellation import ConfirmedServiceDay
    from infrastructure.mysql.order_cancellation_repository import MySqlOrderCancellationRepository
    from subsystems.orders.cancellation_workflow import OrderCancellationWorkflow, OrderCancellationApplyRequest
    change_fee(connection, 1000, 'terms-before-cancellation')
    original = receipt_application(connection).query(_CASE_NO)['obligations']
    waiting = bank_source(connection, 6800, [item['obligation_identity'] for item in original])
    with connection.cursor() as cursor:
        cursor.execute("UPDATE orders SET status='服務中',actual_start_date='2026-10-01' WHERE case_no=%s", (_CASE_NO,))
        cursor.execute('SELECT staff_id FROM case_staff_assignments WHERE case_no=%s', (_CASE_NO,))
        staff_id = cursor.fetchone()['staff_id']
    connection.commit()
    workflow = OrderCancellationWorkflow(MySqlOrderCancellationRepository(connection), lambda: MySqlUnitOfWork(connection),
        FixedBusinessClock(datetime(2026,10,3,12,tzinfo=TAIPEI_TIME_ZONE)))
    days = (ConfirmedServiceDay(date(2026,10,1),staff_id),ConfirmedServiceDay(date(2026,10,2),staff_id))
    preview = workflow.preview(_CASE_NO, days)
    request = OrderCancellationApplyRequest(_CASE_NO, days, ExpectedVersion(preview.order_version),
        ExpectedVersion(preview.scheduling_version), ExpectedVersion(preview.client_finance_version),
        ExpectedVersion(preview.payroll_version),preview.fingerprint,IdempotencyKey('early-end'),
        ActorContext('synthetic-accounting'),'確認實際提前結束',CorrelationId('early-end'))
    receipt = workflow.apply(request)
    assert workflow.apply(request) == receipt
    target = bank_candidate(connection, waiting)['reconciliation_target']
    assert target is not None
    assert target['obligation_identities'] != [item['obligation_identity'] for item in original]
    receive(connection, waiting, target['obligation_identities'], 'early-end-receipt')
    assert bank_candidate(connection, waiting)['status'] == 'posted'
