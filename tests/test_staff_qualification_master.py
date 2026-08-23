"""
File: test_staff_qualification_master.py
Description: 驗證 Staff qualification master 的 typed sections、PII 邊界與唯讀 SQL。
"""

from datetime import date, datetime
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymysql.err import ProgrammingError

from api.dependencies.admin_auth import require_admin
from api.exception_handlers import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.routes.staff_qualification_master import (
    get_staff_qualification_master_application,
    router,
)
from infrastructure.mysql.staff_qualification_master_repository import (
    MySqlStaffQualificationMasterRepository,
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.staff.qualification_master_query import (
    QualificationMasterQueryApplication,
    StaffQualificationMasterQuery,
    StaffQualificationMasterQueryService,
    StaffQualificationSourceRecord,
    StaffQualificationNotFound,
    UnavailabilitySourceRecord,
)


def _source(*, blocks=(), availability_ready=True):
    return StaffQualificationSourceRecord(
        staff_id=7,
        staff_name="去敏服務人員",
        staff_source_version="2026-08-21T01:02:03",
        special_skills=("新生兒照護",),
        cooking_skills=(("葷食", "低油"),),
        massage_certified=True,
        unavailability_source_available=availability_ready,
        unavailability_source_reason=(
            "scheduling_staff_unavailability_ready"
            if availability_ready
            else "staff_unavailability_schema_not_ready"
        ),
        unavailability_blocks=tuple(blocks),
    )


def _application(source):
    class _Repository:
        def fetch(self, _query):
            return source

    return QualificationMasterQueryApplication(
        StaffQualificationMasterQueryService(_Repository())
    )


def _client(application):
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(
        9,
        "staff-reader",
        "Staff Reader",
        "admin",
    )
    app.dependency_overrides[get_staff_qualification_master_application] = lambda: application
    return TestClient(app)


def test_staff_qualification_master_projects_all_owned_sections_and_redacts_pii():
    block = UnavailabilitySourceRecord(
        block_id=91,
        kind="long_leave",
        start_date=date(2026, 8, 20),
        end_date=date(2026, 8, 30),
        source_version="2026-08-19T09:00:00",
    )
    response = _client(_application(_source(blocks=(block,)))).get(
        "/api/v1/staff/7/qualification-master",
        params={"as_of": "2026-08-21"},
        headers={"X-Correlation-ID": "staff-qualification-01"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert tuple(section["kind"] for section in payload["sections"]) == (
        "skills",
        "cooking",
        "certifications",
        "medical",
        "validity",
        "unavailability",
    )
    assert payload["overall_availability"] == "unavailable"
    assert payload["availability_reason"] == "effective_staff_unavailability"
    assert payload["sections"][3]["availability"] == "unavailable"
    assert payload["sections"][3]["availability_reason"] == "staff_medical_registry_not_provided"
    assert payload["sections"][4]["availability_reason"] == "qualification_validity_registry_not_provided"
    assert payload["sections"][5]["items"][0]["valid_until"] == "2026-08-30"
    assert "phone" not in payload
    assert "address" not in payload
    assert "email" not in payload
    assert response.headers["X-Correlation-ID"] == "staff-qualification-01"


def test_staff_qualification_master_keeps_unknown_availability_when_schedule_source_is_not_ready():
    response = _client(_application(_source(availability_ready=False))).get(
        "/api/v1/staff/7/qualification-master",
        params={"as_of": "2026-08-21"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["overall_availability"] == "unknown"
    section = next(item for item in payload["sections"] if item["kind"] == "unavailability")
    assert section["availability"] == "unavailable"
    assert section["availability_reason"] == "staff_unavailability_schema_not_ready"


def test_staff_qualification_master_rejects_missing_staff_as_typed_not_found():
    class _Repository:
        def fetch(self, _query):
            raise StaffQualificationNotFound("staff:7")

    application = QualificationMasterQueryApplication(
        StaffQualificationMasterQueryService(_Repository())
    )
    response = _client(application).get(
        "/api/v1/staff/7/qualification-master",
        headers={"X-Correlation-ID": "staff-qualification-404"},
    )

    assert response.status_code == 404
    error = response.json()["detail"]["error"]
    assert error["code"] == "staff_qualification_staff_not_found"
    assert error["correlation_id"] == "staff-qualification-404"


def test_staff_qualification_master_requires_admin_before_application():
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)

    def _must_not_run():
        raise AssertionError("qualification application must not be built")

    app.dependency_overrides[get_staff_qualification_master_application] = _must_not_run
    response = TestClient(app).get("/api/v1/staff/7/qualification-master")

    assert response.status_code == 401


class _Cursor:
    def __init__(self, staff_row, cooking_rows, unavailability_rows):
        self._staff_row = staff_row
        self._cooking_rows = cooking_rows
        self._unavailability_rows = unavailability_rows
        self.executed = []
        self._fetchone_used = False
        self._fetchall_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        self.executed.append((sql, params))

    def fetchone(self):
        self._fetchone_used = True
        return self._staff_row

    def fetchall(self):
        self._fetchall_count += 1
        return self._cooking_rows if self._fetchall_count == 1 else self._unavailability_rows


class _Connection:
    def __init__(self, cursor):
        self.cursor_instance = cursor
        self.commit_called = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commit_called = True
        raise AssertionError("qualification query must not commit")


def test_staff_qualification_repository_uses_bounded_selects_without_commit():
    cursor = _Cursor(
        {
            "id": 7,
            "name": "去敏服務人員",
            "has_massage_cert": 1,
            "special_skills": '["新生兒照護"]',
            "updated_at": datetime(2026, 8, 21, 1, 2, 3),
        },
        [{"skill_name": "葷食", "custom_skill_detail": None}],
        [],
    )
    connection = _Connection(cursor)
    source = MySqlStaffQualificationMasterRepository(connection).fetch(
        StaffQualificationMasterQuery(7, date(2026, 8, 21))
    )

    assert source.staff_id == 7
    assert source.special_skills == ("新生兒照護",)
    assert source.cooking_skills == (("葷食", None),)
    assert source.unavailability_blocks == ()
    assert len(cursor.executed) == 3
    assert all(re.search(r"\b(?:INSERT|UPDATE|DELETE)\b", sql, re.IGNORECASE) is None for sql, _ in cursor.executed)
    assert connection.commit_called is False


def test_staff_qualification_repository_fails_closed_on_malformed_legacy_skill_json():
    cursor = _Cursor(
        {
            "id": 7,
            "name": "去敏服務人員",
            "has_massage_cert": 0,
            "special_skills": "not-json",
            "updated_at": None,
        },
        [],
        [],
    )

    with pytest.raises(ValueError, match="special_skills JSON"):
        MySqlStaffQualificationMasterRepository(_Connection(cursor)).fetch(
            StaffQualificationMasterQuery(7, date(2026, 8, 21))
        )


class _MissingAvailabilityCursor(_Cursor):
    def execute(self, sql, params):
        super().execute(sql, params)
        if "scheduling_staff_unavailability_blocks" in sql:
            raise ProgrammingError(1146, "table missing")


def test_staff_qualification_repository_marks_missing_schedule_table_unavailable():
    cursor = _MissingAvailabilityCursor(
        {
            "id": 7,
            "name": "去敏服務人員",
            "has_massage_cert": 0,
            "special_skills": None,
            "updated_at": None,
        },
        [],
        [],
    )

    source = MySqlStaffQualificationMasterRepository(_Connection(cursor)).fetch(
        StaffQualificationMasterQuery(7, date(2026, 8, 21))
    )

    assert source.unavailability_source_available is False
    assert source.unavailability_source_reason == "staff_unavailability_schema_not_ready"
    assert source.unavailability_blocks == ()
