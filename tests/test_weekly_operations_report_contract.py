"""
File: test_weekly_operations_report_contract.py
Description: 驗證營運週報週界、彙總、遮罩、正式工時、strict API 與三分頁 XLSX。
"""

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from api.dependencies.admin_auth import require_admin
from api.dependencies.operations_reports import (
    get_weekly_operations_report_query,
    get_weekly_report_metrics_service,
)
from api.exception_handlers import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.routes import operations_reports
from shared_kernel.clock import TAIPEI_TIME_ZONE
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.reporting.weekly_operations_report_query import (
    SubsidyFact,
    SubsidyFacts,
    WeeklyCaseFact,
    WeeklyOperationsReportQuery,
    WeeklyServiceFact,
)
from subsystems.reporting.weekly_report_metrics_service import (
    WeeklyReportMetric,
    WeeklyReportMetricsService,
    week_starts_between,
)
from infrastructure.mysql import weekly_operations_report_query_adapter as report_adapter
from infrastructure.mysql.weekly_operations_report_query_adapter import (
    _CASE_FACTS_SQL,
    _SERVICE_FACTS_SQL,
    _case_application_roc_year,
    _hsinchu_district_or_address,
)


class _Facts:
    def list_case_facts(self, start_date, end_date):
        assert (start_date, end_date) == (date(2026, 8, 20), date(2026, 8, 26))
        return [
            WeeklyCaseFact(
                7, "115000007", datetime(2026, 8, 20, 9), "王小美", "一般市民", None,
                "東區", "服務中", 20, 8, date(2026, 8, 10), date(2026, 9, 4),
            ),
            WeeklyCaseFact(
                8, "115000008", datetime(2026, 8, 24, 10), "林大華", None, "資格不符",
                "北區", None, None, None, None, None,
            ),
        ]

    def list_service_facts(self, start_date, end_date):
        return [
            WeeklyServiceFact(
                31, "115000007", "王小美", "陳月嫂", date(2026, 8, 10), date(2026, 9, 4),
                8, 5, date(2026, 8, 17), date(2026, 8, 23), "服務中", "active",
            ),
            WeeklyServiceFact(
                32, "115000009", "林大華", "吳月嫂", date(2026, 8, 17), date(2026, 9, 11),
                7, 4, date(2026, 8, 17), date(2026, 8, 23), "服務中", "active",
            ),
            WeeklyServiceFact(
                33, "115000010", "陳美玲", "周月嫂", date(2026, 8, 24), date(2026, 9, 18),
                4, 5, date(2026, 8, 24), date(2026, 8, 30), "服務中", "active",
            ),
        ]

    def list_subsidy_facts(self, start_date, end_date):
        assert (start_date, end_date) == (date(2026, 8, 20), date(2026, 8, 26))
        return SubsidyFacts(
            general=(
                SubsidyFact(
                    1, "114000007", "一般市民", date(2026, 8, 10), date(2026, 8, 20),
                    Decimal("40"), Decimal("5"), 20, 12000, 300,
                    "王小美", "陳月嫂", "A123456789", "完整地址",
                    application_roc_year=114,
                    claim_period_label="第三季",
                ),
            ),
            subsidized=(),
        )

    def list_weekly_metrics(self, start_date, end_date):
        assert (start_date, end_date) == (date(2026, 8, 20), date(2026, 8, 26))
        return [
            WeeklyReportMetric(date(2026, 8, 17), date(2026, 8, 23), 12, 34),
            WeeklyReportMetric(date(2026, 8, 24), date(2026, 8, 30), 5, 6),
        ]


class _MetricsService:
    def __init__(self):
        self.saved = []

    def list_metrics(self, start_date, end_date):
        return _Facts().list_weekly_metrics(start_date, end_date)

    def save_metric(self, week_start_date, promotion_count, inquiry_count):
        self.saved.append((week_start_date, promotion_count, inquiry_count))
        if week_start_date.weekday() != 0:
            raise ValueError("weekly_report_metric_start_must_be_monday")
        return WeeklyReportMetric(
            week_start_date,
            date.fromordinal(week_start_date.toordinal() + 6),
            promotion_count,
            inquiry_count,
            datetime(2026, 8, 24, 9, tzinfo=TAIPEI_TIME_ZONE),
        )


_METRICS_SERVICE = _MetricsService()


def _query():
    return WeeklyOperationsReportQuery(
        _Facts(),
        lambda: datetime(2026, 8, 23, 12, tzinfo=TAIPEI_TIME_ZONE),
    )


def _app():
    app = FastAPI()
    app.include_router(operations_reports.router)
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(7, "reports", "Reports", "admin")
    app.dependency_overrides[get_weekly_operations_report_query] = _query
    app.dependency_overrides[get_weekly_report_metrics_service] = lambda: _METRICS_SERVICE
    return app


def test_weekly_query_is_redacted_and_uses_official_work_days():
    response = TestClient(_app()).get(
        "/api/v1/operations-reports/weekly",
        params={"start_date": "2026-08-20", "end_date": "2026-08-26"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["schema_version"] == "operations-report.v3"
    assert data["period"] == {
        "start_date": "2026-08-20",
        "end_date": "2026-08-26",
        "timezone": "Asia/Taipei",
        "period_label": "2026-08-20 ~ 2026-08-26",
    }
    assert data["summary"]["application_count"] == 2
    assert data["summary"]["general_eligible_count"] == 1
    assert data["summary"]["rejection_unpartitioned_count"] == 1
    assert [(item["week_start_date"], item["promotion_count"]) for item in data["weekly_metrics"]] == [
        ("2026-08-17", 12),
        ("2026-08-24", 5),
    ]
    assert data["service_rows"][0]["weekly_work_days"] == 5
    assert data["service_rows"][0]["weekly_hours"] == 40
    assert data["case_rows"][0]["applicant_name"] == "王小美"
    assert data["subsidy_partitions"][0]["rows"][0]["identity_card"] == "A123456789"
    assert data["subsidy_partitions"][0]["rows"][0]["application_roc_year"] == 114
    assert data["subsidy_partitions"][0]["rows"][0]["claim_period_label"] == "第三季"
    assert data["subsidy_partitions"][0]["rows"][0]["reconciliation_status"] == "結案"
    assert data["subsidy_partitions"][0]["rows"][0]["notes"] == ""
    assert "王小美" in response.text
    assert "A123456789" in response.text
    assert "完整地址" in response.text


def test_operations_report_rejects_inverted_date_range():
    response = TestClient(_app()).get(
        "/api/v1/operations-reports/weekly",
        params={"start_date": "2026-08-26", "end_date": "2026-08-20"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "weekly_operations_report_invalid"


def test_operations_report_rejects_legacy_week_start_parameter():
    response = TestClient(_app()).get(
        "/api/v1/operations-reports/weekly",
        params={"start_date": "2026-08-20", "end_date": "2026-08-26", "week_start": "2026-08-20"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "weekly_operations_report_invalid"


def test_weekly_query_retains_missing_application_date_as_typed_quality_issue():
    class MissingDateFacts(_Facts):
        def list_case_facts(self, start_date, end_date):
            return [
                WeeklyCaseFact(
                    9, "OPS96-WEEKLY-D-MISSING-DATE", None, "林大華", "一般市民", None,
                    "北區", "洽談中", None, None, None, None,
                ),
            ]

    def query():
        return WeeklyOperationsReportQuery(
            MissingDateFacts(),
            lambda: datetime(2026, 8, 23, 12, tzinfo=TAIPEI_TIME_ZONE),
        )

    app = _app()
    app.dependency_overrides[get_weekly_operations_report_query] = query
    response = TestClient(app).get(
        "/api/v1/operations-reports/weekly",
        params={"start_date": "2026-08-20", "end_date": "2026-08-26"},
    )
    assert response.status_code == 200
    row = response.json()["data"]["case_rows"][0]
    assert row["application_date"] is None
    assert "application_date_missing" in row["data_quality_codes"]


def test_case_source_keeps_date_scoped_rows_inside_requested_window_only():
    assert "OR c.created_at IS NULL" not in _CASE_FACTS_SQL
    assert "c.created_at >= %s AND c.created_at < %s" in _CASE_FACTS_SQL
    assert "c.city,c.address" in _CASE_FACTS_SQL


def test_historical_unserved_is_an_established_order_waiting_for_service():
    row = WeeklyOperationsReportQuery._case_row(WeeklyCaseFact(
        9, "115000009", datetime(2026, 8, 24, 9), "歷史客戶", "一般市民", None,
        "香山", "歷史訂單－未服務", 20, 8, date(2026, 9, 1), date(2026, 9, 20),
    ))

    assert row.order_established == 1
    assert row.service_status == "等待服務"


def test_hsinchu_district_uses_three_business_labels_and_falls_back_to_full_address():
    assert _hsinchu_district_or_address("新竹市", "新竹市東區中央路一段 1 號") == "東區"
    assert _hsinchu_district_or_address("新竹市", "新竹市北區中正路 2 號") == "北區"
    assert _hsinchu_district_or_address("新竹市", "新竹市香山區中華路 3 號") == "香山"
    assert _hsinchu_district_or_address("新竹市", "新竹市未分區測試路 4 號") == "新竹市未分區測試路 4 號"


def test_subsidy_application_year_only_accepts_year_000_sequence_case_number():
    assert _case_application_roc_year("114000007") == 114
    assert _case_application_roc_year("114100007") is None
    assert _case_application_roc_year("14000007") is None


def test_weekly_subsidy_uses_end_date_calendar_year_for_annual_candidate(monkeypatch):
    requested = []

    def build(report_year, connection_factory):
        requested.append((report_year, connection_factory))
        return {"general_citizen_rows": [], "subsidized_citizen_rows": []}

    monkeypatch.setattr(
        report_adapter.reconciliation_register_query,
        "build_operations_report_annual_subsidy_rows",
        build,
    )

    result = report_adapter.MySqlWeeklyOperationsReportQueryAdapter(None).list_subsidy_facts(
        date(2025, 12, 29),
        date(2026, 1, 4),
    )

    assert requested == [(2026, report_adapter.get_connection)]
    assert result == SubsidyFacts(general=(), subsidized=())


def test_weekly_service_source_excludes_unrestarted_historical_overlays():
    assert "JOIN scheduling_generations g" in _SERVICE_FACTS_SQL
    assert "g.effective_marker=1" in _SERVICE_FACTS_SQL
    assert "JOIN staff_schedule ss" in _SERVICE_FACTS_SQL
    assert "ss.effective_marker=1 AND ss.is_work_day=1" in _SERVICE_FACTS_SQL
    assert "historical_order" not in _SERVICE_FACTS_SQL
    assert "historical_stage" not in _SERVICE_FACTS_SQL


def test_weekly_export_has_fixed_three_sheets_and_summary_without_pii():
    response = TestClient(_app()).get(
        "/api/v1/operations-reports/weekly/export",
        params={"start_date": "2026-08-20", "end_date": "2026-08-26"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "2026-08-20_2026-08-26" in response.headers["content-disposition"]
    workbook = load_workbook(BytesIO(response.content), read_only=True, data_only=True)
    assert workbook.sheetnames == ["週報案件受理總表", "補助案件統計表", "每周服務中說明"]
    case_values = list(workbook["週報案件受理總表"].values)
    assert case_values[0][:2] == ("報表期間", "2026-08-20 ~ 2026-08-26")
    # 欄位與雙層表頭不變；明細直接按實際週次開始，沒有查詢期間合計列。
    assert "平台序號" in case_values[1]
    assert "一般市民符合" in case_values[2]
    assert case_values[3][3] == "2026-08-17 ~ 2026-08-23"
    assert case_values[3][5:7] == (12, 34)
    assert case_values[3][7:16] == (1, 1, None, None, None, 1, None, None, None)
    assert any(row[3] == "2026-08-24 ~ 2026-08-30" for row in case_values[3:])
    workbook_text = " ".join(str(value) for sheet in workbook for row in sheet.values for value in row if value is not None)
    assert "王小美" in workbook_text
    # 補助案件統計表對齊模板：經費統計格式，不包含身分證字號與地址個資
    assert "A123456789" not in workbook_text
    subsidy_sheet = workbook["補助案件統計表"]
    assert subsidy_sheet.cell(row=6, column=2).value == "114000007"
    assert subsidy_sheet.cell(row=6, column=3).value == "(114)一般市民"
    assert subsidy_sheet.cell(row=6, column=5).value == "114000007"
    assert subsidy_sheet.cell(row=6, column=14).value == "第三季"
    assert subsidy_sheet.cell(row=6, column=2).number_format == "@"
    assert subsidy_sheet.cell(row=6, column=5).number_format == "@"
    assert subsidy_sheet.cell(row=1, column=6).value == "114市民總計:"
    assert subsidy_sheet.cell(row=1, column=7).value == 1
    assert subsidy_sheet.cell(row=1, column=11).value == 12000
    assert subsidy_sheet.cell(row=2, column=6).value == "115市民總計:"
    assert subsidy_sheet.cell(row=2, column=7).value == 0
    assert subsidy_sheet.cell(row=2, column=11).value == 0

    # 每周服務中說明：對齊使用者提供的 10 欄範例
    service_values = list(workbook["每周服務中說明"].values)
    assert service_values[0][0] == "服務總表-案件服務中說明(每周)"
    expected_headers = (
        "週數", "序號", "市府案號", "雇主", "每週起始日",
        "每週結束日", "服務時數", "每周工作日數", "每周工時", "結案",
    )
    assert service_values[1][:10] == expected_headers
    assert service_values[2][0] == "8-3"
    assert service_values[2][1:10] == (1, "115000007", "王小美", "2026/8/17", "2026/8/23", 8, 5, 40, None)
    assert service_values[3][0] is None
    assert service_values[3][1:10] == (2, "115000009", "林大華", "2026/8/17", "2026/8/23", 7, 4, 28, None)
    assert service_values[4][:10] == expected_headers
    assert service_values[5][0:2] == ("8-4", 1)
    styled_service_sheet = load_workbook(BytesIO(response.content), data_only=True)["每周服務中說明"]
    assert str(styled_service_sheet["J2"].fill.fgColor.rgb).endswith("F4B6C2")
    assert "A3:A4" in {str(cell_range) for cell_range in styled_service_sheet.merged_cells.ranges}
    assert styled_service_sheet.page_setup.orientation == "landscape"
    assert styled_service_sheet.page_setup.fitToWidth == 1


def test_weekly_export_rejects_retired_query_level_metrics():
    response = TestClient(_app()).get(
        "/api/v1/operations-reports/weekly/export",
        params={
            "start_date": "2026-08-20",
            "end_date": "2026-08-26",
            "promotion_count": 12,
            "inquiry_count": 34,
        },
    )
    assert response.status_code == 400


def test_weekly_metrics_list_and_save_are_monday_keyed():
    client = TestClient(_app())
    listed = client.get(
        "/api/v1/operations-reports/weekly/metrics",
        params={"start_date": "2026-08-20", "end_date": "2026-08-26"},
    )
    assert listed.status_code == 200
    assert [row["week_start_date"] for row in listed.json()["data"]] == ["2026-08-17", "2026-08-24"]

    saved = client.put(
        "/api/v1/operations-reports/weekly/metrics/2026-08-24",
        json={"promotion_count": 0, "inquiry_count": None},
    )
    assert saved.status_code == 200
    assert saved.json()["data"]["promotion_count"] == 0
    assert saved.json()["data"]["inquiry_count"] is None

    rejected = client.put(
        "/api/v1/operations-reports/weekly/metrics/2026-08-25",
        json={"promotion_count": 1, "inquiry_count": 1},
    )
    assert rejected.status_code == 400


def test_weekly_metric_storage_preserves_null_zero_and_rejects_non_monday_key():
    class Cursor:
        def __init__(self, connection):
            self.connection = connection
            self.rows = []
            self.row = None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params):
            normalized = " ".join(sql.split()).lower()
            if normalized.startswith("insert into weekly_report_metrics"):
                week_start, promotion, inquiry = params
                self.connection.values[week_start] = {
                    "week_start_date": week_start,
                    "promotion_count": promotion,
                    "inquiry_count": inquiry,
                    "updated_at": datetime(2026, 8, 24, 9),
                }
            elif "where week_start_date = %s" in normalized:
                if self.connection.fail_read:
                    raise RuntimeError("readback failed")
                self.row = self.connection.values.get(params[0])
            else:
                start, end = params
                self.rows = [value for key, value in sorted(self.connection.values.items()) if start <= key <= end]

        def fetchall(self):
            return self.rows

        def fetchone(self):
            return self.row

    class Connection:
        def __init__(self):
            self.values = {}
            self.commits = 0
            self.rollbacks = 0
            self.fail_read = False

        def cursor(self):
            return Cursor(self)

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

    connection = Connection()
    service = WeeklyReportMetricsService(connection)
    saved = service.save_metric(date(2026, 8, 24), None, 0)
    assert (saved.promotion_count, saved.inquiry_count) == (None, 0)
    assert saved.updated_at.tzinfo == TAIPEI_TIME_ZONE
    assert connection.commits == 1

    connection.fail_read = True
    try:
        service.save_metric(date(2026, 8, 31), 2, 3)
    except RuntimeError:
        pass
    else:
        raise AssertionError("failed readback must fail the mutation")
    assert connection.rollbacks == 1
    assert week_starts_between(date(2026, 12, 31), date(2027, 1, 4)) == (
        date(2026, 12, 28),
        date(2027, 1, 4),
    )

    try:
        service.save_metric(date(2026, 8, 25), 1, 1)
    except ValueError:
        pass
    else:
        raise AssertionError("non-Monday week start must be rejected")
    assert connection.commits == 1
