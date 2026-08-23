"""
File: weekly_operations_report_query_adapter.py
Description: 從 MySQL 唯讀取得營運週報案件、effective 正式排班與補助 owner 資料。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from subsystems.government_subsidy import reconciliation_register_query
from subsystems.reporting.weekly_operations_report_query import (
    SubsidyFact,
    SubsidyFacts,
    WeeklyCaseFact,
    WeeklyServiceFact,
)


class MySqlWeeklyOperationsReportQueryAdapter:
    def __init__(self, connection) -> None:
        self._connection = connection

    def list_case_facts(self, week_start: date, week_end: date) -> list[WeeklyCaseFact]:
        with self._connection.cursor() as cursor:
            cursor.execute(_CASE_FACTS_SQL, (week_start, week_end + timedelta(days=1)))
            rows = cursor.fetchall()
        return [
            WeeklyCaseFact(
                client_id=int(row["client_id"]),
                case_no=_optional_text(row.get("case_no")),
                created_at=_datetime(row["application_created_at"]),
                applicant_name=_optional_text(row.get("applicant_name")),
                identity_status=_optional_text(row.get("identity_status")),
                reject_reason=_optional_text(row.get("reject_reason")),
                district=_optional_text(row.get("district")),
                order_status=_optional_text(row.get("order_status")),
                service_days=_optional_int(row.get("service_days")),
                service_hours_per_day=_optional_int(row.get("service_hours_per_day")),
                planned_start_date=_optional_date(row.get("planned_start_date")),
                planned_end_date=_optional_date(row.get("planned_end_date")),
            )
            for row in rows
        ]

    def list_service_facts(self, week_start: date, week_end: date) -> list[WeeklyServiceFact]:
        with self._connection.cursor() as cursor:
            cursor.execute(_SERVICE_FACTS_SQL, (week_start, week_end))
            rows = cursor.fetchall()
        return [
            WeeklyServiceFact(
                assignment_id=int(row["assignment_id"]),
                case_no=str(row["case_no"]),
                client_name=_optional_text(row.get("client_name")),
                staff_name=_optional_text(row.get("staff_name")),
                service_start_date=_optional_date(row.get("service_start_date")),
                service_end_date=_optional_date(row.get("service_end_date")),
                service_hours_per_day=_optional_int(row.get("service_hours_per_day")),
                weekly_work_days=int(row["weekly_work_days"]),
                order_status=str(row["order_status"]),
                assignment_status=str(row["assignment_status"]),
            )
            for row in rows
        ]

    def list_subsidy_facts(self, application_year: int, cutoff_date: date) -> SubsidyFacts:
        report = reconciliation_register_query.build_year_to_date_subsidy_rows(
            application_year,
            cutoff_date,
        )
        return SubsidyFacts(
            general=tuple(_subsidy_fact(row) for row in report["general_citizen_rows"]),
            subsidized=tuple(_subsidy_fact(row) for row in report["subsidized_citizen_rows"]),
        )


def _subsidy_fact(row: dict[str, object]) -> SubsidyFact:
    return SubsidyFact(
        serial_number=int(row["序號"]),
        case_no=str(row["市府訂單號碼"]),
        eligibility=str(row["補助資格"]),
        service_start=_date(row["服務開始"]),
        service_end=_date(row["服務結束"]),
        subsidy_hours=Decimal(row["補助時數"]),
        subsidy_days=Decimal(row["補助天數"]),
        service_days=int(row["服務天數"]),
        subsidy_amount_ntd=int(Decimal(row["補助款金額"])),
        unit_price_ntd=int(Decimal(row["單價"])),
        employer_name=_optional_text(row.get("雇主")),
        staff_name=_optional_text(row.get("服務人員")),
        identity_card=_optional_text(row.get("身分證字號")),
        address=_optional_text(row.get("地址")),
    )


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_int(value: object) -> int | None:
    return None if value is None else int(value)


def _date(value: object) -> date:
    result = _optional_date(value)
    if result is None:
        raise ValueError("weekly_operations_report_date_invalid")
    return result


def _optional_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    return date.fromisoformat(str(value)[:10])


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    return datetime.fromisoformat(str(value))


_CASE_FACTS_SQL = """
SELECT c.id AS client_id,c.case_no,c.created_at AS application_created_at,
       c.name AS applicant_name,c.identity_status,c.reject_reason,c.city AS district,
       o.status AS order_status,o.service_days,o.service_hours_per_day,
       o.start_date AS planned_start_date,o.end_date AS planned_end_date
FROM clients c
LEFT JOIN orders o ON o.client_id=c.id AND o.case_no=c.case_no
WHERE c.created_at >= %s AND c.created_at < %s
ORDER BY c.created_at,c.id
"""

_SERVICE_FACTS_SQL = """
SELECT a.id AS assignment_id,a.case_no,c.name AS client_name,s.name AS staff_name,
       a.assigned_start_date AS service_start_date,
       a.assigned_end_date AS service_end_date,o.service_hours_per_day,
       COUNT(DISTINCT ss.work_date) AS weekly_work_days,
       o.status AS order_status,a.status AS assignment_status
FROM case_staff_assignments a
JOIN scheduling_generations g ON g.id=a.generation_id AND g.effective_marker=1
JOIN staff_schedule ss ON ss.assignment_id=a.id AND ss.generation_id=a.generation_id
    AND ss.effective_marker=1 AND ss.is_work_day=1
JOIN orders o ON o.case_no=a.case_no
JOIN clients c ON c.id=o.client_id
JOIN staff s ON s.id=a.staff_id
WHERE a.status NOT IN ('cancelled','replaced')
  AND ss.work_date >= %s AND ss.work_date <= %s
GROUP BY a.id,a.case_no,c.name,s.name,a.assigned_start_date,a.assigned_end_date,
         o.service_hours_per_day,o.status,a.status
ORDER BY a.id
"""


__all__ = ["MySqlWeeklyOperationsReportQueryAdapter"]
