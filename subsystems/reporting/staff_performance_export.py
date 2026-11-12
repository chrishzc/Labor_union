"""Export the same performance candidate as a formatted XLSX workbook."""
from io import BytesIO
import re

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from subsystems.reporting.staff_performance_query import StaffPerformanceReport


def export_staff_performance(report: StaffPerformanceReport, sort_by: str = "service_hours") -> bytes:
    if sort_by not in {"service_hours", "case_count", "total_amount_ntd"}:
        raise ValueError("staff_performance_sort_invalid")
    workbook = Workbook()
    period_label = f"{report.year}年" + (f"{report.month}月" if report.period == "month" else f"第{report.quarter}季" if report.period == "quarter" else "全年")
    staff_index = {staff.staff_id: staff for staff in report.staff_options}
    def staff_label(staff_id):
        staff = staff_index[staff_id]
        return f"{staff.union_no or '未設定'} {staff.staff_name}"
    scope_label = "全部月嫂" if report.selected_staff_id is None else staff_label(report.selected_staff_id)
    metric_label = {"service_hours": "服務工時（含歷史估算）", "case_count": "接案數", "total_amount_ntd": "本期認列金額"}[sort_by]
    def numeric(value):
        return "待確認" if value is None else value

    def prepare(sheet, title, headers):
        sheet.append((title,))
        sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
        sheet.append(("統計期間", period_label, "資料截至", str(report.through_date)))
        sheet.append(("月嫂範圍", scope_label, "排名依據", metric_label))
        previous_label = f"{report.previous_start_date} ～ {report.previous_end_date}" if report.previous_start_date <= report.previous_end_date else "尚無比較期間"
        sheet.append(("前期比較期間", previous_label))
        sheet.append(())
        sheet.append(headers)
        sheet.freeze_panes = "A7"
        sheet.row_dimensions[1].height = 28
        for row_index in (2, 3, 4):
            sheet.row_dimensions[row_index].height = 30
            for cell in sheet[row_index]:
                cell.alignment = Alignment(wrap_text=True, vertical="center")
        sheet.row_dimensions[6].height = 36
        sheet["A1"].font = Font(bold=True, size=14, color="9A3412")
        return sheet

    summary = workbook.active
    summary.title = "期間摘要"
    prepare(summary, "期間摘要｜所選期間合計", ("統計期間", "服務月嫂數", "接案數", "服務工時（小時，含歷史估算）", "本期認列金額（元）"))
    summary.append((period_label, report.service_staff_count, numeric(report.totals.case_count), numeric(report.totals.service_hours), numeric(report.totals.total_amount_ntd)))
    def row_key(row):
        natural_no = tuple((0, int(part)) if part.isdecimal() else (1, part.casefold()) for part in re.split(r"(\d+)", row.union_no or ""))
        return (getattr(row.totals, sort_by) is None, -(getattr(row.totals, sort_by) or 0), not bool(row.union_no), natural_no, row.staff_id)
    rows = sorted(report.rows, key=row_key)
    comparison = workbook.create_sheet("月嫂表現比較")
    prepare(comparison, "月嫂表現比較｜逐人比較開案與服務表現", ("排名", "公會編號", "姓名", "接案數", "服務工時（小時，含歷史估算）", "本期認列金額（元）", "前期接案數", "前期服務工時（小時，含歷史估算）", "前期認列金額（元）"))
    details = workbook.create_sheet("服務案件")
    prepare(details, "服務案件｜查核每人每案的工時與認列", ("公會編號", "姓名", "案件編號", "實際開案日", "開案主責月嫂", "本期服務起日", "本期服務迄日", "工作日數（含估算）", "服務工時（小時，含歷史估算）", "整案總額（元）", "本期認列件數", "本期認列金額（元）"))
    for row in rows:
        value = getattr(row.totals, sort_by)
        rank = None if value is None or value <= 0 else 1 + sum(getattr(other.totals, sort_by) is not None and getattr(other.totals, sort_by) > value for other in rows)
        comparison.append((rank, row.union_no, row.staff_name, numeric(row.totals.case_count), numeric(row.totals.service_hours), numeric(row.totals.total_amount_ntd),
            numeric(row.previous_totals.case_count), numeric(row.previous_totals.service_hours), numeric(row.previous_totals.total_amount_ntd)))
        for case in row.cases:
            details.append((row.union_no, row.staff_name, case.case_no, str(case.actual_start_date) if case.actual_start_date else "待確認",
                staff_label(case.primary_staff_id), str(case.service_start) if case.service_start else "—",
                str(case.service_end) if case.service_end else "—", case.work_days, numeric(case.service_hours),
                numeric(case.total_amount_ntd), numeric(case.recognized_case_count), numeric(case.recognized_amount_ntd)))
    trend = workbook.create_sheet("期間趨勢")
    prepare(trend, "期間趨勢｜每月合計", ("統計月份", "接案數", "服務工時（小時，含歷史估算）", "本期認列金額（元）"))
    for point in report.trend:
        trend.append((f"{point.start_date.year}年{point.start_date.month}月", numeric(point.totals.case_count), numeric(point.totals.service_hours), numeric(point.totals.total_amount_ntd)))
    for sheet in workbook:
        sheet.auto_filter.ref = f"A6:{get_column_letter(sheet.max_column)}{sheet.max_row}"
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_setup.orientation = "landscape"
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.print_title_rows = "1:6"
        for cell in sheet[6]:
            cell.font = Font(bold=True, color="9A3412")
            cell.fill = PatternFill("solid", fgColor="FFF0E8")
            cell.alignment = Alignment(wrap_text=True, vertical="center")
        for column in sheet.columns:
            sheet.column_dimensions[get_column_letter(column[0].column)].width = 22
            for cell in column:
                if isinstance(cell.value, str):
                    cell.data_type = "s"
                elif isinstance(cell.value, (int, float)):
                    header = sheet.cell(6, cell.column).value or ""
                    cell.number_format = "#,##0.0#" if "工時" in header else "#,##0"
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
