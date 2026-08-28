"""
File: historical_baseline_scheduling_owner_adapter.py
Description: 讀取 Scheduling 歷史基準的正式日期、世代與服務事實。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time, timedelta
from typing import Any

from domains.orders.historical_operational_baseline import (
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    HistoricalBaselineOwnerObservation,
    HistoricalBaselineOwnerObservationV2,
    HistoricalBaselineOwnerRootDescriptor,
    HistoricalOrderIdentity,
)
from shared_kernel.clock import BusinessClock, SystemBusinessClock, TAIPEI_TIME_ZONE
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.validation import require_canonical_text
from subsystems.orders.historical_baseline_owner_vector import (
    HistoricalBaselineOwnerObservationReadback,
)


_DATE_DESCRIPTOR = next(
    descriptor
    for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    if descriptor.contract_id.endswith("scheduling.confirmed_service_date")
)
_GENERATION_DESCRIPTOR = next(
    descriptor
    for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    if descriptor.contract_id.endswith("scheduling.effective_generation")
)
_ASSIGNMENT_DATE_DESCRIPTOR = next(
    descriptor
    for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    if descriptor.contract_id.endswith("scheduling.assignment_official_date")
)
_OFFICIAL_SERVICE_DESCRIPTOR = next(
    descriptor
    for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    if descriptor.contract_id.endswith("scheduling.official_service")
)
_SUPPORTED_DESCRIPTORS = {
    descriptor.contract_id: descriptor
    for descriptor in (
        _DATE_DESCRIPTOR,
        _GENERATION_DESCRIPTOR,
        _ASSIGNMENT_DATE_DESCRIPTOR,
        _OFFICIAL_SERVICE_DESCRIPTOR,
    )
}
_ACTIVE_ASSIGNMENT_STATUSES = frozenset({"planned", "active", "completed"})
_IDENTITY_MAXIMUM_LENGTH = 191


_CONFIRMED_DATE_SQL = """
SELECT o.case_no AS order_case_no, o.service_days,
       v.id AS version_id, v.version AS confirmed_version, v.is_current
FROM orders o
LEFT JOIN confirmed_service_date_versions v
  ON v.case_no=o.case_no AND v.is_current=1
WHERE o.case_no=%s
"""

_CONFIRMED_DAYS_SQL = """
SELECT d.confirmed_version_id, d.ordinal, d.service_date
FROM confirmed_service_date_days d
WHERE d.confirmed_version_id=%s
ORDER BY d.ordinal
"""

_GENERATION_SQL = """
SELECT a.case_no AS aggregate_case_no,
       a.aggregate_version, a.effective_generation_id,
       g.id AS generation_id, g.case_no AS generation_case_no,
       g.resulting_aggregate_version, g.status AS generation_status,
       g.effective_marker,
       r.id AS rebuild_event_id, r.case_no AS rebuild_case_no,
       r.new_generation_id, r.expected_scheduling_version,
       r.resulting_scheduling_version
FROM scheduling_aggregates a
LEFT JOIN scheduling_generations g
  ON g.id=a.effective_generation_id AND g.case_no=a.case_no
LEFT JOIN scheduling_rebuild_events r
  ON r.new_generation_id=g.id AND r.case_no=g.case_no
WHERE a.case_no=%s
"""

_OFFICIAL_DATES_SQL = """
SELECT o.case_no AS order_case_no, o.service_days,
       o.service_start_time, o.service_end_time,
       o.service_end_day_offset,
       a.id AS assignment_id, a.case_no AS assignment_case_no,
       a.generation_id AS assignment_generation_id,
       a.staff_id AS assignment_staff_id, a.status AS assignment_status,
       a.assigned_start_date, a.assigned_end_date,
       s.id AS schedule_id, s.case_no AS schedule_case_no,
       s.generation_id AS schedule_generation_id,
       s.assignment_id AS schedule_assignment_id,
       s.staff_id AS schedule_staff_id, s.work_date,
       s.effective_marker AS schedule_effective_marker,
       s.is_work_day AS schedule_is_work_day,
       g.id AS generation_id, g.status AS generation_status,
       g.effective_marker AS generation_effective_marker,
       aroot.effective_generation_id, aroot.aggregate_version,
       r.id AS rebuild_event_id, r.resulting_scheduling_version
FROM orders o
JOIN scheduling_aggregates aroot ON aroot.case_no=o.case_no
JOIN scheduling_generations g
  ON g.id=aroot.effective_generation_id AND g.case_no=o.case_no
LEFT JOIN scheduling_rebuild_events r
  ON r.new_generation_id=g.id AND r.case_no=g.case_no
JOIN case_staff_assignments a
  ON a.case_no=o.case_no AND a.generation_id=g.id
JOIN staff_schedule s
  ON s.case_no=o.case_no AND s.generation_id=g.id
 AND s.assignment_id=a.id
WHERE o.case_no=%s
  AND s.effective_marker=1 AND s.is_work_day=1
ORDER BY s.work_date, s.id, a.id
"""


class MySqlHistoricalBaselineSchedulingOwnerAdapter:
    """Borrow a caller-owned connection to read Scheduling observations only."""

    owner_domain = "scheduling"

    def __init__(self, connection: Any, clock: BusinessClock | None = None) -> None:
        self._connection = connection
        self._clock = clock or SystemBusinessClock()

    def read_owner_observations(
        self,
        identity: HistoricalOrderIdentity,
        descriptor: HistoricalBaselineOwnerRootDescriptor,
        *,
        for_update: bool = False,
    ) -> HistoricalBaselineOwnerObservationReadback:
        if not isinstance(identity, HistoricalOrderIdentity):
            raise TypeError("historical baseline scheduling identity is invalid")
        expected = (
            _SUPPORTED_DESCRIPTORS.get(descriptor.contract_id)
            if isinstance(descriptor, HistoricalBaselineOwnerRootDescriptor)
            else None
        )
        if expected is None or descriptor != expected or descriptor.owner_domain != self.owner_domain:
            raise ValueError("historical_baseline_scheduling_descriptor_unsupported")
        if not isinstance(for_update, bool):
            raise TypeError("historical baseline scheduling lock mode is invalid")
        if descriptor == _DATE_DESCRIPTOR:
            observations = self._confirmed_dates(identity, for_update=for_update)
        elif descriptor == _GENERATION_DESCRIPTOR:
            observations = self._effective_generation(identity, for_update=for_update)
        elif descriptor == _ASSIGNMENT_DATE_DESCRIPTOR:
            observations = self._assignment_dates(identity, for_update=for_update)
        else:
            observations = self._official_service(identity, for_update=for_update)
        return HistoricalBaselineOwnerObservationReadback(identity, observations)

    def _confirmed_dates(
        self, identity: HistoricalOrderIdentity, *, for_update: bool
    ) -> tuple[HistoricalBaselineOwnerObservation, ...]:
        suffix = _lock_suffix(for_update)
        with self._connection.cursor() as cursor:
            cursor.execute(_CONFIRMED_DATE_SQL + suffix, (identity.case_no,))
            try:
                roots = _rows(cursor.fetchall())
            except (TypeError, ValueError):
                return (
                    _unavailable(
                        _DATE_DESCRIPTOR,
                        identity,
                        "scheduling_confirmed_service_date_malformed",
                    ),
                )
            if len(roots) != 1:
                return (_unavailable(_DATE_DESCRIPTOR, identity, "scheduling_confirmed_service_date_unavailable"),)
            root = roots[0]
            if root.get("order_case_no") != identity.case_no:
                return (_unavailable(_DATE_DESCRIPTOR, identity, "scheduling_confirmed_service_date_cross_case"),)
            expected_days = _positive_int(root.get("service_days"))
            version_id = _positive_int(root.get("version_id"))
            version = _nonnegative_int(root.get("confirmed_version"))
            if expected_days is None or version_id is None or version is None or root.get("is_current") != 1:
                return (_unavailable(_DATE_DESCRIPTOR, identity, "scheduling_confirmed_service_date_missing"),)
            cursor.execute(_CONFIRMED_DAYS_SQL + suffix, (version_id,))
            try:
                days = _rows(cursor.fetchall())
            except (TypeError, ValueError):
                return (
                    _unavailable(
                        _DATE_DESCRIPTOR,
                        identity,
                        "scheduling_confirmed_service_date_malformed",
                    ),
                )
        if len(days) != expected_days:
            return (_unavailable(_DATE_DESCRIPTOR, identity, "scheduling_confirmed_service_date_count_drift"),)
        values: list[tuple[date, int]] = []
        for row in days:
            if row.get("confirmed_version_id") != version_id:
                return (_unavailable(_DATE_DESCRIPTOR, identity, "scheduling_confirmed_service_date_cross_case"),)
            value = _as_date(row.get("service_date"))
            ordinal = _positive_int(row.get("ordinal"))
            if value is None or ordinal is None:
                return (_unavailable(_DATE_DESCRIPTOR, identity, "scheduling_confirmed_service_date_malformed"),)
            values.append((value, ordinal))
        if {ordinal for _value, ordinal in values} != set(range(1, expected_days + 1)):
            return (_unavailable(_DATE_DESCRIPTOR, identity, "scheduling_confirmed_service_date_ordinal_drift"),)
        dates = [value for value, _ordinal in values]
        if len(set(dates)) != len(dates):
            return (_unavailable(_DATE_DESCRIPTOR, identity, "scheduling_confirmed_service_date_duplicate"),)
        values.sort(key=lambda item: (item[0], item[1]))
        return tuple(
            _available(
                _DATE_DESCRIPTOR,
                identity.case_no,
                f"scheduling.confirmed_service_date:{identity.case_no}:v{version}:{value.isoformat()}",
                f"scheduling.confirmed_service_date_version:{version_id}",
                version,
                True,
            )
            for value, _ordinal in values
        )

    def _effective_generation(
        self, identity: HistoricalOrderIdentity, *, for_update: bool
    ) -> tuple[HistoricalBaselineOwnerObservation, ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(_GENERATION_SQL + _lock_suffix(for_update), (identity.case_no,))
            try:
                rows = _rows(cursor.fetchall())
            except (TypeError, ValueError):
                return (
                    _unavailable(
                        _GENERATION_DESCRIPTOR,
                        identity,
                        "scheduling_effective_generation_malformed",
                    ),
                )
        if len(rows) != 1:
            return (_unavailable(_GENERATION_DESCRIPTOR, identity, "scheduling_effective_generation_unavailable"),)
        row = rows[0]
        aggregate_case = row.get("aggregate_case_no")
        generation_case = row.get("generation_case_no")
        rebuild_case = row.get("rebuild_case_no")
        effective_id = _positive_int(row.get("effective_generation_id"))
        generation_id = _positive_int(row.get("generation_id"))
        aggregate_version = _nonnegative_int(row.get("aggregate_version"))
        resulting_generation_version = _nonnegative_int(row.get("resulting_aggregate_version"))
        event_id = _positive_int(row.get("rebuild_event_id"))
        event_generation = _positive_int(row.get("new_generation_id"))
        expected_version = _nonnegative_int(row.get("expected_scheduling_version"))
        resulting_version = _nonnegative_int(row.get("resulting_scheduling_version"))
        if (
            aggregate_case != identity.case_no
            or generation_case != identity.case_no
            or rebuild_case != identity.case_no
            or None in (effective_id, generation_id, aggregate_version, resulting_generation_version,
                        event_id, event_generation, expected_version, resulting_version)
            or effective_id != generation_id
            or event_generation != generation_id
            or row.get("generation_status") != "effective"
            or row.get("effective_marker") != 1
            or resulting_generation_version != aggregate_version
            or expected_version + 1 != resulting_version
            or resulting_version != aggregate_version
        ):
            return (_unavailable(_GENERATION_DESCRIPTOR, identity, "scheduling_effective_generation_incomplete"),)
        return (
            _available(
                _GENERATION_DESCRIPTOR,
                identity.case_no,
                f"scheduling.effective_generation:{identity.case_no}:{generation_id}",
                f"scheduling.rebuild_event:{event_id}",
                resulting_version,
                True,
            ),
        )

    def _assignment_dates(
        self, identity: HistoricalOrderIdentity, *, for_update: bool
    ) -> tuple[HistoricalBaselineOwnerObservation, ...]:
        try:
            rows = self._official_rows(identity, for_update=for_update)
            valid, details = _validate_official_rows(identity, rows)
            if valid:
                rows = tuple(
                    sorted(
                        rows,
                        key=lambda row: (
                            _date_text(row["work_date"]), row["schedule_id"]
                        ),
                    )
                )
        except (TypeError, ValueError):
            valid, details = False, "scheduling_assignment_official_date_malformed"
        if not valid:
            return (_unavailable(_ASSIGNMENT_DATE_DESCRIPTOR, identity, details),)
        return tuple(
            _available(
                _ASSIGNMENT_DATE_DESCRIPTOR,
                identity.case_no,
                f"scheduling.assignment:{row['assignment_id']}:official-date:{_date_text(row['work_date'])}",
                f"scheduling.staff_schedule:{row['schedule_id']}",
                _positive_int(row["schedule_id"]),
                True,
            )
            for row in rows
        )

    def _official_service(
        self, identity: HistoricalOrderIdentity, *, for_update: bool
    ) -> tuple[HistoricalBaselineOwnerObservation, ...]:
        try:
            rows = self._official_rows(identity, for_update=for_update)
            valid, details = _validate_official_rows(identity, rows)
            if valid:
                rows = tuple(
                    sorted(
                        rows,
                        key=lambda row: (
                            _date_text(row["work_date"]), row["schedule_id"]
                        ),
                    )
                )
        except (TypeError, ValueError):
            valid, details = False, "scheduling_assignment_official_date_malformed"
        if not valid:
            return (_unavailable(_OFFICIAL_SERVICE_DESCRIPTOR, identity, details),)
        dates = tuple(sorted({_as_date(row["work_date"]) for row in rows}))
        start_time = _as_time(rows[0].get("service_start_time"))
        end_time = _as_time(rows[0].get("service_end_time"))
        end_offset = rows[0].get("service_end_day_offset")
        if start_time is None or end_time is None or end_offset not in (0, 1):
            return (_unavailable(_OFFICIAL_SERVICE_DESCRIPTOR, identity, "scheduling_official_service_time_missing"),)
        now = self._clock.now()
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise TypeError("business clock must return timezone-aware datetime")
        now_local = now.astimezone(TAIPEI_TIME_ZONE)
        end_moments = tuple(
            datetime.combine(value, end_time).replace(tzinfo=TAIPEI_TIME_ZONE)
            for value in dates
        )
        if end_offset:
            end_moments = tuple(
                moment + timedelta(days=end_offset) for moment in end_moments
            )
        terminal = bool(end_moments and now_local >= max(end_moments))
        generation_id = _positive_int(rows[0].get("effective_generation_id"))
        if generation_id is None:
            return (
                _unavailable(
                    _OFFICIAL_SERVICE_DESCRIPTOR,
                    identity,
                    "scheduling_official_service_generation_missing",
                ),
            )
        digest = fingerprint_payload(
            {
                "case_no": identity.case_no,
                "generation_id": generation_id,
                "official_service": tuple(
                    (
                        _date_text(row["work_date"]),
                        _positive_int(row["assignment_id"]),
                        _positive_int(row["schedule_staff_id"]),
                        _positive_int(row["schedule_id"]),
                    )
                    for row in rows
                ),
            }
        ).value
        schedule_source_versions = tuple(
            _positive_int(row["schedule_id"]) for row in rows
        )
        source_version = max(schedule_source_versions)
        return (
            _available(
                _OFFICIAL_SERVICE_DESCRIPTOR,
                identity.case_no,
                f"scheduling.official_service:{identity.case_no}:{digest}",
                f"scheduling.staff_schedule_set:{digest}",
                source_version,
                terminal,
            ),
        )

    def _official_rows(self, identity: HistoricalOrderIdentity, *, for_update: bool) -> tuple[Mapping[str, Any], ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(_OFFICIAL_DATES_SQL + _lock_suffix(for_update), (identity.case_no,))
            return _rows(cursor.fetchall())


def _lock_suffix(for_update: bool) -> str:
    return " FOR UPDATE" if for_update else ""


def _rows(value: object) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (tuple, list)) or any(not isinstance(row, Mapping) for row in value):
        raise ValueError("historical_baseline_scheduling_rows_invalid")
    return tuple(value)


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def _nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _as_date(value: object) -> date | None:
    return value if isinstance(value, date) and not isinstance(value, datetime) else None


def _as_time(value: object) -> time | None:
    return value if isinstance(value, time) else None


def _date_text(value: object) -> str:
    parsed = _as_date(value)
    if parsed is None:
        raise ValueError("historical_baseline_scheduling_date_invalid")
    return parsed.isoformat()


def _available(
    descriptor: HistoricalBaselineOwnerRootDescriptor,
    case_no: str,
    root_identity: str,
    event_identity: str,
    source_version: int | None,
    terminal: bool,
) -> HistoricalBaselineOwnerObservation:
    require_canonical_text(root_identity, "historical scheduling root identity", _IDENTITY_MAXIMUM_LENGTH)
    require_canonical_text(event_identity, "historical scheduling event identity", _IDENTITY_MAXIMUM_LENGTH)
    if source_version is None or source_version < 0:
        raise ValueError("historical_baseline_scheduling_source_version_invalid")
    return HistoricalBaselineOwnerObservationV2(
        descriptor, root_identity, event_identity, source_version, terminal, None, case_no
    )


def _unavailable(
    descriptor: HistoricalBaselineOwnerRootDescriptor,
    identity: HistoricalOrderIdentity,
    code: str,
) -> HistoricalBaselineOwnerObservation:
    return HistoricalBaselineOwnerObservation.unavailable(
        descriptor, code=code, case_no=identity.case_no
    )


def _validate_official_rows(
    identity: HistoricalOrderIdentity, rows: tuple[Mapping[str, Any], ...]
) -> tuple[bool, str]:
    if not rows:
        return False, "scheduling_assignment_official_date_missing"
    order_case = _safe_set(row.get("order_case_no") for row in rows)
    if order_case is None:
        return False, "scheduling_assignment_official_date_malformed"
    if order_case != {identity.case_no}:
        return False, "scheduling_assignment_official_date_cross_case"
    service_days = _safe_set(_positive_int(row.get("service_days")) for row in rows)
    if service_days is None:
        return False, "scheduling_assignment_official_date_malformed"
    if len(service_days) != 1 or None in service_days:
        return False, "scheduling_assignment_official_date_service_days_invalid"
    expected_days = next(iter(service_days))
    dates = [_as_date(row.get("work_date")) for row in rows]
    if any(value is None for value in dates):
        return False, "scheduling_assignment_official_date_malformed"
    if len(dates) != expected_days or len(set(dates)) != expected_days:
        return False, "scheduling_assignment_official_date_count_drift"
    generation_ids = _safe_set(_positive_int(row.get("effective_generation_id")) for row in rows)
    aggregate_versions = _safe_set(_nonnegative_int(row.get("aggregate_version")) for row in rows)
    if generation_ids is None or aggregate_versions is None:
        return False, "scheduling_assignment_official_date_malformed"
    if (
        len(generation_ids) != 1
        or None in generation_ids
        or len(aggregate_versions) != 1
        or None in aggregate_versions
    ):
        return False, "scheduling_assignment_official_date_ambiguous"
    generation_row_ids = _safe_set(_positive_int(row.get("generation_id")) for row in rows)
    generation_statuses = _safe_set(row.get("generation_status") for row in rows)
    generation_markers = _safe_set(row.get("generation_effective_marker") for row in rows)
    if generation_row_ids is None or generation_statuses is None or generation_markers is None:
        return False, "scheduling_assignment_official_date_malformed"
    if (
        generation_row_ids != generation_ids
        or generation_statuses != {"effective"}
        or generation_markers != {1}
    ):
        return False, "scheduling_assignment_official_date_generation_invalid"
    service_time_tuples = _safe_set(
        (
            row.get("service_start_time"),
            row.get("service_end_time"),
            row.get("service_end_day_offset"),
        )
        for row in rows
    )
    if service_time_tuples is None:
        return False, "scheduling_assignment_official_date_malformed"
    if len(service_time_tuples) != 1:
        return False, "scheduling_assignment_official_date_service_time_ambiguous"
    seen_dates: set[date] = set()
    for row, value in zip(rows, dates):
        assignment_id = _positive_int(row.get("assignment_id"))
        schedule_id = _positive_int(row.get("schedule_id"))
        generation_id = _positive_int(row.get("effective_generation_id"))
        if assignment_id is None or schedule_id is None or generation_id is None:
            return False, "scheduling_assignment_official_date_identity_invalid"
        if row.get("assignment_case_no") != identity.case_no or row.get("schedule_case_no") != identity.case_no:
            return False, "scheduling_assignment_official_date_cross_case"
        if row.get("assignment_generation_id") != generation_id or row.get("schedule_generation_id") != generation_id:
            return False, "scheduling_assignment_official_date_generation_mismatch"
        if row.get("schedule_assignment_id") != assignment_id:
            return False, "scheduling_assignment_official_date_owner_missing"
        if row.get("assignment_status") not in _ACTIVE_ASSIGNMENT_STATUSES:
            return False, "scheduling_assignment_official_date_assignment_cancelled"
        if row.get("schedule_effective_marker") != 1 or row.get("schedule_is_work_day") != 1:
            return False, "scheduling_assignment_official_date_not_effective"
        assignment_staff_id = _positive_int(row.get("assignment_staff_id"))
        schedule_staff_id = _positive_int(row.get("schedule_staff_id"))
        if assignment_staff_id is None or schedule_staff_id is None:
            return False, "scheduling_assignment_official_date_staff_identity_invalid"
        if schedule_staff_id != assignment_staff_id:
            return False, "scheduling_assignment_official_date_owner_mismatch"
        start = _as_date(row.get("assigned_start_date"))
        end = _as_date(row.get("assigned_end_date"))
        if start is None or end is None or start > end or value < start or value > end:
            return False, "scheduling_assignment_official_date_outside_assignment"
        if value in seen_dates:
            return False, "scheduling_assignment_official_date_duplicate"
        seen_dates.add(value)
    return True, ""


def _safe_set(values: Any) -> set[Any] | None:
    try:
        return set(values)
    except TypeError:
        return None


HistoricalBaselineSchedulingOwnerAdapter = MySqlHistoricalBaselineSchedulingOwnerAdapter


__all__ = [
    "HistoricalBaselineSchedulingOwnerAdapter",
    "MySqlHistoricalBaselineSchedulingOwnerAdapter",
]
