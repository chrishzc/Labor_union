"""
File: test_wp77_disposable_mysql_e2e.py
Description: 以 disposable MySQL 驗證 Staff adoption、HCM／BeClass 警示與重試停損。
"""

from __future__ import annotations

import hashlib
import os
import time
from uuid import uuid4

import pytest

from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.anomaly_runtime import build_anomaly_runtime
from infrastructure.mysql.beclass_import_review_anomaly_source import (
    project_beclass_import_review_page,
)
from subsystems.case_import.beclass_import_outbox_consumer import (
    consume_beclass_import_review_events,
)
from subsystems.case_import.beclass_review_intake import record_invalid_beclass_row
from domains.case_import.beclass_import_review import BeClassImportSourceKind
from subsystems.case_import.hcm_import_review_intake import record_hcm_import_review
from subsystems.anomalies.hcm_import_review_outbox_consumer import (
    consume_hcm_import_review_events,
)
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


def test_newer_staff_snapshot_replaces_name_bank_relations_and_keeps_old_replay():
    token = uuid4().hex
    identity_card = f"B{int(token[:9], 16) % 1_000_000_000:09d}"
    old_digest = hashlib.sha256(f"old:{token}".encode()).hexdigest()
    new_digest = hashlib.sha256(f"new:{token}".encode()).hexdigest()
    old_bank = ("001", "0001", f"1{token[:11]}", True)
    new_bank = ("002", "0002", f"2{token[:11]}", True)
    old_record = _staff_snapshot(identity_card, "舊姓名", "2026-08-01 09:00:00")
    new_record = _staff_snapshot(identity_card, "新姓名", "2026-08-02 09:00:00")
    connection = get_connection()
    try:
        staff_id = _seed_staff_snapshot(connection, old_record, old_bank)
        old_result = _adopt_snapshot(
            connection, old_digest, 2, old_record, old_bank, "舊地區"
        )
        new_result = _adopt_snapshot(
            connection, new_digest, 3, new_record, new_bank, "新地區"
        )
        old_replay = _adopt_snapshot(
            connection, old_digest, 2, old_record, old_bank, "舊地區"
        )

        assert old_result.outcome == "adopted_existing"
        assert new_result.changed_fields == ("name", "registered_at")
        assert old_replay.replayed is True
        _assert_replaced_staff_snapshot(connection, staff_id, new_bank)
        projection = consume_beclass_import_review_events(
            connection,
            runtime=build_anomaly_runtime(),
        )
        assert projection.failed_count == 0
        _assert_staff_name_trace_review(connection)
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


def test_hcm_review_outbox_projects_field_warnings_and_replays_without_duplicates():
    digest = hashlib.sha256(uuid4().bytes).hexdigest()
    connection = get_connection()
    try:
        # 共用 disposable schema 可能含前序案例事件，先排空才只驗證本筆 review 投影。
        consume_hcm_import_review_events(connection)
        review_identity = record_hcm_import_review(
            connection,
            source_content_digest=digest,
            source_sheet="任意資料頁",
            source_row=8,
            case_identity="HCM-TEST-0008",
            issue_codes=(
                "hcm_field_missing:服務日期",
                "hcm_field_invalid:服務時間",
            ),
            evidence_snapshot={"invalid_field_count": 2, "has_case_identity": True},
        )

        first = consume_hcm_import_review_events(connection)
        replay = consume_hcm_import_review_events(connection)

        assert first.delivered_count == 1
        assert first.failed_count == 0
        assert replay.delivered_count == 0
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT logical_code,field_path,masked_subject,issue_codes,evidence_snapshot "
                "FROM import_warning_occurrences "
                "WHERE source_receipt_identity=%s ORDER BY field_path",
                (review_identity,),
            )
            warnings = cursor.fetchall()
            assert [(row["logical_code"], row["field_path"]) for row in warnings] == [
                ("HCM-FIELD-001", "服務日期"),
                ("HCM-FIELD-002", "服務時間"),
            ]
            assert all(row["masked_subject"] == "hcm-***-0008" for row in warnings)
            assert all("HCM-TEST-0008" not in str(row) for row in warnings)
            cursor.execute(
                "SELECT tracking_status,tracking_version FROM import_warning_current_tasks task "
                "JOIN import_warning_occurrences occurrence ON occurrence.id=task.occurrence_id "
                "WHERE occurrence.source_receipt_identity=%s ORDER BY occurrence.field_path",
                (review_identity,),
            )
            assert cursor.fetchall() == [
                {"tracking_status": "open", "tracking_version": 1},
                {"tracking_status": "open", "tracking_version": 1},
            ]
    finally:
        connection.close()


def test_hcm_row_below_import_threshold_is_audited_but_not_sent_to_anomaly_center():
    digest = hashlib.sha256(uuid4().bytes).hexdigest()
    connection = get_connection()
    try:
        consume_hcm_import_review_events(connection)
        review_identity = record_hcm_import_review(
            connection,
            source_content_digest=digest,
            source_sheet="任意資料頁",
            source_row=10,
            case_identity=None,
            issue_codes=("hcm_case_import:case_import_case_no_required",),
            evidence_snapshot={"has_case_identity": False},
        )

        result = consume_hcm_import_review_events(connection)

        assert result.delivered_count == 1
        assert result.failed_count == 0
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM import_warning_occurrences "
                "WHERE source_receipt_identity=%s",
                (review_identity,),
            )
            assert cursor.fetchone() == {"count": 0}
            cursor.execute(
                "SELECT COUNT(*) AS count FROM anomaly_current_alerts "
                "WHERE definition_code='IMPORT-004' AND source_identity=%s",
                (review_identity,),
            )
            assert cursor.fetchone() == {"count": 0}
            cursor.execute(
                "SELECT outbox.published_at,outbox.attempts,outbox.last_error "
                "FROM case_import_hcm_review_outbox outbox "
                "JOIN case_import_hcm_review_rows root ON root.id=outbox.review_row_id "
                "WHERE root.review_identity=%s",
                (review_identity,),
            )
            outbox = cursor.fetchone()
            assert outbox["published_at"] is not None
            assert outbox["attempts"] == 0
            assert outbox["last_error"] is None
    finally:
        connection.close()


def test_hcm_unknown_issue_retries_then_dead_letters_without_partial_warning():
    digest = hashlib.sha256(uuid4().bytes).hexdigest()
    raw_issue = "future_hcm_state:完整姓名不得寫入錯誤"
    connection = get_connection()
    try:
        consume_hcm_import_review_events(connection)
        review_identity = record_hcm_import_review(
            connection,
            source_content_digest=digest,
            source_sheet="任意資料頁",
            source_row=11,
            case_identity="HCM-TEST-0011",
            issue_codes=(raw_issue,),
            evidence_snapshot={"has_case_identity": True},
        )

        for attempt in range(3):
            result = consume_hcm_import_review_events(connection, maximum_events=1)
            assert result.failed_count == 1
            immediate = consume_hcm_import_review_events(connection, maximum_events=1)
            assert immediate.failed_count == 0
            if attempt < 2:
                time.sleep(1.05)
        stopped = consume_hcm_import_review_events(connection, maximum_events=1)

        assert stopped.delivered_count == 0
        assert stopped.failed_count == 0
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS count FROM import_warning_occurrences "
                "WHERE source_receipt_identity=%s",
                (review_identity,),
            )
            assert cursor.fetchone() == {"count": 0}
            cursor.execute(
                "SELECT outbox.published_at,outbox.attempts,outbox.last_error "
                "FROM case_import_hcm_review_outbox outbox "
                "JOIN case_import_hcm_review_rows root ON root.id=outbox.review_row_id "
                "WHERE root.review_identity=%s",
                (review_identity,),
            )
            outbox = cursor.fetchone()
            assert outbox["published_at"] is None
            assert outbox["attempts"] == 3
            failure = __import__("json").loads(outbox["last_error"])
            assert failure["terminal"] is True
            assert failure["error_code"].startswith(
                "import_warning_projection_unknown_issue:hcm:"
            )
            assert raw_issue not in str(outbox["last_error"])
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


def test_staff_beclass_review_outbox_acknowledges_canonical_review_without_legacy_warning_rows():
    digest = hashlib.sha256(uuid4().bytes).hexdigest()
    connection = get_connection()
    try:
        # 先排空前序 HCM／BeClass 事件，使本案例不受測試執行順序影響。
        consume_beclass_import_review_events(
            connection,
            runtime=build_anomaly_runtime(),
        )
        review_identity = record_invalid_beclass_row(
            connection,
            source_kind=BeClassImportSourceKind.STAFF,
            source_content_digest=digest,
            source_sheet="任意資料頁",
            source_row=9,
            masked_identifier="staff-***-0009",
            source_payload={"has_identity_card": True, "has_name": True},
            issue_codes=("staff_field_invalid:銀行代號",),
        )
        connection.commit()

        result = consume_beclass_import_review_events(
            connection,
            runtime=build_anomaly_runtime(),
        )

        assert result.delivered_count == 1
        assert result.failed_count == 0
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT published_at,attempts,last_error FROM beclass_import_review_outbox outbox "
                "JOIN beclass_import_review_rows root ON root.id=outbox.review_row_id "
                "WHERE root.review_identity=%s",
                (review_identity,),
            )
            rows = cursor.fetchall()
            assert len(rows) == 1
            assert rows[0]["published_at"] is not None
            assert rows[0]["attempts"] == 0
            assert rows[0]["last_error"] is None
    finally:
        connection.close()


def test_beclass_unknown_issue_is_delivered_as_canonical_review_evidence():
    digest = hashlib.sha256(uuid4().bytes).hexdigest()
    raw_issue = "future_client_state:完整手機不得寫入錯誤"
    connection = get_connection()
    try:
        consume_beclass_import_review_events(
            connection,
            runtime=build_anomaly_runtime(),
        )
        review_identity = record_invalid_beclass_row(
            connection,
            source_kind=BeClassImportSourceKind.CLIENT,
            source_content_digest=digest,
            source_sheet="任意資料頁",
            source_row=12,
            masked_identifier="client-***-0012",
            source_payload={"has_name": True, "has_phone": True},
            issue_codes=(raw_issue,),
        )
        connection.commit()

        result = consume_beclass_import_review_events(
            connection,
            maximum_events=1,
            runtime=build_anomaly_runtime(),
        )
        assert result.delivered_count == 1
        assert result.failed_count == 0

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT outbox.published_at,outbox.attempts,outbox.last_error "
                "FROM beclass_import_review_outbox outbox "
                "JOIN beclass_import_review_rows root ON root.id=outbox.review_row_id "
                "WHERE root.review_identity=%s AND outbox.intent_type='review_opened'",
                (review_identity,),
            )
            outbox = cursor.fetchone()
            assert outbox["published_at"] is not None
            assert outbox["attempts"] == 0
            assert outbox["last_error"] is None
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


def _staff_snapshot(identity_card, name, registered_at):
    return {
        "identity_card": identity_card,
        "name": name,
        "registered_at": registered_at,
        "status": "active",
    }


def _seed_staff_snapshot(connection, record, bank):
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO staff (name,identity_card,registered_at,status) "
            "VALUES (%s,%s,%s,'active')",
            (record["name"], record["identity_card"], record["registered_at"]),
        )
        staff_id = int(cursor.lastrowid)
        cursor.execute(
            "INSERT INTO staff_bank_accounts "
            "(staff_id,bank_code,branch_code,account_no,is_primary) "
            "VALUES (%s,%s,%s,%s,%s)",
            (staff_id, *bank),
        )
        cursor.execute(
            "INSERT INTO staff_regions (staff_id,region_name) VALUES (%s,'舊地區')",
            (staff_id,),
        )
    connection.commit()
    return staff_id


def _adopt_snapshot(connection, digest, row, record, bank, region):
    return adopt_existing_staff(
        connection,
        source_content_digest=digest,
        source_row=row,
        identity_card=record["identity_card"],
        historical_record=record,
        source_sheet="任意資料頁",
        review_payload={"has_identity_card": True},
        bank_accounts=(bank,),
        relations={"staff_regions": ((region, None),)},
    )


def _assert_replaced_staff_snapshot(connection, staff_id, expected_bank):
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM staff WHERE id=%s", (staff_id,))
        assert cursor.fetchone() == {"name": "新姓名"}
        cursor.execute(
            "SELECT bank_code,branch_code,account_no,is_primary "
            "FROM staff_bank_accounts WHERE staff_id=%s",
            (staff_id,),
        )
        assert tuple(cursor.fetchone().values()) == expected_bank
        cursor.execute(
            "SELECT region_name FROM staff_regions WHERE staff_id=%s",
            (staff_id,),
        )
        assert cursor.fetchall() == [{"region_name": "新地區"}]
        cursor.execute(
            "SELECT issue_codes FROM beclass_import_review_rows "
            "WHERE source_kind='staff' ORDER BY id DESC LIMIT 1"
        )
        assert "historical_name_changed" in str(cursor.fetchone()["issue_codes"])


def _assert_staff_name_trace_review(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT root.review_identity FROM beclass_import_review_rows root "
            "WHERE root.source_kind='staff' "
            "AND JSON_CONTAINS(root.issue_codes,%s) ORDER BY root.id DESC LIMIT 1",
            ('"historical_name_changed"',),
        )
        review_identity = cursor.fetchone()["review_identity"]
        cursor.execute(
            "SELECT published_at,attempts,last_error FROM beclass_import_review_outbox outbox "
            "JOIN beclass_import_review_rows root ON root.id=outbox.review_row_id "
            "WHERE root.review_identity=%s",
            (review_identity,),
        )
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["published_at"] is not None
        assert rows[0]["attempts"] == 0
        assert rows[0]["last_error"] is None
