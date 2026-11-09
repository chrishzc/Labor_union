"""
File: test_finance_source_review_mysql_e2e.py
Description: 驗證銀行對帳單匯入過濾無關流水、跨銀行待核對對象與案件補齊及手動核銷 E2E 契約。
"""
from __future__ import annotations

from argparse import Namespace
from dataclasses import asdict
from datetime import date
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

import pandas as pd
import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap
from scripts.imports.finance_formats.sinopac import SINOPAC_HEADERS
from scripts.imports.finance_statement_normalizer import normalize_workbook

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
                      'finance_import_dispatch_events', 'finance_import_apply_receipts',
                      'client_finance_apply_receipts', 'client_ledger_entries', 'staff_payout_events')
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


def test_sinopac_receipt_posts_only_a_unique_installment_and_replay_is_safe(tmp_path):
    bootstrap(_arguments())
    from api.dependencies.finance_import import build_finance_import_application
    from api.routes.finance_import import _materialize, _row_payload
    from api.schemas.finance_import import FinanceBankTransactionPageView, FinanceImportRowView
    from infrastructure.mysql.finance_import_owning_domain_composite import MySqlFinanceImportOwningDomainComposite
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.finance_import.import_workflow import FinanceImportApplyRequest
    from subsystems.finance_import.ingestion import ingest_finance_workbook
    from subsystems.finance_import.query import FinanceImportQueryService

    cases = (
        ('115000041', None, True),
        ('115000042', '2026-11-20', True),
        ('115000043', '2026-10-27', False),
    )
    actor = ActorContext('isolated-finance-test')
    connection = get_connection()
    try:
        application = build_finance_import_application(connection, MySqlFinanceImportOwningDomainComposite(connection))
        query = FinanceImportQueryService(connection)
        for sequence, (case_no, second_due, should_post) in enumerate(cases, start=1):
            installments = [('deposit', 6000, '2026-06-26'), ('first', 12000, '2026-10-19')]
            if second_due:
                installments.append(('second', 12000, second_due))
            with connection.cursor() as cursor:
                cursor.execute('INSERT INTO clients(case_no,name) VALUES (%s,%s)', (case_no, 'Synthetic receipt client'))
                cursor.execute("INSERT INTO orders(case_no,client_id,status) VALUES (%s,%s,'服務中')", (case_no, cursor.lastrowid))
                for stage, amount, due_date in installments:
                    identity = f'client-obligation:{case_no}:{stage}'
                    cursor.execute(
                        "INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,"
                        "event_type,before_amount_ntd,after_amount_ntd,after_due_date,source_event_identity,"
                        "expected_account_version,idempotency_key,actor,reason) "
                        "VALUES (%s,%s,%s,'receivable_from_client','established',0,%s,%s,%s,0,%s,%s,'Synthetic original installment')",
                        (identity, case_no, stage, amount, due_date, identity, identity, actor.actor_id),
                    )
                    cursor.execute(
                        "INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,"
                        "amount_due_ntd,due_date,status,current_event_id,projection_version) "
                        "VALUES (%s,%s,%s,'receivable_from_client',%s,%s,'open',%s,0)",
                        (identity, case_no, stage, amount, due_date, cursor.lastrowid),
                    )
            connection.commit()

            workbook = tmp_path / f'{case_no}.xlsx'
            virtual_account = f'99781699{case_no[:3]}{case_no[-3:]}'
            pd.DataFrame([[
                '123456789012', f'2026/10/20 09:0{sequence}:00', '2026/10/20', '2026/10/20',
                '轉帳', 'TWD', None, 12000, 12000 * sequence, None, virtual_account, case_no, None, None, None,
            ]], columns=SINOPAC_HEADERS).to_excel(workbook, index=False)
            first = ingest_finance_workbook(str(workbook), IdempotencyKey(f'{case_no}:ingest'), actor,
                                            connection_factory=get_connection, normalizer=normalize_workbook)
            assert first.canonical_created_count == 1
            correlation = CorrelationId(case_no)
            plan = application.preview_batch(first.batch_identity, correlation)
            assert plan.apply_allowed
            assert plan.counts.ready_dispatch == int(should_post)
            assert len(plan.rows) == 1
            row_id = plan.rows[0].row_identity.split(':')[1]
            first_identity = f'client-obligation:{case_no}:first'
            if should_post:
                assert plan.rows[0].target_identities == (first_identity,)
            else:
                assert set(plan.rows[0].target_identities) == {first_identity, f'client-obligation:{case_no}:second'}
                preview_row = FinanceImportRowView.model_validate(_row_payload(plan.rows[0]))
                assert preview_row.client_receipt_review.reason == 'sinopac_client_receipt_multiple_same_month_exact'
                page = query.bank_transactions(bank='sinopac', direction='incoming', status='all', start=None,
                                               end=None, search=f'bank:{row_id}', limit=10, before_row_id=None)
                assert page['items'][0]['recorded_client_receipt_review'] is None

            request = FinanceImportApplyRequest(
                first.batch_identity, ExpectedVersion(plan.batch_version), plan.fingerprint,
                IdempotencyKey(f'{case_no}:apply'), actor, 'Synthetic receipt', correlation,
            )
            receipt = application.apply_batch(request)
            assert receipt.reconciled_count == int(should_post)
            assert application.apply_batch(request) == receipt

            repeat = ingest_finance_workbook(str(workbook), IdempotencyKey(f'{case_no}:reimport'), actor,
                                             connection_factory=get_connection, normalizer=normalize_workbook)
            assert repeat.batch_identity != first.batch_identity
            assert repeat.canonical_created_count == 0 and repeat.duplicate_occurrence_count == 1
            assert application.preview_batch(repeat.batch_identity, correlation).counts.ready_dispatch == 0

            page = query.bank_transactions(bank='sinopac', direction='incoming', status='all', start=None,
                                           end=None, search=f'bank:{row_id}', limit=10, before_row_id=None)
            FinanceBankTransactionPageView.model_validate(_materialize(page))
            assert [(row['status'], row['cases']) for row in page['items']] == [
                ('posted' if should_post else 'pending', [case_no]),
            ]
            target = page['items'][0]['reconciliation_target']
            if should_post:
                assert target is None
            else:
                assert target == {
                    'case_no': case_no, 'staff_id': None, 'requires_selection': True,
                    'obligation_identities': sorted(f'client-obligation:{case_no}:{stage}' for stage, _, _ in installments),
                }
            recorded = page['items'][0]['recorded_client_receipt_review']
            if should_post:
                assert recorded is None
            else:
                assert recorded['reason'] == 'sinopac_client_receipt_multiple_same_month_exact'
                assert [(item['obligation_type'], item['due_date']) for item in recorded['candidates']] == [
                    ('first', '2026-10-19'), ('second', '2026-10-27'),
                ]
            with connection.cursor() as cursor:
                cursor.execute(
                    'SELECT obligation_type, amount_due_ntd, status FROM client_obligations '
                    'WHERE case_no=%s ORDER BY obligation_type', (case_no,),
                )
                assert [(row['obligation_type'], row['amount_due_ntd'], row['status']) for row in cursor.fetchall()] == [
                    (stage, 0, 'settled') if stage == 'first' and should_post else (stage, amount, 'open')
                    for stage, amount, _ in installments
                ]
                cursor.execute(
                    'SELECT entry.amount_ntd, allocation.obligation_identity, allocation.amount_ntd AS allocated '
                    'FROM client_ledger_entries entry LEFT JOIN client_ledger_obligation_allocations allocation '
                    'ON allocation.ledger_entry_id=entry.id WHERE entry.case_no=%s', (case_no,),
                )
                assert list(cursor.fetchall()) == (
                    [{'amount_ntd': 12000, 'obligation_identity': first_identity, 'allocated': 12000}] if should_post else []
                )
            if not should_post:
                # The same pending bank source enters the existing owner flow;
                # a human explicitly chooses first, leaving second untouched.
                from api.dependencies.client_receipt_reconciliation import ClientReceiptReconciliationApplication
                from infrastructure.mysql.client_receipt_reconciliation_repository import MySqlClientReceiptReconciliationRepository, ClientReceiptMySqlUnitOfWork
                from subsystems.client_finance.reconciliation_workflow import ClientReconciliationWorkflow, ReconciliationSelection, ClientReconciliationApplyRequest
                from infrastructure.mysql.accounting_workspace_repository import build_accounting_workspace
                accounting = build_accounting_workspace(connection).query(case_no)
                assert set(target['obligation_identities']) <= {item.identity for item in accounting.client_items}
                repository = MySqlClientReceiptReconciliationRepository(connection)
                manual = ClientReceiptReconciliationApplication(repository, ClientReconciliationWorkflow(repository, lambda: ClientReceiptMySqlUnitOfWork(connection)))
                selection = ReconciliationSelection(case_no, None, (row_id,), (first_identity,))
                preview = manual.preview(selection)
                command = ClientReconciliationApplyRequest(selection, ExpectedVersion(preview.account_version), preview.fingerprint,
                                                           IdempotencyKey(f'{case_no}:manual'), actor, 'Synthetic human selects first', correlation)
                manual_receipt = manual.apply(command)
                assert manual.apply(command) == manual_receipt
                with connection.cursor() as cursor:
                    cursor.execute('SELECT amount_due_ntd,status FROM client_obligations WHERE obligation_identity=%s', (first_identity,))
                    assert cursor.fetchone() == {'amount_due_ntd': 0, 'status': 'settled'}
                    cursor.execute('SELECT amount_due_ntd,status FROM client_obligations WHERE obligation_identity=%s', (f'client-obligation:{case_no}:second',))
                    assert cursor.fetchone() == {'amount_due_ntd': 12000, 'status': 'open'}
                    cursor.execute('SELECT amount_ntd,finance_import_row_id FROM client_ledger_entries WHERE case_no=%s', (case_no,))
                    assert list(cursor.fetchall()) == [{'amount_ntd': 12000, 'finance_import_row_id': int(row_id)}]
                refreshed = query.bank_transactions(bank='sinopac', direction='incoming', status='all', start=None,
                                                    end=None, search=f'bank:{row_id}', limit=10, before_row_id=None)
                assert refreshed['items'][0]['status'] == 'posted'
    finally:
        connection.close()


def test_taishin_import_uses_only_memo_case_suffix_or_staff_name(tmp_path):
    bootstrap(_arguments())
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import ActorContext, IdempotencyKey
    from subsystems.finance_import.ingestion import ingest_finance_workbook
    from subsystems.finance_import.query import FinanceImportQueryService

    _seed_deposit('115000003', 'synthetic-taishin-case-proof')
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO staff(name) VALUES ('合成人員甲')")
            cursor.execute("UPDATE orders SET staff_id=%s WHERE case_no='115000003'", (cursor.lastrowid,))
        connection.commit()
    finally:
        connection.close()
    workbook = tmp_path / 'taishin-case-proof.xlsx'
    pd.DataFrame([
        ['說明'],
        ['序號', '交易日期', '交易時間', '帳務日期', '摘要', '支出金額', '存入金額', '帳戶餘額', '備註'],
        ['0001', '2026/10/15', '09:01:00', '2026/10/15', '轉出', '12000', '', '88000', 'HC115003'],
        ['0002', '2026/10/15', '09:02:00', '2026/10/15', '轉出', '12000', '', '76000', 'HC115004'],
        ['0003', '2026/10/15', '09:03:00', '2026/10/15', '轉出', '12000', '', '64000', '無識別資料'],
        ['0004', '2026/10/15', '09:04:00', '2026/10/15', '轉出', '12000', '', '52000', '合成人員甲'],
    ]).to_excel(workbook, index=False, header=False)

    receipt = ingest_finance_workbook(str(workbook), IdempotencyKey('synthetic-case-proof'), ActorContext('test'),
                                      connection_factory=get_connection, normalizer=normalize_workbook)
    assert receipt.canonical_created_count == 2
    assert _counts()['finance_import_rows'] == _counts()['finance_import_occurrences'] == 2
    connection = get_connection()
    try:
        page = FinanceImportQueryService(connection).bank_transactions(
            bank='taishin', direction='outgoing', status='pending', start=None, end=None, search='',
            limit=10, before_row_id=None,
        )
        assert {row['classification_type'] for row in page['items']} == {'client_subsidy_return', 'staff_payout'}
        for row in page['items']:
            assert row['cases'] == ['115000003']
            assert row['reconciliation_target']['case_no'] == '115000003'
            assert row['reconciliation_target']['obligation_identities'] == []
            assert row['reconciliation_target']['requires_selection'] is True
            assert row['reconciliation_unavailable_reason'] == 'no_open_items'
    finally:
        connection.close()


def test_taishin_accountless_subsidies_post_and_replay_without_duplicate_ledger(tmp_path):
    """Real owner writers accept memo proof, not a fabricated bank account."""
    bootstrap(_arguments())
    from api.dependencies.finance_import import build_finance_import_application
    from infrastructure.mysql.finance_import_owning_domain_composite import MySqlFinanceImportOwningDomainComposite
    from infrastructure.mysql.client_refund_reversal_repository import MySqlClientRefundReversalRepository
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.finance_import.import_workflow import FinanceImportApplyRequest
    from subsystems.finance_import.ingestion import ingest_finance_workbook
    from subsystems.finance_import.query import FinanceImportQueryService

    client_case, staff_case = '115000003', '115000004'
    _seed_deposit(client_case, 'synthetic-client-subsidy')
    _seed_deposit(staff_case, 'synthetic-staff-subsidy')
    client_obligation, staff_obligation = 'subsidy:115000003', 'payable:115000004'
    actor = ActorContext('synthetic-taishin-payout')
    correlation = CorrelationId('synthetic-taishin-payout')
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("UPDATE orders SET actual_end_date='2026-08-31',end_date='2026-08-31' WHERE case_no=%s", (client_case,))
            cursor.execute("INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,after_due_date,source_event_identity,expected_account_version,idempotency_key,actor,reason) VALUES (%s,%s,'subsidy_return','payable_to_client','established',0,12000,'2026-10-15',%s,0,%s,'test','Synthetic subsidy payable')", (client_obligation, client_case, client_obligation, client_obligation))
            cursor.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,amount_due_ntd,due_date,status,current_event_id,projection_version) VALUES (%s,%s,'subsidy_return','payable_to_client',12000,'2026-10-15','open',%s,0)", (client_obligation, client_case, cursor.lastrowid))
            cursor.execute("INSERT INTO staff(name) VALUES ('合成月嫂甲')")
            staff_id = cursor.lastrowid
            cursor.execute('UPDATE orders SET staff_id=%s WHERE case_no=%s', (staff_id, staff_case))
            cursor.execute("INSERT INTO case_staff_assignments(case_no,staff_id,assignment_sequence,status) VALUES (%s,%s,1,'completed')", (staff_case, staff_id))
            assignment_id = cursor.lastrowid
            cursor.execute("INSERT INTO staff_obligation_events(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,event_type,before_amount_ntd,after_amount_ntd,due_date,payroll_fingerprint,expected_payroll_version,resulting_payroll_version,idempotency_key,actor,reason) VALUES (%s,%s,%s,%s,'service_pay','payable_to_staff','established',0,6000,'2026-10-15',%s,0,1,%s,'test','Synthetic original payable')", (staff_obligation, assignment_id, staff_case, staff_id, 'a' * 64, staff_obligation))
            cursor.execute("INSERT INTO staff_obligations(obligation_identity,assignment_id,case_no,staff_id,obligation_kind,direction,amount_due_ntd,due_date,status,current_event_id,payroll_version) VALUES (%s,%s,%s,%s,'service_pay','payable_to_staff',6000,'2026-10-15','open',%s,1)", (staff_obligation, assignment_id, staff_case, staff_id, cursor.lastrowid))
        connection.commit()

        workbook = tmp_path / 'taishin-accountless-payouts.xlsx'
        pd.DataFrame([
            ['說明'],
            ['序號', '交易日期', '交易時間', '帳務日期', '摘要', '支出金額', '存入金額', '帳戶餘額', '備註'],
            ['0001', '2026/10/15', '09:01:00', '2026/10/15', '轉出', '12000', '', '88000', 'HC115003'],
            # Conflicting six digits point to the client case; the staff name must win.
            ['0002', '2026/10/15', '09:02:00', '2026/10/15', '轉出', '6000', '', '82000', '合成月嫂甲 HC115003'],
        ]).to_excel(workbook, index=False, header=False)
        first = ingest_finance_workbook(str(workbook), IdempotencyKey('taishin-accountless:first'), actor,
                                       connection_factory=get_connection, normalizer=normalize_workbook)
        assert first.canonical_created_count == 2
        application = build_finance_import_application(connection, MySqlFinanceImportOwningDomainComposite(connection))
        plan = application.preview_batch(first.batch_identity, correlation)
        assert plan.counts.ready_dispatch == 2, plan
        assert MySqlClientRefundReversalRepository(connection).query(client_case)['subsidy_return_bank_facts'][0]['eligible_obligation_identities'] == (client_obligation,)
        assert MySqlClientRefundReversalRepository(connection).query(staff_case)['subsidy_return_bank_facts'] == ()
        request = FinanceImportApplyRequest(first.batch_identity, ExpectedVersion(plan.batch_version), plan.fingerprint,
                                           IdempotencyKey('taishin-accountless:apply'), actor, 'Synthetic verified memo payouts', correlation)
        receipt = application.apply_batch(request)
        assert receipt.reconciled_count == 2
        applied = _counts()
        assert application.apply_batch(request) == receipt
        assert _counts() == applied
        repeat = ingest_finance_workbook(str(workbook), IdempotencyKey('taishin-accountless:reimport'), actor,
                                        connection_factory=get_connection, normalizer=normalize_workbook)
        assert repeat.canonical_created_count == 0 and repeat.duplicate_occurrence_count == 2
        assert application.preview_batch(repeat.batch_identity, correlation).counts.ready_dispatch == 0
        final = _counts()
        assert final['client_ledger_entries'] == applied['client_ledger_entries'] == 1
        assert final['staff_payout_events'] == applied['staff_payout_events'] == 1
        assert final['finance_import_dispatch_events'] == applied['finance_import_dispatch_events'] == 2
        with connection.cursor() as cursor:
            cursor.execute('SELECT amount_due_ntd,status FROM client_obligations WHERE obligation_identity=%s', (client_obligation,))
            assert cursor.fetchone() == {'amount_due_ntd': 0, 'status': 'settled'}
            cursor.execute('SELECT obligation_amount_ntd,net_paid_ntd,balance_ntd,status FROM staff_payable_projections WHERE obligation_identity=%s', (staff_obligation,))
            assert cursor.fetchone() == {'obligation_amount_ntd': 6000, 'net_paid_ntd': 6000, 'balance_ntd': 0, 'status': 'completed'}
            cursor.execute('SELECT amount_ntd,finance_import_row_id FROM staff_payout_events')
            staff_event = cursor.fetchone()
            assert staff_event['amount_ntd'] == 6000
            cursor.execute('SELECT amount_ntd,finance_import_row_id FROM client_ledger_entries')
            client_entry = cursor.fetchone()
            assert client_entry['amount_ntd'] == 12000
            assert client_entry['finance_import_row_id'] != staff_event['finance_import_row_id']
            for table in ('staff_bank_accounts', 'client_refund_recipient_snapshots'):
                cursor.execute(f'SELECT COUNT(*) n FROM {table}')
                assert cursor.fetchone()['n'] == 0
            cursor.execute('SELECT counterparty_account,debit,memo FROM finance_import_rows ORDER BY id')
            assert list(cursor.fetchall()) == [
                {'counterparty_account': None, 'debit': 12000, 'memo': 'HC115003'},
                {'counterparty_account': None, 'debit': 6000, 'memo': '合成月嫂甲 HC115003'},
            ]
        page = FinanceImportQueryService(connection).bank_transactions(bank='taishin', direction='outgoing', status='all',
                                                                       start=None, end=None, search='', limit=10, before_row_id=None)
        assert sorted((item['cases'], item['status']) for item in page['items']) == [([client_case], 'posted'), ([staff_case], 'posted')]
    finally:
        connection.close()


def test_both_banks_first_import_and_new_key_reimport(tmp_path):
    bootstrap(_arguments())
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.dependencies.admin_auth import require_admin, require_system_admin
    from api.dependencies.finance_import import build_finance_import_application
    from api.routes.client_receipt_reconciliation import router as receipt_router
    from api.routes.finance_import import router
    from infrastructure.mysql.finance_import_owning_domain_composite import MySqlFinanceImportOwningDomainComposite
    from infrastructure.mysql.monthly_accounting_repository import MySqlMonthlyAccountingSource
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.access.authentication_session import AdminPrincipal
    from subsystems.finance_import.import_workflow import FinanceImportApplyRequest
    from subsystems.finance_import.ingestion import ingest_finance_workbook
    from subsystems.finance_import.query import FinanceImportQueryService

    _seed_deposit('115000003', 'synthetic-first-and-repeat')
    sinopac = tmp_path / 'sinopac.xlsx'
    pd.DataFrame([
        ['123456789012', f'2026/09/0{day} 09:00:00', f'2026/09/0{day}', f'2026/09/0{day}',
         '轉帳', 'TWD', None, amount, balance, None, '99781699115003', f'test-{day}', None, None, None]
        for day, amount, balance in [(1, 300, 300), (2, 259, 559), (3, 204, 763)]
    ], columns=SINOPAC_HEADERS).to_excel(sinopac, index=False)
    taishin = tmp_path / 'taishin.xlsx'
    taishin_headers = ['序號', '交易日期', '交易時間', '帳務日期', '摘要', '支出金額', '存入金額', '帳戶餘額', '備註']
    pd.DataFrame([
        ['說明'], taishin_headers,
        ['0001', '2026/09/01', '09:00:00', '2026/09/01', '政府補助', '', '500', '80000', '新竹市政府補助入款'],
        ['0002', '2026/09/02', '09:00:00', '2026/09/02', '轉出', '80', '', '79920', '對象未知'],
        ['0003', '2026/09/03', '09:00:00', '2026/09/03', '轉入', '', '999', '80919', '借款'],
    ]).to_excel(taishin, index=False, header=False)

    actor = ActorContext('isolated-finance-test')
    correlation = CorrelationId('first-and-repeat')
    for workbook, source_count, posted_count, pending_amounts in (
        (sinopac, 3, 1, [204, 259]), (taishin, 1, 0, [500]),
    ):
        before = _counts()
        first = ingest_finance_workbook(str(workbook), IdempotencyKey(f'{workbook.stem}:first'), actor,
                                        connection_factory=get_connection, normalizer=normalize_workbook)
        assert (first.source_row_count, first.canonical_created_count, first.duplicate_occurrence_count) == (source_count, source_count, 0)
        connection = get_connection()
        try:
            application = build_finance_import_application(connection, MySqlFinanceImportOwningDomainComposite(connection))
            plan = application.preview_batch(first.batch_identity, correlation)
            assert plan.counts.ready_dispatch == posted_count
            if posted_count:
                result = application.apply_batch(FinanceImportApplyRequest(
                    first.batch_identity, ExpectedVersion(plan.batch_version), plan.fingerprint,
                    IdempotencyKey(f'{workbook.stem}:apply'), actor, 'Synthetic workbook', correlation,
                ))
                assert result.reconciled_count == posted_count
        finally:
            connection.close()
        repeat = ingest_finance_workbook(str(workbook), IdempotencyKey(f'{workbook.stem}:repeat'), actor,
                                         connection_factory=get_connection, normalizer=normalize_workbook)
        assert first.batch_identity != repeat.batch_identity
        assert (repeat.source_row_count, repeat.canonical_created_count, repeat.duplicate_occurrence_count) == (source_count, 0, source_count)
        connection = get_connection()
        try:
            query = FinanceImportQueryService(connection)
            first_pending = query.list_review_rows(first.batch_identity, limit=50)
            repeat_pending = query.list_review_rows(repeat.batch_identity, limit=50)
            assert sorted(row.amount_ntd for row in first_pending) == pending_amounts
            assert not repeat_pending
            manifest = query.get_manifest(repeat.batch_identity)
            assert manifest.format_id == workbook.stem
            assert manifest.review_count == 0
            assert manifest.occurrence_count == 0
            application = build_finance_import_application(connection, MySqlFinanceImportOwningDomainComposite(connection))
            plan = application.preview_batch(repeat.batch_identity, correlation)
            assert (plan.counts.ready_dispatch, plan.counts.existing, plan.counts.duplicate_occurrences) == (0, 0, source_count)
            assert plan.apply_allowed
            cash = MySqlMonthlyAccountingSource(connection).bank_facts(date(2026, 9, 1), date(2026, 9, 1))
            assert [(row.bank, row.amount_ntd) for row in cash] == [('sinopac', 300)]
        finally:
            connection.close()
        after = _counts()
        assert after['finance_import_rows'] - before['finance_import_rows'] == source_count
        assert after['finance_import_occurrences'] - before['finance_import_occurrences'] == source_count
        assert after['client_ledger_entries'] - before['client_ledger_entries'] == posted_count

    app = FastAPI()
    app.include_router(router)
    app.include_router(receipt_router)
    for guard in (require_admin, require_system_admin):
        app.dependency_overrides[guard] = lambda: AdminPrincipal(1, 'test', 'Synthetic', 'system_admin')
    with TestClient(app) as client:
        base = '/api/v1/finance-import'

        def read(path, **kwargs):
            response = client.get(base + path, **kwargs)
            assert response.status_code == 200, response.text
            return response.json()['data']

        page = read('/bank-transactions')
        assert page['pending_count'] == len(page['items']) == 3
        assert len({row['row_id'] for row in page['items']}) == 3
        assert {row['bank'] for row in page['items']} == {'sinopac', 'taishin'}
        for item in page['items']:
            if item['bank'] == 'sinopac':
                assert item['counterparty_name'] == 'T11 synthetic client'
                assert item['cases'] == ['115000003']
            else:
                assert item['classification_type'] == 'government_subsidy'
                assert item['counterparty_name'] == '新竹市政府'
                assert item['cases'] == []
        posted = read('/bank-transactions', params={'transaction_status': 'posted', 'search': '115000003'})
        assert posted['pending_count'] is None
        assert [(row['amount_ntd'], row['cases']) for row in posted['items']] == [(300, ['115000003'])]
        tai = read('/bank-transactions', params={'bank': 'taishin', 'direction': 'incoming', 'start_date': '2026-09-01'})
        assert [(row['amount_ntd'], row['counterparty_name']) for row in tai['items']] == [(500, '新竹市政府')]
        exact_reference = read('/bank-transactions', params={'search': 'test-2'})
        assert [row['amount_ntd'] for row in exact_reference['items']] == [259]
        first_page = read('/bank-transactions', params={'limit': 2})
        second_page = read('/bank-transactions', params={'limit': 2, 'before_row_id': first_page['next_before_row_id']})
        assert first_page['items'] + second_page['items'] == page['items']

        history = read('/import-history')
        assert [
            (row['bank'], row['new_count'], row['duplicate_count'], row['reconciled_count'], row['pending_count'])
            for row in history['items']
        ] == [
            ('taishin', 0, 1, 0, 0), ('taishin', 1, 0, 0, 1),
            ('sinopac', 0, 3, 0, 0), ('sinopac', 3, 0, 1, 2),
        ]
        history_first = read('/import-history', params={'limit': 2})
        history_second = read('/import-history', params={'limit': 2, 'before': history_first['next_before']})
        assert history_first['items'] + history_second['items'] == history['items']
        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO finance_import_batches(format_id,source_file,sheet_name,header_row,status) "
                    "VALUES ('legacy','older-statement.xlsx','Sheet',1,'completed')"
                )
                cursor.execute(
                    "INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,"
                    "direction,event_type,before_amount_ntd,after_amount_ntd,after_due_date,source_event_identity,"
                    "expected_account_version,idempotency_key,actor,reason) VALUES "
                    "('first:115000003','115000003','first','receivable_from_client','established',0,259,"
                    "'2026-09-02','synthetic:first',1,'synthetic:first','test','Synthetic first payment')"
                )
                cursor.execute(
                    "INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,"
                    "amount_due_ntd,due_date,status,current_event_id,projection_version) VALUES "
                    "('first:115000003','115000003','first','receivable_from_client',259,'2026-09-02','open',%s,1)",
                    (cursor.lastrowid,),
                )
            connection.commit()
        finally:
            connection.close()
        receipt_url = '/api/v1/orders/115000003/client-finance/receipt-reconciliation'
        selection = {'payment_stage': 'first', 'finance_import_row_ids': [exact_reference['items'][0]['row_id']],
                     'obligation_identities': ['first:115000003']}
        preview = client.post(receipt_url + '/preview', json=selection)
        assert preview.status_code == 200, preview.text
        proof = preview.json()['data']
        applied = client.post(receipt_url + '/apply', headers={'Idempotency-Key': 'later-manual', 'X-Correlation-ID': 'later-manual'},
                              json={**selection, 'expected_account_version': proof['account_version'],
                                    'preview_fingerprint': proof['preview_fingerprint'], 'reason': 'Synthetic manual confirmation'})
        assert applied.status_code == 200, applied.text
        assert read('/bank-transactions')['pending_count'] == 2
        after_manual = read('/import-history')['items']
        assert after_manual[:4] == history['items']
        assert (after_manual[4]['source_file'], after_manual[4]['pending_count']) == ('older-statement.xlsx', None)

        assert read('/workbooks/ingestion-outcome', headers={'Idempotency-Key': 'sinopac:repeat'})['status'] == 'committed'
        named_upload = client.post(base + '/workbooks/ingest',
                                   headers={'Idempotency-Key': 'named-upload', 'X-Correlation-ID': 'named-upload'},
                                   files={'workbook': ('original-bank-statement.xlsx', sinopac.read_bytes())})
        assert named_upload.status_code == 200, named_upload.text
        assert read('/import-history')['items'][0]['source_file'] == 'original-bank-statement.xlsx'
        failed_key = {'Idempotency-Key': 'synthetic-format-failure', 'X-Correlation-ID': 'test-format-failure'}
        bad_file = tmp_path / 'bad-format.xlsx'
        pd.DataFrame([['not a bank statement']]).to_excel(bad_file, index=False, header=False)
        failed = client.post(base + '/workbooks/ingest', headers=failed_key,
                             files={'workbook': (bad_file.name, bad_file.read_bytes())})
        assert failed.status_code == 422, failed.text
        assert read('/workbooks/ingestion-outcome', headers=failed_key)['status'] == 'rolled_back'
        assert read('/workbooks/ingestion-outcome', headers={'Idempotency-Key': 'missing-attempt'})['status'] == 'unknown'
        assert read('/import-history')['items'][0]['status'] == 'failed'


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
    from subsystems.finance_import.query import FinanceImportQueryService

    token = uuid4().hex
    # Unique canonical virtual-account case in this disposable schema, not production data.
    sequence = int(token[:6], 16) % 1000
    year = 200 + int(token[6:10], 16) % 700
    case_no = f'{year:03d}{sequence:06d}'
    _seed_deposit(case_no, token)
    workbook = tmp_path / 't11-source-review.xlsx'
    headers = ['帳號', '交易日', '計息日', '入帳日', '摘要', '幣別', '支出', '存入', '餘額', '銷帳編號', '交易參考編號', '', '更正註記', '存摺備註']
    account = '123456789012'
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
        reviews = client.get(url+'/review-rows')
        assert reviews.status_code == 200, reviews.text
        page = reviews.json()['data']
        assert page['batch_identity'] == batch
        assert manifest.json()['data']['review_count'] == len(page['items']) + len(page['source_reviews'])
        assert len(page['items']) == 1 and page['items'][0]['disposition'] == 'business_pending'
        # Source-format warnings are audit evidence, not matched pending receipts.
        assert page['source_reviews'] == []
        global_page = client.get('/api/v1/finance-import/bank-transactions')
        assert global_page.status_code == 200, global_page.text
        assert global_page.json()['data']['pending_count'] == 1
        audit_connection = get_connection()
        try:
            source_reviews = FinanceImportQueryService(audit_connection).list_source_reviews(batch, limit=100)
        finally:
            audit_connection.close()
        assert len(source_reviews) == 1
        source = asdict(source_reviews[0])
        assert source['source_sheet'] == '來源' and source['source_row'] == 3
        assert 'finance_source_field_invalid:transaction_amount' in source['issue_codes']
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
        assert applied['finance_import_apply_receipts'] == staged['finance_import_apply_receipts'] + 1
        assert applied['client_finance_apply_receipts'] == staged['client_finance_apply_receipts'] + 1
        assert applied['client_ledger_entries'] == staged['client_ledger_entries'] + 1
        assert staged['finance_import_source_review_occurrences'] == before['finance_import_source_review_occurrences'] + 1
        assert applied['finance_import_source_review_occurrences'] == staged['finance_import_source_review_occurrences']
        assert applied['staff_payout_events'] == staged['staff_payout_events']  # This batch contains no staff payout.
        after_apply_reviews = client.get(url+'/review-rows').json()['data']
        assert after_apply_reviews['items'] == [], 'posted receipts must leave the owner pending list'
        assert after_apply_reviews['source_reviews'] == page['source_reviews']
        audit_connection = get_connection()
        try:
            assert FinanceImportQueryService(audit_connection).list_source_reviews(batch, limit=100) == source_reviews
        finally:
            audit_connection.close()
        replay = ingest(headers_http['Idempotency-Key'])
        reselect = ingest(headers_http['Idempotency-Key'])
        assert replay.status_code == reselect.status_code == 200
        assert replay.json()['data']['batch_identity'] == reselect.json()['data']['batch_identity'] == batch
        assert _counts() == applied, 'replay/same-key reselect must not duplicate dispatch, receipts, payout or review occurrences'
        assert client.get(url+'/manifest').json()['data']['review_count'] == 0
        # Exact API response crosses the real typed client and page, without DB credentials in the UI process.
        exchange = tmp_path/'review-exchange.json'
        exchange.write_text(json.dumps({'bank_page': global_page.json(), 'source_audit': source}, default=str), encoding='utf-8')
        root = Path(__file__).resolve().parents[1]
        ui_report = tmp_path/'typed-ui-report.json'
        # Direct Node invocation also works on Windows without shell/npm.cmd lookup.
        ui_environment = {name: os.environ[name] for name in ('PATH','SystemRoot','TEMP','TMP') if name in os.environ}
        ui_environment.update(HOME=str(tmp_path), CI='true', FI_REVIEW_EXCHANGE=str(exchange))
        result = subprocess.run(['node', str(root/'ui_react/node_modules/vitest/vitest.mjs'), 'run', 'src/tests/domains/finance-import/subsystems/finance-import/modules/statement-workspace/bank_reconciliation_workspace.test.tsx', '-t', 'same-run source-review', '--reporter=json', '--outputFile', str(ui_report)], cwd=root/'ui_react', env=ui_environment, capture_output=True, text=True, timeout=60)
        assert result.returncode == 0, result.stdout[-5000:]+result.stderr[-5000:]
        report = json.loads(ui_report.read_text(encoding='utf-8'))
        assert report.get('numPassedTests') == 1 and report.get('numFailedTests') == 0, report
        print('T11_2_READBACK', json.dumps({'before': before, 'staged': staged, 'applied_and_replayed': applied, 'source_review_count': 1, 'typed_ui': 'passed'}, sort_keys=True))
