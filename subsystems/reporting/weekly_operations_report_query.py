"""
File: weekly_operations_report_query.py
Description: 協調營運週報三分頁根事實、遮罩、彙總與資料品質結果。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol


SCHEMA_VERSION = "operations-report.v2"
SOURCE_REVISION = "operations_report_query_v3"
TIMEZONE = "Asia/Taipei"
GENERAL_CITIZEN = "一般市民"
SUBSIDIZED_CITIZEN = "補助市民"


@dataclass(frozen=True, slots=True)
class WeeklyCaseFact:
    client_id: int
    case_no: str | None
    created_at: datetime | None
    applicant_name: str | None
    identity_status: str | None
    reject_reason: str | None
    district: str | None
    order_status: str | None
    service_days: int | None
    service_hours_per_day: int | None
    planned_start_date: date | None
    planned_end_date: date | None
    seq_num: int | None = None
    hc_query_no: str | None = None
    bound_week_code: str | None = None


@dataclass(frozen=True, slots=True)
class WeeklyServiceFact:
    assignment_id: int
    case_no: str
    client_name: str | None
    staff_name: str | None
    service_start_date: date | None
    service_end_date: date | None
    service_hours_per_day: int | None
    weekly_work_days: int
    order_status: str
    assignment_status: str
    weekly_rest_days: list[int] | None = None


@dataclass(frozen=True, slots=True)
class SubsidyFact:
    serial_number: int
    case_no: str
    eligibility: str
    service_start: date
    service_end: date
    subsidy_hours: Decimal
    subsidy_days: Decimal
    service_days: int
    subsidy_amount_ntd: int
    unit_price_ntd: int
    employer_name: str | None
    staff_name: str | None
    identity_card: str | None
    address: str | None
    hc_case_no: str = ""
    annual_seq: str = ""
    claim_period_label: str = ""
    reconciliation_status: str = "結案"
    notes: str = ""


@dataclass(frozen=True, slots=True)
class SubsidyFacts:
    general: tuple[SubsidyFact, ...]
    subsidized: tuple[SubsidyFact, ...]


class WeeklyOperationsReportFacts(Protocol):
    def list_case_facts(self, start_date: date, end_date: date) -> list[WeeklyCaseFact]: ...

    def list_service_facts(self, start_date: date, end_date: date) -> list[WeeklyServiceFact]: ...

    def list_subsidy_facts(self, start_date: date, end_date: date) -> SubsidyFacts: ...


@dataclass(frozen=True, slots=True)
class DataQualityIssue:
    code: str
    field: str
    row_count: int
    message: str


@dataclass(frozen=True, slots=True)
class WeeklyCaseRow:
    case_no: str
    applicant_name: str
    application_date: date | None
    identity_status: str | None
    review_result: str
    order_status: str | None
    service_days: int | None
    service_hours_per_day: int | None
    planned_start_date: date | None
    planned_end_date: date | None
    district: str | None
    data_quality_codes: tuple[str, ...]
    # 模板雙層表頭 23 欄擴充
    serial_number: int = 1
    month_label: str = ""
    application_date_roc: str = ""
    week_code: str = ""
    general_eligible: int = 0
    general_ineligible: int = 0
    subsidized_eligible: int = 0
    subsidized_ineligible: int = 0
    order_established: int = 0
    negotiating: int = 0
    cancelled: int = 0
    review_rejected: int = 0
    service_status: str = ""
    notes: str = ""


@dataclass(frozen=True, slots=True)
class WeeklySubsidyRow:
    serial_number: int
    case_no: str
    eligibility: str
    service_start: date
    service_end: date
    subsidy_hours: Decimal
    subsidy_days: Decimal
    service_days: int
    subsidy_amount_ntd: int
    unit_price_ntd: int
    employer_name: str
    staff_name: str
    identity_card: str
    address: str
    hc_case_no: str = ""
    annual_seq: str = ""
    claim_period_label: str = ""
    reconciliation_status: str = "結案"
    notes: str = ""


@dataclass(frozen=True, slots=True)
class WeeklySubsidyPartition:
    citizen_kind: str
    rows: tuple[WeeklySubsidyRow, ...]


@dataclass(frozen=True, slots=True)
class WeeklyServiceRow:
    assignment_id: int
    case_no: str
    client_name: str
    staff_name: str
    service_start_date: date
    service_end_date: date
    period_start_date: date
    period_end_date: date
    service_hours_per_day: int
    weekly_work_days: int
    weekly_hours: int
    order_status: str
    completed: bool
    data_quality_codes: tuple[str, ...]
    week_code: str = ""
    week_serial: int = 1
    rest_mode: str = "周休二日"
    rest_days_count: int = 0
    special_rest: str = ""
    is_closed: str = ""


@dataclass(frozen=True, slots=True)
class WeeklySummary:
    promotion_count: int | None
    inquiry_count: int | None
    application_count: int
    general_eligible_count: int
    general_ineligible_count: int | None
    subsidized_eligible_count: int
    subsidized_ineligible_count: int | None
    rejection_unpartitioned_count: int
    order_established_count: int
    negotiating_count: int
    cancelled_count: int
    incomplete_count: int


@dataclass(frozen=True, slots=True)
class WeeklyOperationsReport:
    schema_version: str
    start_date: date
    end_date: date
    timezone: str
    period_label: str
    generated_at: datetime
    source_revision: str
    summary: WeeklySummary
    case_rows: tuple[WeeklyCaseRow, ...]
    subsidy_partitions: tuple[WeeklySubsidyPartition, ...]
    service_rows: tuple[WeeklyServiceRow, ...]
    data_quality_issues: tuple[DataQualityIssue, ...]
    weekly_metrics: dict[str, tuple[int, int]] = field(default_factory=dict)


def _week_code(d: date | None) -> str:
    if d is None:
        return ""
    week_num = (d.day - 1) // 7 + 1
    return f"{d.month}-{week_num}"


def _roc_date(d: date | None) -> str:
    if d is None:
        return ""
    return f"{d.year - 1911}/{d.month:02d}/{d.day:02d}"


def _service_status(order_status: str | None) -> str:
    if not order_status:
        return ""
    if order_status in ("訂單完成", "歷史訂單－服務完成", "歷史訂單－帳務完成"):
        return "服務中結案"
    if order_status in ("訂單成立", "待補件"):
        return "等待服務"
    if order_status in ("服務中", "歷史訂單－服務中"):
        return "服務中"
    if order_status in ("訂單取消",):
        return "取消"
    if order_status in ("洽談中",):
        return "洽談中"
    return order_status


class WeeklyOperationsReportQuery:
    def __init__(self, facts: WeeklyOperationsReportFacts, now) -> None:
        self._facts = facts
        self._now = now

    def query(
        self,
        start_date: date,
        end_date: date,
        promotion_count: int | None = None,
        inquiry_count: int | None = None,
        annual_ytd: bool = False,
    ) -> WeeklyOperationsReport:
        if start_date > end_date:
            raise ValueError("operations_report_date_range_invalid")
        query_start = date(end_date.year, 1, 1) if annual_ytd else start_date
        facts_cases = self._facts.list_case_facts(query_start, end_date)
        facts_cases_sorted = sorted(
            facts_cases,
            key=lambda f: (f.created_at or datetime.min, f.client_id)
        )
        case_rows = []
        last_month = None
        for idx, fact in enumerate(facts_cases_sorted, start=1):
            app_dt = fact.created_at.date() if fact.created_at is not None else None
            month_str = f"{app_dt.month}月" if app_dt and app_dt.month != last_month else ""
            if app_dt:
                last_month = app_dt.month
            case_rows.append(self._case_row(fact, serial_number=idx, month_label=month_str))
        case_rows_tuple = tuple(case_rows)

        service_candidates = tuple(
            self._service_row(fact, query_start, end_date, idx)
            for idx, fact in enumerate(self._facts.list_service_facts(query_start, end_date), start=1)
        )
        service_rows = tuple(row for row in service_candidates if row is not None)
        incomplete_service_count = len(service_candidates) - len(service_rows)
        subsidies = self._facts.list_subsidy_facts(query_start, end_date)
        subsidy_partitions = (
            self._subsidy_partition("general", subsidies.general),
            self._subsidy_partition("subsidized", subsidies.subsidized),
        )
        metrics_getter = getattr(self._facts, "list_weekly_metrics", None)
        metrics_map = metrics_getter(end_date.year) if callable(metrics_getter) else {}
        effective_promo = promotion_count
        effective_inq = inquiry_count
        if effective_promo is None and metrics_map:
            effective_promo = sum(p for p, _ in metrics_map.values())
        if effective_inq is None and metrics_map:
            effective_inq = sum(i for _, i in metrics_map.values())

        issues = self._issues(case_rows_tuple, subsidy_partitions, incomplete_service_count, effective_promo, effective_inq)
        return WeeklyOperationsReport(
            schema_version=SCHEMA_VERSION,
            start_date=query_start,
            end_date=end_date,
            timezone=TIMEZONE,
            period_label=f"{query_start.isoformat()} ~ {end_date.isoformat()}",
            generated_at=self._now(),
            source_revision=SOURCE_REVISION,
            summary=self._summary(case_rows_tuple, promotion_count=effective_promo, inquiry_count=effective_inq),
            case_rows=case_rows_tuple,
            subsidy_partitions=subsidy_partitions,
            service_rows=service_rows,
            data_quality_issues=issues,
            weekly_metrics=metrics_map,
        )

    @staticmethod
    def _case_row(fact: WeeklyCaseFact, serial_number: int = 1, month_label: str = "") -> WeeklyCaseRow:
        quality_codes: list[str] = []
        if fact.created_at is None:
            quality_codes.append("application_date_missing")
        if not fact.case_no:
            quality_codes.append("case_no_missing")
        if fact.order_status is None:
            quality_codes.append("order_missing")
        if fact.service_days is None:
            quality_codes.append("service_days_missing")
        if fact.service_hours_per_day is None:
            quality_codes.append("service_hours_per_day_missing")
        if fact.planned_start_date is None or fact.planned_end_date is None:
            quality_codes.append("planned_service_period_missing")

        is_general = fact.identity_status == GENERAL_CITIZEN
        is_subsidized = fact.identity_status == SUBSIDIZED_CITIZEN
        is_rejected = bool(fact.reject_reason)

        if is_rejected:
            review_result = "rejected_unpartitioned"
        elif is_general:
            review_result = "general_eligible"
        elif is_subsidized:
            review_result = "subsidized_eligible"
        else:
            review_result = "pending"
            quality_codes.append("review_result_pending")

        app_date = fact.created_at.date() if fact.created_at is not None else None

        gen_elig = 1 if is_general and not is_rejected else 0
        gen_inelig = 1 if is_general and is_rejected else 0
        sub_elig = 1 if is_subsidized and not is_rejected else 0
        sub_inelig = 1 if is_subsidized and is_rejected else 0

        ord_estab = 1 if fact.order_status in {"訂單成立", "服務中", "訂單完成", "歷史訂單－服務中", "歷史訂單－服務完成", "歷史訂單－帳務完成"} else 0
        negotiating = 1 if fact.order_status == "洽談中" else 0
        cancelled = 1 if fact.order_status == "訂單取消" and not is_rejected else 0
        review_rej = 1 if is_rejected or fact.order_status == "審核不符合" else 0

        week_code = fact.bound_week_code or _week_code(app_date)
        roc_date_str = _roc_date(app_date)
        serv_status = _service_status(fact.order_status)
        seq = fact.seq_num if fact.seq_num is not None else serial_number

        return WeeklyCaseRow(
            case_no=fact.case_no or "—",
            applicant_name=_canonical_name(fact.applicant_name),
            application_date=app_date,
            identity_status=fact.identity_status,
            review_result=review_result,
            order_status=fact.order_status,
            service_days=_positive_or_none(fact.service_days),
            service_hours_per_day=_positive_or_none(fact.service_hours_per_day),
            planned_start_date=fact.planned_start_date,
            planned_end_date=fact.planned_end_date,
            district=fact.district,
            data_quality_codes=tuple(quality_codes),
            serial_number=seq,
            month_label=month_label,
            application_date_roc=roc_date_str,
            week_code=week_code,
            general_eligible=gen_elig,
            general_ineligible=gen_inelig,
            subsidized_eligible=sub_elig,
            subsidized_ineligible=sub_inelig,
            order_established=ord_estab,
            negotiating=negotiating,
            cancelled=cancelled,
            review_rejected=review_rej,
            service_status=serv_status,
            notes="",
        )

    @staticmethod
    def _service_row(
        fact: WeeklyServiceFact,
        start_date: date,
        end_date: date,
        serial: int = 1,
    ) -> WeeklyServiceRow | None:
        hours_per_day = _positive_or_none(fact.service_hours_per_day)
        if hours_per_day is None or fact.service_start_date is None or fact.service_end_date is None:
            return None
        week_code = _week_code(end_date)
        rest_days = fact.weekly_rest_days or [0, 6]
        rest_mode = "周休二日" if len(rest_days) >= 2 else "休周日"
        rest_count = max(0, 7 - fact.weekly_work_days)
        is_closed = "結案" if (fact.order_status in ("訂單完成", "歷史訂單－服務完成") or fact.assignment_status == "completed" or (fact.service_end_date and fact.service_end_date <= end_date)) else ""

        return WeeklyServiceRow(
            assignment_id=fact.assignment_id,
            case_no=fact.case_no,
            client_name=_canonical_name(fact.client_name),
            staff_name=_canonical_name(fact.staff_name),
            service_start_date=fact.service_start_date,
            service_end_date=fact.service_end_date,
            period_start_date=start_date,
            period_end_date=end_date,
            service_hours_per_day=hours_per_day,
            weekly_work_days=fact.weekly_work_days,
            weekly_hours=fact.weekly_work_days * hours_per_day,
            order_status=fact.order_status,
            completed=fact.order_status == "訂單完成" or fact.assignment_status == "completed",
            data_quality_codes=(),
            week_code=week_code,
            week_serial=serial,
            rest_mode=rest_mode,
            rest_days_count=rest_count,
            special_rest="",
            is_closed=is_closed,
        )

    @staticmethod
    def _subsidy_partition(kind: str, facts: tuple[SubsidyFact, ...]) -> WeeklySubsidyPartition:
        return WeeklySubsidyPartition(
            citizen_kind=kind,
            rows=tuple(
                WeeklySubsidyRow(
                    serial_number=fact.serial_number,
                    case_no=fact.case_no,
                    eligibility=fact.eligibility,
                    service_start=fact.service_start,
                    service_end=fact.service_end,
                    subsidy_hours=fact.subsidy_hours,
                    subsidy_days=fact.subsidy_days,
                    service_days=fact.service_days,
                    subsidy_amount_ntd=fact.subsidy_amount_ntd,
                    unit_price_ntd=fact.unit_price_ntd,
                    employer_name=_canonical_name(fact.employer_name),
                    staff_name=_canonical_name(fact.staff_name),
                    identity_card=_canonical_identity_card(fact.identity_card),
                    address=str(fact.address or "").strip() or "—",
                    hc_case_no=fact.hc_case_no or fact.case_no,
                    annual_seq=fact.annual_seq or str(fact.serial_number),
                    claim_period_label=fact.claim_period_label or "",
                    reconciliation_status=fact.reconciliation_status or "結案",
                    notes=fact.notes or "",
                )
                for fact in facts
            ),
        )

    @staticmethod
    def _summary(
        rows: tuple[WeeklyCaseRow, ...],
        promotion_count: int | None = None,
        inquiry_count: int | None = None,
    ) -> WeeklySummary:
        return WeeklySummary(
            promotion_count=promotion_count,
            inquiry_count=inquiry_count,
            application_count=len(rows),
            general_eligible_count=sum(row.general_eligible for row in rows),
            general_ineligible_count=sum(row.general_ineligible for row in rows) if any(row.general_ineligible for row in rows) else None,
            subsidized_eligible_count=sum(row.subsidized_eligible for row in rows),
            subsidized_ineligible_count=sum(row.subsidized_ineligible for row in rows) if any(row.subsidized_ineligible for row in rows) else None,
            rejection_unpartitioned_count=sum(row.review_result == "rejected_unpartitioned" for row in rows),
            order_established_count=sum(row.order_established for row in rows),
            negotiating_count=sum(row.negotiating for row in rows),
            cancelled_count=sum(row.cancelled for row in rows),
            incomplete_count=sum(row.order_status is None or bool(row.data_quality_codes) for row in rows),
        )

    @staticmethod
    def _issues(
        case_rows: tuple[WeeklyCaseRow, ...],
        partitions: tuple[WeeklySubsidyPartition, ...],
        incomplete_service_count: int,
        promotion_count: int | None = None,
        inquiry_count: int | None = None,
    ) -> tuple[DataQualityIssue, ...]:
        issues = []
        if promotion_count is None:
            issues.append(DataQualityIssue("manual_metric_not_recorded", "promotion_count", 0, "推廣次數尚無 canonical root fact。"))
        if inquiry_count is None:
            issues.append(DataQualityIssue("manual_metric_not_recorded", "inquiry_count", 0, "詢問人次尚無 canonical root fact。"))
        issues.append(
            DataQualityIssue(
                "rejection_partition_unknown",
                "general_ineligible_count,subsidized_ineligible_count",
                sum(row.review_result == "rejected_unpartitioned" for row in case_rows),
                "不符合案件尚無一般／補助 canonical 分類。",
            )
        )
        for code in sorted({code for row in case_rows for code in row.data_quality_codes}):
            issues.append(DataQualityIssue(code, "case_rows", sum(code in row.data_quality_codes for row in case_rows), "歷史案件根事實待補正。"))
        subsidy_count = sum(len(partition.rows) for partition in partitions)
        if subsidy_count and not any(row.claim_period_label for p in partitions for row in p.rows):
            issues.append(DataQualityIssue("subsidy_reconciliation_month_not_recorded", "subsidy_partitions", subsidy_count, "核銷月份 root fact 尚未登錄。"))
        if incomplete_service_count:
            issues.append(DataQualityIssue("service_row_incomplete", "service_rows", incomplete_service_count, "正式排班缺少起訖或每日服務時數，該列待補正。"))
        return tuple(issues)


def _positive_or_none(value: int | None) -> int | None:
    return value if value is not None and value > 0 else None


def _canonical_name(value: str | None) -> str:
    return str(value or "").strip() or "—"

def _canonical_identity_card(value: str | None) -> str:
    return str(value or "").strip() or "—"

__all__ = [
    "DataQualityIssue",
    "SubsidyFact",
    "SubsidyFacts",
    "WeeklyCaseFact",
    "WeeklyOperationsReport",
    "WeeklyOperationsReportFacts",
    "WeeklyOperationsReportQuery",
    "WeeklyServiceFact",
]
