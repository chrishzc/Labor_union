"""Proof that one confirmed over-receipt becomes one receipt and one refund payable."""

from __future__ import annotations

import hashlib
import os
from argparse import Namespace
from uuid import uuid4

import pymysql
import pytest

from domains.client_finance.reconciliation import PaymentStage, ReconciliationStatus
from infrastructure.mysql.client_receipt_reconciliation_repository import (
    ClientReceiptMySqlUnitOfWork,
    MySqlClientReceiptReconciliationRepository,
)
from scripts.bootstrap_disposable_mysql_schema import bootstrap
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.client_finance.reconciliation_workflow import (
    ClientReconciliationApplyRequest,
    ClientReconciliationWorkflow,
    ReconciliationSelection,
)


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def test_confirmed_client_overreceipt_creates_only_the_refund_remaining() -> None:
    bootstrap(_arguments())
    case_no = f"OVER-{uuid4().hex[:16]}"
    connection = _connection()
    try:
        row_id, obligation_identity = _seed_root_facts(connection, case_no)
        receipt = _apply_overage(connection, case_no, row_id, obligation_identity)

        assert receipt.status is ReconciliationStatus.OVERAGE
        _assert_persisted_result(connection, case_no, row_id, obligation_identity)
    finally:
        connection.close()


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


def _seed_root_facts(connection, case_no: str) -> tuple[int, str]:
    obligation_identity = f"{case_no}:deposit"
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO clients(case_no,name) VALUES (%s,'Overage Client')", (case_no,))
        client_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO beclass_records(query_no,refund_bank_code,refund_account_no) "
            "VALUES (%s,'812','test-client-refund-account')",
            (case_no,),
        )
        cursor.execute("INSERT INTO orders(case_no,client_id,status) VALUES (%s,%s,'洽談中')", (case_no, client_id))
        cursor.execute("INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES (%s,0)", (case_no,))
        cursor.execute(
            "INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,before_due_date,after_due_date,source_event_identity,source_obligation_identity,expected_account_version,idempotency_key,actor,reason) VALUES (%s,%s,'deposit','receivable_from_client','established',0,2500,NULL,'2026-08-05',%s,NULL,0,%s,'test','fixture')",
            (obligation_identity, case_no, f"root:{case_no}", f"root:{case_no}"),
        )
        cursor.execute(
            "INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,source_obligation_identity,amount_due_ntd,due_date,status,current_event_id,projection_version) VALUES (%s,%s,'deposit','receivable_from_client',NULL,2500,'2026-08-05','open',%s,0)",
            (obligation_identity, case_no, cursor.lastrowid),
        )
        cursor.execute(
            "INSERT INTO finance_import_batches(format_id,sheet_name,header_row,row_count,status) "
            "VALUES ('sinopac','transactions',1,1,'completed')"
        )
        batch_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO finance_import_rows(dedup_fingerprint,batch_id,format_id,transaction_date,debit,credit,direction,currency,cancellation_code,bank_references,warnings,raw_payload,classification_type) VALUES (%s,%s,'sinopac','2026-08-05',NULL,3000,'incoming','TWD',%s,JSON_OBJECT(),JSON_ARRAY(),JSON_OBJECT(),'client_receipt')",
            (hashlib.sha256(case_no.encode()).hexdigest(), batch_id, f"99781699{case_no[-3:]}001"),
        )
        row_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO finance_import_classification_events "
            "(batch_id,finance_import_row_id,classification_version,canonical_fact_version,classification_type,disposition,decision_facts_fingerprint,target_identities,evidence,available_actions,actor,reason) "
            "VALUES (%s,%s,1,1,'client_receipt','create',%s,JSON_ARRAY(%s),JSON_ARRAY(),JSON_ARRAY('reconcile'),'test',%s)",
            (batch_id, row_id, hashlib.sha256(f"classification:{case_no}".encode()).hexdigest(), f"client:{client_id}", f"client_receipt_heuristic:{case_no}"),
        )
    connection.commit()
    return row_id, obligation_identity


def _apply_overage(connection, case_no: str, row_id: int, obligation_identity: str):
    repository = MySqlClientReceiptReconciliationRepository(connection)
    workflow = ClientReconciliationWorkflow(repository, lambda: ClientReceiptMySqlUnitOfWork(connection))
    selection = ReconciliationSelection(case_no, PaymentStage.DEPOSIT, (str(row_id),), (obligation_identity,), True)
    preview = workflow.preview(selection)
    request = ClientReconciliationApplyRequest(selection, ExpectedVersion(preview.account_version), preview.fingerprint, IdempotencyKey(f"overage:{case_no}"), ActorContext("test"), "confirmed overreceipt", CorrelationId(f"overage:{case_no}"))
    repository.bind_apply_request(request)
    try:
        return workflow.apply(request)
    finally:
        repository.clear_apply_request()


def _assert_persisted_result(connection, case_no: str, row_id: int, obligation_identity: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT amount_due_ntd,status FROM client_obligations WHERE obligation_identity=%s", (obligation_identity,))
        assert cursor.fetchone() == {"amount_due_ntd": 0, "status": "settled"}
        cursor.execute("SELECT amount_due_ntd,status FROM client_obligations WHERE case_no=%s AND obligation_type='refund'", (case_no,))
        assert cursor.fetchone() == {"amount_due_ntd": 500, "status": "open"}
        cursor.execute("SELECT overage_amount_ntd FROM client_receipt_overage_dispositions WHERE finance_import_row_id=%s", (row_id,))
        assert cursor.fetchone() == {"overage_amount_ntd": 500}
        cursor.execute("SELECT reconciliation_status FROM finance_import_rows WHERE id=%s", (row_id,))
        assert cursor.fetchone() == {"reconciliation_status": "reconciled"}
