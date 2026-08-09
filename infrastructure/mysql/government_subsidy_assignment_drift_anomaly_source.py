"""MySQL root-fact source and atomic page projection for GOVSUB-005."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from domains.anomalies.registry import default_anomaly_registry
from infrastructure.mysql.anomaly_registry_repository import (
    MySqlAnomalyRepository,
)
from subsystems.anomalies.government_subsidy_assignment_drift_anomaly_source import (
    GovernmentSubsidyAssignmentDriftAnomalyConsumer,
    GovernmentSubsidyAssignmentDriftRootFact,
    GovernmentSubsidyAssignmentDriftScanPage,
    GovernmentSubsidyAssignmentDriftScanRequest,
)
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.anomalies.alert_workflow import AnomalyApplication

_SOURCE_VERSION_COUNTER_BASE = 4_294_967_296


class BorrowedGovernmentSubsidyAssignmentDriftUnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class MySqlGovernmentSubsidyAssignmentDriftRootFactSource:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_page(
        self,
        request: GovernmentSubsidyAssignmentDriftScanRequest,
    ) -> GovernmentSubsidyAssignmentDriftScanPage:
        with self._connection.cursor() as cursor:
            cursor.execute(
                _CLAIM_ITEM_ASSIGNMENT_FACT_SELECT_SQL,
                (request.after_claim_item_id, request.limit),
            )
            rows = _mapping_rows(cursor.fetchall())
        facts = tuple(_root_fact(row) for row in rows)
        return GovernmentSubsidyAssignmentDriftScanPage(
            facts,
            _next_cursor(facts, request.limit),
        )


def project_government_subsidy_assignment_drift_page(
    connection: Any,
    request: GovernmentSubsidyAssignmentDriftScanRequest,
):
    consumer = _projection_consumer(connection)
    try:
        connection.begin()
        result = consumer.scan_page(request)
        connection.commit()
        return result
    except Exception:
        connection.rollback()
        raise


def _projection_consumer(connection):
    application = AnomalyApplication(
        default_anomaly_registry(),
        MySqlAnomalyRepository(connection),
        BorrowedGovernmentSubsidyAssignmentDriftUnitOfWork,
    )
    return GovernmentSubsidyAssignmentDriftAnomalyConsumer(
        MySqlGovernmentSubsidyAssignmentDriftRootFactSource(connection),
        application,
    )


def _root_fact(row):
    values = {**_frozen_values(row), **_official_values(row)}
    return GovernmentSubsidyAssignmentDriftRootFact(
        **values,
        source_event_identity=_source_event_identity(values),
    )


def _frozen_values(row):
    return {
        "claim_item_id": _positive_integer(row, "claim_item_id"),
        "batch_id": _positive_integer(row, "batch_id"),
        "frozen_assignment_id": _positive_integer(row, "frozen_assignment_id"),
        "frozen_case_no": _text(row, "frozen_case_no"),
        "frozen_staff_id": _positive_integer(row, "frozen_staff_id"),
        "frozen_claimed_hours": _nonnegative_integer(row, "frozen_claimed_hours"),
    }


def _official_values(row):
    return {
        "authoritative_assignment_id": _positive_integer(
            row,
            "authoritative_assignment_id",
        ),
        "authoritative_case_no": _text(row, "authoritative_case_no"),
        "authoritative_staff_id": _positive_integer(
            row,
            "authoritative_staff_id",
        ),
        "official_service_hours": _nonnegative_integer(
            row,
            "official_service_hours",
        ),
        "assignment_effective": bool(_binary_integer(row, "assignment_effective")),
        "source_version": _nonnegative_integer(row, "source_version"),
    }


def _source_event_identity(values):
    digest = fingerprint_payload(values).value
    return f"govsub-assignment-drift:{digest}"


def _next_cursor(facts, limit):
    if not facts or len(facts) < limit:
        return None
    return facts[-1].claim_item_id


def _mapping_rows(rows):
    result = tuple(rows)
    if any(not isinstance(row, Mapping) for row in result):
        raise TypeError("claim assignment roots contain an invalid row")
    return result


def _positive_integer(row, field):
    value = _integer(row, field)
    if value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _nonnegative_integer(row, field):
    value = _integer(row, field)
    if value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return value


def _binary_integer(row, field):
    value = _integer(row, field)
    if value not in (0, 1):
        raise ValueError(f"{field} must be zero or one")
    return value


def _integer(row, field):
    value = row.get(field)
    if isinstance(value, bool):
        raise TypeError(f"{field} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    raise TypeError(f"{field} must be an integer")


def _text(row, field):
    value = row.get(field)
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field} must be canonical text")
    return value


_CLAIM_ITEM_ASSIGNMENT_FACT_SELECT_SQL = f"""
SELECT i.id AS claim_item_id,
       i.batch_id,
       i.assignment_id AS frozen_assignment_id,
       i.case_no AS frozen_case_no,
       i.staff_id AS frozen_staff_id,
       i.claimed_hours AS frozen_claimed_hours,
       a.id AS authoritative_assignment_id,
       a.case_no AS authoritative_case_no,
       a.staff_id AS authoritative_staff_id,
       CASE WHEN a.generation_id=sa.effective_generation_id
                  AND generation.status='effective'
                  AND generation.effective_marker=1
                  AND a.status NOT IN ('cancelled','replaced')
            THEN 1 ELSE 0 END AS assignment_effective,
       CASE WHEN a.generation_id=sa.effective_generation_id
                  AND generation.status='effective'
                  AND generation.effective_marker=1
                  AND a.status NOT IN ('cancelled','replaced')
            THEN (
                SELECT COUNT(DISTINCT schedule.work_date)
                FROM staff_schedule schedule
                WHERE schedule.assignment_id=a.id
                  AND schedule.generation_id=a.generation_id
                  AND schedule.effective_marker=1
                  AND schedule.is_work_day=1
                  AND schedule.work_date >= MAKEDATE(batch.application_year,1)
                    + INTERVAL ((batch.quarter-1)*3) MONTH
                  AND schedule.work_date < MAKEDATE(batch.application_year,1)
                    + INTERVAL (batch.quarter*3) MONTH
            ) * orders.service_hours_per_day
            ELSE 0 END AS official_service_hours,
       CAST(UNIX_TIMESTAMP(i.updated_at) AS UNSIGNED)
           * {_SOURCE_VERSION_COUNTER_BASE}
           + COALESCE(sa.aggregate_version,0) AS source_version
FROM subsidy_claim_batch_items i
JOIN subsidy_claim_batches batch ON batch.id=i.batch_id
JOIN case_staff_assignments a ON a.id=i.assignment_id
LEFT JOIN scheduling_aggregates sa ON sa.case_no=a.case_no
LEFT JOIN scheduling_generations generation
  ON generation.id=sa.effective_generation_id
JOIN orders orders ON orders.case_no=a.case_no
WHERE i.id>%s
ORDER BY i.id
LIMIT %s
"""


__all__ = [
    "BorrowedGovernmentSubsidyAssignmentDriftUnitOfWork",
    "MySqlGovernmentSubsidyAssignmentDriftRootFactSource",
    "project_government_subsidy_assignment_drift_page",
]
