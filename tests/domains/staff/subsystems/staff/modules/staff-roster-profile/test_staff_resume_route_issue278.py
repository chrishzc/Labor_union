"""Focused API coverage for the Staff-owned current resume projection."""

from datetime import UTC, datetime
from unittest.mock import Mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_registry_reader
from api.routes import staff
from subsystems.controlled_files.workflow import (
    ControlledFileOwner,
    ControlledFilePurpose,
    ControlledFileReadback,
)
from subsystems.staff.profile_query import StaffProfileNotFound


def _client(profile_application: Mock, workflow: Mock) -> TestClient:
    app = FastAPI()
    app.include_router(staff.router)
    app.dependency_overrides[require_registry_reader] = lambda: object()
    app.dependency_overrides[staff.get_staff_profile_application] = lambda: profile_application
    app.dependency_overrides[staff.get_controlled_file_workflow] = lambda: workflow
    return TestClient(app)


def test_current_staff_resume_is_bounded_to_stable_staff_document_identity() -> None:
    profile_application = Mock()
    workflow = Mock()
    workflow.find_current_readback.return_value = ControlledFileReadback(
        file_id="cf_" + "a" * 32,
        owner=ControlledFileOwner.STAFF,
        purpose=ControlledFilePurpose.STAFF_RESUME,
        subject_reference="123",
        filename="王小美履歷.pdf",
        logical_folder="staff/123/resume",
        version=3,
        sha256_digest="b" * 64,
        mime_type="application/pdf",
        size_bytes=100,
        status="available",
        applied_at=datetime(2026, 9, 12, tzinfo=UTC),
    )

    response = _client(profile_application, workflow).get("/api/v1/staff/123/resume")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "staff_id": 123,
        "resume": {
            "file_id": "cf_" + "a" * 32,
            "filename": "王小美履歷.pdf",
            "version": 3,
        },
    }
    workflow.find_current_readback.assert_called_once_with(
        ControlledFileOwner.STAFF,
        ControlledFilePurpose.STAFF_RESUME,
        "123",
        "resume",
    )


def test_staff_without_resume_returns_null_and_missing_staff_is_rejected() -> None:
    profile_application = Mock()
    workflow = Mock()
    workflow.find_current_readback.return_value = None
    client = _client(profile_application, workflow)

    empty = client.get("/api/v1/staff/123/resume")
    assert empty.status_code == 200
    assert empty.json()["data"] == {"staff_id": 123, "resume": None}

    profile_application.query.side_effect = StaffProfileNotFound()
    missing = client.get("/api/v1/staff/999/resume")
    assert missing.status_code == 404
    workflow.find_current_readback.assert_called_once()
