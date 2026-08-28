"""
File: test_anomaly_closed_loop_disposable_mysql_e2e.py
Description: 以隔離 MySQL 驗證排班異常閉環；拒絕非 lu_test_* 目標。
"""

from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

import pytest

from domains.anomalies.registry import (
    AlertWorkflowStatus,
    default_anomaly_registry,
)
from infrastructure.mysql.anomaly_registry_repository import (
    AnomalyMySqlUnitOfWork,
    MySqlAnomalyRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.anomalies.alert_workflow import (
    AnomalyApplication,
    AnomalyWorkflowRequest,
)
from subsystems.anomalies.scheduling_coverage_anomaly_consumer import (
    AssignmentOfficialServiceDays,
    SchedulingCoverageRootFact,
    build_schedule_coverage_project_request,
)


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
if DATABASE and (DATABASE == "union_db" or not DATABASE.startswith("lu_test_")):
    raise RuntimeError(
        "LABOR_UNION_TEST_MYSQL_DATABASE must be a disposable lu_test_* database"
    )

pytestmark = pytest.mark.skipif(
    not DATABASE or os.getenv("DB_DATABASE") != DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def test_scheduling_anomaly_claim_repair_and_reopen_closed_loop():
    case_no = f"ANOM-{uuid4().hex[:12]}"
    application, connection = _application()
    try:
        opened = application.project(_project_request(case_no, 1, active=True))
        assert opened is not None
        assert opened.workflow_status is AlertWorkflowStatus.OPEN
        assert application.project(_project_request(case_no, 1, active=True)) == opened
        _assert_projection_count(connection, opened.fingerprint.value, 1)

        claimed = application.claim(_workflow_request(opened, 0, "claim"))
        assert claimed.workflow_status is AlertWorkflowStatus.CLAIMED
        with pytest.raises(ValueError, match="anomaly_version_conflict"):
            application.claim(_workflow_request(opened, 0, "claim-race"))

        with pytest.raises(ValueError, match="anomaly_manual_resolve_forbidden"):
            application.resolve(_workflow_request(claimed, 1, "resolve"))
        still_claimed = application.query_detail(opened.fingerprint).summary.projection
        assert still_claimed.predicate_active is True
        assert still_claimed.workflow_status is AlertWorkflowStatus.CLAIMED

        auto_resolved = application.project(_project_request(case_no, 2, active=False))
        assert auto_resolved is not None
        assert auto_resolved.workflow_status is AlertWorkflowStatus.RESOLVED
        reintroduced = application.project(_project_request(case_no, 3, active=True))
        assert reintroduced is not None
        assert reintroduced.workflow_status is AlertWorkflowStatus.OPEN
        _assert_detail(application, reintroduced, case_no)
    finally:
        connection.close()


def _application() -> tuple[AnomalyApplication, object]:
    connection = get_connection()
    application = AnomalyApplication(
        default_anomaly_registry(),
        MySqlAnomalyRepository(connection),
        lambda: AnomalyMySqlUnitOfWork(connection),
    )
    return application, connection


def _project_request(case_no: str, source_version: int, *, active: bool):
    dates = (date(2026, 8, 1),) if active else (date(2026, 8, 1), date(2026, 8, 2))
    root_fact = SchedulingCoverageRootFact(
        case_no=case_no,
        generation=1,
        expected_service_days=2,
        assignments=(AssignmentOfficialServiceDays(1, dates),),
        generation_effective=True,
        completed_eligible=True,
        source_version=source_version,
        source_event_identity=f"schedule-root:{case_no}:{source_version}",
    )
    return build_schedule_coverage_project_request(root_fact)


def _workflow_request(projection, expected_version: int, action: str):
    identity = f"anomaly-{action}-{uuid4().hex}"
    return AnomalyWorkflowRequest(
        projection.fingerprint,
        expected_version,
        IdempotencyKey(identity),
        ActorContext(f"operator-{action}"),
        "operator recorded review outcome",
        CorrelationId(identity),
    )


def _assert_projection_count(connection, fingerprint: str, expected_count: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) AS count FROM anomaly_current_alerts WHERE fingerprint=%s",
            (fingerprint,),
        )
        assert cursor.fetchone() == {"count": expected_count}


def _assert_detail(application, projection, case_no: str) -> None:
    detail = application.query_detail(projection.fingerprint)
    expected_definition = default_anomaly_registry().require(
        detail.summary.projection.definition_code
    )
    assert detail.summary.severity is expected_definition.severity
    assert detail.summary.projection.predicate_active is True
    assert detail.summary.display_snapshot["case_no"] == case_no
    assert [event["action"] for event in detail.timeline] == [
        "claim",
        "resolve",
        "reopen",
        "auto_resolve",
        "reopen",
    ]
