"""Management saves accept omitted notes without weakening command identity or facts."""
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from api.schemas.client_registry import BeClassCorrectionApplyRequest, ClientProfileAdminApplyRequest
from api.schemas.holidays import HolidayApplyRequest
from api.schemas.line_notification_rules import ApplyLineNotificationManualReplayRequest, UpdateLineNotificationMessageTemplateRequest
from api.schemas.line_rich_menus import RichMenuPublishRequest, RichMenuPublicationRetryRequest
from api.schemas.operational_retention import RetentionPreviewRequest
from api.schemas.staff_availability import StaffAvailabilityApplyBody
from api.schemas.staff_registry_mutation import StaffBankAccountApplyRequest
from api.schemas.staff_retirement import StaffLifecycleTransitionInput
from api.routes.client_deposit_skip import ApplyBody as DepositSkipApplyBody
from api.routes.order_reopen import OrderReopenApplyBody
from api.routes.service_date_confirmation import ServiceDateApplyBody, HistoricalArrangementApplyBody
from api.routes.contract_signing import ManualContractAttestationBody
from domains.staff.retirement import StaffLifecycleFact, StaffLifecycleState, StaffLifecycleTransition, build_transition
from shared_kernel.validation import require_canonical_text


FINGERPRINT = "a" * 64
IDENTITY = {"idempotency_key": "management-save-1", "correlation_id": "management-command-1"}


@pytest.mark.parametrize(("model", "payload"), [
    (ClientProfileAdminApplyRequest, {"changes": {"name": "測試姓名"}, "expected_version": 1, "preview_fingerprint": FINGERPRINT}),
    (BeClassCorrectionApplyRequest, {"changes": {"admin_notes": "測試註記"}, "expected_version": 1, "preview_fingerprint": FINGERPRINT}),
    (StaffBankAccountApplyRequest, {"command": {"operation": "set_primary", "account_id": 1}, "expected_version": 1, "preview_fingerprint": FINGERPRINT}),
    (StaffAvailabilityApplyBody, {"action": "create_pause", "start_date": "2026-10-21", "expected_version": 1, "preview_fingerprint": FINGERPRINT}),
    (HolidayApplyRequest, {"action": "delete", "holiday_date": "2026-10-21", "expected_calendar_version": FINGERPRINT, "preview_fingerprint": FINGERPRINT}),
    (RichMenuPublishRequest, {"preview_id": 1, **IDENTITY}),
    (RichMenuPublicationRetryRequest, IDENTITY),
    (ApplyLineNotificationManualReplayRequest, IDENTITY),
    (UpdateLineNotificationMessageTemplateRequest, {"content": "測試通知", "expected_revision": 1}),
    (RetentionPreviewRequest, {"source_id": "line_delivery_attempts"}),
    (DepositSkipApplyBody, {"expected_account_version": 1, "preview_fingerprint": FINGERPRINT}),
    (OrderReopenApplyBody, {"expected_order_version": 1, "expected_client_finance_version": 2, "expected_payroll_version": 3, "preview_fingerprint": FINGERPRINT}),
    (ServiceDateApplyBody, {"service_dates": ["2026-10-21"], "expected_order_version": 1, "expected_scheduling_version": 2, "preview_fingerprint": FINGERPRINT}),
    (HistoricalArrangementApplyBody, {"segments": [{"staff_id": 1, "service_dates": ["2026-10-21"]}], "expected_order_version": 1, "expected_scheduling_version": 2, "expected_confirmed_version": 3, "preview_fingerprint": FINGERPRINT}),
    (ManualContractAttestationBody, {"confirmation_method": "phone"}),
])
def test_operator_reason_can_be_omitted_or_blank(model, payload):
    assert model.model_validate(payload).reason == ""
    assert model.model_validate({**payload, "reason": ""}).reason == ""
    assert model.model_validate({**payload, "reason": "補充說明"}).reason == "補充說明"
    with pytest.raises(ValidationError):
        model.model_validate({**payload, "reason": "x" * 1001})


@pytest.mark.parametrize("field", ["idempotency_key", "correlation_id"])
def test_optional_reason_does_not_make_command_identity_optional(field):
    with pytest.raises(ValidationError):
        RichMenuPublishRequest.model_validate({"preview_id": 1, **IDENTITY, field: "", "reason": ""})


def test_optional_reason_does_not_allow_blank_notification_content():
    with pytest.raises(ValidationError):
        UpdateLineNotificationMessageTemplateRequest.model_validate({"content": " ", "expected_revision": 1, "reason": ""})


def test_retirement_accepts_no_reason_and_still_validates_supplied_classification():
    effective_at = datetime(2026, 10, 21, tzinfo=timezone.utc)
    body = StaffLifecycleTransitionInput(effective_at=effective_at)
    fact = StaffLifecycleFact(1, StaffLifecycleState.ACTIVE, 2)
    candidate = build_transition(fact, StaffLifecycleTransition.RETIRE, effective_at=body.effective_at, reason_code=body.reason_code)
    assert candidate.after.state is StaffLifecycleState.RETIRED
    assert candidate.after.version == 3
    assert candidate.after.reason_code == ""
    with pytest.raises(ValueError, match="staff_retirement_reason_invalid"):
        build_transition(fact, StaffLifecycleTransition.RETIRE, effective_at=effective_at, reason_code="unsupported")


def test_empty_text_is_only_permitted_for_the_explicit_optional_reason_contract():
    assert require_canonical_text("", "operator reason", 500, allow_empty=True) == ""
    with pytest.raises(ValueError):
        require_canonical_text("", "actor identity", 500)
