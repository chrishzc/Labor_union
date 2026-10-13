"""Retired workbook corrections cannot reach persistence; intake and review remain."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.dependencies.hcm_import import get_hcm_resubmission_workflow, get_hcm_workbook_import_service
from api.routes.hcm_import import router
from subsystems.case_import.hcm_resubmission_workflow import HcmResubmissionWorkflow


@pytest.mark.parametrize("operation", ["preview", "apply"])
def test_retired_workbook_correction_route_is_absent_and_cannot_open_persistence(operation):
    app = FastAPI()
    app.include_router(router)

    def forbidden_dependency():
        pytest.fail("Retired workbook correction must not open persistence")

    app.dependency_overrides[get_hcm_resubmission_workflow] = forbidden_dependency
    app.dependency_overrides[get_hcm_workbook_import_service] = forbidden_dependency
    path = f"/api/v1/case-import/hcm/resubmissions/{operation}"
    response = TestClient(app).post(path, files={"workbook": ("correction.xlsx", b"retired")})

    assert response.status_code == 404
    assert path not in app.openapi()["paths"]


def test_intake_review_and_audited_skip_routes_remain_available():
    app = FastAPI()
    app.include_router(router)
    paths = app.openapi()["paths"]
    prefix = "/api/v1/case-import/hcm"
    for route, method in [
        ("/workbooks/preview", "post"), ("/workbooks/apply", "post"),
        ("/workbooks/results", "get"), ("/reviews", "get"),
        ("/reviews/{review_identity}", "get"),
        ("/reviews/{review_identity}/skip-field/preview", "post"),
        ("/reviews/{review_identity}/skip-field/apply", "post"),
    ]:
        assert method in paths[prefix + route]
    assert not hasattr(HcmResubmissionWorkflow, "preview")
    assert not hasattr(HcmResubmissionWorkflow, "apply")
