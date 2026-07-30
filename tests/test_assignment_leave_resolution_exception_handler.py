from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.exception_handlers.assignment_leave_resolution import (
    assignment_leave_resolution_exception_handler,
)
from services.assignment_schedule_rest_date_service import (
    AssignmentLeaveResolutionDomainError,
)


def test_central_handler_owns_domain_error_http_mapping():
    app = FastAPI()
    app.add_exception_handler(
        AssignmentLeaveResolutionDomainError,
        assignment_leave_resolution_exception_handler,
    )

    @app.get("/conflict")
    def conflict():
        raise AssignmentLeaveResolutionDomainError(
            category="conflict",
            code="formal_service_conflict",
            reason="caregiver is occupied",
            details={"staff_id": 7, "work_date": "2026-08-01"},
        )

    response = TestClient(app).get("/conflict")

    assert response.status_code == 409
    assert response.json()["detail"] == {
        "category": "conflict",
        "code": "formal_service_conflict",
        "reason": "caregiver is occupied",
        "details": {"staff_id": 7, "work_date": "2026-08-01"},
    }
