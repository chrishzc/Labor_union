"""
File: test_wp77_disposable_mysql_e2e.py
Description: 以明確 disposable MySQL 驗證 Staff adoption receipt與HCM review/outbox原子性。
"""

from __future__ import annotations

import hashlib
import os
from uuid import uuid4

import pytest

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.beclass_import_review_anomaly_source import (
    project_beclass_import_review_page,
)
from subsystems.case_import.beclass_review_intake import record_invalid_beclass_row
from domains.case_import.beclass_import_review import BeClassImportSourceKind
from subsystems.case_import.hcm_import_review_intake import record_hcm_import_review
from subsystems.case_import.staff_historical_adoption import adopt_existing_staff


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE or os.getenv("DB_DATABASE") != DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def test_staff_existing_identity_fills_blank_and_replays_receipt():
    token = uuid4().hex
    identity_card = f"A{int(token[:9], 16) % 1_000_000_000:09d}"
    digest = hashlib.sha256(token.encode()).hexdigest()
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO staff (name,identity_card,email,status) VALUES (%s,%s,%s,'active')",
                ("WP77測試", identity_card, "current@example.test"),
            )
            staff_id = int(cursor.lastrowid)
        connection.commit()
        record = {
            "name": "WP77測試",
            "identity_card": identity_card,
            "phone": "0912345678",
            "email": "historical@example.test",
            "status": "active",
        }

        first = adopt_existing_staff(
            connection,
            source_content_digest=digest,
            source_row=2,
            identity_card=identity_card,
            historical_record=record,
            source_sheet="任意資料頁",
            review_payload=record,
        )
        replay = adopt_existing_staff(
            connection,
            source_content_digest=digest,
            source_row=2,
            identity_card=identity_card,
            historical_record=record,
            source_sheet="任意資料頁",
            review_payload=record,
        )

        assert first.outcome == "adopted_existing"
        assert first.staff_id == staff_id
        assert first.changed_fields == ("phone",)
        assert first.conflict_fields == ("email",)
        assert replay.replayed is True
        _assert_staff_adoption_rows(connection, staff_id)
    finally:
        connection.close()


def test_hcm_invalid_row_creates_root_and_outbox_then_exactly_replays():
    digest = hashlib.sha256(uuid4().bytes).hexdigest()
    arguments = {
        "source_content_digest": digest,
        "source_sheet": "任意資料頁",
        "source_row": 3,
        "case_identity": "HCM-TEST-0003",
        "issue_codes": ("hcm_field_invalid:服務日期",),
        "evidence_snapshot": {"invalid_field_count": 1, "has_case_identity": True},
    }
    connection = get_connection()
    try:
        first = record_hcm_import_review(connection, **arguments)
        replay = record_hcm_import_review(connection, **arguments)

        assert replay == first
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM case_import_hcm_review_rows WHERE review_identity=%s",
                (first,),
            )
            assert int(cursor.fetchone()["count"]) == 1
            cursor.execute(
                "SELECT COUNT(*) AS count FROM case_import_hcm_review_outbox outbox "
                "JOIN case_import_hcm_review_rows root ON root.id=outbox.review_row_id "
                "WHERE root.review_identity=%s",
                (first,),
            )
            assert int(cursor.fetchone()["count"]) == 1
    finally:
        connection.close()


def test_beclass_review_root_rescan_rebuilds_missing_current_projection():
    digest = hashlib.sha256(uuid4().bytes).hexdigest()
    connection = get_connection()
    try:
        review_identity = record_invalid_beclass_row(
            connection,
            source_kind=BeClassImportSourceKind.STAFF,
            source_content_digest=digest,
            source_sheet="任意資料頁",
            source_row=7,
            masked_identifier="staff-***-0007",
            source_payload={"has_identity_card": True},
            issue_codes=("staff_field_invalid:銀行代號",),
        )
        source_event = f"beclass-review-rescan:{review_identity}:0:1"
        partition = f"IMPORT-001:{review_identity}"
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE beclass_import_review_outbox SET published_at=CURRENT_TIMESTAMP "
                "WHERE review_row_id=(SELECT id FROM beclass_import_review_rows "
                "WHERE review_identity=%s)",
                (review_identity,),
            )
            cursor.execute(
                "INSERT INTO anomaly_consumer_checkpoints "
                "(consumer_identity,partition_identity,source_event_identity,source_version,processed_at) "
                "VALUES ('beclass-import-anomaly-projector-v1',%s,%s,0,CURRENT_TIMESTAMP)",
                (partition, source_event),
            )
        connection.commit()

        cursor_after = 0
        while True:
            page = project_beclass_import_review_page(
                connection, after_review_row_id=cursor_after, limit=25
            )
            if page.next_review_row_id is None:
                break
            cursor_after = page.next_review_row_id

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM anomaly_current_alerts "
                "WHERE definition_code='IMPORT-001' AND source_identity=%s "
                "AND predicate_active=TRUE",
                (review_identity,),
            )
            assert cursor.fetchone() == {"count": 1}
    finally:
        connection.close()


def _assert_staff_adoption_rows(connection, staff_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT phone,email FROM staff WHERE id=%s", (staff_id,))
        staff = cursor.fetchone()
        assert staff == {"phone": "0912345678", "email": "current@example.test"}
        cursor.execute(
            "SELECT outcome,changed_fields FROM staff_historical_adoption_receipts WHERE staff_id=%s",
            (staff_id,),
        )
        receipt = cursor.fetchone()
        assert receipt["outcome"] == "adopted_existing"
        assert "phone" in str(receipt["changed_fields"])
