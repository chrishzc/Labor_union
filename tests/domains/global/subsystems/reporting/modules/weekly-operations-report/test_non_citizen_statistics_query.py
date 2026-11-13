"""Exercise the Reporting adapter's joins and calendar filters on synthetic rows."""

from contextlib import contextmanager
from datetime import date, datetime
import sqlite3

import pytest

from infrastructure.mysql.case_category_query import CASE_CATEGORY_SQL
from infrastructure.mysql.weekly_operations_report_query_adapter import MySqlWeeklyOperationsReportQueryAdapter
from subsystems.reporting.weekly_operations_report_query import WeeklyOperationsReportQuery


class SqliteReportingConnection:
    def __init__(self, connection):
        self.connection = connection

    @contextmanager
    def cursor(self):
        cursor = self.connection.cursor()

        class Cursor:
            def execute(self, sql, params=()):
                # Keep the adapter query. Substitute only the SQL dialect and the
                # separately owned accounting classification for this test.
                sql = (
                    sql.replace(CASE_CATEGORY_SQL, "c.category")
                    .replace("DATE_ADD(r.approved_at_utc,INTERVAL 8 HOUR)", "datetime(r.approved_at_utc,'+8 hours')")
                    .replace("JSON_UNQUOTE(JSON_EXTRACT(m.source_snapshot,'$.client_attributes.created_at'))",
                             "json_extract(m.source_snapshot,'$.client_attributes.created_at')")
                    .replace("CAST(REPLACE(json_extract(m.source_snapshot,'$.client_attributes.created_at'),'T',' ') AS DATETIME(6))",
                             "replace(json_extract(m.source_snapshot,'$.client_attributes.created_at'),'T',' ')")
                    .replace("CONCAT('manual-non-citizen:',o.case_no)", "('manual-non-citizen:' || o.case_no)")
                    .replace("YEAR(", "report_year(")
                    .replace("%s", "?")
                )
                cursor.execute(sql, tuple(value.isoformat(sep=" ") for value in params))

            def fetchall(self):
                return [dict(row) for row in cursor.fetchall()]

        try:
            yield Cursor()
        finally:
            cursor.close()


@pytest.fixture
def report_source():
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.create_function("report_year", 1, lambda value: int(value[:4]))
        db.executescript("""
            CREATE TABLE clients (
                id INTEGER PRIMARY KEY, category TEXT, identity_status TEXT, hcm_review_status TEXT
            );
            CREATE TABLE orders (case_no TEXT PRIMARY KEY, client_id INTEGER, status TEXT);
            CREATE TABLE provisional_client_registrations (id INTEGER PRIMARY KEY, approved_at_utc TEXT);
            CREATE TABLE provisional_registration_case_issue_events (
                registration_id INTEGER UNIQUE, case_no TEXT UNIQUE, client_id INTEGER
            );
            CREATE TABLE case_import_events (
                case_no TEXT UNIQUE, client_id INTEGER, idempotency_key TEXT UNIQUE, source_snapshot TEXT
            );
            INSERT INTO clients VALUES
                (1, 'non_citizen', '非市民', NULL), (2, 'non_citizen', '非市民', NULL),
                (3, 'non_citizen', '非市民', NULL), (4, 'non_citizen', '非市民', NULL),
                (5, 'non_citizen', '非市民', NULL), (6, 'subsidy', '一般市民', NULL),
                (7, 'non_citizen', '非市民', '不符合'), (8, 'non_citizen', '非市民', NULL);
            INSERT INTO orders VALUES
                ('A116001', 1, '訂單成立'), ('A115001', 2, '洽談中'),
                ('A116002', 3, '待補件'), ('A116003', 4, '洽談中'),
                ('A116004', 5, '服務中'), ('115000001', 6, '洽談中'),
                ('115000002', 7, '訂單取消'), ('A116005', 8, '洽談中');
            INSERT INTO provisional_client_registrations VALUES
                (10, '2026-12-31 16:00:00'), (11, NULL), (12, NULL);
            INSERT INTO provisional_registration_case_issue_events VALUES
                (10, 'A116001', 1), (12, 'A116002', 3);
            INSERT INTO case_import_events VALUES
                ('A116001', 1, 'manual-non-citizen:A116001', '{"client_attributes":{"created_at":"2027-02-01T00:00:00"}}'),
                ('A115001', 2, 'manual-non-citizen:A115001', '{"client_attributes":{"created_at":"2026-12-31T23:59:59"}}'),
                ('A116002', 3, 'manual-non-citizen:A116002', '{"client_attributes":{"created_at":"2027-01-01T00:00:00"}}'),
                ('A116003', 4, 'legacy:A116003', '{"client_attributes":{"created_at":"2027-01-01T00:00:00"}}'),
                ('A116004', 5, 'manual-non-citizen:A116004', '{"client_attributes":{"created_at":"2027-01-01T00:00:00"}}'),
                ('115000001', 6, 'manual-non-citizen:115000001', '{"client_attributes":{"created_at":"2027-01-01T00:00:00"}}'),
                ('115000002', 7, 'manual-non-citizen:115000002', '{"client_attributes":{"created_at":"2027-01-01T00:00:00"}}'),
                ('A116005', 2, 'manual-non-citizen:A116005', '{"client_attributes":{"created_at":"2027-01-01T00:00:00"}}');
        """)
        yield MySqlWeeklyOperationsReportQueryAdapter(SqliteReportingConnection(db))


def test_manual_case_counts_in_selected_period(report_source):
    report = WeeklyOperationsReportQuery(report_source, lambda: datetime(2027, 1, 1))
    assert report.query_case_statistics(2026, month=12, case_category="non_citizen").summary.application_count == 1
    assert report.query_case_statistics(2026, month=11, case_category="non_citizen").summary.application_count == 0


def test_manual_case_counts_in_annual_total_outside_selected_month(report_source):
    report = WeeklyOperationsReportQuery(report_source, lambda: datetime(2027, 1, 1))
    assert report.query_case_statistics(2026, month=11, case_category="non_citizen").annual_application_count == 1


def test_formal_liff_and_manual_cases_share_one_taipei_calendar(report_source):
    report = WeeklyOperationsReportQuery(report_source, lambda: datetime(2027, 1, 1))
    december = report_source.list_non_citizen_case_statistics_facts(date(2026, 12, 31), date(2026, 12, 31))
    assert [(fact.client_id, fact.created_at) for fact in december] == [(2, datetime(2026, 12, 31, 23, 59, 59))]
    january = report_source.list_non_citizen_case_statistics_facts(date(2027, 1, 1), date(2027, 1, 1))
    assert [(fact.client_id, fact.created_at) for fact in january] == [(1, datetime(2027, 1, 1)), (5, datetime(2027, 1, 1))]
    assert report_source.list_non_citizen_case_years() == [2027, 2026]
    january_totals = report.query_case_statistics(2027, month=1, case_category="non_citizen")
    assert january_totals.summary.application_count == january_totals.annual_application_count == 2
    assert january_totals.summary.order_status_counts["訂單成立"] == 1
    assert january_totals.summary.order_status_counts["服務中"] == 1
    assert report.query_case_statistics(2027, month=2, case_category="non_citizen").summary.application_count == 0
