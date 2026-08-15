"""
File: test_import_warning_tracking_disposable_mysql_e2e.py
Description: 驗證隔離 MySQL 中匯入警示 event、receipt 與 outbox 的原子寫入。
"""

import os
from uuid import uuid4

import pytest

from domains.anomalies.import_warning_tracking import ImportWarningTrackingStatus
from infrastructure.mysql.import_warning_tracking_repository import MySqlImportWarningTrackingRepository
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.anomalies.import_warning_tracking_workflow import ImportWarningTrackingApplication, WarningTransitionRequest


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(not DATABASE or os.getenv("DB_DATABASE") != DATABASE, reason="requires an explicitly configured disposable lu_test_* MySQL database")


def test_apply_appends_event_receipt_and_outbox_once() -> None:
    connection = get_connection()
    identity = f"wp94-{uuid4().hex}"
    try:
        _seed(connection, identity)
        application = ImportWarningTrackingApplication(MySqlImportWarningTrackingRepository(connection), lambda: MySqlUnitOfWork(connection))
        request = WarningTransitionRequest(identity, 1, ImportWarningTrackingStatus.AWAITING_EXTERNAL_CONFIRMATION, ActorContext("operator-wp94"), "contact_started", None, None, IdempotencyKey(f"wp94-{uuid4().hex}"), CorrelationId(f"wp94-{uuid4().hex}"))

        receipt = application.apply(request)
        replay = application.apply(request)

        assert receipt == replay
        assert receipt.resulting_version == 2
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM import_warning_tracking_events WHERE occurrence_id=(SELECT id FROM import_warning_occurrences WHERE occurrence_identity=%s)", (identity,))
            assert cursor.fetchone()["count"] == 2
            cursor.execute("SELECT COUNT(*) AS count FROM import_warning_tracking_receipts WHERE idempotency_key=%s", (request.idempotency_key.value,))
            assert cursor.fetchone()["count"] == 1
            cursor.execute("SELECT COUNT(*) AS count FROM import_warning_tracking_outbox b JOIN import_warning_tracking_events e ON e.id=b.tracking_event_id JOIN import_warning_occurrences o ON o.id=e.occurrence_id WHERE o.occurrence_identity=%s", (identity,))
            assert cursor.fetchone()["count"] == 1
    finally:
        connection.close()


def _seed(connection, identity: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO import_warning_occurrences (occurrence_identity,owning_lane,source_kind,source_event_identity,logical_code,field_path,masked_subject,issue_codes,evidence_snapshot) VALUES (%s,'hcm','workbook',%s,'IMPORT-004','phone','masked',JSON_ARRAY('invalid_phone'),JSON_OBJECT())", (identity, f"source-{identity}"))
        occurrence_id = cursor.lastrowid
        cursor.execute("INSERT INTO import_warning_tracking_events (event_identity,occurrence_id,action,before_status,after_status,expected_version,resulting_version,actor_kind,actor_identity,reason_code,command_fingerprint,idempotency_key,correlation_id) VALUES (%s,%s,'opened',NULL,'open',0,1,'system','system','opened',%s,%s,%s)", (f"seed-{identity}", occurrence_id, "0" * 64, f"seed-key-{identity}", f"seed-correlation-{identity}"))
        event_id = cursor.lastrowid
        cursor.execute("INSERT INTO import_warning_current_tasks (occurrence_id,tracking_status,tracking_version,last_event_id) VALUES (%s,'open',1,%s)", (occurrence_id, event_id))
    connection.commit()
