"""Disposable-MySQL proof that review creation does not write a reversal."""

from argparse import Namespace
import os

import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def _arguments():
    return Namespace(
        host=os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        port=int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        user=os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        password=os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        database=DATABASE,
        confirm_database=DATABASE,
    )


@pytest.fixture(autouse=True)
def _use_disposable_database(monkeypatch):
    settings = {
        "DB_HOST": os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        "DB_PORT": os.environ["LABOR_UNION_TEST_MYSQL_PORT"],
        "DB_USER": os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        "DB_PASSWORD": os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        "DB_DATABASE": DATABASE,
    }
    for name, value in settings.items():
        monkeypatch.setenv(name, value)
    from infrastructure.mysql import mysql_adapter

    monkeypatch.setattr(
        mysql_adapter,
        "DB_CONFIG",
        {
            "host": settings["DB_HOST"],
            "port": int(settings["DB_PORT"]),
            "user": settings["DB_USER"],
            "password": settings["DB_PASSWORD"],
            "database": settings["DB_DATABASE"],
            "charset": "utf8mb4",
        },
    )


def test_review_event_projects_blocking_anomaly_without_refund_reversal():
    bootstrap(_arguments())
    _seed_reviewable_return()

    from domains.client_finance.refund_return_review import RefundReturnReviewSelection
    from infrastructure.mysql.finance_import_repository import (
        FinanceImportMySqlUnitOfWork,
        MySqlFinanceImportRepository,
    )
    from infrastructure.mysql.anomaly_runtime import build_anomaly_runtime
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.finance_import.finance_import_anomaly_consumer import consume_finance_import_anomaly_events
    from subsystems.finance_import.refund_return_review_workflow import (
        RefundReturnReviewApplyRequest,
        RefundReturnReviewWorkflow,
    )

    selection = RefundReturnReviewSelection(
        "finance-import-row:1",
        "client-ledger-entry:1",
        "C-1",
        "bank return receipt verified",
        ("bank-return-document:1",),
    )
    connection = get_connection()
    try:
        workflow = RefundReturnReviewWorkflow(
            MySqlFinanceImportRepository(connection),
            lambda: FinanceImportMySqlUnitOfWork(connection),
        )
        preview = workflow.preview(selection, CorrelationId("review-preview"))
        receipt = workflow.apply(
            RefundReturnReviewApplyRequest(
                selection,
                ExpectedVersion(preview.batch_version),
                preview.fingerprint,
                IdempotencyKey("refund-return-review-e2e"),
                ActorContext("lu-test-runner"),
                CorrelationId("review-apply"),
            )
        )
        assert workflow.apply(
            RefundReturnReviewApplyRequest(
                selection,
                ExpectedVersion(preview.batch_version),
                preview.fingerprint,
                IdempotencyKey("refund-return-review-e2e"),
                ActorContext("lu-test-runner"),
                CorrelationId("review-apply"),
            )
        ) == receipt
        result = consume_finance_import_anomaly_events(
            connection, runtime=build_anomaly_runtime()
        )
        assert result.delivered_count == 1
        with connection.cursor() as cursor:
            cursor.execute("SELECT entry_type FROM client_ledger_entries ORDER BY id")
            assert cursor.fetchall() == [{"entry_type": "refund"}]
            cursor.execute("SELECT COUNT(*) AS count FROM client_refund_return_review_events")
            assert cursor.fetchone() == {"count": 1}
            cursor.execute("SELECT COUNT(*) AS count FROM client_refund_return_review_receipts")
            assert cursor.fetchone() == {"count": 1}
            cursor.execute("SELECT COUNT(*) AS count FROM anomaly_current_alerts WHERE definition_code='CLIENTREFUND-001'")
            assert cursor.fetchone() == {"count": 0}
            cursor.execute("INSERT INTO client_ledger_entries(case_no,finance_import_row_id,entry_type,amount_ntd,occurred_on,reconciliation_reference,reversal_of_entry_id,idempotency_key,actor,reason) VALUES ('C-1',1,'refund_reversal',300,'2026-08-05','fixture-refund-return',1,'fixture-refund-return','lu-test-runner','fixture reversal')")
            cursor.execute("INSERT INTO finance_import_outbox(batch_id,intent_key,intent_type,payload_snapshot) VALUES (1,'fixture-refund-return-resolution','manual_correction_completed',JSON_OBJECT('row_identity','finance-import-row:1','batch_identity','finance-import-batch:1','classification_type','client_refund_return','refund_ledger_entry_identity','client-ledger-entry:1'))")
        connection.commit()
        resolved = consume_finance_import_anomaly_events(
            connection, runtime=build_anomaly_runtime()
        )
        assert resolved.delivered_count == 1
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM anomaly_current_alerts WHERE definition_code='CLIENTREFUND-001'")
            assert cursor.fetchone() == {"count": 0}
    finally:
        connection.close()


def _seed_reviewable_return():
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO clients(case_no,name) VALUES ('C-1','Review Client')")
            client_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO orders(case_no,client_id,status) VALUES ('C-1',%s,'訂單完成')", (client_id,))
            cursor.execute("INSERT INTO finance_import_batches(format_id,sheet_name,header_row,row_count,status) VALUES ('taishin','Sheet1',1,1,'completed')")
            batch_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO finance_import_batch_contracts(batch_id,batch_identity,source_content_digest,classifier_version,fingerprint_version,batch_version) VALUES (%s,'finance-import-batch:1',%s,'fixture','fixture',3)", (batch_id, "a" * 64))
            cursor.execute("INSERT INTO finance_import_rows(dedup_fingerprint,batch_id,format_id,sheet_name,source_row,transaction_date,credit,direction,bank_references,warnings,raw_payload,reconciliation_status) VALUES (%s,%s,'taishin','Sheet1',2,'2026-08-05',300,'incoming',JSON_OBJECT(),JSON_ARRAY(),JSON_OBJECT(),'pending')", ("b" * 64, batch_id))
            row_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO finance_import_occurrences(batch_id,finance_import_row_id,sheet_name,source_row,warnings) VALUES (%s,%s,'Sheet1',2,JSON_ARRAY())", (batch_id, row_id))
            cursor.execute("INSERT INTO client_ledger_entries(id,case_no,entry_type,amount_ntd,occurred_on,reconciliation_reference,idempotency_key,actor,reason) VALUES (1,'C-1','refund',300,'2026-08-04','fixture-refund','fixture-refund','lu-test-runner','fixture refund')")
        connection.commit()
    finally:
        connection.close()
