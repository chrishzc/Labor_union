"""G06: Client Finance corrections never mutate the Orders service-data lock."""

from __future__ import annotations

from argparse import Namespace
import os

import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap


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


def test_g06_refund_and_reversal_preserve_the_immutable_service_data_lock():
    bootstrap(_arguments())
    _seed_locked_refund_case()
    from api.dependencies.client_refund_reversal import ClientRefundReversalApplication
    from infrastructure.mysql.client_refund_reversal_repository import ClientRefundReversalMySqlUnitOfWork, MySqlClientRefundReversalRepository
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.client_finance.client_refund_reversal_workflow import ClientFinanceCorrectionType, ClientRefundReversalApplyRequest, ClientRefundReversalSelection, ClientRefundReversalWorkflow

    connection = get_connection()
    try:
        repository = MySqlClientRefundReversalRepository(connection)
        application = ClientRefundReversalApplication(repository, ClientRefundReversalWorkflow(repository, lambda: ClientRefundReversalMySqlUnitOfWork(connection)))
        before = _lock_snapshot(connection)
        selection = ClientRefundReversalSelection("G06-CASE", ClientFinanceCorrectionType.REFUND, bank_fact_identities=("1",), obligation_identities=("refund:G06-CASE",))
        preview = application.preview(selection, CorrelationId("g06-refund-preview"))
        application.apply(ClientRefundReversalApplyRequest(selection, ExpectedVersion(preview.account_version), preview.fingerprint, IdempotencyKey("g06-refund-apply"), ActorContext("g06-test"), "verified refund", CorrelationId("g06-refund-apply")))
        assert _lock_snapshot(connection) == before
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM client_ledger_entries WHERE entry_type='refund'")
            ledger_id = str(cursor.fetchone()["id"])
        reversal = ClientRefundReversalSelection("G06-CASE", ClientFinanceCorrectionType.REVERSAL, reversal_target_identities=(ledger_id,), reversal_occurred_on="2026-08-02")
        reversal_preview = application.preview(reversal, CorrelationId("g06-reversal-preview"))
        application.apply(ClientRefundReversalApplyRequest(reversal, ExpectedVersion(reversal_preview.account_version), reversal_preview.fingerprint, IdempotencyKey("g06-reversal-apply"), ActorContext("g06-test"), "verified reversal", CorrelationId("g06-reversal-apply")))
        assert _lock_snapshot(connection) == before
    finally:
        connection.close()


def _seed_locked_refund_case() -> None:
    from infrastructure.mysql.mysql_adapter import get_connection
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO clients(case_no,name) VALUES ('G06-CASE','G06 Client')")
            client_id = cursor.lastrowid
            cursor.execute("INSERT INTO orders(case_no,client_id,status) VALUES ('G06-CASE',%s,'服務中')", (client_id,))
            cursor.execute("INSERT INTO order_lifecycle_state_events(case_no,trigger_event,before_status,after_status,actor,business_date,expected_version,idempotency_key,facts_snapshot) VALUES ('G06-CASE','service_complete','服務中','訂單完成','g06-test','2026-08-01',0,'g06-lock-event',JSON_OBJECT())")
            lifecycle_event_id = cursor.lastrowid
            cursor.execute("INSERT INTO order_service_data_locks(case_no,lifecycle_event_id,client_settlement_fingerprint,created_by) VALUES ('G06-CASE',%s,%s,'g06-test')", (lifecycle_event_id, "a" * 64))
            cursor.execute("INSERT INTO client_finance_accounts(case_no,aggregate_version) VALUES ('G06-CASE',0)")
            cursor.execute("INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,before_due_date,after_due_date,source_event_identity,source_obligation_identity,expected_account_version,idempotency_key,actor,reason) VALUES ('refund:G06-CASE','G06-CASE','refund','payable_to_client','established',0,300,NULL,'2026-08-15','g06-refund-root',NULL,0,'g06-refund-root','g06-test','fixture')")
            event_id = cursor.lastrowid
            cursor.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,source_obligation_identity,amount_due_ntd,due_date,status,current_event_id,projection_version) VALUES ('refund:G06-CASE','G06-CASE','refund','payable_to_client',NULL,300,'2026-08-15','open',%s,0)", (event_id,))
            cursor.execute("INSERT INTO finance_import_rows(dedup_fingerprint,format_id,transaction_date,debit,credit,direction,currency,bank_references,warnings,raw_payload,classification_type) VALUES (%s,'taishin','2026-08-01',300,NULL,'outgoing','TWD',JSON_OBJECT(),JSON_ARRAY(),JSON_OBJECT(),'client_refund')", ("b" * 64,))
        connection.commit()
    finally:
        connection.close()


def _lock_snapshot(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT case_no,lifecycle_event_id,client_settlement_fingerprint,created_by FROM order_service_data_locks WHERE case_no='G06-CASE'")
        return cursor.fetchone()
