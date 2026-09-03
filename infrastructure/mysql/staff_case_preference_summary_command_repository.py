"""MySQL writer for the six Staff roster case-preference relation topics."""

from __future__ import annotations

from typing import Any

from subsystems.staff.case_preference_summary_command import (
    PreferenceTopicDraft,
    StaffCasePreferencePersistenceError,
    StaffCasePreferenceSnapshot,
)


_RELATION_SPECS = {
    "service_regions": ("staff_regions", "region_name", "custom_region_detail"),
    "service_periods": ("staff_time_slots", "slot_name", "custom_slot_detail"),
    "rest_schedule": ("staff_weekly_rest", "rest_type", "custom_rest_detail"),
    "baby_counts": ("staff_baby_types", "baby_type", "custom_baby_detail"),
    "holiday_availability": (
        "staff_holiday_availability",
        "holiday_name",
        "custom_holiday_detail",
    ),
    "transportation": ("staff_transportation", "vehicle_type", None),
}


class MySqlStaffCasePreferenceCommandRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def begin(self) -> None:
        self._connection.begin()

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def load(
        self,
        staff_id: int,
        *,
        lock: bool,
    ) -> StaffCasePreferenceSnapshot | None:
        suffix = " FOR UPDATE" if lock else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM staff WHERE id=%s LIMIT 1" + suffix,
                (staff_id,),
            )
            if cursor.fetchone() is None:
                return None

            topics: dict[str, PreferenceTopicDraft] = {}
            for key, (table_name, value_column, detail_column) in _RELATION_SPECS.items():
                columns = value_column
                if detail_column is not None:
                    columns += f",{detail_column}"
                cursor.execute(
                    f"SELECT {columns} FROM {table_name} WHERE staff_id=%s" + suffix,
                    (staff_id,),
                )
                topics[key] = _topic_from_rows(
                    cursor.fetchall() or (),
                    value_column=value_column,
                    detail_column=detail_column,
                )

        return StaffCasePreferenceSnapshot(
            service_regions=topics["service_regions"],
            service_periods=topics["service_periods"],
            rest_schedule=topics["rest_schedule"],
            baby_counts=topics["baby_counts"],
            holiday_availability=topics["holiday_availability"],
            transportation=topics["transportation"],
        )

    def replace(
        self,
        staff_id: int,
        snapshot: StaffCasePreferenceSnapshot,
    ) -> None:
        with self._connection.cursor() as cursor:
            for key, (table_name, value_column, detail_column) in _RELATION_SPECS.items():
                topic = getattr(snapshot, key)
                cursor.execute(
                    f"DELETE FROM {table_name} WHERE staff_id=%s",
                    (staff_id,),
                )
                rows = _rows_for_topic(staff_id, topic, detail_column is not None)
                if not rows:
                    continue
                columns = f"staff_id,{value_column}"
                placeholders = "%s,%s"
                if detail_column is not None:
                    columns += f",{detail_column}"
                    placeholders += ",%s"
                cursor.executemany(
                    f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})",
                    rows,
                )


def _topic_from_rows(
    rows: tuple[dict[str, object], ...] | list[dict[str, object]],
    *,
    value_column: str,
    detail_column: str | None,
) -> PreferenceTopicDraft:
    values: set[str] = set()
    details: set[str] = set()
    for row in rows:
        value = _optional_text(row.get(value_column))
        detail = _optional_text(row.get(detail_column)) if detail_column else None
        if value is not None and value != "其他":
            values.add(value)
        if detail is not None:
            details.add(detail)
    if len(details) > 1:
        raise StaffCasePreferencePersistenceError(
            "staff_case_preference_other_detail_ambiguous"
        )
    return PreferenceTopicDraft(
        values=tuple(sorted(values)),
        other_detail=next(iter(details), None),
    )


def _rows_for_topic(
    staff_id: int,
    topic: PreferenceTopicDraft,
    has_detail: bool,
) -> list[tuple[object, ...]]:
    if not has_detail:
        return [(staff_id, value) for value in topic.values]
    rows: list[tuple[object, ...]] = [
        (staff_id, value, None) for value in topic.values
    ]
    if topic.other_detail is not None:
        rows.append((staff_id, "其他", topic.other_detail))
    return rows


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = ["MySqlStaffCasePreferenceCommandRepository"]
