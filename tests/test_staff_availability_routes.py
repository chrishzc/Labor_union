from datetime import date

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_admin
from api.dependencies.staff_availability import get_staff_availability_application
from api.routes.staff_availability import router
from domains.scheduling.staff_availability import (
    StaffAvailabilityAction,
    StaffAvailabilityBlockStatus,
    StaffAvailabilityFacts,
    StaffUnavailabilityBlock,
    StaffUnavailabilityKind,
    build_staff_availability_preview,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling.staff_availability_workflow import StaffAvailabilityApplyReceipt


class FakeApplication:
    def query(self, _request):
        return (_block(),)

    def preview(self, request):
        return build_staff_availability_preview(
            request.intent,
            StaffAvailabilityFacts(request.intent.staff_id, 2, (), ()),
        )

    def apply(self, request):
        return StaffAvailabilityApplyReceipt(
            request.intent.staff_id,
            request.intent.action,
            _block(),
            3,
            request.preview_fingerprint,
            request.idempotency_key,
        )


def test_query_returns_typed_staff_availability_blocks():
    response = _client().get(
        "/api/v1/scheduling/staff/7/availability-blocks",
        params={"range_start": "2026-09-01", "range_end": "2026-09-30"},
    )

    assert response.status_code == 200
    block = response.json()["data"][0]
    assert block["kind"] == "long_leave"
    assert block["status"] == "effective"


def test_preview_rejects_unknown_fields_and_returns_source_version():
    client = _client()
    invalid = client.post(
        "/api/v1/scheduling/staff/7/availability-blocks/preview",
        json={
            "action": "create_pause",
            "reason": "暫停接案",
            "start_date": "2026-10-01",
            "unknown": True,
        },
    )
    valid = client.post(
        "/api/v1/scheduling/staff/7/availability-blocks/preview",
        json={
            "action": "create_pause",
            "reason": "暫停接案",
            "start_date": "2026-10-01",
        },
    )

    assert invalid.status_code == 422
    assert valid.status_code == 200
    assert valid.json()["data"]["source_version"] == 2
    assert valid.json()["data"]["can_apply"] is True


def test_apply_uses_header_identities_and_typed_receipt():
    response = _client().post(
        "/api/v1/scheduling/staff/7/availability-blocks/apply",
        headers={
            "Idempotency-Key": "pause-7-001",
            "X-Correlation-ID": "pause-7-correlation",
        },
        json={
            "action": "create_pause",
            "reason": "暫停接案",
            "start_date": "2026-10-01",
            "expected_version": 2,
            "preview_fingerprint": "0" * 64,
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["idempotency_key"] == "pause-7-001"
    assert response.json()["data"]["aggregate_version"] == 3


def test_apply_invalid_command_shape_returns_typed_validation_error():
    response = _client().post(
        "/api/v1/scheduling/staff/7/availability-blocks/apply",
        headers={
            "Idempotency-Key": "invalid-pause",
            "X-Correlation-ID": "invalid-pause-correlation",
        },
        json={
            "action": "create_pause",
            "reason": "暫停接案",
            "start_date": "2026-10-01",
            "end_date": "2026-10-02",
            "expected_version": 2,
            "preview_fingerprint": "0" * 64,
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error"]["code"] == "invalid_staff_availability_intent"


def _client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: AdminPrincipal(
        7,
        "tester",
        "測試人員",
        "system_admin",
    )
    app.dependency_overrides[get_staff_availability_application] = lambda: FakeApplication()
    return TestClient(app)


def _block():
    return StaffUnavailabilityBlock(
        91,
        7,
        StaffUnavailabilityKind.LONG_LEAVE,
        date(2026, 9, 1),
        date(2026, 9, 30),
        StaffAvailabilityBlockStatus.EFFECTIVE,
        "照顧家人",
    )
