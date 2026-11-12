"""Requirement oracles for staff performance, its read boundary and workbook."""
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
import sqlite3

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from api.dependencies.admin_auth import require_admin
from api.dependencies.operations_reports import get_staff_performance_query
from api.routes.operations_reports import router
from subsystems.reporting.staff_performance_query import (
    PerformanceCaseOpening, PerformanceHistoricalAssignment, PerformanceServiceDay, PerformanceStaff,
    StaffPerformanceQuery,
)
from subsystems.reporting.staff_performance_export import export_staff_performance
from shared_kernel.clock import TAIPEI_TIME_ZONE


class Facts:
    def __init__(self):
        self.days = (
            PerformanceServiceDay(1, "A", date(2026, 9, 30), 8),
            PerformanceServiceDay(1, "A", date(2026, 10, 1), 8.5),
            PerformanceServiceDay(1, "A", date(2026, 10, 2), 8),
            PerformanceServiceDay(2, "A", date(2026, 10, 1), 6),
            PerformanceServiceDay(1, "B", date(2026, 10, 3), 10),
        )
        self.amounts = {"A": 100000, "B": 20000}
        self.openings = {"A": PerformanceCaseOpening("A", date(2026, 9, 30), 1), "B": PerformanceCaseOpening("B", date(2026, 10, 3), 1)}

    def list_staff(self):
        return (PerformanceStaff(1, "U2", "甲"), PerformanceStaff(2, "U10", "乙"), PerformanceStaff(3, None, "丙"))

    def list_years(self):
        return (2026,)

    def list_service_days(self, start, end):
        return tuple(day for day in self.days if start <= day.work_date <= end)

    def list_historical_assignments(self, start, end):
        return ()

    def case_amounts(self, case_nos):
        return {case: self.amounts.get(case) for case in case_nos}

    def list_case_openings(self, start, end, service_cases):
        return tuple(opening for opening in self.openings.values() if opening.case_no in service_cases
                     or opening.actual_start_date is not None and start <= opening.actual_start_date <= end)


def query(facts=None, now=datetime(2026, 11, 4, 10, tzinfo=TAIPEI_TIME_ZONE)):
    return StaffPerformanceQuery(facts or Facts(), lambda: now)


def test_month_whole_case_amounts_shared_staff_and_half_hour():
    facts = Facts()
    facts.days += (facts.days[1],)
    report = query(facts).query(2026, "month", 10)
    assert (report.service_staff_count, report.totals.case_count, report.totals.service_hours, report.totals.total_amount_ntd) == (2, 1, 32.5, 20000)
    assert report.rows[0].totals.total_amount_ntd == 20000
    assert report.rows[1].totals.total_amount_ntd == 0
    assert report.rows[1].totals.case_count == 0 and report.rows[1].totals.service_hours == 6
    assert report.rows[1].cases[0].total_amount_ntd == 100000
    assert report.rows[1].cases[0].recognized_amount_ntd == 0
    assert report.rows[0].previous_totals.service_hours == 8
    assert report.rows[2].totals.case_count == 0
    assert len(report.trend) == 1 and report.trend[0].label == "10月"


def test_months_sum_to_quarter_and_year_without_recounting_ongoing_cases():
    q = query()
    september = q.query(2026, "month", 9)
    october = q.query(2026, "month", 10)
    year = q.query(2026, "year")
    quarter = q.query(2026, "quarter", quarter=4)
    assert september.totals.case_count + october.totals.case_count == year.totals.case_count == 2
    assert quarter.totals.case_count == 1 and quarter.totals.total_amount_ntd == 20000
    assert year.totals.total_amount_ntd == 120000
    assert year.totals.service_hours == 40.5
    assert quarter.through_date == date(2026, 11, 4)
    assert sum(point.totals.case_count for point in year.trend) == year.totals.case_count
    assert sum(point.totals.service_hours for point in year.trend) == year.totals.service_hours
    assert sum(point.totals.total_amount_ntd for point in year.trend) == year.totals.total_amount_ntd
    assert sum(row.totals.case_count for row in year.rows) == year.totals.case_count
    assert sum(row.totals.service_hours for row in year.rows) == year.totals.service_hours
    assert sum(row.totals.total_amount_ntd for row in year.rows) == year.totals.total_amount_ntd


def test_current_period_excludes_future_and_compares_equal_elapsed_days():
    facts = Facts()
    facts.days += (PerformanceServiceDay(1, "A", date(2026, 11, 4), 8), PerformanceServiceDay(1, "A", date(2026, 11, 5), 8))
    report = query(facts).query(2026, "month", 11)
    assert report.totals.service_hours == 8
    assert report.previous_end_date == date(2026, 10, 4)
    future = query(facts).query(2026, "month", 12)
    assert future.totals.case_count == 0 and future.trend == ()


def test_missing_values_propagate_and_staff_selection_keeps_options():
    facts = Facts()
    facts.days = tuple(replace(day, hours=None) if day.case_no == "B" else day for day in facts.days)
    facts.amounts["B"] = None
    report = query(facts).query(2026, "month", 10)
    assert report.totals.service_hours is None and report.totals.total_amount_ntd is None
    selected = query(facts).query(2026, "month", 10, staff_id=2)
    assert len(selected.staff_options) == 3 and len(selected.rows) == 1
    assert selected.totals.total_amount_ntd == 0 and selected.totals.service_hours == 6


@pytest.mark.parametrize("kwargs", [dict(year=1, period="year"), dict(year=2026, period="month"), dict(year=2026, period="year", month=1), dict(year=2026, period="quarter", quarter=5)])
def test_invalid_periods(kwargs):
    with pytest.raises(ValueError, match="staff_performance_period_invalid"):
        query().query(**kwargs)


def test_xlsx_contains_same_totals_and_forces_text_cells():
    facts = Facts()
    facts.list_staff = lambda: (PerformanceStaff(1, "=1+1", "=HYPERLINK(\"unsafe\")"), PerformanceStaff(2, "U10", "乙"))
    report = query(facts).query(2026, "month", 10)
    book = load_workbook(BytesIO(export_staff_performance(report)))
    assert book.sheetnames == ["期間摘要", "月嫂表現比較", "服務案件", "期間趨勢"]
    assert tuple(cell.value for cell in book["期間摘要"][7]) == ("2026年10月", 2, 1, 32.5, 20000)
    assert book["月嫂表現比較"]["B7"].data_type == "s"
    assert book["月嫂表現比較"]["C7"].data_type == "s"
    assert book["服務案件"].max_row == 9
    assert book["期間趨勢"].max_row == 7
    assert book["期間趨勢"]["A7"].value == "2026年10月"
    assert book["月嫂表現比較"]["D3"].value == "服務工時（含歷史估算）"
    assert book["月嫂表現比較"]["B4"].value == "2026-09-01 ～ 2026-09-30"


def test_authenticated_api_and_export_reject_mismatched_parameters():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: object()
    app.dependency_overrides[get_staff_performance_query] = query
    with TestClient(app) as client:
        response = client.get("/api/v1/operations-reports/staff-performance?year=2026&period=month&month=10")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["schema_version"] == "staff-performance.v2"
        assert data["totals"]["total_amount_ntd"] == 20000
        assert client.get("/api/v1/operations-reports/staff-performance?year=2026&period=year&month=10").status_code == 400
        assert client.get("/api/v1/operations-reports/staff-performance?year=2026&period=year&sort_by=invalid").status_code == 400
        assert client.get("/api/v1/operations-reports/staff-performance?year=2026&period=month&month=10&staff_id=999").status_code == 400
        export = client.get("/api/v1/operations-reports/staff-performance/export?year=2026&period=month&month=10&sort_by=case_count")
        assert export.status_code == 200 and export.headers["X-Staff-Performance-Version"] == "staff-performance.v2"
        assert load_workbook(BytesIO(export.content))["月嫂表現比較"].max_row == 9
    def deny_admin():
        raise HTTPException(status_code=401)
    app.dependency_overrides[require_admin] = deny_admin
    with TestClient(app) as client:
        assert client.get("/api/v1/operations-reports/staff-performance?year=2026&period=year").status_code in {401, 403}


def test_adapter_reads_effective_work_days_without_writes():
    from infrastructure.mysql.staff_performance_query_repository import MySqlStaffPerformanceQueryRepository

    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, params):
            assert "SELECT DISTINCT" in sql
            assert "g.effective_marker=1" in sql and "ss.is_work_day=1" in sql and "ss.effective_marker=1" in sql
            assert "'cancelled','replaced'" in sql
            assert params == (date(2026, 10, 1), date(2026, 10, 31))
        def fetchall(self):
            return [{"staff_id": 1, "case_no": "A", "work_date": date(2026, 10, 1), "service_hours_per_day": Decimal("8.5")}]

    class Connection:
        def cursor(self): return Cursor()

    days = MySqlStaffPerformanceQueryRepository(Connection()).list_service_days(date(2026, 10, 1), date(2026, 10, 31))
    assert days[0].hours == 8.5


def test_case_amount_adapter_borrows_full_owner_pricing_facts(monkeypatch):
    from domains.client_finance.pricing_policy import CasePricingTerms, HourlyRates, IdentityRule
    from subsystems.client_finance.pricing_configuration import CasePricingFacts, PricingServiceDay
    from infrastructure.mysql import staff_performance_query_repository as adapter

    class PricingRepository:
        def __init__(self, connection): pass
        def case(self, case_no):
            assert case_no == "A"
            return CasePricingFacts("A", 1, (), CasePricingTerms("補助市民", IdentityRule.SOCIAL,
                Decimal(120), HourlyRates(350, 350), HourlyRates(300, 300)), "policy",
                (PricingServiceDay(date(2026, 9, 30), Decimal(8)), PricingServiceDay(date(2026, 10, 1), Decimal(8))), 500)
    monkeypatch.setattr(adapter, "MySqlPricingConfigurationRepository", PricingRepository)
    assert adapter.MySqlStaffPerformanceQueryRepository(object()).case_amounts(("A",)) == {"A": 6100}


def cross_month_facts():
    facts = Facts()
    facts.days = (PerformanceServiceDay(1, "A", date(2026, 10, 30), 8),
                  PerformanceServiceDay(1, "A", date(2026, 10, 31), 8),
                  PerformanceServiceDay(1, "A", date(2026, 11, 1), 8))
    facts.openings = {"A": PerformanceCaseOpening("A", date(2026, 10, 30), 1)}
    return facts


def test_user_example_october_november_and_fourth_quarter():
    q = query(cross_month_facts())
    october, november, quarter = q.query(2026, "month", 10), q.query(2026, "month", 11), q.query(2026, "quarter", quarter=4)
    assert (october.totals.case_count, october.totals.service_hours, october.totals.total_amount_ntd) == (1, 16, 100000)
    assert (november.totals.case_count, november.totals.service_hours, november.totals.total_amount_ntd) == (0, 8, 0)
    assert (quarter.totals.case_count, quarter.totals.service_hours, quarter.totals.total_amount_ntd) == (1, 24, 100000)
    assert [(point.label, point.totals.case_count, point.totals.service_hours, point.totals.total_amount_ntd) for point in quarter.trend] == [("10月", 1, 16, 100000), ("11月", 0, 8, 0)]
    assert november.service_staff_count == 1
    detail = november.rows[0].cases[0]
    assert detail.total_amount_ntd == 100000 and detail.recognized_amount_ntd == 0


def test_historical_assignment_spans_three_months_and_only_credits_the_opening_month():
    case_no = "HISTORICAL-THREE-MONTHS"
    start, end = date(2026, 7, 27), date(2026, 9, 4)
    facts = Facts()
    facts.days = ()
    facts.openings = {case_no: PerformanceCaseOpening(case_no, start, 1)}
    facts.amounts = {case_no: 57600}
    assignment = PerformanceHistoricalAssignment(1, case_no, start, end, "週休二日", 8, 30, 24)
    facts.list_historical_assignments = lambda _start, _end: (assignment,)
    report_query = query(facts)
    expected = [(4, 32, 1, 57600), (17, 136, 0, 0), (3, 24, 0, 0)]

    for month, (days, hours, count, amount) in zip((7, 8, 9), expected, strict=True):
        report = report_query.query(2026, "month", month=month, staff_id=1)
        assert report.service_staff_count == 1
        assert (report.totals.service_hours, report.totals.case_count, report.totals.total_amount_ntd) == (hours, count, amount)
        (case,) = report.rows[0].cases
        assert (case.case_no, case.work_days, case.service_hours, case.recognized_case_count,
                case.recognized_amount_ntd, case.total_amount_ntd) == (case_no, days, hours, count, amount, 57600)

    quarter = report_query.query(2026, "quarter", quarter=3, staff_id=1)
    year = report_query.query(2026, "year", staff_id=1)
    assert (quarter.totals.service_hours, quarter.totals.case_count, quarter.totals.total_amount_ntd) == (192, 1, 57600)
    assert year.totals == quarter.totals
    assert [(point.totals.service_hours, point.totals.case_count, point.totals.total_amount_ntd)
            for point in quarter.trend] == [row[1:] for row in expected]


def test_handover_has_hours_but_never_takes_the_opening_credit():
    facts = cross_month_facts()
    facts.days = facts.days[:2] + (replace(facts.days[2], staff_id=2),)
    report = query(facts).query(2026, "quarter", quarter=4)
    assert (report.rows[0].totals.case_count, report.rows[0].totals.total_amount_ntd) == (1, 100000)
    assert (report.rows[1].totals.case_count, report.rows[1].totals.service_hours, report.rows[1].totals.total_amount_ntd) == (0, 8, 0)
    november = query(facts).query(2026, "month", 11, staff_id=2)
    assert november.service_staff_count == 1 and november.rows[0].totals.service_hours == 8
    assert november.rows[0].cases[0].primary_staff_id == 1


def test_opening_principal_with_no_personal_work_days_is_still_credited():
    facts = cross_month_facts()
    facts.days = tuple(replace(day, staff_id=2) for day in facts.days)
    report = query(facts).query(2026, "month", 10, staff_id=1)
    assert (report.totals.case_count, report.totals.service_hours, report.totals.total_amount_ntd) == (1, 0, 100000)
    assert report.service_staff_count == 0
    assert report.rows[0].cases[0].service_start is None
    assert report.rows[0].cases[0].recognized_amount_ntd == 100000


def test_missing_actual_start_keeps_hours_and_marks_credit_unknown():
    facts = cross_month_facts()
    facts.openings["A"] = replace(facts.openings["A"], actual_start_date=None)
    report = query(facts).query(2026, "month", 10)
    assert report.totals.service_hours == 16
    assert report.totals.case_count is None and report.totals.total_amount_ntd is None
    assert report.rows[0].cases[0].recognized_case_count is None
    book = load_workbook(BytesIO(export_staff_performance(report)))
    assert book["期間摘要"]["C7"].value == book["期間摘要"]["E7"].value == "待確認"
    assert book["服務案件"]["D7"].value == "待確認"


def test_date_and_amount_corrections_move_credit_without_duplicates():
    facts = cross_month_facts()
    facts.openings["A"] = replace(facts.openings["A"], actual_start_date=date(2026, 11, 1))
    facts.days = (PerformanceServiceDay(1, "A", date(2026, 11, 1), 8),)
    facts.amounts["A"] = 90000
    q = query(facts)
    assert q.query(2026, "month", 10).totals.case_count == 0
    assert q.query(2026, "month", 10).totals.total_amount_ntd == 0
    assert q.query(2026, "month", 11).totals.total_amount_ntd == 90000
    assert q.query(2026, "quarter", quarter=4).totals.case_count == 1


def test_cross_year_service_only_credits_the_opening_year():
    facts = cross_month_facts()
    facts.openings["A"] = replace(facts.openings["A"], actual_start_date=date(2025, 12, 31))
    facts.days = (PerformanceServiceDay(1, "A", date(2025, 12, 31), 8), PerformanceServiceDay(1, "A", date(2026, 1, 1), 8))
    q = query(facts)
    assert q.query(2025, "year").totals.total_amount_ntd == 100000
    assert (q.query(2026, "year").totals.case_count, q.query(2026, "year").totals.total_amount_ntd) == (0, 0)
    assert q.query(2026, "year").totals.service_hours == 8


def test_cancellation_retains_opening_and_only_confirmed_remaining_schedule():
    facts = cross_month_facts()
    facts.days = facts.days[:1]
    facts.amounts["A"] = 2800
    report = query(facts).query(2026, "month", 10)
    assert (report.totals.case_count, report.totals.service_hours, report.totals.total_amount_ntd) == (1, 8, 2800)
    assert query(facts).query(2026, "month", 11).totals.case_count == 0


def test_xlsx_recognized_detail_and_monthly_trend_reconcile():
    report = query(cross_month_facts()).query(2026, "quarter", quarter=4)
    book = load_workbook(BytesIO(export_staff_performance(report, "service_hours")))
    assert book["期間摘要"]["A7"].value == "2026年第4季"
    assert [(row[0], row[1], row[2], row[3]) for row in book["期間趨勢"].iter_rows(min_row=7, values_only=True)] == [("2026年10月", 1, 16, 100000), ("2026年11月", 0, 8, 0)]
    assert book["服務案件"]["J7"].value == 100000
    assert book["服務案件"]["L7"].value == 100000
    november = load_workbook(BytesIO(export_staff_performance(query(cross_month_facts()).query(2026, "month", 11))))
    assert november["服務案件"]["J7"].value == 100000 and november["服務案件"]["L7"].value == 0
    assert november["月嫂表現比較"]["A7"].value == 1


def test_opening_repository_resolves_first_day_substitution_after_rebuild():
    from infrastructure.mysql.staff_performance_query_repository import MySqlStaffPerformanceQueryRepository
    responses = [
        [{"case_no": "A", "actual_start_date": date(2026, 10, 30), "first_assignment_id": 3}],
        [{"case_no": "A", "id": i, "staff_id": 1 if i == 1 else 2, "assignment_sequence": 1,
          "first_service_date": date(2026, 10, 30)} for i in (1, 2, 3)],
        [{"case_no": "A", "old_assignment_identity": "assignment:2", "new_assignment_id": 3}],
        [{"case_no": "A", "original_assignment_id": 1, "original_work_date": date(2026, 10, 30),
          "resulting_assignment_id": 2, "resulting_service_date": date(2026, 10, 30)}],
        [],
    ]
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, params): assert sql.strip().startswith("SELECT")
        def fetchall(self): return responses.pop(0)
    class Connection:
        def cursor(self): return Cursor()
    result = MySqlStaffPerformanceQueryRepository(Connection()).list_case_openings(date(2026, 10, 1), date(2026, 10, 31), ("A",))
    assert result == (PerformanceCaseOpening("A", date(2026, 10, 30), 1),)


@pytest.mark.parametrize("missing_pricing_reason", [
    "historical_client_payment_terms_missing",
    "client_finance_bootstrap_required",
])
def test_historical_hours_follow_rest_mode_and_confirmed_days_across_months(monkeypatch, missing_pricing_reason):
    from infrastructure.mysql import staff_performance_query_repository as adapter

    database = sqlite3.connect(":memory:", detect_types=sqlite3.PARSE_DECLTYPES)
    database.row_factory = sqlite3.Row
    database.create_function("YEAR", 1, lambda value: int(value[:4]))
    database.executescript("""
        CREATE TABLE orders (case_no TEXT, actual_start_date DATE, status TEXT, service_hours_per_day REAL,
            service_days INT, client_id INT);
        CREATE TABLE clients (id INT, service_type TEXT);
        CREATE TABLE staff (id INT, union_no TEXT, name TEXT);
        CREATE TABLE scheduling_generations (id INT, case_no TEXT, effective_marker INT);
        CREATE TABLE staff_schedule (assignment_id INT, generation_id INT, effective_marker INT,
            is_work_day INT, work_date DATE);
        CREATE TABLE case_staff_assignments (id INT, case_no TEXT, staff_id INT, generation_id INT,
            status TEXT, assignment_sequence INT, assigned_start_date DATE, assigned_end_date DATE);
        CREATE TABLE historical_order_adoption_receipts (id INT, case_no TEXT, outcome TEXT);
        CREATE TABLE historical_order_pairing_evidence (receipt_id INT, staff_id INT, assignment_id INT,
            source_start_date DATE, source_end_date DATE);
        CREATE TABLE historical_service_day_projections (case_no TEXT, current_event_id INT);
        CREATE TABLE historical_service_day_items (event_id INT, assignment_id INT, staff_id INT, actual_service_days INT);
        CREATE TABLE scheduling_rebuild_lineage (old_assignment_identity TEXT, new_assignment_id INT);
        CREATE TABLE scheduling_leave_substitution_receipts (case_no TEXT, batch_key TEXT);
        CREATE TABLE scheduling_leave_substitution_outcomes (batch_key TEXT, original_assignment_id INT,
            original_work_date DATE, resulting_assignment_id INT, resulting_service_date DATE);
        INSERT INTO staff VALUES (1,'U1','甲'),(2,'U2','乙');
        INSERT INTO clients VALUES (1,'週休二日'),(2,'週休一日');
        INSERT INTO orders VALUES
            ('H','2024-10-30','歷史訂單－帳務完成',8,11,1),
            ('P','2023-11-02','歷史訂單－服務完成',8,4,2),
            ('A','2024-10-03','歷史訂單－服務中',8,3,1),
            ('U','2024-10-01','歷史訂單－未服務',8,5,1),
            ('S','2024-10-20','歷史訂單－服務完成',8,4,1);
        INSERT INTO historical_order_adoption_receipts VALUES
            (1,'H','adopted'),(2,'H','adopted'),(3,'P','adopted'),(4,'A','adopted'),
            (5,'U','adopted'),(6,'S','adopted');
        INSERT INTO case_staff_assignments VALUES
            (1,'H',2,NULL,'completed',1,'2024-10-30','2024-11-05'),
            (2,'H',1,NULL,'completed',2,'2024-10-30','2024-11-05'),
            (3,'P',2,NULL,'completed',1,'2023-11-02','2023-11-08'),
            (4,'A',1,NULL,'completed',1,'2024-10-03','2024-10-12'),
            (5,'U',2,NULL,'completed',1,'2024-10-01','2024-10-05'),
            (6,'S',2,NULL,'completed',1,'2024-10-20','2024-10-25'),
            (7,'S',1,1,'completed',2,'2024-10-20','2024-10-25'),
            (8,'H',2,NULL,'completed',3,'2024-11-01','2024-11-05');
        INSERT INTO historical_service_day_projections VALUES ('H',1);
        INSERT INTO historical_service_day_items VALUES (1,2,1,7),(1,8,2,2);
        INSERT INTO historical_order_pairing_evidence VALUES
            (1,2,1,'2024-10-30','2024-11-10'),(2,1,2,'2024-10-30','2024-11-10'),
            (3,2,3,'2023-11-02','2023-11-08'),(4,1,4,'2024-10-03','2024-10-12'),
            (4,NULL,NULL,'2024-10-03','2024-10-05'),(5,2,5,'2024-10-01','2024-10-05'),
            (6,2,6,'2024-10-20','2024-10-25');
        INSERT INTO scheduling_generations VALUES (1,'S',1);
        INSERT INTO staff_schedule VALUES (7,1,1,1,'2024-10-20');
    """)

    class Cursor:
        def __enter__(self):
            self.cursor = database.cursor()
            return self

        def __exit__(self, *args):
            self.cursor.close()

        def execute(self, sql, params=()):
            self.cursor.execute(sql.replace("%s", "?"), params)

        def fetchall(self):
            return self.cursor.fetchall()

    class PricingRepository:
        def __init__(self, connection):
            pass

        def case(self, case_no):
            if case_no == "P":
                raise ValueError(missing_pricing_reason)
            return {"H": 12800, "S": 2000}[case_no]

    class Connection:
        def cursor(self):
            return Cursor()

    monkeypatch.setattr(adapter, "MySqlPricingConfigurationRepository", PricingRepository)
    monkeypatch.setattr(adapter, "case_total_amount", lambda amount: amount)
    repository = adapter.MySqlStaffPerformanceQueryRepository(Connection())
    try:
        october = query(repository).query(2024, "month", 10)
        november = query(repository).query(2024, "month", 11)
        missing_amount = query(repository).query(2023, "month", 11)
        quarter = query(repository).query(2024, "quarter", quarter=4)
        continuing_openings = repository.list_case_openings(date(2024, 11, 1), date(2024, 11, 30), ("H",))
    finally:
        database.close()

    assert (october.totals.case_count, october.totals.total_amount_ntd, october.totals.service_hours) == (2, 14800, 32)
    assert october.rows[1].cases == ()
    historical_case = october.rows[0].cases[0]
    assert (historical_case.case_no, historical_case.recognized_amount_ntd, historical_case.service_hours) == ("H", 12800, 24)
    assert historical_case.work_days == 3
    assert (november.totals.case_count, november.totals.service_hours, november.service_staff_count) == (0, 48, 2)
    assert continuing_openings == (PerformanceCaseOpening("H", date(2024, 10, 30), 1),)
    assert november.rows[1].cases[0].service_hours == 16
    assert missing_amount.rows[1].cases[0].service_hours == 32
    assert missing_amount.rows[1].cases[0].service_start == date(2023, 11, 2)
    assert (missing_amount.totals.case_count, missing_amount.totals.total_amount_ntd) == (1, None)
    assert quarter.totals.case_count == 2
    assert quarter.totals.service_hours == 80
    assert [point.totals.service_hours for point in quarter.trend] == [32, 48, 0]
    assert [(point.totals.case_count, point.totals.total_amount_ntd) for point in quarter.trend] == [
        (2, 14800), (0, 0), (0, 0),
    ]
    assert october.available_years == (2026, 2024, 2023)
    workbook = load_workbook(BytesIO(export_staff_performance(october)))
    assert workbook["服務案件"]["I7"].value == 24
    assert workbook["服務案件"]["L7"].value == 12800
