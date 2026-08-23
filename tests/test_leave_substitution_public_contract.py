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
