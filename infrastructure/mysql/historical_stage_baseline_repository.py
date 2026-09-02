"""Read immutable Historical Orders baseline lineage for timeline overlay."""

from __future__ import annotations

from datetime import date
import json
from typing import Any, Mapping

from domains.orders.lifecycle import OrderLifecycleStatus
from subsystems.orders.historical_stage_baseline_overlay import HistoricalStageBaselineFacts


class MySqlHistoricalStageBaselineRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def fetch_for_cases(
        self, case_nos: tuple[str, ...]
    ) -> tuple[HistoricalStageBaselineFacts, ...]:
        if not case_nos:
            return ()
        placeholders = ",".join(["%s"] * len(case_nos))
        sql = f"""
SELECT o.case_no,
       o.status,
       o.actual_start_date,
       receipt.id AS adoption_receipt_id,
       receipt.result_snapshot AS adoption_result_snapshot,
       lifecycle.after_status AS adoption_after_status,
       lifecycle.facts_snapshot AS adoption_facts_snapshot,
       baseline.id AS baseline_event_version,
       baseline.baseline_event_identity,
       baseline.selected_step
  FROM orders o
  JOIN (
       SELECT case_no, MAX(id) AS receipt_id
         FROM historical_order_adoption_receipts
        WHERE outcome = 'adopted'
          AND case_no IS NOT NULL
        GROUP BY case_no
  ) latest ON latest.case_no = o.case_no
  JOIN historical_order_adoption_receipts receipt
    ON receipt.id = latest.receipt_id
  LEFT JOIN order_lifecycle_state_events lifecycle
    ON lifecycle.id = receipt.lifecycle_event_id
  LEFT JOIN (
       SELECT event.id,
              event.case_no,
              event.baseline_event_identity,
              event.selected_step
         FROM historical_order_operational_baseline_events event
         JOIN (
              SELECT case_no, MAX(id) AS event_id
                FROM historical_order_operational_baseline_events
               GROUP BY case_no
         ) latest_baseline
           ON latest_baseline.event_id = event.id
  ) baseline ON baseline.case_no = o.case_no
 WHERE o.case_no IN ({placeholders})
 ORDER BY o.case_no
"""
        with self._connection.cursor() as cursor:
            cursor.execute(sql, case_nos)
            rows = tuple(cursor.fetchall() or ())
        return tuple(_facts(row) for row in rows)


def _facts(row) -> HistoricalStageBaselineFacts:
    receipt_snapshot = _json_object(row.get("adoption_result_snapshot"))
    lifecycle_snapshot = _json_object(row.get("adoption_facts_snapshot"))
    lifecycle_status = _historical_lifecycle_status(row, receipt_snapshot)
    actual_start = _historical_actual_start(row, receipt_snapshot, lifecycle_snapshot)
    selected_step = _selected_step(row, receipt_snapshot, lifecycle_status, actual_start)
    return HistoricalStageBaselineFacts(
        str(row["case_no"]),
        int(row["adoption_receipt_id"]),
        lifecycle_status,
        actual_start,
        selected_step,
        _optional_text(row.get("baseline_event_identity")),
        _optional_int(row.get("baseline_event_version")),
    )


def _selected_step(
    row: Mapping[str, object],
    receipt_snapshot: Mapping[str, object],
    lifecycle_status: OrderLifecycleStatus,
    actual_start: date | None,
) -> int | None:
    formal = _optional_int(row.get("selected_step"))
    if formal is not None:
        return _validated_step(formal)
    if "operational_baseline_step" in receipt_snapshot:
        value = receipt_snapshot.get("operational_baseline_step")
        if value is not None:
            return _validated_step(_required_int(value, "operational_baseline_step"))
        event_step = _adoption_event_step(row, actual_start)
        if event_step is not None:
            return event_step
    return _legacy_step(lifecycle_status, actual_start)


def _historical_lifecycle_status(
    row: Mapping[str, object],
    receipt_snapshot: Mapping[str, object],
) -> OrderLifecycleStatus:
    source_status = receipt_snapshot.get("historical_source_status")
    if source_status is not None:
        mapped = {
            "cancelled": OrderLifecycleStatus.CANCELLED,
            "deposit_paid": OrderLifecycleStatus.ESTABLISHED,
            "discussion": OrderLifecycleStatus.DISCUSSION,
        }.get(str(source_status))
        if mapped is None:
            raise ValueError("historical_stage_baseline_source_status_invalid")
        return mapped
    event_status = row.get("adoption_after_status")
    if event_status is not None:
        return OrderLifecycleStatus(str(event_status))
    return OrderLifecycleStatus(str(row["status"]))


def _historical_actual_start(
    row: Mapping[str, object],
    receipt_snapshot: Mapping[str, object],
    lifecycle_snapshot: Mapping[str, object],
) -> date | None:
    if "operational_baseline_actual_start_date" in receipt_snapshot:
        return _optional_date(receipt_snapshot.get("operational_baseline_actual_start_date"))
    event_value = _event_actual_start(lifecycle_snapshot)
    if event_value is not _MISSING:
        return _optional_date(event_value)
    return _optional_date(row.get("actual_start_date"))


_MISSING = object()


def _event_actual_start(snapshot: Mapping[str, object]):
    patch = snapshot.get("date_patch")
    if not isinstance(patch, (list, tuple)):
        return _MISSING
    for item in patch:
        if (
            isinstance(item, (list, tuple))
            and len(item) == 2
            and item[0] == "actual_start_date"
        ):
            return item[1]
    return _MISSING


def _adoption_event_step(
    row: Mapping[str, object], actual_start: date | None
) -> int | None:
    raw_status = row.get("adoption_after_status")
    if raw_status is None:
        return None
    try:
        status = OrderLifecycleStatus(str(raw_status))
    except ValueError as error:
        raise ValueError("historical_stage_baseline_event_status_invalid") from error
    return _legacy_step(status, actual_start)


def _legacy_step(
    lifecycle_status: OrderLifecycleStatus,
    actual_start: date | None,
) -> int | None:
    if lifecycle_status in {
        OrderLifecycleStatus.COMPLETED,
        OrderLifecycleStatus.HISTORICAL_SERVICE_COMPLETED,
        OrderLifecycleStatus.HISTORICAL_ACCOUNTING_COMPLETED,
    }:
        return 11
    if lifecycle_status in {
        OrderLifecycleStatus.IN_SERVICE,
        OrderLifecycleStatus.HISTORICAL_IN_SERVICE,
    }:
        return 10
    if (
        actual_start is not None
        and lifecycle_status
        in {
            OrderLifecycleStatus.DISCUSSION,
            OrderLifecycleStatus.ESTABLISHED,
        }
    ):
        return 10
    if lifecycle_status in {
        OrderLifecycleStatus.ESTABLISHED,
        OrderLifecycleStatus.HISTORICAL_UNSERVED,
    }:
        return 9
    return None


def _json_object(value: object) -> Mapping[str, object]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return value
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if not isinstance(value, str):
        raise ValueError("historical_stage_baseline_snapshot_invalid")
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("historical_stage_baseline_snapshot_invalid")
    return parsed


def _optional_date(value: object) -> date | None:
    if value is None or type(value) is date:
        return value
    return date.fromisoformat(str(value))


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _required_int(value, "historical baseline integer")


def _required_int(value: object, field_name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field_name} is invalid")
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} is invalid") from error
    return result


def _validated_step(value: int) -> int:
    if not 1 <= value <= 11:
        raise ValueError("historical_stage_baseline_step_invalid")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text:
        raise ValueError("historical_stage_baseline_identity_invalid")
    return text


__all__ = ["MySqlHistoricalStageBaselineRepository"]
