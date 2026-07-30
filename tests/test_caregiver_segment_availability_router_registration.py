from pathlib import Path

from api.main import app


def test_caregiver_segment_availability_router_registration_and_uniqueness():
    source = Path("api/main.py").read_text(encoding="utf-8")
    assert "caregiver_segment_availability.router" in source
    assert source.count("app.include_router(caregiver_segment_availability.router)") == 1
    assert source.count("app.include_router(finance_alerts.router)") == 1
    assert source.count("app.include_router(multi_caregiver_schedule.router)") == 1
    assert source.count("app.include_router(multi_caregiver_schedule_read.router)") == 1
    assert source.count("app.include_router(multi_caregiver_case_assignments.router)") == 1
    assert source.count("app.include_router(contracts.router)") == 1
    assert source.count("app.include_router(finance_reports.router)") == 1


def test_caregiver_segment_availability_path_is_exposed_once():
    paths = app.openapi()["paths"]
    key = "/api/v1/orders/{case_no}/caregiver-segment-availability/search"
    assert key in paths
    assert len([method for method in paths[key].keys() if method.upper() == "POST"]) == 1


def test_legacy_payments_endpoints_removed():
    paths = app.openapi()["paths"]
    assert not any(path.startswith("/api/v1/payments") for path in paths)
