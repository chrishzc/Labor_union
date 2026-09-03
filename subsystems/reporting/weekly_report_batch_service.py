"""
File: weekly_report_batch_service.py
Description: 營運週報結算批次與案件封存管理服務 (方案 C)，支援批次指標儲存、未結算案件查詢與封存綁定。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from shared_kernel.clock import TAIPEI_TIME_ZONE


@dataclass(frozen=True, slots=True)
class WeeklyBatchRecord:
    id: int
    year: int
    week_code: str
    cutoff_at: datetime
    promotion_count: int
    inquiry_count: int
    notes: str | None
    case_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class UnclosedCaseRecord:
    case_no: str
    applicant_name: str
    created_at: datetime | None
    order_status: str | None
    service_days: int | None
    service_hours_per_day: int | None


class WeeklyReportBatchService:
    def __init__(self, connection) -> None:
        self._conn = connection

    def list_batches(self, year: int) -> list[WeeklyBatchRecord]:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT b.id, b.year, b.week_code, b.cutoff_at,
                       b.promotion_count, b.inquiry_count, b.notes,
                       COUNT(bc.case_no) AS case_count,
                       b.created_at, b.updated_at
                FROM weekly_report_batches b
                LEFT JOIN weekly_report_batch_cases bc ON bc.batch_id = b.id
                WHERE b.year = %s
                GROUP BY b.id, b.year, b.week_code, b.cutoff_at,
                         b.promotion_count, b.inquiry_count, b.notes,
                         b.created_at, b.updated_at
                ORDER BY b.id ASC
                """,
                (year,),
            )
            rows = cur.fetchall()
            return [
                WeeklyBatchRecord(
                    id=r["id"],
                    year=r["year"],
                    week_code=r["week_code"],
                    cutoff_at=r["cutoff_at"],
                    promotion_count=r["promotion_count"],
                    inquiry_count=r["inquiry_count"],
                    notes=r["notes"],
                    case_count=r["case_count"],
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
                for r in rows
            ]

    def get_weekly_metrics_map(self, year: int) -> dict[str, tuple[int, int]]:
        """回傳 week_code -> (promotion_count, inquiry_count) 的對應字典。"""
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT week_code, promotion_count, inquiry_count
                FROM weekly_report_batches
                WHERE year = %s
                """,
                (year,),
            )
            return {
                r["week_code"]: (r["promotion_count"], r["inquiry_count"])
                for r in cur.fetchall()
            }

    def get_unclosed_cases(self, year: int | None = None) -> list[UnclosedCaseRecord]:
        with self._conn.cursor() as cur:
            sql = """
                SELECT o.case_no, c.name AS applicant_name, o.created_at,
                       o.status AS order_status, o.service_days, o.service_hours_per_day
                FROM orders o
                LEFT JOIN clients c ON c.id = o.client_id
                LEFT JOIN weekly_report_batch_cases bc ON bc.case_no = o.case_no
                WHERE bc.case_no IS NULL
            """
            params: list[Any] = []
            if year:
                sql += " AND (YEAR(o.created_at) = %s OR o.created_at IS NULL)"
                params.append(year)
            sql += " ORDER BY o.created_at ASC, o.case_no ASC"
            cur.execute(sql, tuple(params))
            return [
                UnclosedCaseRecord(
                    case_no=r["case_no"],
                    applicant_name=r["applicant_name"] or "—",
                    created_at=r["created_at"],
                    order_status=r["order_status"],
                    service_days=r["service_days"],
                    service_hours_per_day=r["service_hours_per_day"],
                )
                for r in cur.fetchall()
            ]

    def close_batch(
        self,
        year: int,
        week_code: str,
        promotion_count: int = 0,
        inquiry_count: int = 0,
        case_nos: list[str] | None = None,
        notes: str | None = None,
        cutoff_at: datetime | None = None,
    ) -> WeeklyBatchRecord:
        now = cutoff_at or datetime.now(TAIPEI_TIME_ZONE).replace(tzinfo=None)
        with self._conn.cursor() as cur:
            # 1. 建立或更新批次
            cur.execute(
                """
                INSERT INTO weekly_report_batches (year, week_code, cutoff_at, promotion_count, inquiry_count, notes, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    cutoff_at = VALUES(cutoff_at),
                    promotion_count = VALUES(promotion_count),
                    inquiry_count = VALUES(inquiry_count),
                    notes = VALUES(notes),
                    updated_at = VALUES(updated_at)
                """,
                (year, week_code, now, promotion_count, inquiry_count, notes, now, now),
            )
            # 取得 batch id
            cur.execute(
                "SELECT id FROM weekly_report_batches WHERE year = %s AND week_code = %s",
                (year, week_code),
            )
            batch_id = cur.fetchone()["id"]

            # 2. 決定要綁定的案件
            if case_nos is None:
                # 若未指定 case_nos，自動將當前所有未結算且建立時間在 cutoff_at 之前的案件綁定進來
                cur.execute(
                    """
                    SELECT o.case_no
                    FROM orders o
                    LEFT JOIN weekly_report_batch_cases bc ON bc.case_no = o.case_no
                    WHERE bc.case_no IS NULL
                      AND (o.created_at <= %s OR o.created_at IS NULL)
                    """,
                    (now,),
                )
                case_nos = [r["case_no"] for r in cur.fetchall()]

            for c_no in case_nos:
                cur.execute(
                    """
                    INSERT INTO weekly_report_batch_cases (case_no, batch_id, bound_at)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE batch_id = VALUES(batch_id), bound_at = VALUES(bound_at)
                    """,
                    (c_no, batch_id, now),
                )
        self._conn.commit()

        # 重新讀取並回傳
        batches = self.list_batches(year)
        for b in batches:
            if b.id == batch_id:
                return b
        raise RuntimeError("Failed to retrieve closed batch")

    def update_batch_metrics(
        self,
        batch_id: int,
        promotion_count: int,
        inquiry_count: int,
        week_code: str | None = None,
        notes: str | None = None,
    ) -> WeeklyBatchRecord:
        now = datetime.now(TAIPEI_TIME_ZONE).replace(tzinfo=None)
        with self._conn.cursor() as cur:
            sql = "UPDATE weekly_report_batches SET promotion_count = %s, inquiry_count = %s, updated_at = %s"
            params: list[Any] = [promotion_count, inquiry_count, now]
            if week_code is not None:
                sql += ", week_code = %s"
                params.append(week_code)
            if notes is not None:
                sql += ", notes = %s"
                params.append(notes)
            sql += " WHERE id = %s"
            params.append(batch_id)
            cur.execute(sql, tuple(params))
            cur.execute("SELECT year FROM weekly_report_batches WHERE id = %s", (batch_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError("batch_not_found")
            year = row["year"]
        self._conn.commit()

        batches = self.list_batches(year)
        for b in batches:
            if b.id == batch_id:
                return b
        raise RuntimeError("Batch not found after update")


__all__ = ["WeeklyReportBatchService", "WeeklyBatchRecord", "UnclosedCaseRecord"]
