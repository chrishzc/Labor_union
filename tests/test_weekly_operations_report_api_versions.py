"""週報 v3/v4 wire contract：使用實際 FastAPI route，Query/auth 為 dependency overrides。"""
import json

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.routes import operations_reports as routes
from api.schemas.operations_reports import (
    WeeklyOperationsReportTotalsView,
    WeeklyOperationsReportView,
)


@dataclass
class _Summary:
    application_count: int = 0
    general_eligible_count: int = 0
    general_ineligible_count: int | None = None
    subsidized_eligible_count: int = 0
    subsidized_ineligible_count: int | None = None
    rejection_unpartitioned_count: int = 0
    order_established_count: int = 0
    negotiating_count: int = 0
    cancelled_count: int = 0
    incomplete_count: int = 0


@dataclass
class _Totals(_Summary):
    year: int = 2026
    month: int | None = None
    start_date: date = date(2026, 1, 5)
    end_date: date = date(2026, 9, 13)
    promotion_count: int | None = None
    inquiry_count: int | None = 0
    review_rejected_count: int = 0
    order_status_counts: dict[str, int] = field(default_factory=lambda: {"待補件": 0})


PARAMS = {"start_date": "2026-08-31", "end_date": "2026-09-13"}
V3_KEYS = {
    "schema_version", "period", "generated_at", "source_revision", "summary",
    "case_rows", "subsidy_partitions", "service_rows", "weekly_metrics", "data_quality_issues",
}


@pytest.fixture
def api():
    report = SimpleNamespace(
        start_date=date(2026, 8, 31), end_date=date(2026, 9, 13), timezone="Asia/Taipei",
        period_label="2026-08-31 ~ 2026-09-13", generated_at=datetime(2026, 9, 23, tzinfo=timezone.utc),
        source_revision="wire-contract-fixture", summary=_Summary(), case_rows=(),
        subsidy_partitions=tuple(SimpleNamespace(citizen_kind=kind, rows=()) for kind in ("general", "subsidized")),
        service_rows=(), weekly_metrics=(), data_quality_issues=(),
        annual_totals=(_Totals(),),
        monthly_subtotals=(_Totals(month=8, start_date=date(2026, 8, 31)),),
    )
    calls = []

    class Query:
        def query(self, start_date, end_date):
            calls.append((start_date, end_date))
            return report

    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.require_admin] = lambda: object()
    app.dependency_overrides[routes.get_weekly_operations_report_query] = Query
    with TestClient(app) as client:
        yield client, report, calls, app


def test_unversioned_client_gets_exact_v3_without_new_keys(api):
    client, report, calls, _ = api
    # Even the projection must not read totals when an old client asks for v3.
    del report.annual_totals, report.monthly_subtotals
    response = client.get("/api/v1/operations-reports/weekly", params=PARAMS)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["schema_version"] == "operations-report.v3"
    assert set(data) == V3_KEYS
    assert WeeklyOperationsReportView.model_validate_json(json.dumps(data))
    assert len(calls) == 1


def test_explicit_v3_matches_default_and_v4_only_adds_required_totals(api):
    client, _, _, _ = api
    legacy = client.get("/api/v1/operations-reports/weekly", params=PARAMS).json()["data"]
    explicit = client.get("/api/v1/operations-reports/weekly", params={**PARAMS, "schema_version": "operations-report.v3"})
    assert explicit.status_code == 200
    assert explicit.json()["data"] == legacy
    response = client.get("/api/v1/operations-reports/weekly", params={**PARAMS, "schema_version": "operations-report.v4"})
    assert response.status_code == 200
    current = response.json()["data"]
    assert set(current) == V3_KEYS | {"annual_totals", "monthly_subtotals"}
    assert current["schema_version"] == "operations-report.v4"
    assert current["annual_totals"][0]["promotion_count"] is None
    assert current["annual_totals"][0]["inquiry_count"] == 0
    assert current["monthly_subtotals"][0]["order_status_counts"] == {"待補件": 0}
    assert {k: v for k, v in current.items() if k in V3_KEYS and k != "schema_version"} == {
        k: v for k, v in legacy.items() if k != "schema_version"
    }


@pytest.mark.parametrize("version", ["operations-report.v2", "operations-report.v5", "", "4"])
def test_unsupported_versions_are_rejected_before_query(api, version):
    client, _, calls, _ = api
    response = client.get("/api/v1/operations-reports/weekly", params={**PARAMS, "schema_version": version})
    assert response.status_code == 422
    assert calls == []


def test_strict_versions_cannot_be_mixed_or_default_missing_totals(api):
    _, report, _, _ = api
    current = routes._weekly_report_view(report, "operations-report.v4").model_dump()
    with pytest.raises(ValidationError):
        WeeklyOperationsReportView.model_validate({**current, "schema_version": "operations-report.v3"})
    for field_name in ("annual_totals", "monthly_subtotals"):
        missing = dict(current)
        del missing[field_name]
        with pytest.raises(ValidationError):
            WeeklyOperationsReportTotalsView.model_validate(missing)
    with pytest.raises(ValidationError):
        WeeklyOperationsReportTotalsView.model_validate({**current, "unexpected": 1})


def test_export_marks_actual_new_format_and_preserves_media_and_filename(api, monkeypatch):
    client, report, _, _ = api
    payload = b"PK\x03\x04fixture"
    seen = []

    def export(candidate):
        seen.append(candidate)
        return payload

    monkeypatch.setattr(routes, "export_weekly_operations_report", export)
    response = client.get("/api/v1/operations-reports/weekly/export", params=PARAMS)
    assert response.status_code == 200
    assert response.headers["X-Operations-Report-Version"] == "operations-report.v4"
    assert response.headers["content-type"] == routes.XLSX_MEDIA_TYPE
    assert response.headers["content-disposition"] == 'attachment; filename="operations-report-2026-08-31_2026-09-13.xlsx"'
    assert response.content == payload
    assert seen == [report]


def test_openapi_exposes_default_v3_and_both_response_versions(api):
    _, _, _, app = api
    schema = app.openapi()
    operation = schema["paths"]["/api/v1/operations-reports/weekly"]["get"]
    version = next(p for p in operation["parameters"] if p["name"] == "schema_version")
    assert version["schema"]["default"] == "operations-report.v3"
    assert version["schema"]["enum"] == ["operations-report.v3", "operations-report.v4"]
    models = schema["components"]["schemas"]
    assert "annual_totals" not in models["WeeklyOperationsReportView"]["properties"]
    assert {"annual_totals", "monthly_subtotals"}.issubset(models["WeeklyOperationsReportTotalsView"]["required"])
