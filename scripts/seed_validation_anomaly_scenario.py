"""Create one replay-safe scheduling anomaly through its formal projection workflow."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from domains.anomalies.registry import AlertWorkflowStatus, default_anomaly_registry
from infrastructure.mysql.anomaly_registry_repository import (
    AnomalyMySqlUnitOfWork,
    MySqlAnomalyRepository,
)
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.anomalies.alert_workflow import AnomalyApplication, AnomalyWorkflowRequest
from subsystems.anomalies.scheduling_coverage_anomaly_consumer import (
    AssignmentOfficialServiceDays,
    SchedulingCoverageRootFact,
    build_schedule_coverage_project_request,
)


_DATABASE_PATTERN = re.compile(r"lu_test_dataset_[a-z0-9_]+")
_CASE_NO = "DSV1-CASE-0001"
_SERVICE_START = date(2026, 8, 1)
_EXPECTED_SERVICE_DAYS = 5
_EXPECTED_TIMELINE = ["claim", "resolve", "reopen", "auto_resolve", "reopen"]
_PARTIAL_TIMELINE = ["claim", "resolve", "reopen"]


def seed(
    *,
    case_no: str = _CASE_NO,
    service_start: date = _SERVICE_START,
    expected_service_days: int = _EXPECTED_SERVICE_DAYS,
) -> dict[str, object]:
    _configure_scenario(case_no, service_start, expected_service_days)
    _require_dataset_database()
    application, connection = _application()
    try:
        opened = _existing_projection(application)
        if opened is None:
            opened = application.project(_request(1, active=True))
            if opened is None or opened.workflow_status is not AlertWorkflowStatus.OPEN:
                raise RuntimeError("scheduling anomaly was not opened")
            _open_and_reopen_if_fresh(application, opened)
        if _timeline_actions(application, opened) == _EXPECTED_TIMELINE:
            return _seed_result(application, opened)
        _require_partial_timeline(application, opened)
        repaired = application.project(_request(3, active=False))
        if repaired is None or repaired.workflow_status is not AlertWorkflowStatus.RESOLVED:
            raise RuntimeError("resolved root did not clear the anomaly")
        reintroduced = application.project(_request(4, active=True))
        if reintroduced is None or reintroduced.workflow_status is not AlertWorkflowStatus.OPEN:
            raise RuntimeError("recurring root did not reopen the anomaly")
        return _seed_result(application, reintroduced)
    finally:
        connection.close()


def _configure_scenario(
    case_no: str,
    service_start: date,
    expected_service_days: int,
) -> None:
    global _CASE_NO, _SERVICE_START, _EXPECTED_SERVICE_DAYS
    if not case_no.strip():
        raise ValueError("case_no_is_required")
    if expected_service_days < 2:
        raise ValueError("expected_service_days_must_be_at_least_two")
    _CASE_NO = case_no.strip()
    _SERVICE_START = service_start
    _EXPECTED_SERVICE_DAYS = expected_service_days


def _require_dataset_database() -> None:
    from infrastructure.mysql.mysql_adapter import DB_CONFIG

    if not _DATABASE_PATTERN.fullmatch(str(DB_CONFIG["database"])):
        raise ValueError("DB_DATABASE must match lu_test_dataset_[a-z0-9_]+")


def _application():
    connection = get_connection()
    return AnomalyApplication(default_anomaly_registry(), MySqlAnomalyRepository(connection), lambda: AnomalyMySqlUnitOfWork(connection)), connection


def _open_and_reopen_if_fresh(application, opened) -> None:
    timeline = application.query_detail(opened.fingerprint).timeline
    if timeline:
        return
    claimed = application.claim(_workflow_request(opened, 0, "claim"))
    resolved = application.resolve(_workflow_request(claimed, 1, "resolve"))
    reopened = application.project(_request(2, active=True))
    if reopened is None or reopened.workflow_status is not AlertWorkflowStatus.OPEN:
        raise RuntimeError("active root did not reopen the anomaly")


def _existing_projection(application):
    request = _request(1, active=True)
    fingerprint = default_anomaly_registry().fingerprint(request.desired)
    try:
        return application.query_detail(fingerprint).summary.projection
    except ValueError as error:
        if str(error) != "anomaly_not_found":
            raise
        return None


def _require_partial_timeline(application, projection) -> None:
    if _timeline_actions(application, projection) != _PARTIAL_TIMELINE:
        raise RuntimeError("scheduling anomaly workflow timeline is not resumable")


def _request(source_version: int, *, active: bool):
    dates = tuple(
        _SERVICE_START + timedelta(days=offset)
        for offset in range(_EXPECTED_SERVICE_DAYS - 1)
    )
    if not active:
        dates += (_SERVICE_START + timedelta(days=_EXPECTED_SERVICE_DAYS - 1),)
    root = SchedulingCoverageRootFact(
        case_no=_CASE_NO,
        generation=1,
        expected_service_days=_EXPECTED_SERVICE_DAYS,
        assignments=(AssignmentOfficialServiceDays(1, dates),),
        generation_effective=True,
        completed_eligible=True,
        source_version=source_version,
        source_event_identity=f"validation-schedule-coverage:{_CASE_NO}:{source_version}",
    )
    return build_schedule_coverage_project_request(root)


def _seed_result(application, projection) -> dict[str, object]:
    timeline = _timeline_actions(application, projection)
    if timeline != _EXPECTED_TIMELINE:
        raise RuntimeError("scheduling anomaly workflow timeline is incomplete")
    return {
        "case_no": _CASE_NO,
        "fingerprint": projection.fingerprint.value,
        "status": projection.workflow_status.value,
        "timeline_actions": timeline,
    }


def _timeline_actions(application, projection) -> list[str]:
    return [event["action"] for event in application.query_detail(projection.fingerprint).timeline]


def _workflow_request(projection, expected_version: int, action: str) -> AnomalyWorkflowRequest:
    identity = f"validation-schedule-006-{_CASE_NO}-{action}"
    return AnomalyWorkflowRequest(projection.fingerprint, expected_version, IdempotencyKey(identity), ActorContext("validation-dataset-seed"), "exercise anomaly UI state transition", CorrelationId(identity))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-no", default=_CASE_NO)
    parser.add_argument("--service-start", default=_SERVICE_START.isoformat())
    parser.add_argument("--expected-service-days", type=int, default=_EXPECTED_SERVICE_DAYS)
    arguments = parser.parse_args()
    print(
        seed(
            case_no=arguments.case_no,
            service_start=date.fromisoformat(arguments.service_start),
            expected_service_days=arguments.expected_service_days,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
