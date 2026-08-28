"""
File: test_anomaly_necessity_migration_disposable_mysql_e2e.py
Description: 以明確 lu_test_* MySQL 驗證必要性移轉 Q/P/A、replay、batch 與 completion sweep。
"""

from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import (
    require_anomaly_necessity_migration_operator,
)
from api.dependencies.anomaly_recovery import _maintenance_application
from api.main import app
from domains.anomalies.registry import default_anomaly_registry
from domains.anomalies.maintenance import (
    AnomalyReclassificationApplyRequest,
    AnomalyReclassificationCursorPageRequest,
)
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.anomaly_registry_repository import (
    AnomalyMySqlUnitOfWork,
    MySqlAnomalyRepository,
)
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.anomalies.alert_workflow import AnomalyApplication
from subsystems.anomalies.necessity_migration_policy import (
    approved_anomaly_necessity_migration_policy,
)
from subsystems.anomalies.process_reminder_anomaly_source import (
    build_schedule_holiday_preference_requests,
)


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
if DATABASE and (DATABASE == "union_db" or not DATABASE.startswith("lu_test_")):
    raise RuntimeError(
        "LABOR_UNION_TEST_MYSQL_DATABASE must be a lu_test_* database"
    )

pytestmark = pytest.mark.skipif(
    not DATABASE or os.getenv("DB_DATABASE") != DATABASE,
    reason="requires an explicitly configured lu_test_* MySQL database",
)


def test_single_query_preview_apply_and_replay_are_real_mysql() -> None:
    scenario = f"task96-anm-nm-a-single:{uuid4().hex}"
    alert, source_identity = _seed_alert(scenario)
    source_connection = get_connection()
    projection_connection = get_connection()
    workflow = _maintenance_application(source_connection, projection_connection)
    policy = approved_anomaly_necessity_migration_policy()
    actor = ActorContext("admin:task96-migration", ("system.administration",))
    try:
        page = workflow.query_reclassification(
            AnomalyReclassificationCursorPageRequest(100),
            eligible_codes=policy.eligible_codes,
        )
        current = next(
            item for item in page.items if item.source_identity == source_identity
        )
        before = _row_counts(source_connection, alert)
        policy_candidate = policy.build_candidate(
            current,
            actor=actor,
            reason="SCHEDULE-005 is a retired preference false positive",
            evidence_reference=f"test-scenario:{scenario}",
        )
        preview = workflow.preview_reclassification(
            current,
            policy_candidate.disposition,
            policy_candidate.target,
            actor,
            policy_candidate.reason,
            policy_candidate.evidence_reference,
            policy_candidate.rulebook_reference,
            policy_candidate.release_evidence_reference,
        )
        assert _row_counts(source_connection, alert) == before

        request = AnomalyReclassificationApplyRequest.from_preview(
            preview,
            idempotency_key=IdempotencyKey(f"task96-single:{uuid4().hex}"),
            correlation_id=CorrelationId(f"task96-single:{uuid4().hex}"),
        )
        receipt = workflow.apply_reclassification(request)
        replay = workflow.apply_reclassification(request)
        assert replay.receipt_identity == receipt.receipt_identity
        assert replay.replayed is True
        _assert_terminal_readback(source_connection, alert, expected_batches=0)
    finally:
        projection_connection.close()
        source_connection.close()


def test_batch_replay_and_completion_sweep_are_real_mysql() -> None:
    scenario = f"task96-anm-nm-a-batch:{uuid4().hex}"
    alert, _ = _seed_alert(scenario)
    source_connection = get_connection()
    projection_connection = get_connection()
    workflow = _maintenance_application(source_connection, projection_connection)
    policy = approved_anomaly_necessity_migration_policy()
    actor = ActorContext("admin:task96-migration", ("system.administration",))
    operation_identity = f"task96-anm-nm-a-batch:{uuid4().hex}"
    request = AnomalyReclassificationCursorPageRequest(100)

    def resolve(current):
        return policy.build_candidate(
            current,
            actor=actor,
            reason="SCHEDULE-005 is a retired preference false positive",
            evidence_reference=f"test-scenario:{scenario}",
        )

    try:
        result = workflow.run_reclassification_batch(
            request,
            eligible_codes=policy.eligible_codes,
            operation_identity=operation_identity,
            policy_identity=policy.identity,
            policy_fingerprint=policy.fingerprint,
            actor=actor,
            resolve_candidate=resolve,
            correlation_id=CorrelationId(f"task96-batch:{uuid4().hex}"),
        )
        replay = workflow.run_reclassification_batch(
            request,
            eligible_codes=policy.eligible_codes,
            operation_identity=operation_identity,
            policy_identity=policy.identity,
            policy_fingerprint=policy.fingerprint,
            actor=actor,
            resolve_candidate=resolve,
            correlation_id=CorrelationId(f"task96-batch-replay:{uuid4().hex}"),
        )
        assert result.applied_count >= 1
        assert result.blocked_items == ()
        assert replay.batch_receipt_identity == result.batch_receipt_identity
        sweep = workflow.query_reclassification(
            AnomalyReclassificationCursorPageRequest(100),
            eligible_codes=policy.eligible_codes,
        )
        assert sweep.items == ()
        assert sweep.next_cursor is None
        _assert_terminal_readback(source_connection, alert, expected_batches=1)
    finally:
        projection_connection.close()
        source_connection.close()


def test_http_query_preview_apply_and_replay_use_real_mysql() -> None:
    scenario = f"task96-anm-nm-a-http:{uuid4().hex}"
    fingerprint, source_identity = _seed_alert(scenario)
    principal = AdminPrincipal(
        96,
        "task96-migration-operator",
        "Task 96 Migration Operator",
        "system_admin",
        capabilities=frozenset({"system.administration"}),
    )
    app.dependency_overrides[
        require_anomaly_necessity_migration_operator
    ] = lambda: principal
    try:
        client = TestClient(app)
        query = client.get(
            "/api/v1/admin/anomaly-necessity-migration/alerts",
            params={"maximum_items": 100},
        )
        assert query.status_code == 200, query.text
        item = next(
            row
            for row in query.json()["data"]["items"]
            if row["source_identity"] == source_identity
        )
        body = {
            "expected_definition_code": item["definition_code"],
            "expected_source_identity": item["source_identity"],
            "expected_source_version": item["source_version"],
            "expected_workflow_version": item["workflow_version"],
            "reason": "SCHEDULE-005 is a retired preference false positive",
            "evidence_reference": f"test-scenario:{scenario}",
        }
        preview = client.post(
            f"/api/v1/admin/anomaly-necessity-migration/alerts/{fingerprint}/preview",
            json=body,
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["data"]["disposition"] == "retired_false_positive"

        apply_body = {
            **body,
            "preview_fingerprint": preview.json()["data"]["preview_fingerprint"],
        }
        headers = {
            "Idempotency-Key": f"task96-http:{uuid4().hex}",
            "X-Correlation-ID": f"task96-http:{uuid4().hex}",
        }
        applied = client.post(
            f"/api/v1/admin/anomaly-necessity-migration/alerts/{fingerprint}/apply",
            json=apply_body,
            headers=headers,
        )
        assert applied.status_code == 200, applied.text
        assert applied.json()["data"]["resulting_predicate_active"] is False
        replay = client.post(
            f"/api/v1/admin/anomaly-necessity-migration/alerts/{fingerprint}/apply",
            json=apply_body,
            headers=headers,
        )
        assert replay.status_code == 200, replay.text
        assert replay.json()["data"]["replayed"] is True
    finally:
        app.dependency_overrides.pop(
            require_anomaly_necessity_migration_operator,
            None,
        )


def _seed_alert(scenario: str) -> tuple[str, str]:
    staff_id = 900_000_000 + int(uuid4().hex[:7], 16)
    work_date = date(2099, 12, 31)
    request = build_schedule_holiday_preference_requests(
        [
            {
                "staff_id": staff_id,
                "staff_name": "Task96 Migration Scenario",
                "work_date": work_date,
                "holiday_name": "Task96 Test Holiday",
                "case_no": scenario,
                "is_work_day": 1,
            }
        ],
        as_of=work_date,
    )[0]
    connection = get_connection()
    try:
        application = AnomalyApplication(
            default_anomaly_registry(),
            MySqlAnomalyRepository(connection),
            lambda: AnomalyMySqlUnitOfWork(connection),
        )
        projection = application.project(request)
        assert projection is not None
        assert projection.predicate_active is True
        return projection.fingerprint.value, projection.source_identity
    finally:
        connection.close()


def _row_counts(connection, fingerprint: str) -> tuple[int, int, int]:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS count FROM anomaly_reclassification_dispositions "
            "WHERE alert_fingerprint=%s",
            (fingerprint,),
        )
        disposition_count = int(cursor.fetchone()["count"])
        cursor.execute(
            "SELECT COUNT(*) AS count FROM anomaly_reclassification_receipts r "
            "JOIN anomaly_reclassification_dispositions d "
            "ON d.id=r.disposition_id WHERE d.alert_fingerprint=%s",
            (fingerprint,),
        )
        receipt_count = int(cursor.fetchone()["count"])
        cursor.execute(
            "SELECT COUNT(*) AS count FROM anomaly_workflow_events "
            "WHERE alert_fingerprint=%s AND action='auto_resolve'",
            (fingerprint,),
        )
        event_count = int(cursor.fetchone()["count"])
    return disposition_count, receipt_count, event_count


def _assert_terminal_readback(
    connection,
    fingerprint: str,
    *,
    expected_batches: int,
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT predicate_active,workflow_status,workflow_version "
            "FROM anomaly_current_alerts WHERE fingerprint=%s",
            (fingerprint,),
        )
        row = cursor.fetchone()
        assert row == {
            "predicate_active": 0,
            "workflow_status": "resolved",
            "workflow_version": 1,
        }
        assert _row_counts(connection, fingerprint) == (1, 1, 1)
        cursor.execute(
            "SELECT COUNT(*) AS count FROM anomaly_reclassification_batch_receipts "
            "WHERE status IN ('completed','blocked')"
        )
        assert int(cursor.fetchone()["count"]) >= expected_batches
