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
# The shared Terms fixture accepts arbitrary IDs. This bank acceptance must use
# a canonical imported case number so the real virtual-account resolver can bind it.
_CASE_NO = '115000337'
_seed, _seed_effective_assignment = (_fixture[name] for name in ('_seed', '_seed_effective_assignment'))
_seed.__globals__['_CASE_NO'] = _CASE_NO
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
from scripts.check_runtime_database import ReadOnlyRuntimeConfig
from scripts.migrate_preserved_database_additive_schema import ROOT, local_additive_target_state
from shared_kernel.migration_release import load_migration_release_manifest

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
        artifact = '1081_order_established_unserved_status.sql'
        release = load_migration_release_manifest(
            ROOT / 'db/migration_releases/labor_union_2026_11_23_order_established_unserved_v1.json', ROOT,
        )
        schema_state = local_additive_target_state(
            ReadOnlyRuntimeConfig({**config, 'database': name}), name, artifact,
            release.owned_object_descriptors(ROOT)[artifact],
        )
        assert schema_state['state'] == 'exact', 'The real feature schema must match the strict 1081 descriptor.'
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


@pytest.mark.parametrize('paid', (0, 1000))
def test_early_service_end_replaces_bank_candidates_and_receives_original_source(connection, paid, monkeypatch):
    change_fee(connection, 1000, 'terms-before-early-end')
    original = receipt_application(connection).query(_CASE_NO)['obligations']
    if paid:
        staff_items, _ = query_case_staff_accounting(connection, _CASE_NO)
        staff_item = next(item for item in staff_items if item.direction == 'payable')
        service = CaseManualSupplementService(MySqlCaseManualSupplementRepository(connection))
        for direction, target in (('client_receipt', original[0]['obligation_identity']), ('staff_salary', staff_item.identity)):
            with MySqlUnitOfWork(connection) as unit:
                service.execute(_CASE_NO, 'sinopac', direction, target, paid, '2026-10-01',
                    '合成原收付款', 'early-original-' + direction, 'synthetic-accounting', settlement_mode='partial')
                unit.commit()
    original_cash = cash_snapshot(connection)
    waiting = bank_source(connection, 7400-paid, [item['obligation_identity'] for item in original])
    client_before_early_end = receipt_application(connection).query(_CASE_NO)
    assert sum(item['amount_due_ntd'] for item in client_before_early_end['obligations']) > 7400-paid
    with connection.cursor() as cursor:
        cursor.execute("UPDATE orders SET status='服務中',actual_start_date='2026-10-01',"
                       "service_start_time='09:00:00',service_end_time='17:00:00',service_end_day_offset=0 "
                       "WHERE case_no=%s", (_CASE_NO,))
        cursor.execute('SELECT id FROM case_staff_assignments WHERE case_no=%s', (_CASE_NO,))
        assignment_id = cursor.fetchone()['id']
    connection.commit()
    workflow = OrderTermsWorkflow(MySqlOrderTermsRepository(connection), lambda: MySqlUnitOfWork(connection),
        FixedBusinessClock(datetime(2026,10,3,12,tzinfo=TAIPEI_TIME_ZONE)))
    before = MySqlOrderTermsRepository(connection).load_for_query(_CASE_NO)
    proposed = replace(before.registry.order.terms, service_days=2)
    days = (date(2026,10,1), date(2026,10,2))
    replacement = dict(replacement_service_dates=days, replacement_allocations=((assignment_id, 2),),
                       replacement_assignment_dates=((assignment_id, days),), allow_started_service_change=True)
    preview = workflow.preview(_CASE_NO, proposed, **replacement)
    assert MySqlOrderTermsRepository(connection).load_for_query(_CASE_NO) == before
    request = OrderTermsApplyRequest(_CASE_NO, proposed, ExpectedVersion(preview.order_version),
        ExpectedVersion(preview.scheduling_version), ExpectedVersion(preview.client_finance_version),
        ExpectedVersion(preview.payroll_version),preview.fingerprint,IdempotencyKey('early-end'),
        ActorContext('synthetic-accounting'),'確認實際提前結束',CorrelationId('early-end'), **replacement)
    if paid:
        class FailingRepository(MySqlOrderTermsRepository):
            def persist_payroll_impact(self, command):
                super().persist_payroll_impact(command)
                raise RuntimeError('synthetic early-end payroll rollback')
        failure = OrderTermsWorkflow(FailingRepository(connection), lambda: MySqlUnitOfWork(connection),
            FixedBusinessClock(datetime(2026,10,3,12,tzinfo=TAIPEI_TIME_ZONE)))
        with pytest.raises(RuntimeError, match='synthetic early-end payroll rollback'):
            failure.apply(request)
        assert cash_snapshot(connection) == original_cash
        assert MySqlOrderTermsRepository(connection).load_for_query(_CASE_NO) == before
        items, _ = query_case_staff_accounting(connection, _CASE_NO)
        assert sum(item.expected_ntd for item in items if item.direction=='payable' and item.summary_included) == 13000
    receipt = workflow.apply(request)
    assert workflow.apply(request) == receipt
    assert cash_snapshot(connection) == original_cash
    with connection.cursor() as cursor:
        cursor.execute('SELECT status,service_days,actual_end_date FROM orders WHERE case_no=%s', (_CASE_NO,))
        assert cursor.fetchone() == {'status':'服務中', 'service_days':2, 'actual_end_date':date(2026,10,2)}
        cursor.execute('SELECT COUNT(*) AS count FROM order_cancellation_events WHERE case_no=%s', (_CASE_NO,))
        assert cursor.fetchone()['count'] == 0
    terms_payroll, _ = query_case_staff_accounting(connection, _CASE_NO)
    assert sum(item.expected_ntd for item in terms_payroll
               if item.direction == 'payable' and item.summary_included) == 5800, _early_end_diagnostic(connection)
    _finish_yesterdays_service_via_durable_worker(connection, monkeypatch)
    _assert_early_end_core_stages(connection, client_settled=False)
    items, _ = query_case_staff_accounting(connection, _CASE_NO)
    payables = [item for item in items if item.direction=='payable' and item.summary_included]
    assert sum(item.expected_ntd for item in payables) == 5800, _early_end_diagnostic(connection)
    assert sum(item.actual_ntd for item in payables) == paid
    assert sum(item.remaining_ntd for item in payables) == 5800-paid
    target = bank_candidate(connection, waiting)['reconciliation_target']
    assert target is not None
    current_client = receipt_application(connection).query(_CASE_NO)
    assert receipt.client_finance_version is not None
    assert receipt.client_finance_version > client_before_early_end['account_version']
    assert current_client['account_version'] >= receipt.client_finance_version
    assert target['case_no'] == _CASE_NO
    assert set(target['obligation_identities']) == {
        item['obligation_identity'] for item in current_client['obligations']
    }
    assert sum(item['amount_due_ntd'] for item in current_client['obligations']) == 7400-paid
    # REPLACE_OPEN may retain the obligation identity. Its current balance and
    # owner version, rather than an ID change, establish a fresh bank candidate.
    selection = ReconciliationSelection(_CASE_NO, None, (str(waiting),), tuple(target['obligation_identities']))
    current_preview = receipt_application(connection).preview(selection)
    assert current_preview.account_version == current_client['account_version']
    assert current_preview.candidate.status.value == 'exact'
    assert current_preview.candidate.bank_total.amount == 7400-paid
    assert current_preview.candidate.obligation_total.amount == 7400-paid
    assert current_preview.candidate.overage_amount.amount == 0
    receive(connection, waiting, target['obligation_identities'], 'early-end-receipt')
    assert bank_candidate(connection, waiting)['status'] == 'posted'
    _assert_early_end_core_stages(connection, client_settled=True)
    _assert_early_end_monthly_payable(connection)
    after_cash = cash_snapshot(connection)
    assert all(row in after_cash[table] for table, rows in original_cash.items() for row in rows)
    assert after_cash['staff_payout_events'] == original_cash['staff_payout_events']
    assert after_cash['staff_payout_obligation_links'] == original_cash['staff_payout_obligation_links']


def _finish_yesterdays_service_via_durable_worker(connection, monkeypatch):
    from api.dependencies.durable_job_handlers import default_job_handlers
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from infrastructure.mysql.order_auto_completion_job_repository import MySqlDueOrderAutoCompletionRepository
    from subsystems.jobs.command_application import DurableJobCommandApplication
    from subsystems.jobs.durable_job_worker import DurableJobWorker
    from subsystems.orders.auto_completion_job_dispatch import AutoCompletionJobDispatcher

    config = mysql_adapter._database_config_from_environment()
    database = connection.db.decode() if isinstance(connection.db, bytes) else connection.db
    assert database.startswith('lu_test_accounting_sync_')

    def isolated_connection():
        return pymysql.connect(**{**config, 'database':database, 'cursorclass':pymysql.cursors.DictCursor,
                                  'charset':'utf8mb4', 'autocommit':False})

    repository = BackgroundJobRepository(connection)
    dispatcher = AutoCompletionJobDispatcher(MySqlDueOrderAutoCompletionRepository(connection),
        DurableJobCommandApplication(repository, connection))
    today = datetime(2026,10,3,12,tzinfo=TAIPEI_TIME_ZONE)
    before_completion = _early_end_diagnostic(connection)
    dispatch = dispatcher.dispatch_due_orders(today)
    assert dispatch.scanned_count == dispatch.enqueued_count == 1
    with monkeypatch.context() as patch:
        patch.setattr(mysql_adapter, 'get_connection', isolated_connection)
        worker = DurableJobWorker(repository, connection, default_job_handlers(), 'early-end-catchup', retry_delay_seconds=0)
        assert worker.recover_and_run_once() is True
    with connection.cursor() as cursor:
        cursor.execute('SELECT status,error_payload,receipt_payload FROM background_jobs')
        job_results = cursor.fetchall()
        diagnostic = {
            'before_completion': before_completion,
            'after_completion': _early_end_diagnostic(connection),
            'jobs': job_results,
        }
        cursor.execute('SELECT status,actual_end_date FROM orders WHERE case_no=%s', (_CASE_NO,))
        assert cursor.fetchone() == {'status':'訂單完成', 'actual_end_date':date(2026,10,2)}, diagnostic
        cursor.execute('SELECT status FROM background_jobs')
        assert [row['status'] for row in cursor.fetchall()] == ['succeeded'], diagnostic
        cursor.execute('SELECT COUNT(*) AS count FROM order_auto_completion_apply_receipts WHERE case_no=%s', (_CASE_NO,))
        assert cursor.fetchone()['count'] == 1
    assert dispatcher.dispatch_due_orders(today).scanned_count == 0


def _early_end_diagnostic(connection):
    """Read only synthetic owner facts so a failed durable command remains diagnosable."""
    from infrastructure.mysql.payroll_rebuild_repository import MySqlPayrollRebuildRepository

    state = {}
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT status,lifecycle_version,service_days,actual_start_date,actual_end_date,staff_payment_due_date '
            'FROM orders WHERE case_no=%s', (_CASE_NO,),
        )
        state['order'] = cursor.fetchone()
        cursor.execute(
            'SELECT o.obligation_identity,o.assignment_id,o.payroll_version,o.direction,o.status,'
            'o.amount_due_ntd,o.source_obligation_identity,p.net_paid_ntd,p.status AS payout_status,'
            'c.effective_ntd,c.settlement_base_ntd '
            'FROM staff_obligations o '
            'LEFT JOIN staff_payable_projections p ON p.obligation_identity=o.obligation_identity '
            'LEFT JOIN payroll_amount_controls c ON c.obligation_identity=o.obligation_identity '
            'WHERE o.case_no=%s ORDER BY o.obligation_identity', (_CASE_NO,),
        )
        state['staff_obligations'] = cursor.fetchall()
        cursor.execute(
            'SELECT id,staff_id,generation_id,status FROM case_staff_assignments '
            'WHERE case_no=%s ORDER BY id', (_CASE_NO,),
        )
        state['assignments'] = cursor.fetchall()
    try:
        state['rebuild_facts'] = repr(MySqlPayrollRebuildRepository(connection).load(_CASE_NO, for_update=False))
    except (ValueError, TypeError, RuntimeError) as error:
        state['rebuild_facts_error'] = f'{type(error).__name__}: {error}'
    return json.loads(json.dumps(state, default=str))


def _assert_early_end_core_stages(connection, *, client_settled):
    from infrastructure.mysql.orders_stage_projection_repository import MySqlOrdersStageProjectionRepository
    from subsystems.orders.core_stage_projection_query import project_core_stage_timeline
    from subsystems.orders.stage_projection_query import OrderStageProjectionQueryService, StageProjectionQuery

    page = OrderStageProjectionQueryService(MySqlOrdersStageProjectionRepository(connection),
        FixedBusinessClock(datetime(2026,10,3,12,tzinfo=TAIPEI_TIME_ZONE))).query(StageProjectionQuery(20))
    timeline = project_core_stage_timeline(next(item for item in page.items if item.case_no == _CASE_NO))
    stages = {stage.code: stage for stage in timeline.core_stages}
    assert timeline.lifecycle_status.value == '訂單完成'
    assert stages['service_completion'].status == 'completed'
    assert (stages['client_settlement'].status == 'completed') is client_settled
    assert stages['staff_payout'].status != 'completed'
    assert timeline.current_core_stage_code == ('staff_payout' if client_settled else 'client_settlement')


def _assert_early_end_monthly_payable(connection):
    """The completed case remains available in its official staff payment month."""
    from domains.payroll.monthly_aggregation import MonthlyPayrollDirection
    from infrastructure.mysql.payroll_rebuild_repository import MySqlPayrollRebuildRepository

    with connection.cursor() as cursor:
        cursor.execute('SELECT staff_payment_due_date FROM orders WHERE case_no=%s', (_CASE_NO,))
        due_date = cursor.fetchone()['staff_payment_due_date']
        cursor.execute(
            "SELECT DISTINCT staff_id FROM staff_obligations WHERE case_no=%s "
            "AND direction='payable_to_staff' AND status='open' ORDER BY staff_id",
            (_CASE_NO,),
        )
        staff_ids = tuple(row['staff_id'] for row in cursor.fetchall())
    assert isinstance(due_date, date), _early_end_diagnostic(connection)
    assert len(staff_ids) == 1, _early_end_diagnostic(connection)
    summary = MySqlPayrollRebuildRepository(connection).query_staff_month(
        staff_ids[0], due_date.year, due_date.month,
    )
    case_payables = tuple(
        item for item in summary.obligations
        if item.case_no == _CASE_NO and item.direction is MonthlyPayrollDirection.PAYABLE_TO_STAFF
    )
    assert sum(item.amount_due.amount for item in case_payables) == 5800, {
        'staff_payment_due_date': str(due_date),
        'monthly_summary': repr(summary),
        'owner_facts': _early_end_diagnostic(connection),
    }
