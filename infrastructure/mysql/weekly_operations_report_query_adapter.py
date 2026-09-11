"""
File: weekly_operations_report_query_adapter.py
Description: 從 MySQL 唯讀取得營運週報案件、effective 正式排班與當年度補助 owner 資料。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.government_subsidy import reconciliation_register_query
from subsystems.reporting.weekly_operations_report_query import (
    SubsidyFact,
    SubsidyFacts,
    WeeklyCaseFact,
    WeeklyServiceFact,
)
from subsystems.reporting.weekly_report_metrics_service import (
    WeeklyReportMetric,
    WeeklyReportMetricsService,
)


class MySqlWeeklyOperationsReportQueryAdapter:
    def __init__(self, connection) -> None:
        self._connection = connection

    def list_case_facts(self, start_date: date, end_date: date) -> list[WeeklyCaseFact]:
        with self._connection.cursor() as cursor:
            cursor.execute(_CASE_FACTS_SQL, (start_date, end_date + timedelta(days=1)))
            rows = cursor.fetchall()
        return [
            WeeklyCaseFact(
                client_id=int(row["client_id"]),
                case_no=_optional_text(row.get("case_no")),
                created_at=_datetime(row["application_created_at"]),
                applicant_name=_optional_text(row.get("applicant_name")),
                identity_status=_optional_text(row.get("identity_status")),
                reject_reason=_optional_text(row.get("reject_reason")),
                district=_hsinchu_district_or_address(row.get("city"), row.get("address")),
                order_status=_optional_text(row.get("order_status")),
                service_days=_optional_int(row.get("service_days")),
                service_hours_per_day=_optional_int(row.get("service_hours_per_day")),
                planned_start_date=_optional_date(row.get("planned_start_date")),
                planned_end_date=_optional_date(row.get("planned_end_date")),
                seq_num=_optional_int(row.get("seq_num")),
            )
            for row in rows
        ]

    def list_service_facts(self, start_date: date, end_date: date) -> list[WeeklyServiceFact]:
        with self._connection.cursor() as cursor:
            cursor.execute(_SERVICE_FACTS_SQL, (start_date, end_date))
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
                week_start_date=_date(row["week_start_date"]),
                week_end_date=_date(row["week_end_date"]),
                order_status=str(row["order_status"]),
                assignment_status=str(row["assignment_status"]),
                weekly_rest_days=_json_rest_days(row.get("weekly_rest_days")),
            )
            for row in rows
        ]

    def list_subsidy_facts(self, start_date: date, end_date: date) -> SubsidyFacts:
        del start_date
        report = reconciliation_register_query.build_operations_report_annual_subsidy_rows(
            end_date.year,
            get_connection,
        )
        return SubsidyFacts(
            general=tuple(_subsidy_fact(row) for row in report["general_citizen_rows"]),
            subsidized=tuple(_subsidy_fact(row) for row in report["subsidized_citizen_rows"]),
        )

    def list_weekly_metrics(self, start_date: date, end_date: date) -> list[WeeklyReportMetric]:
        return WeeklyReportMetricsService(self._connection).list_metrics(start_date, end_date)


def _subsidy_fact(row: dict[str, object]) -> SubsidyFact:
    case_no = str(row["市府訂單號碼"])
    return SubsidyFact(
        serial_number=int(row["序號"]),
        case_no=case_no,
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
        application_roc_year=_case_application_roc_year(case_no),
        claim_period_label=str(row.get("核銷月份") or ""),
        reconciliation_status=str(row.get("核銷狀態") or "結案"),
        notes="",
    )


def _case_application_roc_year(case_no: str) -> int | None:
    return (
        int(case_no[:3])
        if len(case_no) == 9 and case_no.isdigit() and case_no[3:6] == "000"
        else None
    )


def _hsinchu_district_or_address(city: object, address: object) -> str | None:
    city_text = _optional_text(city) or ""
    address_text = _optional_text(address) or ""
    combined = f"{city_text}{address_text}"
    is_hsinchu = "新竹市" in combined or city_text in {"東區", "北區", "香山", "香山區"}
    if is_hsinchu:
        for marker, label in (("東區", "東區"), ("北區", "北區"), ("香山區", "香山"), ("香山", "香山")):
            if marker in combined:
                return label
    return address_text or city_text or None


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


def _datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    return datetime.fromisoformat(str(value))


def _json_rest_days(value: object) -> list[int] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [int(item) for item in value if isinstance(item, (int, str)) and str(item).isdigit()]
    if isinstance(value, str):
        try:
            import json
            data = json.loads(value)
            if isinstance(data, list):
                return [int(item) for item in data if isinstance(item, (int, str)) and str(item).isdigit()]
        except Exception:
            return None
    return None


_CASE_FACTS_SQL = """
SELECT c.id AS client_id,c.seq_num,c.case_no,c.created_at AS application_created_at,
       c.name AS applicant_name,c.identity_status,c.reject_reason,c.city,c.address,
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
       DATE_SUB(ss.work_date, INTERVAL WEEKDAY(ss.work_date) DAY) AS week_start_date,
       DATE_ADD(DATE_SUB(ss.work_date, INTERVAL WEEKDAY(ss.work_date) DAY), INTERVAL 6 DAY) AS week_end_date,
       o.status AS order_status,a.status AS assignment_status,
       s.weekly_rest_days
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
         o.service_hours_per_day,o.status,a.status,s.weekly_rest_days,
         week_start_date,week_end_date
ORDER BY week_start_date,a.id
"""


__all__ = ["MySqlWeeklyOperationsReportQueryAdapter"]
