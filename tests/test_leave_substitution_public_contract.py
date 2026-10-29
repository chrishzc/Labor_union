"""
File: test_leave_substitution_public_contract.py
Description: 驗證請假代班 request、impact、linked 與 receipt 的封閉 typed view。
"""

from __future__ import annotations

from datetime import date

from pydantic import ValidationError
import pytest

from api.schemas.leave_substitution import (
    LeaveImpactSummaryView,
    LeaveSubstitutionApplyBody,
    LeaveSubstitutionPreviewBody,
    LeaveSubstitutionPreviewView,
    LeaveSubstitutionReceiptView,
    LinkedLeaveRequestView,
)


_FINGERPRINT = "b" * 64


def test_database_error_records_mysql_code_and_correlation_without_raw_sql(caplog):
    import logging
    from fastapi import HTTPException
    from pymysql.err import OperationalError
    from api.routes.leave_substitution import _call_endpoint
    from shared_kernel.identities import CorrelationId

    def failing_preview():
        raise OperationalError(1054, "raw-sql-and-row-values-must-not-be-logged")

    with caplog.at_level(logging.ERROR, logger="api.routes.leave_substitution"):
        with pytest.raises(HTTPException) as caught:
            _call_endpoint(failing_preview, "preview", CorrelationId("leave-database-diagnostic"))

    assert caught.value.status_code == 500
    assert caught.value.detail["error"]["code"] == "leave_substitution_database_error"
    assert "mysql_code=1054" in caplog.text
    assert "correlation_id=leave-database-diagnostic" in caplog.text
    assert "raw-sql-and-row-values" not in caplog.text


def _impact() -> dict[str, object]:
    return {
        "expected_version": 1,
        "resulting_version": 2,
        "fingerprint": _FINGERPRINT,
        "blockers": [],
    }


def _linked() -> dict[str, object]:
    return {
        "request_id": 77,
        "expected_version": 4,
        "resolved_version": 5,
        "status": "resolved",
        "receipt_key": "leave-apply-01",
        "notification_intent": "enqueued",
    }


def _assignment() -> dict[str, object]:
    return {
        "candidate_key": "assignment:2",
        "staff_id": 2,
        "sequence": 1,
        "assigned_start_date": date(2026, 8, 3),
        "assigned_end_date": date(2026, 8, 3),
        "official_service_dates": [date(2026, 8, 3)],
        "actual_hours": 8,
        "lineage_source_assignment_ids": [1],
    }


def _preview_payload() -> dict[str, object]:
    return {
        "case_no": "CASE-LEAVE-1",
        "order_version": 1,
        "scheduling_version": 1,
        "scheduling_generation": 2,
        "client_finance_version": 1,
        "payroll_version": 1,
        "cancelled_assignment_ids": [1],
        "assignments": [_assignment()],
        "outcomes": [],
        "client_finance_impact": _impact(),
        "payroll_impact": _impact(),
        "orders_impact": _impact(),
        "calendar_candidate": {
            "before_service_day_count": 1,
            "after_service_day_count": 1,
            "before_service_start_date": date(2026, 8, 3),
            "before_service_end_date": date(2026, 8, 3),
            "after_service_start_date": date(2026, 8, 3),
            "after_service_end_date": date(2026, 8, 3),
            "contracted_service_day_count": 1,
            "deferred_day_count": 0,
            "substitute_day_count": 0,
            "leave_day_count": 0,
            "holiday_rest_day_count": 0,
            "fixed_rest_day_count": 0,
            "holiday_version": "holiday-v1",
            "holiday_rows": [],
            "conservation_status": "conserved",
            "day_cells": [],
        },
        "apply_readiness": {"status": "ready", "blockers": []},
        "linked_request": _linked(),
        "preview_fingerprint": _FINGERPRINT,
    }


def _receipt_payload() -> dict[str, object]:
    return {
        "batch_key": "leave-apply-01",
        "case_no": "CASE-LEAVE-1",
        "order_version": 2,
        "scheduling_generation": 2,
        "scheduling_version": 2,
        "client_finance_version": 2,
        "payroll_version": 2,
        "outcome_event_ids": [1001],
        "preview_fingerprint": _FINGERPRINT,
        "linked_request": _linked(),
    }


def _base_request(*, linked: bool = False) -> dict[str, object]:
    request: dict[str, object] = {"original_assignment_id": 1, "items": []}
    if linked:
        request.update({"leave_request_id": 77, "expected_leave_request_version": 4})
    return request


def _apply_request(*, linked: bool = False) -> dict[str, object]:
    return {
        **_base_request(linked=linked),
        "expected_order_version": 1,
        "expected_scheduling_version": 1,
        "expected_client_finance_version": 1,
        "expected_payroll_version": 1,
        "preview_fingerprint": _FINGERPRINT,
        "reason": "正式處理請假代班",
    }


@pytest.mark.parametrize(
    "model, payload",
    (
        (LeaveSubstitutionPreviewBody, {"leave_request_id": 77}),
        (
            LeaveSubstitutionApplyBody,
            {
                "leave_request_id": 77,
                "expected_order_version": 1,
                "expected_scheduling_version": 1,
                "expected_client_finance_version": 1,
                "expected_payroll_version": 1,
                "preview_fingerprint": _FINGERPRINT,
                "reason": "正式處理請假代班",
            },
        ),
    ),
)
def test_request_models_reject_half_linked_identity_pair(model, payload) -> None:
    with pytest.raises(ValidationError, match="leave_request_identity_pair_required"):
        model.model_validate({**_base_request(), **payload})


def test_complete_pair_and_unlinked_request_are_both_valid_commands() -> None:
    assert LeaveSubstitutionPreviewBody.model_validate(_base_request()).leave_request_id is None
    linked_preview = LeaveSubstitutionPreviewBody.model_validate(
        _base_request(linked=True)
    )
    linked_apply = LeaveSubstitutionApplyBody.model_validate(
        _apply_request(linked=True)
    )

    assert (linked_preview.leave_request_id, linked_preview.expected_leave_request_version) == (77, 4)
    assert (linked_apply.leave_request_id, linked_apply.expected_leave_request_version) == (77, 4)


def test_preview_request_preserves_specified_replacement_date_in_domain_intent() -> None:
    body = LeaveSubstitutionPreviewBody.model_validate({
        "original_assignment_id": 1,
        "items": [{
            "original_schedule_id": 10,
            "work_date": "2026-08-03",
            "resolution_type": "defer_following_assignments",
            "substitute_staff_id": None,
            "is_double_pay": False,
            "replacement_work_date": "2026-08-11",
        }],
    })

    assert body.to_intent().items[0].replacement_work_date == date(2026, 8, 11)


def test_impact_views_are_exactly_typed_and_reject_internal_extension_fields() -> None:
    assert LeaveSubstitutionPreviewView.model_fields[
        "client_finance_impact"
    ].annotation is LeaveImpactSummaryView
    assert LeaveSubstitutionPreviewView.model_fields["payroll_impact"].annotation is LeaveImpactSummaryView
    assert LeaveSubstitutionPreviewView.model_fields["orders_impact"].annotation is LeaveImpactSummaryView

    for field_name in (
        "client_finance_impact",
        "payroll_impact",
        "orders_impact",
    ):
        payload = _preview_payload()
        payload[field_name] = {**_impact(), "internal_payload": {"amount": 1}}
        with pytest.raises(ValidationError):
            LeaveSubstitutionPreviewView.model_validate(payload)

    impact = LeaveImpactSummaryView.model_validate(_impact())
    assert impact.expected_version == 1
    assert impact.resulting_version == 2
    assert impact.blockers == []


def test_linked_and_receipt_views_are_closed_and_preserve_resolution_intent() -> None:
    linked = LinkedLeaveRequestView.model_validate(_linked())
    receipt = LeaveSubstitutionReceiptView.model_validate(_receipt_payload())
    preview = LeaveSubstitutionPreviewView.model_validate(_preview_payload())

    assert linked.request_id == 77
    assert linked.status == "resolved"
    assert linked.notification_intent == "enqueued"
    assert receipt.linked_request == linked
    assert preview.linked_request == linked

    with pytest.raises(ValidationError):
        LinkedLeaveRequestView.model_validate({**_linked(), "staff_id": 1})
    with pytest.raises(ValidationError):
        LeaveSubstitutionReceiptView.model_validate(
            {**_receipt_payload(), "result_snapshot": {"receipt_key": "secret"}}
        )


def test_public_views_reject_uppercase_fingerprint_and_raw_impact_payload() -> None:
    uppercase = _preview_payload()
    uppercase["preview_fingerprint"] = "A" * 64
    with pytest.raises(ValidationError):
        LeaveSubstitutionPreviewView.model_validate(uppercase)

    raw_impact = _impact()
    raw_impact["amount"] = 123
    with pytest.raises(ValidationError):
        LeaveImpactSummaryView.model_validate(raw_impact)


def test_apply_request_has_no_implicit_linked_identity_or_receipt_fields() -> None:
    request = LeaveSubstitutionApplyBody.model_validate(_apply_request())
    assert request.leave_request_id is None
    assert request.expected_leave_request_version is None
    assert "receipt_key" not in request.model_dump()


@pytest.mark.parametrize("expected_version", [1, 99])
def test_retired_review_rejects_current_and_stale_requests_without_opening_application(expected_version):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.dependencies.admin_auth import require_admin
    from api.dependencies.staff_leave_intake import get_staff_leave_customer_coordination_application
    from api.exception_handlers import install_typed_error_handlers
    from api.routes.staff_leave_management import router
    class ForbiddenApplication:
        def __init__(self):
            pytest.fail("retired review must not open the application or write history")
    app = FastAPI()
    install_typed_error_handlers(app)
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(username="fixture")
    app.dependency_overrides[get_staff_leave_customer_coordination_application] = ForbiddenApplication
    response = TestClient(app).post("/api/v1/scheduling/staff-leave-requests/1/review",
        headers={"Idempotency-Key": "review-conflict-fixture"},
        json={"expected_version": expected_version, "action": "accept", "reason": "fixture"})
    assert response.status_code == 410
    error = response.json()["detail"]["error"]
    assert error["code"] == "resource_retired"
    assert error["category"] == "not_found"
    assert error["retryable"] is False


@pytest.mark.parametrize("code", ["leave_request_stale", "leave_request_state_conflict", "leave_request_idempotency_conflict"])
def test_staff_cancel_blocker_preserves_reason_and_recovery_through_global_handler(monkeypatch, code):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.dependencies.staff_leave_intake import get_staff_leave_intake_application
    from api.exception_handlers import install_typed_error_handlers
    from api.routes import staff_leave_intake as routes
    from infrastructure.mysql import line_unit_of_work
    from subsystems.scheduling.staff_leave_intake_workflow import StaffLeaveIntakeWorkflowError

    @contextmanager
    def line_uow():
        yield SimpleNamespace(customer_service=SimpleNamespace(staff_subject=lambda _id: None))
    monkeypatch.setattr(line_unit_of_work, "open_line_unit_of_work", line_uow)
    monkeypatch.setattr(routes, "_verified_line_user_id", lambda _body: SimpleNamespace(value="Ufixture"))
    monkeypatch.setattr(routes, "_required_staff", lambda _subject: {"staff_id": 9, "staff_name": "fixture"})
    class CancelBlocked:
        def review(self, command):
            assert command.actor_is_staff and command.actor_staff_id == 9
            if code == "leave_request_idempotency_conflict":
                raise ValueError(code)
            raise StaffLeaveIntakeWorkflowError(code)
    app = FastAPI()
    install_typed_error_handlers(app)
    app.include_router(routes.router)
    app.dependency_overrides[get_staff_leave_intake_application] = CancelBlocked
    response = TestClient(app).post("/api/v1/line/staff-self-service/leave-requests/17/cancel",
        headers={"Idempotency-Key": "staff-cancel-fixture"},
        json={"line_id_token": "fixture", "expected_version": 2, "reason": "fixture cancellation"})
    assert response.status_code == 409
    error = response.json()["detail"]["error"]
    assert error["code"] == code
    assert "重新查詢" in error["message"]
    if code == "leave_request_state_conflict":
        assert "只能自行取消尚未受理" in error["message"] and "聯繫工會" in error["message"]
