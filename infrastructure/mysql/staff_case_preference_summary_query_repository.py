"""MySQL adapter for the Staff roster case-preference read projection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


_TOPIC_ORDER = (
    "service_regions",
    "service_periods",
    "rest_schedule",
    "baby_counts",
    "holiday_availability",
    "transportation",
)

_TOPIC_FACTS_SQL = """
SELECT 'service_regions' AS topic, region_name AS value, custom_region_detail AS other_detail
FROM staff_regions WHERE staff_id=%s
UNION ALL
SELECT 'service_periods' AS topic, slot_name AS value, custom_slot_detail AS other_detail
FROM staff_time_slots WHERE staff_id=%s
UNION ALL
SELECT 'rest_schedule' AS topic, rest_type AS value, custom_rest_detail AS other_detail
FROM staff_weekly_rest WHERE staff_id=%s
UNION ALL
SELECT 'baby_counts' AS topic, baby_type AS value, custom_baby_detail AS other_detail
FROM staff_baby_types WHERE staff_id=%s
UNION ALL
SELECT 'holiday_availability' AS topic, holiday_name AS value, custom_holiday_detail AS other_detail
FROM staff_holiday_availability WHERE staff_id=%s
UNION ALL
SELECT 'transportation' AS topic, vehicle_type AS value, NULL AS other_detail
FROM staff_transportation WHERE staff_id=%s
""".strip()


class MySqlStaffCasePreferenceSummaryQueryRepository:
    """Read-only adapter; it never owns connection lifecycle or transactions."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def fetch_topics(
        self,
        *,
        staff_id: int,
    ) -> Mapping[str, tuple[Mapping[str, object], ...]] | None:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT id FROM staff WHERE id=%s LIMIT 1", (staff_id,))
            if cursor.fetchone() is None:
                return None
            cursor.execute(_TOPIC_FACTS_SQL, (staff_id,) * len(_TOPIC_ORDER))
            rows = tuple(cursor.fetchall() or ())

        grouped: dict[str, list[Mapping[str, object]]] = {topic: [] for topic in _TOPIC_ORDER}
        for row in rows:
            if not isinstance(row, Mapping) or set(row) != {"topic", "value", "other_detail"}:
                raise ValueError("staff case-preference repository row fields are not canonical")
            raw_topic = row["topic"]
            if not isinstance(raw_topic, str) or raw_topic not in grouped:
                raise ValueError("staff case-preference repository topic is not canonical")
            grouped[raw_topic].append(
                {"value": row["value"], "other_detail": row["other_detail"]}
            )
        return {topic: tuple(grouped[topic]) for topic in _TOPIC_ORDER}


__all__ = ["MySqlStaffCasePreferenceSummaryQueryRepository"]
