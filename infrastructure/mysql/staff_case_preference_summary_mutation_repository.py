"""MySQL writer for the six Staff case-preference relation tables."""

from __future__ import annotations

from typing import Any

from infrastructure.mysql.staff_case_preference_summary_query_repository import (
    MySqlStaffCasePreferenceSummaryQueryRepository,
)
from subsystems.staff.case_preference_summary_mutation import StaffCasePreferenceSnapshot


class MySqlStaffCasePreferenceMutationRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._query = MySqlStaffCasePreferenceSummaryQueryRepository(connection)

    def fetch(self, staff_id: int):
        return self._query.fetch(staff_id)

    def lock_staff(self, staff_id: int) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT id FROM staff WHERE id=%s FOR UPDATE", (staff_id,))
            if cursor.fetchone() is None:
                raise ValueError("staff_not_found")

    def replace(self, staff_id: int, snapshot: StaffCasePreferenceSnapshot) -> None:
        with self._connection.cursor() as cursor:
            _replace_detail_topic(cursor, "staff_regions", "region_name", "custom_region_detail", staff_id, snapshot.service_regions)
            _replace_detail_topic(cursor, "staff_time_slots", "slot_name", "custom_slot_detail", staff_id, snapshot.service_periods)
            _replace_detail_topic(cursor, "staff_weekly_rest", "rest_type", "custom_rest_detail", staff_id, snapshot.rest_schedule)
            _replace_detail_topic(cursor, "staff_baby_types", "baby_type", "custom_baby_detail", staff_id, snapshot.baby_counts)
            _replace_detail_topic(cursor, "staff_holiday_availability", "holiday_name", "custom_holiday_detail", staff_id, snapshot.holiday_availability)
            cursor.execute("DELETE FROM staff_transportation WHERE staff_id=%s", (staff_id,))
            for value in snapshot.transportation.values:
                cursor.execute(
                    "INSERT INTO staff_transportation (staff_id,vehicle_type) VALUES (%s,%s)",
                    (staff_id, value),
                )


def _replace_detail_topic(cursor, table, value_column, detail_column, staff_id, topic) -> None:
    cursor.execute(f"DELETE FROM {table} WHERE staff_id=%s", (staff_id,))
    for value in topic.values:
        cursor.execute(
            f"INSERT INTO {table} (staff_id,{value_column},{detail_column}) VALUES (%s,%s,%s)",
            (staff_id, value, None),
        )
    if topic.other_detail is not None:
        cursor.execute(
            f"INSERT INTO {table} (staff_id,{value_column},{detail_column}) VALUES (%s,%s,%s)",
            (staff_id, "其他", topic.other_detail),
        )


__all__ = ["MySqlStaffCasePreferenceMutationRepository"]
