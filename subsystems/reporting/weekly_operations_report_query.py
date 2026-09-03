"""
File: weekly_operations_report_query.py
Description: 協調營運週報三分頁根事實、遮罩、彙總與資料品質結果。
"""

from __future__ import annotations

from dataclasses import dataclass
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
    applicant_name_masked: str
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
    employer_name_masked: str
    staff_name_masked: str
    identity_card_masked: str
    address_masked: str


@dataclass(frozen=True, slots=True)
class WeeklySubsidyPartition:
    citizen_kind: str
    rows: tuple[WeeklySubsidyRow, ...]


@dataclass(frozen=True, slots=True)
class WeeklyServiceRow:
    assignment_id: int
    case_no: str
    client_name_masked: str
    staff_name_masked: str
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


@dataclass(frozen=True, slots=True)
class WeeklySummary:
    promotion_count: None
    inquiry_count: None
    application_count: int
    general_eligible_count: int
    general_ineligible_count: None
    subsidized_eligible_count: int
    subsidized_ineligible_count: None
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


class WeeklyOperationsReportQuery:
    def __init__(self, facts: WeeklyOperationsReportFacts, now) -> None:
        self._facts = facts
        self._now = now

    def query(self, start_date: date, end_date: date) -> WeeklyOperationsReport:
        if start_date > end_date:
            raise ValueError("operations_report_date_range_invalid")
        case_rows = tuple(self._case_row(fact) for fact in self._facts.list_case_facts(start_date, end_date))
        service_candidates = tuple(
            self._service_row(fact, start_date, end_date)
            for fact in self._facts.list_service_facts(start_date, end_date)
        )
        service_rows = tuple(row for row in service_candidates if row is not None)
        incomplete_service_count = len(service_candidates) - len(service_rows)
        subsidies = self._facts.list_subsidy_facts(start_date, end_date)
        subsidy_partitions = (
            self._subsidy_partition("general", subsidies.general),
            self._subsidy_partition("subsidized", subsidies.subsidized),
        )
        issues = self._issues(case_rows, subsidy_partitions, incomplete_service_count)
        return WeeklyOperationsReport(
            schema_version=SCHEMA_VERSION,
            start_date=start_date,
            end_date=end_date,
            timezone=TIMEZONE,
            period_label=f"{start_date.isoformat()} ~ {end_date.isoformat()}",
            generated_at=self._now(),
            source_revision=SOURCE_REVISION,
            summary=self._summary(case_rows),
            case_rows=case_rows,
            subsidy_partitions=subsidy_partitions,
            service_rows=service_rows,
            data_quality_issues=issues,
        )

    @staticmethod
    def _case_row(fact: WeeklyCaseFact) -> WeeklyCaseRow:
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
        if fact.reject_reason:
            review_result = "rejected_unpartitioned"
        elif fact.identity_status == GENERAL_CITIZEN:
            review_result = "general_eligible"
        elif fact.identity_status == SUBSIDIZED_CITIZEN:
            review_result = "subsidized_eligible"
        else:
            review_result = "pending"
            quality_codes.append("review_result_pending")
        return WeeklyCaseRow(
            case_no=fact.case_no or "—",
            applicant_name_masked=_mask_name(fact.applicant_name),
            application_date=fact.created_at.date() if fact.created_at is not None else None,
            identity_status=fact.identity_status,
            review_result=review_result,
            order_status=fact.order_status,
            service_days=_positive_or_none(fact.service_days),
            service_hours_per_day=_positive_or_none(fact.service_hours_per_day),
            planned_start_date=fact.planned_start_date,
            planned_end_date=fact.planned_end_date,
            district=fact.district,
            data_quality_codes=tuple(quality_codes),
        )

    @staticmethod
    def _service_row(
        fact: WeeklyServiceFact,
        start_date: date,
        end_date: date,
    ) -> WeeklyServiceRow | None:
        hours_per_day = _positive_or_none(fact.service_hours_per_day)
        if hours_per_day is None or fact.service_start_date is None or fact.service_end_date is None:
            return None
        return WeeklyServiceRow(
            assignment_id=fact.assignment_id,
            case_no=fact.case_no,
            client_name_masked=_mask_name(fact.client_name),
            staff_name_masked=_mask_name(fact.staff_name),
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
                    employer_name_masked=_mask_name(fact.employer_name),
                    staff_name_masked=_mask_name(fact.staff_name),
                    identity_card_masked=_mask_identity_card(fact.identity_card),
                    address_masked="地址已遮罩" if str(fact.address or "").strip() else "—",
                )
                for fact in facts
            ),
        )

    @staticmethod
    def _summary(rows: tuple[WeeklyCaseRow, ...]) -> WeeklySummary:
        return WeeklySummary(
            promotion_count=None,
            inquiry_count=None,
            application_count=len(rows),
            general_eligible_count=sum(row.review_result == "general_eligible" for row in rows),
            general_ineligible_count=None,
            subsidized_eligible_count=sum(row.review_result == "subsidized_eligible" for row in rows),
            subsidized_ineligible_count=None,
            rejection_unpartitioned_count=sum(row.review_result == "rejected_unpartitioned" for row in rows),
            order_established_count=sum(row.order_status in {"訂單成立", "服務中", "訂單完成"} for row in rows),
            negotiating_count=sum(row.order_status == "洽談中" for row in rows),
            cancelled_count=sum(row.order_status == "訂單取消" for row in rows),
            incomplete_count=sum(row.order_status is None or bool(row.data_quality_codes) for row in rows),
        )

    @staticmethod
    def _issues(
        case_rows: tuple[WeeklyCaseRow, ...],
        partitions: tuple[WeeklySubsidyPartition, ...],
        incomplete_service_count: int,
    ) -> tuple[DataQualityIssue, ...]:
        issues = [
            DataQualityIssue("manual_metric_not_recorded", "promotion_count", 0, "推廣次數尚無 canonical root fact。"),
            DataQualityIssue("manual_metric_not_recorded", "inquiry_count", 0, "詢問人次尚無 canonical root fact。"),
            DataQualityIssue(
                "rejection_partition_unknown",
                "general_ineligible_count,subsidized_ineligible_count",
                sum(row.review_result == "rejected_unpartitioned" for row in case_rows),
                "不符合案件尚無一般／補助 canonical 分類。",
            ),
        ]
        for code in sorted({code for row in case_rows for code in row.data_quality_codes}):
            issues.append(DataQualityIssue(code, "case_rows", sum(code in row.data_quality_codes for row in case_rows), "歷史案件根事實待補正。"))
        subsidy_count = sum(len(partition.rows) for partition in partitions)
        if subsidy_count:
            issues.append(DataQualityIssue("subsidy_reconciliation_month_not_recorded", "subsidy_partitions", subsidy_count, "核銷月份 root fact 尚未登錄。"))
        if incomplete_service_count:
            issues.append(DataQualityIssue("service_row_incomplete", "service_rows", incomplete_service_count, "正式排班缺少起訖或每日服務時數，該列待補正。"))
        return tuple(issues)


def _positive_or_none(value: int | None) -> int | None:
    return value if value is not None and value > 0 else None


def _mask_name(value: str | None) -> str:
    text = str(value or "").strip()
    return "—" if not text else f"{text[0]}{'*' * max(len(text) - 1, 1)}"


def _mask_identity_card(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return "—"
    return f"{text[0]}{'*' * max(len(text) - 1, 1)}"


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
