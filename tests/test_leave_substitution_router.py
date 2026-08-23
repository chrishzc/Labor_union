"""
File: test_leave_substitution_router.py
Description: 驗證請假代班 route 的成對識別、typed payload、錯誤與重試邊界。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pymysql.err import OperationalError
import pytest

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.leave_substitution import (
    get_leave_substitution_application,
)
from api.exception_handlers import (
    CorrelationBoundaryMiddleware,
    install_typed_error_handlers,
)
from api.routes.leave_substitution import router
from api.schemas.errors import GlobalTypedErrorResponseView
from api.schemas.leave_substitution import (
    LeaveSubstitutionPreviewView,
    LeaveSubstitutionReceiptView,
)
from domains.scheduling.generation import (
    AssignmentCandidate,
    SchedulingGenerationCandidate,
)
from domains.scheduling.leave_substitution import (
    LeaveOutcomeCandidate,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling.leave_substitution_workflow import (
    BlockedLeaveImpact,
    LeaveApplyReadiness,
    LeaveCalendarCandidate,
    LeaveSubstitutionPreview,
    LeaveSubstitutionReceipt,
    LeaveSubstitutionWorkflowError,
    LinkedLeaveRequestIntent,
    LinkedLeaveRequestResult,
)


_FINGERPRINT = PreviewFingerprint("a" * 64)


@dataclass(frozen=True, slots=True)
class _PreviewCandidate:
    scheduling: SchedulingGenerationCandidate
    outcomes: tuple[LeaveOutcomeCandidate, ...]


def _preview_result() -> LeaveSubstitutionPreview:
    service_date = date(2026, 8, 3)
    assignment = AssignmentCandidate(
        "assignment:2",
        1,
        2,
        1,
        service_date,
        service_date,
        (service_date,),
        8,
        (1,),
    )
    scheduling = SchedulingGenerationCandidate(
        "CASE-LEAVE-1",
        2,
        1,
        2,
        (1,),
        (assignment,),
        (),
    )
    candidate = _PreviewCandidate(scheduling, ())
    return LeaveSubstitutionPreview(
        candidate,
        _impact(1, 2),
        _impact(1, 2),
        _impact(1, 2),
        1,
        1,
        1,
        1,
        _FINGERPRINT,
        LeaveCalendarCandidate(
            1,
            1,
            service_date.isoformat(),
            service_date.isoformat(),
            service_date.isoformat(),
            service_date.isoformat(),
            1,
            0,
            0,
            0,
            0,
            0,
            "holiday-v1",
            (),
            "conserved",
            (),
        ),
        LeaveApplyReadiness("ready", ()),
        None,
    )


def _impact(expected_version: int, resulting_version: int) -> BlockedLeaveImpact:
    return BlockedLeaveImpact(
        expected_version,
        resulting_version,
        _FINGERPRINT,
        (),
    )


def _linked_preview() -> LinkedLeaveRequestResult:
    return LinkedLeaveRequestResult(
        77,
        4,
        None,
        "accepted_for_processing",
        None,
        "not_requested",
        1,
    )


def _receipt() -> LeaveSubstitutionReceipt:
    return LeaveSubstitutionReceipt(
        "leave-apply-01",
        "CASE-LEAVE-1",
        2,
        2,
        2,
        2,
        2,
        (1001,),
        _FINGERPRINT,
        LinkedLeaveRequestResult(
            77,
            4,
            5,
            "resolved",
            "leave-apply-01",
            "enqueued",
            1,
        ),
    )


class _RecordingApplication:
    def __init__(self, *, preview_error=None, apply_error=None) -> None:
        self.preview_calls = []
        self.apply_calls = []
        self.preview_error = preview_error
        self.apply_error = apply_error

    def preview(self, request):
        self.preview_calls.append(request)
        if self.preview_error is not None:
            raise self.preview_error
        result = _preview_result()
        if request.linked_request is not None:
            result = _with_linked_preview(result)
        return result

    def apply(self, request):
        self.apply_calls.append(request)
        if self.apply_error is not None:
            raise self.apply_error
        return _receipt()

    def list_effective_assignments(self, _case_no):
        return ()


def _with_linked_preview(preview: LeaveSubstitutionPreview) -> LeaveSubstitutionPreview:
    return LeaveSubstitutionPreview(
        preview.candidate,
        preview.client_finance_impact,
        preview.payroll_impact,
        preview.orders_impact,
        preview.order_version,
        preview.scheduling_version,
        preview.client_finance_version,
        preview.payroll_version,
        preview.fingerprint,
        preview.calendar_candidate,
        preview.apply_readiness,
        _linked_preview(),
    )


def _client(application: _RecordingApplication) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    app.dependency_overrides[require_system_admin] = lambda: AdminPrincipal(
        7,
        "leave-route-test",
        "測試人員",
        "system_admin",
    )
    app.dependency_overrides[get_leave_substitution_application] = lambda: application
    return TestClient(app)


def _preview_body(*, linked: bool = False) -> dict[str, object]:
    body: dict[str, object] = {
        "original_assignment_id": 1,
        "items": [],
    }
    if linked:
        body.update({"leave_request_id": 77, "expected_leave_request_version": 4})
    return body


def _apply_body(*, linked: bool = False) -> dict[str, object]:
    body = {
        **_preview_body(linked=linked),
        "expected_order_version": 1,
        "expected_scheduling_version": 1,
        "expected_client_finance_version": 1,
        "expected_payroll_version": 1,
        "preview_fingerprint": _FINGERPRINT.value,
        "reason": "正式處理請假代班",
    }
    return body


@pytest.mark.parametrize(
    ("path", "body", "headers", "method"),
    (
        (
            "/api/v1/orders/CASE-LEAVE-1/leave-substitution/preview",
            {"original_assignment_id": 1, "leave_request_id": 77},
            {"X-Correlation-ID": "leave-half-preview"},
            "post",
        ),
        (
            "/api/v1/orders/CASE-LEAVE-1/leave-substitution/apply",
            {
                **_apply_body(),
                "leave_request_id": 77,
            },
            {
                "Idempotency-Key": "leave-half-apply",
                "X-Correlation-ID": "leave-half-apply-correlation",
            },
            "post",
        ),
    ),
)
def test_half_linked_request_pair_is_422_before_application(
    path: str,
    body: dict[str, object],
    headers: dict[str, str],
    method: str,
) -> None:
    application = _RecordingApplication()
    response = getattr(_client(application), method)(
        path,
        json=body,
        headers=headers,
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error"]["code"] == "request_validation_error"
    assert application.preview_calls == []
    assert application.apply_calls == []


def test_linked_identity_is_part_of_preview_and_apply_requests_and_views() -> None:
    application = _RecordingApplication()
    client = _client(application)

    preview_response = client.post(
        "/api/v1/orders/CASE-LEAVE-1/leave-substitution/preview",
        json=_preview_body(linked=True),
        headers={"X-Correlation-ID": "leave-linked-preview"},
    )
    apply_response = client.post(
        "/api/v1/orders/CASE-LEAVE-1/leave-substitution/apply",
        json=_apply_body(linked=True),
        headers={
            "Idempotency-Key": "leave-apply-01",
            "X-Correlation-ID": "leave-linked-apply",
        },
    )

    assert preview_response.status_code == 200
    assert apply_response.status_code == 200
    assert application.preview_calls[0].linked_request == LinkedLeaveRequestIntent(77, 4)
    assert application.apply_calls[0].linked_request == LinkedLeaveRequestIntent(77, 4)

    preview = LeaveSubstitutionPreviewView.model_validate(
        preview_response.json()["data"]
    )
    receipt = LeaveSubstitutionReceiptView.model_validate(
        apply_response.json()["data"]
    )
    assert preview.linked_request is not None
    assert preview.linked_request.request_id == 77
    assert preview.linked_request.expected_version == 4
    assert preview.linked_request.status == "accepted_for_processing"
    assert receipt.linked_request is not None
    assert receipt.linked_request.receipt_key == "leave-apply-01"
    assert receipt.linked_request.notification_intent == "enqueued"


def test_global_typed_error_keeps_closed_eight_field_envelope() -> None:
    application = _RecordingApplication(
        apply_error=LeaveSubstitutionWorkflowError(
            TypedError(
                ErrorCategory.CONFLICT,
                "stale_preview",
                "Leave/substitution facts changed after Preview.",
                CorrelationId("leave-global-error"),
            )
        )
    )
    response = _client(application).post(
        "/api/v1/orders/CASE-LEAVE-1/leave-substitution/apply",
        json=_apply_body(),
        headers={
            "Idempotency-Key": "leave-global-error-key",
            "X-Correlation-ID": "leave-global-error",
        },
    )

    assert response.status_code == 409
    payload = GlobalTypedErrorResponseView.model_validate(response.json())
    error = payload.detail.error
    assert error.category.value == "conflict"
    assert error.code == "stale_preview"
    assert error.correlation_id == "leave-global-error"
    assert error.retryable is False
    assert set(response.json()["detail"]["error"]) == {
        "category",
        "code",
        "message",
        "field_errors",
        "domain_blockers",
        "retryable",
        "correlation_id",
        "current_version",
    }


def test_mysql_lock_timeout_is_retryable_503_with_retry_after() -> None:
    application = _RecordingApplication(
        apply_error=OperationalError(1205, "Lock wait timeout exceeded")
    )
    response = _client(application).post(
        "/api/v1/orders/CASE-LEAVE-1/leave-substitution/apply",
        json=_apply_body(),
        headers={
            "Idempotency-Key": "leave-retry-key",
            "X-Correlation-ID": "leave-retry-correlation",
        },
    )

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
    error = response.json()["detail"]["error"]
    assert error["category"] == "unavailable"
    assert error["code"] == "leave_substitution_transaction_temporarily_unavailable"
    assert error["retryable"] is True
    assert error["correlation_id"] == "leave-retry-correlation"
    assert len(application.apply_calls) == 1


def test_route_and_public_schema_do_not_reintroduce_second_uow_wall_clock_or_raw_impact_contract() -> None:
    route_source = Path("api/routes/leave_substitution.py").read_text(encoding="utf-8")
    schema_source = Path("api/schemas/leave_substitution.py").read_text(encoding="utf-8")

    assert "MySqlUnitOfWork" not in route_source
    assert "_resolve_linked_leave_request" not in route_source
    assert "datetime.now(" not in route_source
    assert "dict[str, Any]" not in route_source
    assert "dict[str, Any]" not in schema_source
    assert "client_finance_impact: dict" not in schema_source
    assert "payroll_impact: dict" not in schema_source
    assert "orders_impact: dict" not in schema_source
