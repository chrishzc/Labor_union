"""Global G14 proof for canonical deposit reversal on isolated MySQL."""

from __future__ import annotations

from argparse import Namespace
from datetime import date
import json
import os

import pymysql
import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from infrastructure.mysql.client_deposit_reversal_repository import (
    ClientDepositReversalMySqlUnitOfWork,
    MySqlClientDepositReversalRepository,
)
from subsystems.orders.client_finance_outbox_consumer import (
    consume_client_finance_orders_events,
)
from subsystems.client_finance.deposit_reversal_workflow import (
    DepositReversalApplyRequest,
    DepositReversalSelection,
    DepositReversalWorkflow,
)


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
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


def _workflow(connection):
    repository = MySqlClientDepositReversalRepository(connection)
    return repository, DepositReversalWorkflow(
        repository,
        lambda: ClientDepositReversalMySqlUnitOfWork(connection),
    )


def _request(preview, *, key: str):
    return DepositReversalApplyRequest(
        DepositReversalSelection("G14-CASE", 1, date(2026, 8, 4)),
        ExpectedVersion(preview.account_version),
        preview.fingerprint,
        IdempotencyKey(key),
        ActorContext("lu-test-runner"),
        "bank return confirmed",
        CorrelationId("g14-deposit-reversal"),
    )


def _apply(connection, *, key="g14-deposit-reversal", request=None):
    repository, workflow = _workflow(connection)
    if request is None:
        selection = DepositReversalSelection("G14-CASE", 1, date(2026, 8, 4))
        request = _request(workflow.preview(selection), key=key)
    repository.bind_apply_request(request)
    try:
        return workflow.apply(request), request
    finally:
        repository.clear_apply_request()


def test_g14_pre_service_reversal_reopens_deposit_once_without_legacy_payment_writes():
    bootstrap(_arguments())
    _seed_settled_deposit(status="訂單成立")
    connection = _connection()
    try:
        receipt, request = _apply(connection)
        replay, _ = _apply(connection, request=request)
        assert replay == receipt
        with connection.cursor() as cursor:
            cursor.execute("SELECT entry_type,amount_ntd,reversal_of_entry_id FROM client_ledger_entries ORDER BY id")
            assert cursor.fetchall() == [
                {"entry_type": "receipt", "amount_ntd": 2000, "reversal_of_entry_id": None},
                {"entry_type": "reversal", "amount_ntd": 2000, "reversal_of_entry_id": 1},
            ]
            cursor.execute("SELECT amount_due_ntd,status,projection_version FROM client_obligations")
            assert cursor.fetchone() == {"amount_due_ntd": 2000, "status": "open", "projection_version": 2}
            cursor.execute("SELECT event_type,before_amount_ntd,after_amount_ntd FROM client_obligation_events ORDER BY id")
            assert cursor.fetchall() == [
                {"event_type": "established", "before_amount_ntd": 0, "after_amount_ntd": 2000},
                {"event_type": "reversed", "before_amount_ntd": 0, "after_amount_ntd": 2000},
            ]
            cursor.execute("SELECT settlement_state,settlement_identity,allocated_net_amount_ntd FROM client_deposit_settlement_projection")
            assert cursor.fetchone() == {"settlement_state": "unsettled", "settlement_identity": None, "allocated_net_amount_ntd": 0}
            cursor.execute("SELECT intent_type FROM client_finance_outbox ORDER BY id")
            assert cursor.fetchall() == [{"intent_type": "orders_deposit_reversed"}]
            cursor.execute("SELECT COUNT(*) AS count FROM client_payments")
            assert cursor.fetchone() == {"count": 0}
    finally:
        connection.close()


def test_g14_post_service_reversal_keeps_service_state_and_routes_anomaly():
    bootstrap(_arguments())
    _seed_settled_deposit(status="服務中")
    connection = _connection()
    try:
        receipt, _ = _apply(connection, key="g14-post-service-reversal")
        assert receipt.anomaly_code == "finance.deposit_reversal_after_service_started"
        with connection.cursor() as cursor:
            cursor.execute("SELECT status FROM orders WHERE case_no='G14-CASE'")
            assert cursor.fetchone() == {"status": "服務中"}
            cursor.execute("SELECT intent_type FROM client_finance_outbox ORDER BY id")
            assert cursor.fetchall() == [
                {"intent_type": "orders_deposit_reversed"},
                {"intent_type": "anomaly_review_required"},
            ]
    finally:
        connection.close()


def test_g14_new_deposit_receipt_requires_actual_start_reconfirmation():
    bootstrap(_arguments())
    _seed_settled_deposit(status="服務中")
    connection = _connection()
    try:
        _apply(connection, key="g14-rereceipt-reversal")
        _seed_reconciled_replacement_receipt(connection)

        assert consume_client_finance_orders_events(connection) == (2, 0)
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT state,confirmed_start_date,deposit_settlement_identity_hash "
                "FROM order_lifecycle_control_state"
            )
            assert cursor.fetchone() == {
                "state": "active",
                "confirmed_start_date": None,
                "deposit_settlement_identity_hash": None,
            }
            cursor.execute(
                "SELECT action,payload_snapshot FROM order_lifecycle_control_events "
                "ORDER BY id"
            )
            control = cursor.fetchone()
            assert control["action"] == "activate"
            assert json.loads(control["payload_snapshot"])[
                "deposit_settlement_identity"
            ] == "c" * 64
            cursor.execute(
                "SELECT intent_type,status FROM client_finance_outbox ORDER BY id"
            )
            assert cursor.fetchall() == [
                {"intent_type": "orders_deposit_reversed", "status": "delivered"},
                {"intent_type": "anomaly_review_required", "status": "pending"},
                {"intent_type": "orders_deposit_reconciled", "status": "delivered"},
            ]
            cursor.execute("SELECT COUNT(*) AS count FROM client_payments")
            assert cursor.fetchone() == {"count": 0}
    finally:
        connection.close()


def _seed_settled_deposit(*, status: str):
    connection = _connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO clients(case_no,name) VALUES ('G14-CASE','G14 Client')")
            client_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO orders(case_no,client_id,status,actual_start_date,service_days) "
                "VALUES ('G14-CASE',%s,%s,%s,20)",
                (client_id, status, "2026-08-01" if status == "服務中" else None),
            )
            cursor.execute("INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES ('G14-CASE',1)")
            cursor.execute(
                "INSERT INTO client_obligation_events "
                "(obligation_identity,case_no,obligation_type,direction,event_type,"
                "before_amount_ntd,after_amount_ntd,before_due_date,after_due_date,"
                "source_event_identity,source_obligation_identity,expected_account_version,"
                "idempotency_key,actor,reason) "
                "VALUES ('G14-CASE:deposit','G14-CASE','deposit','receivable_from_client',"
                "'established',0,2000,NULL,'2026-08-01','g14-root',NULL,0,'g14-root',"
                "'lu-test-runner','fixture root fact')"
            )
            event_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO client_obligations "
                "(obligation_identity,case_no,obligation_type,direction,source_obligation_identity,"
                "amount_due_ntd,due_date,status,current_event_id,projection_version) "
                "VALUES ('G14-CASE:deposit','G14-CASE','deposit','receivable_from_client',NULL,"
                "0,'2026-08-01','settled',%s,1)",
                (event_id,),
            )
            cursor.execute(
                "INSERT INTO client_ledger_entries "
                "(case_no,finance_import_row_id,entry_type,amount_ntd,occurred_on,"
                "reconciliation_reference,reversal_of_entry_id,idempotency_key,actor,reason) "
                "VALUES ('G14-CASE',NULL,'receipt',2000,'2026-08-01',%s,NULL,"
                "'g14-receipt','lu-test-runner','fixture receipt')",
                ("a" * 64,),
            )
            cursor.execute(
                "INSERT INTO client_ledger_obligation_allocations "
                "(ledger_entry_id,obligation_identity,amount_ntd,allocation_ordinal) "
                "VALUES (1,'G14-CASE:deposit',2000,1)"
            )
            cursor.execute(
                "INSERT INTO client_deposit_settlement_projection "
                "(case_no,deposit_obligation_identity,settlement_state,contracted_amount_ntd,"
                "allocated_net_amount_ntd,settlement_identity,source_fingerprint,"
                "projection_version,latest_ledger_entry_id) "
                "VALUES ('G14-CASE','G14-CASE:deposit','settled',2000,2000,%s,%s,1,1)",
                ("a" * 64, "b" * 64),
            )
        connection.commit()
    finally:
        connection.close()


def _seed_reconciled_replacement_receipt(connection) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO client_ledger_entries "
            "(case_no,finance_import_row_id,entry_type,amount_ntd,occurred_on,"
            "reconciliation_reference,reversal_of_entry_id,idempotency_key,actor,reason) "
            "VALUES ('G14-CASE',NULL,'receipt',2000,'2026-08-05',%s,NULL,"
            "'g14-rereceipt','lu-test-runner','replacement receipt')",
            ("c" * 64,),
        )
        receipt_id = int(cursor.lastrowid)
        cursor.execute(
            "UPDATE client_obligations SET amount_due_ntd=0,status='settled',"
            "projection_version=3 WHERE obligation_identity='G14-CASE:deposit'"
        )
        cursor.execute(
            "UPDATE client_finance_accounts SET aggregate_version=3 "
            "WHERE case_no='G14-CASE'"
        )
        cursor.execute(
            "UPDATE client_deposit_settlement_projection SET settlement_state='settled',"
            "allocated_net_amount_ntd=2000,settlement_identity=%s,"
            "source_fingerprint=%s,projection_version=3,latest_ledger_entry_id=%s "
            "WHERE case_no='G14-CASE'",
            ("c" * 64, "d" * 64, receipt_id),
        )
        cursor.execute(
            "INSERT INTO client_finance_outbox(case_no,intent_type,intent_key,payload_snapshot) "
            "VALUES ('G14-CASE','orders_deposit_reconciled','g14-rereceipt-outbox',"
            "JSON_OBJECT('case_no','G14-CASE','settlement_identity',%s,"
            "'resulting_account_version',3))",
            ("c" * 64,),
        )
    connection.commit()
