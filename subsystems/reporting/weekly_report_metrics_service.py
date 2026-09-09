"""
File: weekly_report_metrics_service.py
Description: 管理星期一至星期日的每週推廣次數與詢問人次。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


_TAIPEI = ZoneInfo("Asia/Taipei")


@dataclass(frozen=True, slots=True)
class WeeklyReportMetric:
    week_start_date: date
    week_end_date: date
    promotion_count: int | None
    inquiry_count: int | None
    updated_at: datetime | None = None


def monday_of(value: date) -> date:
    return value - timedelta(days=value.weekday())


def sunday_of(value: date) -> date:
    return monday_of(value) + timedelta(days=6)


def week_label(value: date) -> str:
    start = monday_of(value)
    return f"{start.isoformat()} ~ {(start + timedelta(days=6)).isoformat()}"


def week_starts_between(start_date: date, end_date: date) -> tuple[date, ...]:
    if start_date > end_date:
        raise ValueError("weekly_report_metric_date_range_invalid")
    first = monday_of(start_date)
    last = monday_of(end_date)
    result: list[date] = []
    current = first
    while current <= last:
        result.append(current)
        current += timedelta(days=7)
    return tuple(result)


class WeeklyReportMetricsService:
    def __init__(self, connection) -> None:
        self._connection = connection

    def list_metrics(self, start_date: date, end_date: date) -> list[WeeklyReportMetric]:
        week_starts = week_starts_between(start_date, end_date)
        if not week_starts:
            return []
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT week_start_date, promotion_count, inquiry_count, updated_at
                FROM weekly_report_metrics
                WHERE week_start_date >= %s AND week_start_date <= %s
                ORDER BY week_start_date ASC
                """,
                (week_starts[0], week_starts[-1]),
            )
            stored = {row["week_start_date"]: row for row in cursor.fetchall()}
        result: list[WeeklyReportMetric] = []
        for week_start in week_starts:
            row = stored.get(week_start)
            result.append(
                WeeklyReportMetric(
                    week_start_date=week_start,
                    week_end_date=week_start + timedelta(days=6),
                    promotion_count=row["promotion_count"] if row else None,
                    inquiry_count=row["inquiry_count"] if row else None,
                    updated_at=_taipei_datetime(row["updated_at"]) if row else None,
                )
            )
        return result

    def save_metric(
        self,
        week_start_date: date,
        promotion_count: int | None,
        inquiry_count: int | None,
    ) -> WeeklyReportMetric:
        if week_start_date.weekday() != 0:
            raise ValueError("weekly_report_metric_start_must_be_monday")
        if promotion_count is not None and promotion_count < 0:
            raise ValueError("weekly_report_metric_promotion_invalid")
        if inquiry_count is not None and inquiry_count < 0:
            raise ValueError("weekly_report_metric_inquiry_invalid")
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO weekly_report_metrics
                        (week_start_date, promotion_count, inquiry_count)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        promotion_count = VALUES(promotion_count),
                        inquiry_count = VALUES(inquiry_count),
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (week_start_date, promotion_count, inquiry_count),
                )
                cursor.execute(
                    """
                    SELECT week_start_date, promotion_count, inquiry_count, updated_at
                    FROM weekly_report_metrics
                    WHERE week_start_date = %s
                    """,
                    (week_start_date,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise RuntimeError("weekly_report_metric_save_not_visible")
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise
        return WeeklyReportMetric(
            week_start_date=row["week_start_date"],
            week_end_date=sunday_of(row["week_start_date"]),
            promotion_count=row["promotion_count"],
            inquiry_count=row["inquiry_count"],
            updated_at=_taipei_datetime(row["updated_at"]),
        )


def _taipei_datetime(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=_TAIPEI)


__all__ = [
    "WeeklyReportMetric",
    "WeeklyReportMetricsService",
    "monday_of",
    "sunday_of",
    "week_label",
    "week_starts_between",
]
