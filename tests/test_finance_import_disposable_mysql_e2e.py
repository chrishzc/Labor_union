"""
File: test_finance_import_disposable_mysql_e2e.py
Description: 以 disposable MySQL 驗證 Finance Import 資料完整性、投影與重試停損。
"""

from __future__ import annotations

from argparse import Namespace
import os
from pathlib import Path

import pandas as pd
import pytest

from scripts.bootstrap_disposable_mysql_schema import bootstrap
from scripts.imports.finance_statement_normalizer import normalize_workbook


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEIDENTIFIED_TAISHIN_FIXTURE = (
    PROJECT_ROOT / "tests/fixtures/finance_import/taishin_deidentified_minimal.xlsx"
)
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


@pytest.fixture(autouse=True)
def _use_explicit_disposable_database(monkeypatch):
    """Keep every legacy adapter import on this test's isolated database."""
    database_settings = {
        "DB_HOST": os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        "DB_PORT": os.environ["LABOR_UNION_TEST_MYSQL_PORT"],
        "DB_USER": os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        "DB_PASSWORD": os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        "DB_DATABASE": DATABASE,
    }
    for setting_name, setting_value in database_settings.items():
        monkeypatch.setenv(setting_name, setting_value)

    from infrastructure.mysql import mysql_adapter

    monkeypatch.setattr(
        mysql_adapter,
        "DB_CONFIG",
        {
            "host": database_settings["DB_HOST"],
            "port": int(database_settings["DB_PORT"]),
            "user": database_settings["DB_USER"],
            "password": database_settings["DB_PASSWORD"],
            "database": database_settings["DB_DATABASE"],
            "charset": "utf8mb4",
        },
    )


def test_deidentified_taishin_fixture_becomes_root_fact_and_unresolved_reprocess_blocks():
    bootstrap(_arguments())
    workbook = DEIDENTIFIED_TAISHIN_FIXTURE
    assert workbook.is_file()

    from infrastructure.mysql.mysql_adapter import get_connection
    from subsystems.finance_import.ingestion import ingest_finance_workbook
    from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey

    receipt = ingest_finance_workbook(
        str(workbook),
        IdempotencyKey("lu-test-unresolved-historical-reprocess"),
        ActorContext("lu-test-runner"),
        connection_factory=get_connection,
        normalizer=normalize_workbook,
    )

    assert receipt.source_row_count == receipt.canonical_created_count == 1
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT classification_type FROM finance_import_classification_events"
            )
            assert cursor.fetchone()["classification_type"] == "non_business_review"
    finally:
        connection.close()

    from infrastructure.mysql.finance_import_owning_domain_composite import MySqlFinanceImportOwningDomainComposite
    from infrastructure.mysql.finance_import_repository import FinanceImportMySqlUnitOfWork
    from infrastructure.mysql.historical_reprocess_repository import MySqlHistoricalReprocessRepository
    from subsystems.finance_import.historical_reprocess_workflow import HistoricalReprocessWorkflow, HistoricalReprocessWorkflowError

    connection = get_connection()
    try:
        workflow = HistoricalReprocessWorkflow(
            MySqlHistoricalReprocessRepository(connection),
            MySqlFinanceImportOwningDomainComposite(connection),
            lambda: FinanceImportMySqlUnitOfWork(connection),
        )
        with pytest.raises(HistoricalReprocessWorkflowError) as error:
            workflow.preview(receipt.batch_identity, CorrelationId("lu-test-preview"))
    finally:
        connection.close()

    assert error.value.error.code == "reprocess_owner_not_resolved"


def test_mixed_finance_workbook_keeps_valid_row_and_acknowledges_owner_review(tmp_path):
    bootstrap(_arguments())
    workbook = tmp_path / "taishin-mixed-source-review.xlsx"
    pd.DataFrame(
        [
            ["說明"],
            ["序號", "交易日期", "交易時間", "帳務日期", "摘要", "支出金額", "存入金額", "帳戶餘額", "備註"],
            ["0001", "2026/08/04", "09:08:07", "2026/08/04", "轉帳", "300", "", "9000", "正常列"],
            ["0002", "2026/08/05", "09:09:07", "2026/08/05", "轉帳", "300.5", "", "8699.5", "敏感備註 0912345678"],
        ]
    ).to_excel(workbook, sheet_name="交易明細", index=False, header=False)

    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.anomaly_runtime import build_anomaly_runtime
    from shared_kernel.identities import ActorContext, IdempotencyKey
    from subsystems.finance_import.finance_import_anomaly_consumer import (
        consume_finance_import_anomaly_events,
    )
    from subsystems.finance_import.ingestion import ingest_finance_workbook

    receipt = ingest_finance_workbook(
        str(workbook),
        IdempotencyKey("lu-test-finance-source-review"),
        ActorContext("lu-test-runner"),
        connection_factory=get_connection,
        normalizer=normalize_workbook,
    )
    replay = ingest_finance_workbook(
        str(workbook),
        IdempotencyKey("lu-test-finance-source-review"),
        ActorContext("lu-test-runner"),
        connection_factory=get_connection,
        normalizer=normalize_workbook,
    )

    assert receipt == replay
    assert receipt.source_row_count == 2
    assert receipt.canonical_created_count == 1
    assert receipt.source_warning_count == 1
    assert receipt.source_warning_created_count == 1

    connection = get_connection()
    try:
        projected = consume_finance_import_anomaly_events(
            connection, runtime=build_anomaly_runtime()
        )
        assert projected.failed_count == 0
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM finance_import_rows"
            )
            assert cursor.fetchone() == {"count": 1}
            cursor.execute(
                "SELECT source_identity,issue_codes "
                "FROM finance_import_source_reviews"
            )
            stored_review = cursor.fetchone()
            assert stored_review["source_identity"].startswith("finance-taishin-row-")
            assert "invalid:transaction_amount" in stored_review["issue_codes"]
            assert "0912345678" not in str(stored_review)
            assert "敏感備註" not in str(stored_review)
            cursor.execute(
                "SELECT COUNT(*) AS count FROM finance_import_source_review_outbox "
                "WHERE published_at IS NOT NULL"
            )
            assert cursor.fetchone() == {"count": 1}
            cursor.execute(
                "SELECT COUNT(*) AS count FROM import_warning_occurrences "
                "WHERE owning_lane='finance_import'"
            )
            assert cursor.fetchone() == {"count": 0}
    finally:
        connection.close()


def test_historical_owner_selection_posts_once_without_mutating_bank_root_fact(tmp_path):
    bootstrap(_arguments())
    _seed_open_refund_obligation()
    intake_receipt = _ingest_unresolved_taishin_outflow(tmp_path)

    from api.dependencies.finance_import import HistoricalReprocessApplication
    from infrastructure.mysql.finance_import_owning_domain_composite import (
        MySqlFinanceImportOwningDomainComposite,
    )
    from infrastructure.mysql.finance_import_repository import FinanceImportMySqlUnitOfWork
    from infrastructure.mysql.historical_reprocess_repository import MySqlHistoricalReprocessRepository
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import (
        ActorContext,
        CorrelationId,
        ExpectedVersion,
        IdempotencyKey,
    )
    from subsystems.finance_import.historical_reprocess_workflow import (
        HistoricalOwnerSelection,
        HistoricalReprocessApplyRequest,
        HistoricalReprocessWorkflow,
    )

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT bank_references FROM finance_import_rows WHERE id=1"
            )
            original_bank_references = cursor.fetchone()["bank_references"]
        posting_port = MySqlFinanceImportOwningDomainComposite(connection)
        application = HistoricalReprocessApplication(
            HistoricalReprocessWorkflow(
                MySqlHistoricalReprocessRepository(connection),
                posting_port,
                lambda: FinanceImportMySqlUnitOfWork(connection),
            ),
            posting_port,
        )
        selection = HistoricalOwnerSelection(
            "finance-import-row:1",
            "C-1",
            "refund:C-1",
            "reviewed original bank statement and refund request",
            ("bank-statement:line-3", "refund-request:C-1"),
        )
        preview = application.preview(
            intake_receipt.batch_identity,
            CorrelationId("historical-owner-selection-preview"),
            (selection,),
        )
        request = HistoricalReprocessApplyRequest(
            intake_receipt.batch_identity,
            ExpectedVersion(preview.batch_version),
            preview.fingerprint,
            IdempotencyKey("historical-owner-selection-apply"),
            ActorContext("lu-test-runner"),
            "apply reviewed historical refund owner",
            CorrelationId("historical-owner-selection-apply"),
            (selection,),
        )

        receipt = application.apply(request)
        assert application.apply(request) == receipt

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT bank_references FROM finance_import_rows WHERE id=1"
            )
            assert cursor.fetchone()["bank_references"] == original_bank_references
            cursor.execute(
                "SELECT case_no,obligation_identity,source_canonical_fact_version,"
                "resulting_canonical_fact_version,obligation_projection_version "
                "FROM historical_owner_selection_events"
            )
            assert cursor.fetchone() == {
                "case_no": "C-1",
                "obligation_identity": "refund:C-1",
                "source_canonical_fact_version": 0,
                "resulting_canonical_fact_version": 1,
                "obligation_projection_version": 0,
            }
            cursor.execute("SELECT actor FROM finance_import_reprocess_runs")
            assert cursor.fetchone() == {"actor": "lu-test-runner"}
            cursor.execute("SELECT entry_type,amount_ntd FROM client_ledger_entries")
            assert cursor.fetchone() == {"entry_type": "refund", "amount_ntd": 300}
            cursor.execute(
                "SELECT amount_due_ntd,status FROM client_obligations "
                "WHERE obligation_identity='refund:C-1'"
            )
            assert cursor.fetchone() == {"amount_due_ntd": 0, "status": "settled"}
            cursor.execute(
                "SELECT COUNT(*) AS count FROM finance_import_historical_reprocess_receipts"
            )
            assert cursor.fetchone() == {"count": 1}
    finally:
        connection.close()


def test_manual_refund_correction_posts_ledger_allocation_and_resolves_anomaly(tmp_path):
    bootstrap(_arguments())
    _seed_open_refund_obligation()
    _ingest_unresolved_taishin_outflow(tmp_path)
    _deliver_finance_import_outbox()

    from domains.finance_import.correction import FinanceImportCorrectionSelection
    from domains.finance_import.planning import FinanceClassificationType
    from api.dependencies.finance_import import build_finance_import_application
    from infrastructure.mysql.finance_import_owning_domain_composite import MySqlFinanceImportOwningDomainComposite
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.finance_import.correction_workflow import FinanceImportCorrectionApplyRequest

    connection = get_connection()
    try:
        application = build_finance_import_application(
            connection,
            MySqlFinanceImportOwningDomainComposite(connection),
        )
        selection = FinanceImportCorrectionSelection(
            "finance-import-row:1",
            FinanceClassificationType.CLIENT_REFUND,
            ("refund:C-1",),
            "bank statement and customer refund request were reviewed",
            ("bank-statement:line-3", "customer-refund-request:C-1"),
        )
        preview = application.preview_correction(selection, CorrelationId("lu-test-correction-preview"))
        receipt = application.correct_and_post(
            FinanceImportCorrectionApplyRequest(
                selection,
                ExpectedVersion(preview.batch_version),
                ExpectedVersion(preview.canonical_fact_version),
                ExpectedVersion(preview.alert_version),
                preview.fingerprint,
                IdempotencyKey("lu-test-manual-refund-correction"),
                ActorContext("lu-test-runner"),
                CorrelationId("lu-test-correction-apply"),
            )
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT entry_type,amount_ntd FROM client_ledger_entries")
            assert cursor.fetchone() == {"entry_type": "refund", "amount_ntd": 300}
            cursor.execute("SELECT amount_due_ntd,status FROM client_obligations WHERE obligation_identity='refund:C-1'")
            assert cursor.fetchone() == {"amount_due_ntd": 0, "status": "settled"}
    finally:
        connection.close()

    _deliver_finance_import_outbox()
    assert receipt.ledger_entry_count == receipt.allocation_count == 1
    _assert_manual_review_alert_remains_active_without_owner_terminal_contract()


def test_durable_correction_worker_posts_manual_refund_once(tmp_path):
    """A correction survives API-process loss because the worker owns Apply."""
    bootstrap(_arguments())
    _seed_open_refund_obligation()
    _ingest_unresolved_taishin_outflow(tmp_path)
    _deliver_finance_import_outbox()

    from api.dependencies.finance_import import build_finance_import_application
    from api.routes.finance_import import _correction_apply_job_command
    from domains.finance_import.correction import FinanceImportCorrectionSelection
    from domains.finance_import.planning import FinanceClassificationType
    from infrastructure.mysql.background_job_repository import BackgroundJobRepository
    from infrastructure.mysql.finance_import_owning_domain_composite import MySqlFinanceImportOwningDomainComposite
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import CorrelationId
    from api.dependencies.durable_job_handlers import default_job_handlers
    from subsystems.jobs.durable_job_worker import DurableJobWorker
    from subsystems.jobs.command_application import DurableJobCommandApplication

    connection = get_connection()
    try:
        application = build_finance_import_application(
            connection,
            MySqlFinanceImportOwningDomainComposite(connection),
        )
        selection = FinanceImportCorrectionSelection(
            "finance-import-row:1",
            FinanceClassificationType.CLIENT_REFUND,
            ("refund:C-1",),
            "durable manual refund verified",
            ("bank-statement:line-3",),
        )
        preview = application.preview_correction(
            selection,
            CorrelationId("durable-correction-preview"),
        )
        request = _correction_request(
            selection,
            preview,
            "durable-correction-apply",
            "durable-correction-apply",
        )
        repository = BackgroundJobRepository(connection)
        job_id = "durable-correction-job"
        assert DurableJobCommandApplication(repository, connection).enqueue(
            _correction_apply_job_command(job_id, request)
        ).job_id == job_id
    finally:
        connection.close()

    worker_connection = get_connection()
    try:
        worker = DurableJobWorker(
            BackgroundJobRepository(worker_connection),
            worker_connection,
            default_job_handlers(),
            "durable-correction-worker",
            retry_delay_seconds=0,
        )
        assert worker.recover_and_run_once() is True
        assert worker.recover_and_run_once() is False
        stored = BackgroundJobRepository(worker_connection).get_job(job_id)
        assert stored is not None
        assert stored.status == "succeeded", stored.error_payload
        assert stored.receipt_payload == {
            "kind": "success",
            "result_reference": "finance_import_correction:finance-import-row:1",
            "schema_version": 1,
        }
        with worker_connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM client_ledger_entries")
            assert cursor.fetchone() == {"count": 1}
            cursor.execute(
                "SELECT COUNT(*) AS count FROM finance_import_correction_receipts"
            )
            assert cursor.fetchone() == {"count": 1}
    finally:
        worker_connection.close()


def test_real_taishin_refund_return_reopens_original_refund_once(tmp_path):
    bootstrap(_arguments())
    _seed_open_refund_obligation()
    _post_manual_refund(tmp_path)
    _ingest_unresolved_taishin_inflow(tmp_path)
    _deliver_finance_import_outbox()

    from api.dependencies.finance_import import build_finance_import_application
    from domains.finance_import.correction import FinanceImportCorrectionSelection
    from domains.finance_import.planning import FinanceClassificationType
    from infrastructure.mysql.finance_import_owning_domain_composite import MySqlFinanceImportOwningDomainComposite
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.finance_import.correction_workflow import FinanceImportCorrectionApplyRequest

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM client_ledger_entries WHERE entry_type='refund'")
            refund_ledger_entry_id = str(cursor.fetchone()["id"])
        application = build_finance_import_application(connection, MySqlFinanceImportOwningDomainComposite(connection))
        selection = FinanceImportCorrectionSelection(
            "finance-import-row:2", FinanceClassificationType.CLIENT_REFUND_RETURN,
            ("refund:C-1",), "returned customer refund was verified",
            ("bank-statement:return-line", "refund-ledger:" + refund_ledger_entry_id),
            refund_ledger_entry_id,
        )
        preview = application.preview_correction(selection, CorrelationId("lu-test-refund-return-preview"))
        request = FinanceImportCorrectionApplyRequest(
            selection, ExpectedVersion(preview.batch_version), ExpectedVersion(preview.canonical_fact_version),
            ExpectedVersion(preview.alert_version), preview.fingerprint, IdempotencyKey("lu-test-refund-return"),
            ActorContext("lu-test-runner"), CorrelationId("lu-test-refund-return-apply"),
        )
        receipt = application.correct_and_post(request)
        assert application.correct_and_post(request) == receipt
        with connection.cursor() as cursor:
            cursor.execute("SELECT entry_type,amount_ntd FROM client_ledger_entries ORDER BY id")
            assert cursor.fetchall() == [
                {"entry_type": "refund", "amount_ntd": 300},
                {"entry_type": "refund_reversal", "amount_ntd": 300},
            ]
            cursor.execute("SELECT amount_due_ntd,status FROM client_obligations WHERE obligation_identity='refund:C-1'")
            assert cursor.fetchone() == {"amount_due_ntd": 300, "status": "open"}
    finally:
        connection.close()


def test_mismatched_refund_return_remains_manual_review_without_partial_writes(tmp_path):
    bootstrap(_arguments())
    _seed_open_refund_obligation()
    _post_manual_refund(tmp_path)
    _ingest_unresolved_taishin_inflow(tmp_path, amount=299)
    _deliver_finance_import_outbox()

    from api.dependencies.finance_import import build_finance_import_application
    from domains.finance_import.correction import FinanceImportCorrectionSelection
    from domains.finance_import.planning import FinanceClassificationType
    from infrastructure.mysql.finance_import_owning_domain_composite import MySqlFinanceImportOwningDomainComposite
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import CorrelationId
    from subsystems.finance_import.correction_workflow import FinanceImportCorrectionWorkflowError

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM client_ledger_entries WHERE entry_type='refund'")
            ledger_id = str(cursor.fetchone()["id"])
        application = build_finance_import_application(connection, MySqlFinanceImportOwningDomainComposite(connection))
        selection = FinanceImportCorrectionSelection(
            "finance-import-row:2", FinanceClassificationType.CLIENT_REFUND_RETURN,
            ("refund:C-1",), "returned amount does not equal original refund",
            ("bank-statement:return-line", "refund-ledger:" + ledger_id), ledger_id,
        )
        with pytest.raises(FinanceImportCorrectionWorkflowError) as error:
            application.preview_correction(selection, CorrelationId("lu-test-refund-return-mismatch"))
        assert error.value.error.code == "allocation_not_exact"
        with connection.cursor() as cursor:
            cursor.execute("SELECT entry_type FROM client_ledger_entries ORDER BY id")
            assert cursor.fetchall() == [{"entry_type": "refund"}]
            cursor.execute("SELECT reconciliation_status FROM finance_import_rows WHERE id=2")
            assert cursor.fetchone() == {"reconciliation_status": "pending"}
            cursor.execute("SELECT predicate_active,workflow_status FROM anomaly_current_alerts WHERE definition_code='finance_import_manual_review'")
            assert {tuple(row.values()) for row in cursor.fetchall()} >= {(1, "open")}
    finally:
        connection.close()


def test_g12_failed_correction_rolls_back_then_retries_exactly_once(tmp_path):
    bootstrap(_arguments())
    _seed_open_refund_obligation()
    _ingest_unresolved_taishin_outflow(tmp_path)
    _deliver_finance_import_outbox()

    from api.dependencies.finance_import import build_finance_import_application
    from domains.finance_import.correction import FinanceImportCorrectionSelection
    from domains.finance_import.planning import FinanceClassificationType
    from infrastructure.mysql.finance_import_owning_domain_composite import MySqlFinanceImportOwningDomainComposite
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.finance_import.correction_workflow import FinanceImportCorrectionApplyRequest, FinanceImportCorrectionWorkflowError

    selection = FinanceImportCorrectionSelection(
        "finance-import-row:1", FinanceClassificationType.CLIENT_REFUND,
        ("refund:C-1",), "verified customer refund", ("bank-statement:line-3",),
    )
    connection = get_connection()
    try:
        failed_application = build_finance_import_application(connection, _FailingPostingPort())
        preview = failed_application.preview_correction(selection, CorrelationId("g12-failed-preview"))
        failed_request = _correction_request(selection, preview, "g12-retry-key", "g12-failed-apply")
        with pytest.raises(FinanceImportCorrectionWorkflowError) as error:
            failed_application.correct_and_post(failed_request)
        assert error.value.error.code == "transaction_failed"
        _assert_g12_rollback_state(connection)

        application = build_finance_import_application(connection, MySqlFinanceImportOwningDomainComposite(connection))
        retry_preview = application.preview_correction(selection, CorrelationId("g12-retry-preview"))
        receipt = application.correct_and_post(
            _correction_request(selection, retry_preview, "g12-retry-key", "g12-retry-apply")
        )
        assert application.correct_and_post(
            _correction_request(selection, retry_preview, "g12-retry-key", "g12-retry-apply")
        ) == receipt
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM client_ledger_entries")
            assert cursor.fetchone() == {"count": 1}
            cursor.execute("SELECT COUNT(*) AS count FROM finance_import_correction_receipts")
            assert cursor.fetchone() == {"count": 1}
            cursor.execute("SELECT COUNT(*) AS count FROM finance_import_classification_events")
            assert cursor.fetchone() == {"count": 2}
    finally:
        connection.close()


@pytest.mark.parametrize(
    "failure_point",
    (
        "append_manual_classification",
        "post",
        "append_reconciliation_receipt",
        "append_alert_resolved_event",
        "append_outbox",
        "advance_batch_version",
        "save_correction_receipt",
    ),
)
def test_g08_each_finance_correction_persistence_failure_rolls_back(tmp_path, failure_point):
    """Every correction persistence seam shares the same outer MySQL rollback."""
    bootstrap(_arguments())
    _seed_open_refund_obligation()
    _ingest_unresolved_taishin_outflow(tmp_path)
    _deliver_finance_import_outbox()

    from domains.finance_import.correction import FinanceImportCorrectionSelection
    from domains.finance_import.planning import FinanceClassificationType
    from infrastructure.mysql.finance_import_owning_domain_composite import MySqlFinanceImportOwningDomainComposite
    from infrastructure.mysql.finance_import_repository import FinanceImportMySqlUnitOfWork, MySqlFinanceImportRepository
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import CorrelationId
    from subsystems.finance_import.correction_workflow import FinanceImportCorrectionWorkflow, FinanceImportCorrectionWorkflowError

    selection = FinanceImportCorrectionSelection(
        "finance-import-row:1", FinanceClassificationType.CLIENT_REFUND,
        ("refund:C-1",), "G08 persistence fault", ("bank-statement:line-3",),
    )
    connection = get_connection()
    try:
        repository = _FailAtCorrectionPersistence(
            MySqlFinanceImportRepository(connection), failure_point,
        )
        composite = MySqlFinanceImportOwningDomainComposite(connection)
        posting_port = _FailAfterPosting(composite) if failure_point == "post" else composite
        workflow = FinanceImportCorrectionWorkflow(
            repository,
            posting_port,
            lambda: FinanceImportMySqlUnitOfWork(connection),
        )
        preview = workflow.preview(selection, CorrelationId(f"g08-{failure_point}-preview"))
        request = _correction_request(
            selection,
            preview,
            f"g08-{failure_point}",
            f"g08-{failure_point}-apply",
        )
        composite.bind_request(request)
        try:
            with pytest.raises(FinanceImportCorrectionWorkflowError) as error:
                workflow.correct_and_post(request)
        finally:
            composite.clear_request()
        assert error.value.error.code == "transaction_failed"
        _assert_g08_no_partial_correction_commit(connection)
    finally:
        connection.close()


def test_g11_ordinary_finance_review_acknowledges_owner_outbox_without_legacy_projection(tmp_path):
    bootstrap(_arguments())
    receipt = _ingest_unresolved_taishin_outflow(tmp_path)
    replay = _ingest_unresolved_taishin_outflow(tmp_path)
    assert replay == receipt
    _deliver_finance_import_outbox()

    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM anomaly_current_alerts "
                "WHERE definition_code='finance_import_manual_review'"
            )
            assert cursor.fetchone() == {"count": 0}
            cursor.execute("SELECT COUNT(*) AS count FROM finance_import_outbox")
            assert cursor.fetchone() == {"count": 1}
            cursor.execute("SELECT COUNT(*) AS count FROM finance_import_apply_receipts")
            assert cursor.fetchone() == {"count": 0}
            cursor.execute(
                "SELECT COUNT(*) AS count FROM import_warning_occurrences "
                "WHERE owning_lane='finance_import'"
            )
            assert cursor.fetchone() == {"count": 0}
    finally:
        connection.close()


def test_finance_final_dispatch_acknowledges_without_legacy_warning_mutation(tmp_path):
    bootstrap(_arguments())
    _ingest_unresolved_taishin_outflow(tmp_path)
    _deliver_finance_import_outbox()

    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO finance_import_outbox "
                "(batch_id,intent_key,intent_type,payload_snapshot) "
                "VALUES (1,'lu-test-final-dispatch','dispatch_completed',%s)",
                (
                    '{"batch_identity":"finance-import-batch:1",'
                    '"results":[{"row_identity":"finance-import-row:1",'
                    '"outcome":"existing"}]}',
                ),
            )
        connection.commit()
    finally:
        connection.close()

    _deliver_finance_import_outbox()
    _deliver_finance_import_outbox()
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT status FROM finance_import_outbox "
                "WHERE intent_key='lu-test-final-dispatch'"
            )
            assert cursor.fetchone() == {"status": "delivered"}
            cursor.execute(
                "SELECT COUNT(*) AS count FROM import_warning_occurrences "
                "WHERE owning_lane='finance_import'"
            )
            assert cursor.fetchone() == {"count": 0}
    finally:
        connection.close()


def test_real_taishin_subsidy_payout_advances_then_recovers_after_government_allocation(tmp_path):
    bootstrap(_arguments())
    _seed_open_subsidy_return_with_claim_link()
    receipt = _ingest_unresolved_taishin_outflow(tmp_path, amount=6000)
    _deliver_finance_import_outbox()

    from api.dependencies.finance_import import build_finance_import_application
    from domains.finance_import.correction import FinanceImportCorrectionSelection
    from domains.finance_import.planning import FinanceClassificationType
    from infrastructure.mysql.finance_import_owning_domain_composite import MySqlFinanceImportOwningDomainComposite
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.finance_import.correction_workflow import FinanceImportCorrectionApplyRequest

    connection = get_connection()
    try:
        application = build_finance_import_application(
            connection,
            MySqlFinanceImportOwningDomainComposite(connection),
        )
        selection = FinanceImportCorrectionSelection(
            "finance-import-row:1",
            FinanceClassificationType.CLIENT_SUBSIDY_RETURN,
            ("subsidy:C-ADV",),
            "verified subsidy claim has not received a government allocation",
            ("bank-statement:line-3", "subsidy-claim-item:C-ADV"),
        )
        preview = application.preview_correction(
            selection,
            CorrelationId("lu-test-subsidy-advance-preview"),
        )
        posted = application.correct_and_post(
            FinanceImportCorrectionApplyRequest(
                selection,
                ExpectedVersion(preview.batch_version),
                ExpectedVersion(preview.canonical_fact_version),
                ExpectedVersion(preview.alert_version),
                preview.fingerprint,
                IdempotencyKey("lu-test-subsidy-advance-correction"),
                ActorContext("lu-test-runner"),
                CorrelationId("lu-test-subsidy-advance-apply"),
            )
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT entry_type,amount_ntd FROM client_ledger_entries")
            assert cursor.fetchone() == {"entry_type": "subsidy_advance", "amount_ntd": 6000}
            cursor.execute("SELECT amount_due_ntd,status FROM client_obligations WHERE obligation_identity='subsidy:C-ADV'")
            assert cursor.fetchone() == {"amount_due_ntd": 0, "status": "settled"}
    finally:
        connection.close()

    assert posted.ledger_entry_count == posted.allocation_count == 1
    _append_full_government_receipt_allocation()
    _deliver_subsidy_advance_recovery()
    _assert_subsidy_advance_was_recovered_without_second_payout()


def _seed_open_subsidy_return_with_claim_link() -> None:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO clients(case_no,name) VALUES ('C-ADV','Advance Client')")
            client_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO orders(case_no,client_id,status,actual_end_date) VALUES ('C-ADV',%s,'訂單完成','2026-01-31')", (client_id,))
            cursor.execute("INSERT INTO staff(name) VALUES ('Advance Staff')")
            staff_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO case_staff_assignments(case_no,staff_id,assignment_sequence,status) VALUES ('C-ADV',%s,1,'completed')", (staff_id,))
            assignment_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,before_due_date,after_due_date,source_event_identity,source_obligation_identity,expected_account_version,idempotency_key,actor,reason) VALUES ('subsidy:C-ADV','C-ADV','subsidy_return','payable_to_client','established',0,6000,NULL,'2026-03-15','lu-test-subsidy-root',NULL,0,'lu-test-subsidy-root','lu-test-runner','fixture root fact')")
            event_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,source_obligation_identity,amount_due_ntd,due_date,status,current_event_id,projection_version) VALUES ('subsidy:C-ADV','C-ADV','subsidy_return','payable_to_client',NULL,6000,'2026-03-15','open',%s,0)", (event_id,))
            cursor.execute("INSERT INTO subsidy_claim_batches(application_year,quarter,revision,status,requested_amount,approved_amount,paid_amount,submitted_at,approved_at) VALUES (2026,1,1,'approved',6000,6000,0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
            batch_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO subsidy_claim_batch_items(batch_id,case_no,assignment_id,staff_id,requested_amount,approved_amount) VALUES (%s,'C-ADV',%s,%s,6000,6000)", (batch_id, assignment_id, staff_id))
            claim_item_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO client_subsidy_return_claim_item_links(obligation_identity,claim_item_id,entitled_amount_ntd) VALUES ('subsidy:C-ADV',%s,6000)", (claim_item_id,))
        connection.commit()
    finally:
        connection.close()


def _append_full_government_receipt_allocation() -> None:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM subsidy_claim_batches")
            batch_id = int(cursor.fetchone()["id"])
            cursor.execute("SELECT id FROM subsidy_claim_batch_items")
            claim_item_id = int(cursor.fetchone()["id"])
            incoming_row_id = _insert_finance_row(cursor, "b", "incoming", "2026-04-01", credit=6000)
            cursor.execute("INSERT INTO government_subsidy_transactions(claim_batch_id,finance_import_row_id,transaction_type,transaction_status,amount,occurred_at,external_reference) VALUES (%s,%s,'receipt','succeeded',6000,'2026-04-01','lu-test-government-receipt')", (batch_id, incoming_row_id))
            transaction_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO government_subsidy_allocations(transaction_id,claim_batch_id,claim_item_id,allocation_type,allocated_amount) VALUES (%s,%s,%s,'receipt',6000)", (transaction_id, batch_id, claim_item_id))
            cursor.execute("INSERT INTO government_subsidy_batch_accounts(batch_id,aggregate_version,requested_total_ntd,approved_total_ntd,net_allocated_ntd,outstanding_ntd,status) VALUES (%s,1,6000,6000,6000,0,'paid')", (batch_id,))
            cursor.execute("INSERT INTO government_subsidy_projection_events(batch_id,transaction_id,before_status,after_status,before_net_allocated_ntd,after_net_allocated_ntd,outstanding_ntd,expected_batch_version,resulting_batch_version,preview_fingerprint,actor,reason,idempotency_key) VALUES (%s,%s,'approved','paid',0,6000,0,0,1,%s,'lu-test-runner','fixture receipt','lu-test-projection')", (batch_id, transaction_id, "c" * 64))
            projection_event_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO government_subsidy_outbox(batch_id,transaction_id,projection_event_id,intent_key,intent_type,payload_snapshot) VALUES (%s,%s,%s,'lu-test-subsidy-allocation','government_subsidy_receipt_allocated',%s)", (batch_id, transaction_id, projection_event_id, '{"transaction_id":' + str(transaction_id) + ',"allocations":[{"claim_item_id":' + str(claim_item_id) + ',"case_no":"C-ADV","amount_ntd":6000}]}'))
        connection.commit()
    finally:
        connection.close()


def _deliver_subsidy_advance_recovery() -> None:
    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.subsidy_advance_recovery_repository import MySqlSubsidyAdvanceRecoveryRepository
    from subsystems.government_subsidy.subsidy_advance_outbox_consumer import (
        consume_government_subsidy_advance_events,
    )

    connection = get_connection()
    try:
        assert consume_government_subsidy_advance_events(
            connection, MySqlSubsidyAdvanceRecoveryRepository
        ) == (1, 0)
    finally:
        connection.close()


def _assert_subsidy_advance_was_recovered_without_second_payout() -> None:
    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.subsidy_advance_recovery_repository import MySqlSubsidyAdvanceRecoveryRepository

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT entry_type,amount_ntd FROM client_ledger_entries ORDER BY id")
            assert cursor.fetchall() == [{"entry_type": "subsidy_advance", "amount_ntd": 6000}]
            cursor.execute("SELECT recovered_amount_ntd FROM client_subsidy_advance_recoveries")
            assert cursor.fetchone() == {"recovered_amount_ntd": 6000}
    finally:
        connection.close()


def test_government_receipt_recovers_existing_subsidy_advance_without_second_client_payout():
    bootstrap(_arguments())
    _seed_subsidy_advance_recovery_facts()

    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.subsidy_advance_recovery_repository import (
        MySqlSubsidyAdvanceRecoveryRepository,
    )
    from subsystems.government_subsidy.subsidy_advance_outbox_consumer import (
        consume_government_subsidy_advance_events,
    )

    connection = get_connection()
    try:
        assert consume_government_subsidy_advance_events(
            connection, MySqlSubsidyAdvanceRecoveryRepository
        ) == (1, 0)
        with connection.cursor() as cursor:
            cursor.execute("SELECT entry_type,amount_ntd FROM client_ledger_entries ORDER BY id")
            assert cursor.fetchall() == [{"entry_type": "subsidy_advance", "amount_ntd": 6000}]
            cursor.execute("SELECT recovered_amount_ntd FROM client_subsidy_advance_recoveries")
            assert cursor.fetchone() == {"recovered_amount_ntd": 6000}
            cursor.execute("SELECT status FROM government_subsidy_outbox")
            assert cursor.fetchone() == {"status": "delivered"}
    finally:
        connection.close()


def test_partial_government_subsidy_allocation_creates_review_without_auto_netting():
    bootstrap(_arguments())
    _seed_subsidy_advance_recovery_facts(government_allocation_amount=5000)

    from infrastructure.mysql.mysql_adapter import get_connection
    from infrastructure.mysql.subsidy_advance_recovery_repository import MySqlSubsidyAdvanceRecoveryRepository
    from subsystems.government_subsidy.subsidy_advance_outbox_consumer import (
        consume_government_subsidy_advance_events,
    )

    connection = get_connection()
    try:
        assert consume_government_subsidy_advance_events(
            connection, MySqlSubsidyAdvanceRecoveryRepository
        ) == (1, 0)
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM client_subsidy_advance_recoveries")
            assert cursor.fetchone() == {"count": 0}
            cursor.execute("SELECT intent_type,payload_snapshot FROM client_finance_outbox")
            anomaly = cursor.fetchone()
            assert anomaly["intent_type"] == "anomaly_review_required"
            assert "subsidy_advance_settlement_ambiguous" in anomaly["payload_snapshot"]
            cursor.execute("SELECT entry_type,amount_ntd FROM client_ledger_entries ORDER BY id")
            assert cursor.fetchall() == [{"entry_type": "subsidy_advance", "amount_ntd": 6000}]
    finally:
        connection.close()


def _seed_subsidy_advance_recovery_facts(*, government_allocation_amount=6000) -> None:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO clients(case_no,name) VALUES ('C-ADV','Advance Client')")
            client_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO orders(case_no,client_id,status,actual_end_date) VALUES ('C-ADV',%s,'訂單完成','2026-01-31')", (client_id,))
            cursor.execute("INSERT INTO staff(name) VALUES ('Advance Staff')")
            staff_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO case_staff_assignments(case_no,staff_id,assignment_sequence,status) VALUES ('C-ADV',%s,1,'completed')", (staff_id,))
            assignment_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,before_due_date,after_due_date,source_event_identity,source_obligation_identity,expected_account_version,idempotency_key,actor,reason) VALUES ('subsidy:C-ADV','C-ADV','subsidy_return','payable_to_client','established',0,6000,NULL,'2026-03-15','lu-test-subsidy-root',NULL,0,'lu-test-subsidy-root','lu-test-runner','fixture root fact')")
            event_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,source_obligation_identity,amount_due_ntd,due_date,status,current_event_id,projection_version) VALUES ('subsidy:C-ADV','C-ADV','subsidy_return','payable_to_client',NULL,0,'2026-03-15','settled',%s,1)", (event_id,))
            outgoing_row_id = _insert_finance_row(cursor, "a", "outgoing", "2026-03-15", debit=6000)
            cursor.execute("INSERT INTO client_ledger_entries(case_no,finance_import_row_id,entry_type,amount_ntd,occurred_on,reconciliation_reference,idempotency_key,actor,reason) VALUES ('C-ADV',%s,'subsidy_advance',6000,'2026-03-15','lu-test-subsidy-advance','lu-test-subsidy-advance','lu-test-runner','fixture advance')", (outgoing_row_id,))
            advance_entry_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO client_ledger_obligation_allocations(ledger_entry_id,obligation_identity,amount_ntd,allocation_ordinal) VALUES (%s,'subsidy:C-ADV',6000,1)", (advance_entry_id,))
            cursor.execute("INSERT INTO subsidy_claim_batches(application_year,quarter,revision,status,requested_amount,approved_amount,paid_amount,submitted_at,approved_at) VALUES (2026,1,1,'approved',6000,6000,0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)")
            batch_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO subsidy_claim_batch_items(batch_id,case_no,assignment_id,staff_id,requested_amount,approved_amount) VALUES (%s,'C-ADV',%s,%s,6000,6000)", (batch_id, assignment_id, staff_id))
            claim_item_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO client_subsidy_return_claim_item_links(obligation_identity,claim_item_id,entitled_amount_ntd) VALUES ('subsidy:C-ADV',%s,6000)", (claim_item_id,))
            incoming_row_id = _insert_finance_row(cursor, "b", "incoming", "2026-04-01", credit=6000)
            cursor.execute("INSERT INTO government_subsidy_transactions(claim_batch_id,finance_import_row_id,transaction_type,transaction_status,amount,occurred_at,external_reference) VALUES (%s,%s,'receipt','succeeded',%s,'2026-04-01','lu-test-government-receipt')", (batch_id, incoming_row_id, government_allocation_amount))
            transaction_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO government_subsidy_allocations(transaction_id,claim_batch_id,claim_item_id,allocation_type,allocated_amount) VALUES (%s,%s,%s,'receipt',%s)", (transaction_id, batch_id, claim_item_id, government_allocation_amount))
            cursor.execute("INSERT INTO government_subsidy_batch_accounts(batch_id,aggregate_version,requested_total_ntd,approved_total_ntd,net_allocated_ntd,outstanding_ntd,status) VALUES (%s,1,6000,6000,%s,%s,%s)", (batch_id, government_allocation_amount, 6000 - government_allocation_amount, "paid" if government_allocation_amount == 6000 else "partially_paid"))
            cursor.execute("INSERT INTO government_subsidy_projection_events(batch_id,transaction_id,before_status,after_status,before_net_allocated_ntd,after_net_allocated_ntd,outstanding_ntd,expected_batch_version,resulting_batch_version,preview_fingerprint,actor,reason,idempotency_key) VALUES (%s,%s,'approved',%s,0,%s,%s,0,1,%s,'lu-test-runner','fixture receipt','lu-test-projection')", (batch_id, transaction_id, "paid" if government_allocation_amount == 6000 else "partially_paid", government_allocation_amount, 6000 - government_allocation_amount, "c" * 64))
            projection_event_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO government_subsidy_outbox(batch_id,transaction_id,projection_event_id,intent_key,intent_type,payload_snapshot) VALUES (%s,%s,%s,'lu-test-subsidy-allocation','government_subsidy_receipt_allocated',%s)", (batch_id, transaction_id, projection_event_id, '{"transaction_id":' + str(transaction_id) + ',"allocations":[{"claim_item_id":' + str(claim_item_id) + ',"case_no":"C-ADV","amount_ntd":' + str(government_allocation_amount) + '}]}'))
        connection.commit()
    finally:
        connection.close()


def _insert_finance_row(cursor, suffix: str, direction: str, transaction_date: str, *, debit=0, credit=0) -> int:
    cursor.execute("INSERT INTO finance_import_rows(dedup_fingerprint,format_id,transaction_date,debit,credit,direction,bank_references,warnings,raw_payload) VALUES (%s,'taishin',%s,%s,%s,%s,JSON_OBJECT(),JSON_ARRAY(),JSON_OBJECT())", (suffix * 64, transaction_date, debit or None, credit or None, direction))
    return int(cursor.lastrowid)


def _seed_open_refund_obligation() -> None:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            synthetic_account = "9" * 16
            cursor.execute("INSERT INTO clients(case_no,name) VALUES ('C-1','E2E Client')")
            client_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO beclass_records(query_no,refund_bank_code,refund_account_no) "
                "VALUES ('C-1','synthetic-bank',%s)",
                (synthetic_account,),
            )
            cursor.execute("INSERT INTO orders(case_no,client_id,status) VALUES ('C-1',%s,'訂單完成')", (client_id,))
            cursor.execute("INSERT INTO client_obligation_events(obligation_identity,case_no,obligation_type,direction,event_type,before_amount_ntd,after_amount_ntd,before_due_date,after_due_date,source_event_identity,source_obligation_identity,expected_account_version,idempotency_key,actor,reason) VALUES ('refund:C-1','C-1','refund','payable_to_client','established',0,300,NULL,'2026-08-15','lu-test-refund-root',NULL,0,'lu-test-refund-root','lu-test-runner','fixture root fact')")
            event_id = int(cursor.lastrowid)
            cursor.execute("INSERT INTO client_obligations(obligation_identity,case_no,obligation_type,direction,source_obligation_identity,amount_due_ntd,due_date,status,current_event_id,projection_version) VALUES ('refund:C-1','C-1','refund','payable_to_client',NULL,300,'2026-08-15','open',%s,0)", (event_id,))
            cursor.execute(
                "INSERT INTO client_refund_recipient_snapshots "
                "(refund_obligation_identity,case_no,bank_code,bank_account,source_kind) "
                "VALUES ('refund:C-1','C-1','synthetic-bank',%s,'test-fixture')",
                (synthetic_account,),
            )
        connection.commit()
    finally:
        connection.close()


def _ingest_unresolved_taishin_outflow(tmp_path, *, amount=300):
    workbook = tmp_path / "taishin-manual-refund.xlsx"
    if not workbook.exists():
        pd.DataFrame(
            [["說明"], ["序號", "交易日期", "交易時間", "帳務日期", "摘要", "支出金額", "存入金額", "帳戶餘額", "備註"], ["0001", "2026/08/04", "09:08:07", "2026/08/04", "轉帳", str(amount), "", "9000", "客戶退款 " + ("9" * 16)]]
        ).to_excel(workbook, sheet_name="交易明細", index=False, header=False)
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import ActorContext, IdempotencyKey
    from subsystems.finance_import.ingestion import ingest_finance_workbook
    return ingest_finance_workbook(str(workbook), IdempotencyKey("lu-test-manual-refund-ingest"), ActorContext("lu-test-runner"), connection_factory=get_connection, normalizer=normalize_workbook)


def _post_manual_refund(tmp_path):
    receipt = _ingest_unresolved_taishin_outflow(tmp_path)
    _deliver_finance_import_outbox()
    from api.dependencies.finance_import import build_finance_import_application
    from domains.finance_import.correction import FinanceImportCorrectionSelection
    from domains.finance_import.planning import FinanceClassificationType
    from infrastructure.mysql.finance_import_owning_domain_composite import MySqlFinanceImportOwningDomainComposite
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.finance_import.correction_workflow import FinanceImportCorrectionApplyRequest
    connection = get_connection()
    try:
        application = build_finance_import_application(connection, MySqlFinanceImportOwningDomainComposite(connection))
        selection = FinanceImportCorrectionSelection("finance-import-row:1", FinanceClassificationType.CLIENT_REFUND, ("refund:C-1",), "refund verified", ("bank-statement:line-3",))
        preview = application.preview_correction(selection, CorrelationId("lu-test-refund-preview"))
        application.correct_and_post(FinanceImportCorrectionApplyRequest(selection, ExpectedVersion(preview.batch_version), ExpectedVersion(preview.canonical_fact_version), ExpectedVersion(preview.alert_version), preview.fingerprint, IdempotencyKey("lu-test-refund-post"), ActorContext("lu-test-runner"), CorrelationId("lu-test-refund-apply")))
    finally:
        connection.close()
    return receipt


def _ingest_unresolved_taishin_inflow(tmp_path, *, amount=300):
    workbook = tmp_path / "taishin-refund-return.xlsx"
    pd.DataFrame([["說明"], ["序號", "交易日期", "交易時間", "帳務日期", "摘要", "支出金額", "存入金額", "帳戶餘額", "備註"], ["0002", "2026/08/05", "09:08:07", "2026/08/05", "退款退回", "", str(amount), str(9000 + amount), "客戶退款退回"]]).to_excel(workbook, sheet_name="交易明細", index=False, header=False)
    from infrastructure.mysql.mysql_adapter import get_connection
    from shared_kernel.identities import ActorContext, IdempotencyKey
    from subsystems.finance_import.ingestion import ingest_finance_workbook
    return ingest_finance_workbook(str(workbook), IdempotencyKey("lu-test-refund-return-ingest"), ActorContext("lu-test-runner"), connection_factory=get_connection, normalizer=normalize_workbook)


def _correction_request(selection, preview, idempotency_key, correlation_id):
    from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
    from subsystems.finance_import.correction_workflow import FinanceImportCorrectionApplyRequest
    return FinanceImportCorrectionApplyRequest(
        selection, ExpectedVersion(preview.batch_version), ExpectedVersion(preview.canonical_fact_version),
        ExpectedVersion(preview.alert_version), preview.fingerprint, IdempotencyKey(idempotency_key),
        ActorContext("admin_user_id:1"), CorrelationId(correlation_id),
    )


def _assert_g12_rollback_state(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS count FROM client_ledger_entries")
        assert cursor.fetchone() == {"count": 0}
        cursor.execute("SELECT COUNT(*) AS count FROM client_ledger_obligation_allocations")
        assert cursor.fetchone() == {"count": 0}
        cursor.execute("SELECT COUNT(*) AS count FROM finance_import_correction_receipts")
        assert cursor.fetchone() == {"count": 0}
        cursor.execute("SELECT COUNT(*) AS count FROM finance_import_classification_events")
        assert cursor.fetchone() == {"count": 1}
        cursor.execute("SELECT predicate_active,workflow_status FROM anomaly_current_alerts WHERE definition_code='finance_import_manual_review'")
        assert cursor.fetchone() == {"predicate_active": 1, "workflow_status": "open"}


def _assert_g08_no_partial_correction_commit(connection):
    _assert_g12_rollback_state(connection)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS count FROM finance_import_outbox "
            "WHERE intent_type='manual_correction_completed'"
        )
        assert cursor.fetchone() == {"count": 0}
        cursor.execute(
            "SELECT batch_version FROM finance_import_batch_contracts"
        )
        assert cursor.fetchone() == {"batch_version": 0}


class _FailAtCorrectionPersistence:
    def __init__(self, repository, failure_point):
        self._repository = repository
        self._failure_point = failure_point

    def __getattr__(self, name):
        if name == self._failure_point:
            return self._raise_persistence_failure
        return getattr(self._repository, name)

    def _raise_persistence_failure(self, *_args, **_kwargs):
        raise RuntimeError(f"injected failure at {self._failure_point}")


class _FailAfterPosting:
    def __init__(self, posting_port):
        self._posting_port = posting_port

    def post(self, candidate):
        self._posting_port.post(candidate)
        raise RuntimeError("injected failure after owning Domain posting")


class _FailingPostingPort:
    def bind_request(self, request):
        del request

    def clear_request(self):
        return None

    def resolve(self, candidate):
        return candidate

    def post(self, candidate):
        del candidate
        raise RuntimeError("injected owning-domain failure")


def _deliver_finance_import_outbox() -> None:
    from infrastructure.mysql.anomaly_runtime import build_anomaly_runtime
    from infrastructure.mysql.mysql_adapter import get_connection
    from subsystems.finance_import.finance_import_anomaly_consumer import consume_finance_import_anomaly_events
    connection = get_connection()
    try:
        result = consume_finance_import_anomaly_events(
            connection, runtime=build_anomaly_runtime()
        )
        assert result.failed_count == 0
    finally:
        connection.close()


def _assert_manual_review_alert_remains_active_without_owner_terminal_contract() -> None:
    from infrastructure.mysql.mysql_adapter import get_connection
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT predicate_active,workflow_status FROM anomaly_current_alerts WHERE definition_code='finance_import_manual_review'")
            assert cursor.fetchone() == {"predicate_active": 1, "workflow_status": "open"}
    finally:
        connection.close()


def _assert_manual_review_warning_remains_open() -> None:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT task.tracking_status,task.tracking_version "
                "FROM import_warning_current_tasks task "
                "JOIN import_warning_occurrences occurrence "
                "ON occurrence.id=task.occurrence_id "
                "WHERE occurrence.owning_lane='finance_import' "
                "AND occurrence.logical_code='FINANCE-ROW-001'"
            )
            assert cursor.fetchone() == {
                "tracking_status": "open",
                "tracking_version": 1,
            }
            cursor.execute(
                "SELECT event.action,event.actor_kind,event.reason_code "
                "FROM import_warning_tracking_events event "
                "JOIN import_warning_occurrences occurrence "
                "ON occurrence.id=event.occurrence_id "
                "WHERE occurrence.owning_lane='finance_import' "
                "ORDER BY event.resulting_version"
            )
            assert cursor.fetchall() == [
                {
                    "action": "opened",
                    "actor_kind": "system",
                    "reason_code": "source_review_opened",
                }
            ]
            cursor.execute(
                "SELECT COUNT(*) AS count FROM import_warning_tracking_receipts "
                "WHERE occurrence_id=(SELECT id FROM import_warning_occurrences "
                "WHERE owning_lane='finance_import' AND logical_code='FINANCE-ROW-001')"
            )
            assert cursor.fetchone() == {"count": 0}
            cursor.execute(
                "SELECT COUNT(*) AS count FROM import_warning_tracking_outbox outbox "
                "JOIN import_warning_tracking_events event "
                "ON event.id=outbox.tracking_event_id "
                "WHERE event.action='auto_resolved'"
            )
            assert cursor.fetchone() == {"count": 0}
    finally:
        connection.close()
