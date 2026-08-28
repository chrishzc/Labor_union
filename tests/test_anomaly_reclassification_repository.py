"""
File: test_anomaly_reclassification_repository.py
Description: 驗證異常必要性移轉 repository 的唯讀游標與單一交易 append primitive。
"""

from domains.anomalies.maintenance import (
    AnomalyReclassificationApplyRequest,
    AnomalyReclassificationCursorPageRequest,
    AnomalyReclassificationDisposition,
    preview_anomaly_reclassification,
)
from pathlib import Path
from types import SimpleNamespace

from infrastructure.mysql.anomaly_maintenance_repository import (
    MySqlAnomalyMaintenanceRepository,
)
import infrastructure.mysql.anomaly_maintenance_repository as repository_module
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey


class _Cursor:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.lastrowid = 0
        self.rowcount = 0
        self.sql = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, _params=()):
        self.sql.append(sql)
        if sql.startswith("UPDATE anomaly_current_alerts"):
            self.rowcount = 1
        elif sql.startswith("INSERT INTO anomaly_workflow_events"):
            self.lastrowid = 72
        elif sql.startswith("INSERT INTO anomaly_reclassification_dispositions"):
            self.lastrowid = 71

    def fetchall(self):
        return self.responses.pop(0) if self.responses else ()

    def fetchone(self):
        return self.responses.pop(0) if self.responses else None


class _Connection:
    def __init__(self, responses=()):
        self.cursor_value = _Cursor(responses)
        self.commits = 0

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.commits += 1


def _alert_row(**overrides):
    row = {
        "fingerprint": "a" * 64,
        "definition_code": "SCHEDULE-005",
        "source_identity": "schedule:42",
        "source_version": 7,
        "workflow_version": 3,
        "predicate_active": 1,
    }
    row.update(overrides)
    return row


def _request():
    from domains.anomalies.maintenance import (
        AnomalyReclassificationAlertIdentity,
        AnomalyReclassificationTargetBinding,
    )

    alert = AnomalyReclassificationAlertIdentity(
        PreviewFingerprint("a" * 64), "SCHEDULE-005", "schedule:42", 7, 3
    )
    candidate = preview_anomaly_reclassification(
        disposition=AnomalyReclassificationDisposition.REPLACED_BY_SUCCESSOR,
        alert=alert,
        target=AnomalyReclassificationTargetBinding("orders", "work-item:42", 4),
        actor=ActorContext("migration-runner"),
        reason="successor verified",
        evidence_reference="evidence:anomaly:42",
    )
    return candidate, AnomalyReclassificationApplyRequest.from_preview(
        candidate,
        idempotency_key=IdempotencyKey("migration:42"),
        correlation_id=CorrelationId("batch:20260827"),
    )


def test_query_reclassification_page_is_ordered_and_bounded_without_writes():
    rows = [_alert_row(source_identity="schedule:42"), _alert_row(source_identity="schedule:43")]
    connection = _Connection([rows])

    page = MySqlAnomalyMaintenanceRepository(connection).query_reclassification_alerts(
        AnomalyReclassificationCursorPageRequest(maximum_items=1),
        eligible_definitions=("SCHEDULE-005",),
    )

    assert page.items[0].source_identity == "schedule:42"
    assert page.next_cursor.key == ("SCHEDULE-005", "schedule:42")
    assert connection.commits == 0
    assert "predicate_active=1" in connection.cursor_value.sql[0]


def test_query_requires_explicit_eligible_definition_filter():
    connection = _Connection([[]])
    try:
        MySqlAnomalyMaintenanceRepository(connection).query_reclassification_alerts(
            AnomalyReclassificationCursorPageRequest(maximum_items=1)
        )
    except TypeError as error:
        assert "explicit collection" in str(error)
    else:
        raise AssertionError("unfiltered reclassification query was accepted")


def test_persist_appends_three_immutable_records_and_never_commits():
    candidate, request = _request()
    connection = _Connection([_alert_row()])

    receipt = MySqlAnomalyMaintenanceRepository(connection).persist_reclassification(
        request, candidate
    )

    assert receipt.workflow_event_id == 72
    assert receipt.resulting_workflow_version == 4
    assert receipt.resulting_predicate_active is False
    assert receipt.before_state_fingerprint.value != request.alert.alert_fingerprint.value
    assert connection.commits == 0
    sql = "\n".join(connection.cursor_value.sql)
    assert "INSERT INTO anomaly_reclassification_dispositions" in sql
    assert "INSERT INTO anomaly_reclassification_receipts" in sql
    assert "action,expected_workflow_version" in sql
    assert "auto_resolve" in sql


def test_persist_rejects_preview_replay_with_different_payload_before_sql_write():
    candidate, request = _request()
    changed = preview_anomaly_reclassification(
        disposition=candidate.disposition,
        alert=candidate.alert,
        target=candidate.target,
        actor=candidate.actor,
        reason="changed",
        evidence_reference=candidate.evidence_reference,
    )
    changed_request = AnomalyReclassificationApplyRequest.from_preview(
        changed,
        idempotency_key=request.idempotency_key,
        correlation_id=request.correlation_id,
    )
    connection = _Connection([_alert_row()])

    try:
        MySqlAnomalyMaintenanceRepository(connection).persist_reclassification(
            changed_request, candidate
        )
    except ValueError as error:
        assert str(error) == "anomaly_reclassification_preview_stale"
    else:
        raise AssertionError("stale preview was accepted")
    assert connection.cursor_value.sql == []


def test_savepoint_primitives_validate_name_and_preserve_sql_order():
    connection = _Connection()
    repository = MySqlAnomalyMaintenanceRepository(connection)

    repository.create_reclassification_savepoint()
    repository.rollback_reclassification_savepoint()
    repository.release_reclassification_savepoint()

    assert connection.cursor_value.sql == [
        "SAVEPOINT `anm_reclass_item`",
        "ROLLBACK TO SAVEPOINT `anm_reclass_item`",
        "RELEASE SAVEPOINT `anm_reclass_item`",
    ]
    assert connection.commits == 0


def test_disposition_insert_has_one_placeholder_per_schema_column():
    sql = repository_module.MySqlAnomalyMaintenanceRepository._insert_reclassification_disposition
    assert sql is not None
    source = Path(__file__).resolve().parents[1] / "infrastructure/mysql/anomaly_maintenance_repository.py"
    text = source.read_text(encoding="utf-8")
    statement = text[text.index('"INSERT INTO anomaly_reclassification_dispositions'):]
    statement = statement[: statement.index("),", statement.index("VALUES"))]
    assert statement.count("%s") == 18


def test_batch_receipt_uses_keyword_contract_and_materializes_cursor_result():
    from domains.anomalies.maintenance import (
        AnomalyReclassificationCursor,
        AnomalyReclassificationResult,
    )

    request = SimpleNamespace(
        operation_identity="anm-nm-a",
        idempotency_key=IdempotencyKey("batch:anm-nm-a"),
        request_fingerprint=PreviewFingerprint("b" * 64),
        actor=ActorContext("migration-runner"),
        correlation_id=CorrelationId("batch:20260827"),
        eligible_codes=("SCHEDULE-005",),
        maximum_items=2,
        cursor=None,
    )
    result = AnomalyReclassificationResult(
        1,
        1,
        (),
        AnomalyReclassificationCursor("SCHEDULE-005", "schedule:42"),
    )
    connection = _Connection()
    identity = MySqlAnomalyMaintenanceRepository(connection).save_reclassification_batch_receipt(
        operation_identity="anm-nm-a",
        request=request,
        result=result,
        request_fingerprint=PreviewFingerprint("b" * 64),
        actor=ActorContext("migration-runner"),
        correlation_id=CorrelationId("batch:20260827"),
    )

    assert identity.startswith("anomaly-reclassification-batch:")
    assert "INSERT INTO anomaly_reclassification_batch_receipts" in connection.cursor_value.sql[0]
    assert identity


def test_batch_receipt_replay_materializes_both_cursor_parts_and_blocker():
    row = {
        "request_fingerprint": "b" * 64,
        "batch_receipt_identity": "anomaly-reclassification-batch:key",
        "operation_identity": "anm-nm-a",
        "eligible_codes": '["SCHEDULE-005"]',
        "eligible_codes_fingerprint": "c" * 64,
        "cursor_definition_code": "",
        "definition_code": "SCHEDULE-005",
        "cursor_source_identity": "schedule:41",
        "next_cursor_definition_code": "SCHEDULE-005",
        "next_cursor_source_identity": "schedule:42",
        "batch_size": 2,
        "scanned_count": 1,
        "applied_count": 0,
        "blocked_count": 1,
        "blocked_items": '[{"definition_code":"SCHEDULE-005","source_identity":"schedule:41","reason":"target missing","alert_fingerprint":"' + "a" * 64 + '"}]',
        "status": "blocked",
    }
    connection = _Connection([row])

    stored = MySqlAnomalyMaintenanceRepository(connection).find_reclassification_batch_receipt(
        "anomaly-reclassification-batch-key:1"
    )

    assert stored[0] == PreviewFingerprint("b" * 64)
    assert stored[1].next_cursor.key == ("SCHEDULE-005", "schedule:42")
    assert stored[1].blocked_items[0].reason == "target missing"
