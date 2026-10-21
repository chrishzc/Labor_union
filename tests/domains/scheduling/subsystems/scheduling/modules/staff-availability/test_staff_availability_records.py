"""Contract checks for bounded full-history availability reads; no live database."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_admin
from api.dependencies.staff_availability import get_staff_availability_application
from api.routes.staff_availability import router
from domains.scheduling.staff_availability import StaffUnavailabilityBlock
from infrastructure.mysql.staff_availability_repository import MySqlStaffAvailabilityRepository
from subsystems.scheduling.staff_availability_workflow import (
    StaffAvailabilityQuery,
    StaffAvailabilityRecordsQuery,
    StaffAvailabilityWorkflow,
)


def block(identity, start, end):
    return StaffUnavailabilityBlock(identity, 11, "long_leave", date.fromisoformat(start), date.fromisoformat(end), "effective", "")


@pytest.fixture
def client():
    application = SimpleNamespace(query=Mock(return_value=[]), query_records=Mock(return_value=[]))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: object()
    app.dependency_overrides[get_staff_availability_application] = lambda: application
    with TestClient(app) as http:
        yield http, application


def test_omitting_dates_reads_bounded_history_including_past_and_future(client):
    http, application = client
    application.query_records.return_value = [block(101, "2020-01-01", "2020-01-31"), block(102, "2030-01-01", "2030-01-31")]
    response = http.get("/api/v1/scheduling/staff/11/availability-blocks?after_id=100&limit=2")
    assert response.status_code == 200
    assert [item["start_date"] for item in response.json()["data"]] == ["2020-01-01", "2030-01-01"]
    application.query_records.assert_called_once_with(StaffAvailabilityRecordsQuery(11, 100, 2))
    application.query.assert_not_called()


@pytest.mark.parametrize("query", ["limit=201", "limit=0", "after_id=-1", "range_start=2026-01-01"])
def test_rejects_invalid_page_or_partial_date_range(client, query):
    http, _ = client
    assert http.get("/api/v1/scheduling/staff/11/availability-blocks?" + query).status_code == 422


def test_existing_date_query_remains_independent_of_record_pagination(client):
    http, application = client
    response = http.get("/api/v1/scheduling/staff/11/availability-blocks?range_start=2026-01-01&range_end=2026-12-31")
    assert response.status_code == 200
    application.query.assert_called_once_with(StaffAvailabilityQuery(11, date(2026, 1, 1), date(2026, 12, 31)))
    application.query_records.assert_not_called()
    assert http.get("/api/v1/scheduling/staff/11/availability-blocks?range_start=2020-01-01&range_end=2030-01-01").status_code == 422


def test_records_workflow_only_reads_without_opening_a_mutation_unit_of_work():
    repository, unit_of_work = Mock(), Mock()
    repository.list_records.return_value = ()
    workflow = StaffAvailabilityWorkflow(repository, Mock(), unit_of_work)
    query = StaffAvailabilityRecordsQuery(11, 100, 2)
    assert workflow.query_records(query) == ()
    repository.list_records.assert_called_once_with(query)
    unit_of_work.assert_not_called()


def test_mysql_record_query_is_scoped_to_staff_cursor_and_limit_without_commit():
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    cursor.fetchone.return_value = {"id": 11}
    cursor.fetchall.return_value = []
    connection = Mock()
    connection.cursor.return_value = cursor
    assert MySqlStaffAvailabilityRepository(connection).list_records(StaffAvailabilityRecordsQuery(11, 100, 2)) == ()
    sql, parameters = cursor.execute.call_args.args
    assert "WHERE staff_id=%s AND id>%s ORDER BY id LIMIT %s" in sql
    assert parameters == (11, 100, 2)
    assert all(call.args[0].lstrip().startswith("SELECT") for call in cursor.execute.call_args_list)
    connection.commit.assert_not_called()
