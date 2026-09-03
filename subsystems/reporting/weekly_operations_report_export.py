"""
File: weekly_operations_report_export.py
Description: 將同一營運週報 candidate 輸出為固定三分頁且去敏的 XLSX。
"""

from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

from subsystems.reporting.weekly_operations_report_query import WeeklyOperationsReport


SHEET_NAMES = ("週報案件受理總表", "補助案件統計表", "每週服務中與工時")


def export_weekly_operations_report(report: WeeklyOperationsReport) -> bytes:
    workbook = Workbook()
    case_sheet = workbook.active
    case_sheet.title = SHEET_NAMES[0]
    subsidy_sheet = workbook.create_sheet(SHEET_NAMES[1])
    service_sheet = workbook.create_sheet(SHEET_NAMES[2])

    _append_rows(
        case_sheet,
        (
            "案件識別", "申請人", "申請日期", "身分類別", "審核結果", "訂單狀態",
            "服務天數", "每日服務時數", "預計服務開始", "預計服務結束", "區域", "資料品質",
        ),
        (
            (
                row.case_no, row.applicant_name_masked, row.application_date, row.identity_status,
                row.review_result, row.order_status, row.service_days, row.service_hours_per_day,
                row.planned_start_date, row.planned_end_date, row.district, ",".join(row.data_quality_codes),
            )
            for row in report.case_rows
        ),
        preamble=(
            ("報表期間", report.period_label),
            ("推廣次數", _metric(report.summary.promotion_count), "詢問人次", _metric(report.summary.inquiry_count)),
            ("申請案件", report.summary.application_count, "一般符合", report.summary.general_eligible_count,
             "一般不符合", _metric(report.summary.general_ineligible_count)),
            ("補助符合", report.summary.subsidized_eligible_count,
             "補助不符合", _metric(report.summary.subsidized_ineligible_count),
             "未分流不符合", report.summary.rejection_unpartitioned_count),
            ("訂單成立", report.summary.order_established_count, "洽談中", report.summary.negotiating_count,
             "取消", report.summary.cancelled_count, "資料不完整", report.summary.incomplete_count),
            (),
        ),
    )
    _append_rows(
        subsidy_sheet,
        (
            "分區", "序號", "市府訂單號碼", "補助資格", "服務開始", "服務結束", "補助時數",
            "補助天數", "服務天數", "補助款金額", "單價", "雇主", "服務人員", "身分證字號", "地址",
        ),
        (
            (
                partition.citizen_kind, row.serial_number, row.case_no, row.eligibility,
                row.service_start, row.service_end, row.subsidy_hours, row.subsidy_days,
                row.service_days, row.subsidy_amount_ntd, row.unit_price_ntd,
                row.employer_name_masked, row.staff_name_masked, row.identity_card_masked,
                row.address_masked,
            )
            for partition in report.subsidy_partitions
            for row in partition.rows
        ),
    )
    _append_rows(
        service_sheet,
        (
            "指派識別", "案件識別", "雇主", "服務人員", "服務開始", "服務結束", "報表起始日",
            "報表結束日", "每日服務時數", "期間工作日數", "期間工時", "訂單狀態", "結案", "資料品質",
        ),
        (
            (
                row.assignment_id, row.case_no, row.client_name_masked, row.staff_name_masked,
                row.service_start_date, row.service_end_date, row.period_start_date, row.period_end_date,
                row.service_hours_per_day, row.weekly_work_days, row.weekly_hours,
                row.order_status, "是" if row.completed else "否", ",".join(row.data_quality_codes),
            )
            for row in report.service_rows
        ),
    )
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _append_rows(worksheet, headers, rows, *, preamble=()) -> None:
    for row in preamble:
        worksheet.append(row)
    worksheet.append(headers)
    header_row = worksheet.max_row
    for cell in worksheet[header_row]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill(fill_type="solid", fgColor="D9EAF7")
    for row in rows:
        worksheet.append(row)
    worksheet.freeze_panes = f"A{header_row + 1}"
    worksheet.auto_filter.ref = worksheet.dimensions


def _metric(value: int | None) -> int | str:
    return "未登錄" if value is None else value


__all__ = ["SHEET_NAMES", "export_weekly_operations_report"]
