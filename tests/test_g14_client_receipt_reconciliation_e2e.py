"""G14 uses an immutable Finance Import classification and receipt workflow."""

from __future__ import annotations

from argparse import Namespace
from datetime import date
import json
import os

import pymysql
import pytest

from infrastructure.mysql.client_deposit_reversal_repository import (
    ClientDepositReversalMySqlUnitOfWork,
    MySqlClientDepositReversalRepository,
)
from infrastructure.mysql.client_receipt_reconciliation_repository import (
    ClientReceiptMySqlUnitOfWork,
    MySqlClientReceiptReconciliationRepository,
)
from domains.client_finance.reconciliation import PaymentStage
from scripts.bootstrap_disposable_mysql_schema import bootstrap
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.client_finance.deposit_reversal_workflow import (
    DepositReversalApplyRequest,
    DepositReversalSelection,
    DepositReversalWorkflow,
)
from subsystems.client_finance.reconciliation_workflow import (
    ClientReconciliationApplyRequest,
    ClientReconciliationWorkflow,
    ReconciliationSelection,
)
from subsystems.orders.client_finance_outbox_consumer import (
    consume_client_finance_orders_events,
)


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
CASE_NO = "115000001"
VIRTUAL_ACCOUNT_CODE = "99781699115001"
DEPOSIT_OBLIGATION = f"{CASE_NO}:deposit"
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def _arguments() -> Namespace:
    return Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        confirm_database=DATABASE,
    )


def _connection():
    return pymysql.connect(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def test_g14_reversal_then_real_client_receipt_reconciliation_requires_reconfirmation():
    bootstrap(_arguments())
    connection = _connection()
    try:
        _seed_case(connection)
        _reverse_deposit(connection)
        receipt = _reconcile_replacement_receipt(connection)

        assert receipt.status.value == "exact"
        assert consume_client_finance_orders_events(connection) == (2, 0)
        _assert_orders_control(connection, receipt.settlement_identity.value)
        _assert_no_legacy_payment_write(connection)
    finally:
        connection.close()


def _seed_case(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO clients(case_no,name) VALUES (%s,'G14 Receipt Client')",
            (CASE_NO,),
        )
        client_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO orders(case_no,client_id,status,actual_start_date) "
            "VALUES (%s,%s,'服務中','2026-08-01')",
            (CASE_NO, client_id),
        )
        cursor.execute(
            "INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES (%s,1)",
            (CASE_NO,),
        )
        cursor.execute(
            "INSERT INTO client_obligation_events "
            "(obligation_identity,case_no,obligation_type,direction,event_type,"
            "before_amount_ntd,after_amount_ntd,before_due_date,after_due_date,"
            "source_event_identity,source_obligation_identity,expected_account_version,"
            "idempotency_key,actor,reason) "
            "VALUES (%s,%s,'deposit','receivable_from_client','established',"
            "0,2000,NULL,'2026-08-01','g14-reconciliation-root',NULL,0,"
            "'g14-reconciliation-root','lu-test-runner','fixture root fact')",
            (DEPOSIT_OBLIGATION, CASE_NO),
        )
        event_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO client_obligations "
            "(obligation_identity,case_no,obligation_type,direction,"
            "source_obligation_identity,amount_due_ntd,due_date,status,"
            "current_event_id,projection_version) "
            "VALUES (%s,%s,'deposit','receivable_from_client',NULL,0,"
            "'2026-08-01','settled',%s,1)",
            (DEPOSIT_OBLIGATION, CASE_NO, event_id),
        )
        cursor.execute(
            "INSERT INTO client_ledger_entries "
            "(case_no,finance_import_row_id,entry_type,amount_ntd,occurred_on,"
            "reconciliation_reference,reversal_of_entry_id,idempotency_key,actor,reason) "
            "VALUES (%s,NULL,'receipt',2000,'2026-08-01',%s,NULL,"
            "'g14-original-receipt','lu-test-runner','fixture receipt')",
            (CASE_NO, "a" * 64),
        )
        cursor.execute(
            "INSERT INTO client_ledger_obligation_allocations "
            "(ledger_entry_id,obligation_identity,amount_ntd,allocation_ordinal) "
            "VALUES (1,%s,2000,1)",
            (DEPOSIT_OBLIGATION,),
        )
        cursor.execute(
            "INSERT INTO client_deposit_settlement_projection "
            "(case_no,deposit_obligation_identity,settlement_state,contracted_amount_ntd,"
            "allocated_net_amount_ntd,settlement_identity,source_fingerprint,"
            "projection_version,latest_ledger_entry_id) "
            "VALUES (%s,%s,'settled',2000,2000,%s,%s,1,1)",
            (CASE_NO, DEPOSIT_OBLIGATION, "a" * 64, "b" * 64),
        )
    connection.commit()


def _reverse_deposit(connection) -> None:
    repository = MySqlClientDepositReversalRepository(connection)
    workflow = DepositReversalWorkflow(
        repository,
        lambda: ClientDepositReversalMySqlUnitOfWork(connection),
    )
    selection = DepositReversalSelection(CASE_NO, 1, date(2026, 8, 4))
    preview = workflow.preview(selection)
    request = DepositReversalApplyRequest(
        selection,
        ExpectedVersion(preview.account_version),
        preview.fingerprint,
        IdempotencyKey("g14-real-receipt-reversal"),
        ActorContext("lu-test-runner"),
        "bank return confirmed",
        CorrelationId("g14-real-receipt-reversal"),
    )
    repository.bind_apply_request(request)
    try:
        workflow.apply(request)
    finally:
        repository.clear_apply_request()


def _reconcile_replacement_receipt(connection):
    row_id = _insert_classified_receipt_row(connection)
    repository = MySqlClientReceiptReconciliationRepository(connection)
    workflow = ClientReconciliationWorkflow(
        repository,
        lambda: ClientReceiptMySqlUnitOfWork(connection),
    )
    selection = ReconciliationSelection(
        CASE_NO,
        PaymentStage.DEPOSIT,
        (str(row_id),),
        (DEPOSIT_OBLIGATION,),
    )
    preview = workflow.preview(selection)
    request = ClientReconciliationApplyRequest(
        selection,
        ExpectedVersion(preview.account_version),
        preview.fingerprint,
        IdempotencyKey("g14-real-receipt-reconciliation"),
        ActorContext("lu-test-runner"),
        "replacement deposit receipt confirmed",
        CorrelationId("g14-real-receipt-reconciliation"),
    )
    repository.bind_apply_request(request)
    try:
        return workflow.apply(request)
    finally:
        repository.clear_apply_request()


def _insert_classified_receipt_row(connection) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO finance_import_batches "
            "(format_id,sheet_name,header_row,row_count,status) "
            "VALUES ('sinopac','transactions',1,1,'completed')"
        )
        batch_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO finance_import_rows "
            "(dedup_fingerprint,batch_id,format_id,transaction_date,debit,credit,"
            "direction,currency,cancellation_code,bank_references,warnings,raw_payload) "
            "VALUES (%s,%s,'sinopac','2026-08-05',NULL,2000,'incoming','TWD',%s,"
            "JSON_OBJECT('銷帳編號',%s),JSON_ARRAY(),JSON_OBJECT())",
            ("c" * 64, batch_id, VIRTUAL_ACCOUNT_CODE, VIRTUAL_ACCOUNT_CODE),
        )
        row_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO finance_import_classification_events "
            "(batch_id,finance_import_row_id,classification_version,canonical_fact_version,"
            "classification_type,disposition,decision_facts_fingerprint,target_identities,"
            "evidence,available_actions,actor,reason) "
            "VALUES (%s,%s,1,1,'client_receipt','create',%s,JSON_ARRAY(%s),"
            "JSON_ARRAY(JSON_OBJECT('virtual_account',%s)),JSON_ARRAY('reconcile'),"
            "'lu-test-runner','immutable receipt classification')",
            (batch_id, row_id, "d" * 64, DEPOSIT_OBLIGATION, VIRTUAL_ACCOUNT_CODE),
        )
    connection.commit()
    return row_id


def _assert_orders_control(connection, settlement_identity: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT state,current_event_id FROM order_lifecycle_control_state "
            "WHERE case_no=%s",
            (CASE_NO,),
        )
        state = cursor.fetchone()
        assert state is not None and state["state"] == "active"
        cursor.execute(
            "SELECT payload_snapshot FROM order_lifecycle_control_events WHERE id=%s",
            (state["current_event_id"],),
        )
        assert json.loads(cursor.fetchone()["payload_snapshot"])[
            "deposit_settlement_identity"
        ] == settlement_identity


def _assert_no_legacy_payment_write(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS count FROM client_payments")
        assert cursor.fetchone() == {"count": 0}
