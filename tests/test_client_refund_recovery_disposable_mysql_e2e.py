"""Real MySQL proof that client-refund underpayment is recovery-only."""

from __future__ import annotations

import hashlib
import os
from uuid import uuid4

import pytest


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE or os.getenv("DB_DATABASE") != DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def test_refund_requires_exact_settlement_unless_the_operator_confirms_recovery():
    case_no = f"CFR-{uuid4().hex[:16]}"
    first_row_id, second_row_id = _seed_refund_roots(case_no)
    application, connection = _application()
    try:
        normal_selection = _selection(case_no, first_row_id)
        before = _snapshot(connection, case_no)
        _assert_normal_underpayment_has_no_writes(application, normal_selection)
        assert _snapshot(connection, case_no) == before

        recovery_selection = _selection(case_no, first_row_id, recovery=True)
        recovery_request = _apply_request(application, recovery_selection, "recovery")
        first_receipt = application.apply(recovery_request)
        assert application.apply(recovery_request) == first_receipt
        _assert_partial_recovery(connection, case_no, first_row_id)

        second_receipt = _apply(application, _selection(case_no, second_row_id), "exact")
        assert second_receipt.account_version == 2
        _assert_exact_settlement(connection, case_no, second_row_id)
    finally:
        connection.close()


def _application():
    from api.dependencies.client_refund_reversal import ClientRefundReversalApplication
    from infrastructure.mysql.client_refund_reversal_repository import (
        ClientRefundReversalMySqlUnitOfWork,
        MySqlClientRefundReversalRepository,
    )
    from infrastructure.mysql.mysql_adapter import get_connection
    from subsystems.client_finance.client_refund_reversal_workflow import (
        ClientRefundReversalWorkflow,
    )

    connection = get_connection()
    repository = MySqlClientRefundReversalRepository(connection)
    workflow = ClientRefundReversalWorkflow(
        repository,
        lambda: ClientRefundReversalMySqlUnitOfWork(connection),
    )
    return ClientRefundReversalApplication(repository, workflow), connection


def _selection(case_no: str, row_id: int, *, recovery: bool = False):
    from domains.client_finance.client_refund_reversal import (
        ClientFinanceCorrectionType,
    )
    from subsystems.client_finance.client_refund_reversal_workflow import (
        ClientRefundReversalSelection,
    )

    return ClientRefundReversalSelection(
        case_no,
        ClientFinanceCorrectionType.REFUND,
        bank_fact_identities=(str(row_id),),
        obligation_identities=(f"refund:{case_no}",),
        allow_partial_refund_recovery=recovery,
    )


def _apply(application, selection, suffix: str):
    return application.apply(_apply_request(application, selection, suffix))


def _apply_request(application, selection, suffix: str):
    from shared_kernel.identities import (
        ActorContext,
        CorrelationId,
        ExpectedVersion,
        IdempotencyKey,
    )
    from subsystems.client_finance.client_refund_reversal_workflow import (
        ClientRefundReversalApplyRequest,
    )

    correlation = CorrelationId(f"refund-recovery:{suffix}:{selection.case_no}")
    preview = application.preview(selection, correlation)
    return ClientRefundReversalApplyRequest(
        selection,
        ExpectedVersion(preview.account_version),
        preview.fingerprint,
        IdempotencyKey(f"refund-recovery:{suffix}:{selection.case_no}"),
        ActorContext("lu-test-refund-recovery"),
        "operator reviewed the immutable bank statement",
        correlation,
    )


def _assert_normal_underpayment_has_no_writes(application, selection) -> None:
    from subsystems.client_finance.client_refund_reversal_workflow import (
        ClientRefundReversalError,
    )
    from shared_kernel.identities import CorrelationId

    with pytest.raises(ClientRefundReversalError) as error:
        application.preview(
            selection,
            CorrelationId(f"refund-recovery:normal:{selection.case_no}"),
        )
    assert error.value.error.code == "refund_requires_exact_settlement"


def _seed_refund_roots(case_no: str) -> tuple[int, int]:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO clients(case_no,name) VALUES (%s,%s)", (case_no, "Synthetic Refund Client"))
            client_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO orders(case_no,client_id,status) VALUES (%s,%s,'訂單取消')",
                (case_no, client_id),
            )
            cursor.execute(
                "INSERT INTO client_obligation_events("
                "obligation_identity,case_no,obligation_type,direction,event_type,"
                "before_amount_ntd,after_amount_ntd,before_due_date,after_due_date,"
                "source_event_identity,source_obligation_identity,expected_account_version,"
                "idempotency_key,actor,reason) "
                "VALUES (%s,%s,'refund','payable_to_client','established',0,500,"
                "NULL,'2026-08-15',%s,NULL,0,%s,'lu-test-refund-recovery','fixture')",
                (f"refund:{case_no}", case_no, f"refund-root:{case_no}", f"refund-root:{case_no}"),
            )
            event_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO client_obligations("
                "obligation_identity,case_no,obligation_type,direction,"
                "source_obligation_identity,amount_due_ntd,due_date,status,"
                "current_event_id,projection_version) "
                "VALUES (%s,%s,'refund','payable_to_client',NULL,500,'2026-08-15',"
                "'open',%s,0)",
                (f"refund:{case_no}", case_no, event_id),
            )
            cursor.execute(
                "INSERT INTO client_refund_recipient_snapshots("
                "refund_obligation_identity,case_no,bank_code,bank_account,source_kind) "
                "VALUES (%s,%s,'812','test-client-refund-account','fixture')",
                (f"refund:{case_no}", case_no),
            )
            first_row_id = _insert_refund_bank_row(cursor, case_no, 300, "first")
            second_row_id = _insert_refund_bank_row(cursor, case_no, 200, "second")
        connection.commit()
        return int(first_row_id), int(second_row_id)
    finally:
        connection.close()


def _insert_refund_bank_row(cursor, case_no: str, amount: int, suffix: str) -> int:
    digest = hashlib.sha256(f"{case_no}:{suffix}".encode()).hexdigest()
    cursor.execute(
        "INSERT INTO finance_import_rows("
        "dedup_fingerprint,format_id,transaction_date,debit,credit,direction,currency,"
        "bank_references,warnings,raw_payload,classification_type,resolved_counterparty_account) "
        "VALUES (%s,'taishin','2026-08-01',%s,NULL,'outgoing','TWD',"
        "JSON_OBJECT(),JSON_ARRAY(),JSON_OBJECT(),'client_refund','test-client-refund-account')",
        (digest, amount),
    )
    return int(cursor.lastrowid)


def _snapshot(connection, case_no: str) -> tuple[int, int, int]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS count FROM client_ledger_entries WHERE case_no=%s",
            (case_no,),
        )
        ledger_count = int(cursor.fetchone()["count"])
        cursor.execute(
            "SELECT COUNT(*) AS count FROM client_ledger_obligation_allocations "
            "WHERE obligation_identity=%s",
            (f"refund:{case_no}",),
        )
        allocation_count = int(cursor.fetchone()["count"])
        cursor.execute(
            "SELECT COUNT(*) AS count FROM client_refund_reversal_apply_receipts WHERE case_no=%s",
            (case_no,),
        )
        receipt_count = int(cursor.fetchone()["count"])
    return ledger_count, allocation_count, receipt_count


def _assert_partial_recovery(connection, case_no: str, first_row_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT amount_due_ntd,status FROM client_obligations WHERE obligation_identity=%s",
            (f"refund:{case_no}",),
        )
        assert cursor.fetchone() == {"amount_due_ntd": 200, "status": "open"}
        cursor.execute("SELECT reconciliation_status FROM finance_import_rows WHERE id=%s", (first_row_id,))
        assert cursor.fetchone() == {"reconciliation_status": "reconciled"}
    assert _snapshot(connection, case_no) == (1, 1, 1)


def _assert_exact_settlement(connection, case_no: str, second_row_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT amount_due_ntd,status FROM client_obligations WHERE obligation_identity=%s",
            (f"refund:{case_no}",),
        )
        assert cursor.fetchone() == {"amount_due_ntd": 0, "status": "settled"}
        cursor.execute("SELECT reconciliation_status FROM finance_import_rows WHERE id=%s", (second_row_id,))
        assert cursor.fetchone() == {"reconciliation_status": "reconciled"}
    assert _snapshot(connection, case_no) == (2, 2, 2)
