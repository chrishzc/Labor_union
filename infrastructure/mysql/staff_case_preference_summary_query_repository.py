"""MySQL adapter for the bounded Staff case-preference read projection."""

from __future__ import annotations

from typing import Any

from subsystems.staff.case_preference_summary_query import (
    PreferenceTopicFacts,
    StaffCasePreferenceFacts,
)


class MySqlStaffCasePreferenceSummaryQueryRepository:
    """Read Staff-owned relation facts without owning connection lifecycle."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def fetch(self, staff_id: int) -> StaffCasePreferenceFacts | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM staff WHERE id=%s LIMIT 1",
                (staff_id,),
            )
            if cursor.fetchone() is None:
                return None

            return StaffCasePreferenceFacts(
                staff_id=staff_id,
                service_regions=_fetch_topic(
                    cursor,
                    "SELECT region_name,custom_region_detail "
                    "FROM staff_regions WHERE staff_id=%s",
                    staff_id,
                    value_column="region_name",
                    detail_column="custom_region_detail",
                ),
                service_periods=_fetch_topic(
                    cursor,
                    "SELECT slot_name,custom_slot_detail "
                    "FROM staff_time_slots WHERE staff_id=%s",
                    staff_id,
                    value_column="slot_name",
                    detail_column="custom_slot_detail",
                ),
                rest_schedule=_fetch_topic(
                    cursor,
                    "SELECT rest_type,custom_rest_detail "
                    "FROM staff_weekly_rest WHERE staff_id=%s",
                    staff_id,
                    value_column="rest_type",
                    detail_column="custom_rest_detail",
                ),
                baby_counts=_fetch_topic(
                    cursor,
                    "SELECT baby_type,custom_baby_detail "
                    "FROM staff_baby_types WHERE staff_id=%s",
                    staff_id,
                    value_column="baby_type",
                    detail_column="custom_baby_detail",
                ),
                holiday_availability=_fetch_topic(
                    cursor,
                    "SELECT holiday_name,custom_holiday_detail "
                    "FROM staff_holiday_availability WHERE staff_id=%s",
                    staff_id,
                    value_column="holiday_name",
                    detail_column="custom_holiday_detail",
                ),
                transportation=_fetch_topic(
                    cursor,
                    "SELECT vehicle_type FROM staff_transportation WHERE staff_id=%s",
                    staff_id,
                    value_column="vehicle_type",
                ),
            )


def _fetch_topic(
    cursor: Any,
    sql: str,
    staff_id: int,
    *,
    value_column: str,
    detail_column: str | None = None,
) -> PreferenceTopicFacts:
    cursor.execute(sql, (staff_id,))
    rows = cursor.fetchall() or ()
    values: list[str] = []
    other_details: list[str] = []
    for row in rows:
        value = _optional_text(row.get(value_column))
        if value is not None:
            values.append(value)
        if detail_column is not None:
            detail = _optional_text(row.get(detail_column))
            if detail is not None:
                other_details.append(detail)
    return PreferenceTopicFacts(tuple(values), tuple(other_details))


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = ["MySqlStaffCasePreferenceSummaryQueryRepository"]
