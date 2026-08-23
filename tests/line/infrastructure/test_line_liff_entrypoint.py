"""
File: test_line_liff_entrypoint.py
Description: 驗證 LIFF 身分入口、Rich Menu 導向與月嫂自助服務靜態契約。
"""

from pathlib import Path

import pytest
from fastapi import HTTPException

from api.routes import line_identity
from api.schemas.line_identity import LineIdentityFlowValidationRequest
from domains.line.identities import LineUserId
from domains.line.identity_flow import LineIdentityFlowConflict
from api.dependencies import line_worker_operation


ROOT = Path(__file__).resolve().parents[3]


class ExpiredFlowApplication:
    def validate_flow(self, *_):
        raise LineIdentityFlowConflict("LINE identity flow has expired")


def test_identity_flow_url_uses_supported_liff_additional_information_format(
    monkeypatch,
) -> None:
    monkeypatch.setenv("LINE_LIFF_ID", "1234567890-AbCdEf")

    url = line_worker_operation._identity_flow_url("admin_binding", "flow with spaces")

    assert url == (
        "https://liff.line.me/1234567890-AbCdEf/"
        "?purpose=admin_binding&flow_id=flow+with+spaces"
    )


def test_identity_page_reads_flow_context_after_liff_initialization() -> None:
    source = (ROOT / "line" / "static" / "identity.html").read_text(encoding="utf-8")
    initialize_source = source.split("async function initialize()", 1)[1]

    initialization = initialize_source.index("await liff.init")
    context_read = initialize_source.index("readIdentityFlowContext()")

    assert initialization < context_read
    assert "location.assign(`/line-registration?flow_id=${encodeURIComponent(flowId)}`)" in source


def test_identity_page_accepts_both_liff_redirect_paths_without_redirecting() -> None:
    identity_page_paths = {
        route.path
        for route in line_identity.page_router.routes
        if route.endpoint is line_identity.identity_page
    }

    assert identity_page_paths == {"/line-identity", "/line-identity/"}


def test_identity_page_can_recover_flow_context_from_liff_state() -> None:
    source = (ROOT / "line" / "static" / "identity.html").read_text(encoding="utf-8")

    assert "function identityFlowParameters()" in source
    assert 'parameters.get("liff.state")' in source
    assert "new URLSearchParams(stateQuery)" in source


def test_identity_page_validates_flow_before_showing_identity_form() -> None:
    source = (ROOT / "line" / "static" / "identity.html").read_text(encoding="utf-8")
    initialize_source = source.split("async function initialize()", 1)[1]

    validation = initialize_source.index("await validateIdentityFlow(purpose)")
    form_display = initialize_source.index("showIdentityEntry(definition, purpose)")

    assert 'fetch("/api/v1/line/identity/flow/validate"' in source
    assert validation < form_display


def test_flow_validation_route_translates_expired_flow_to_http_410(monkeypatch) -> None:
    monkeypatch.setattr(
        line_identity,
        "get_line_identity_application",
        lambda: ExpiredFlowApplication(),
    )
    monkeypatch.setattr(line_identity, "_verified_line_user_id", lambda _: LineUserId("U-staff"))
    payload = LineIdentityFlowValidationRequest(
        flow_id="flow-expired",
        purpose="staff_verification",
        line_id_token="test-token",
    )

    with pytest.raises(HTTPException) as captured:
        line_identity.validate_identity_flow(payload)

    assert captured.value.status_code == 410


def test_default_service_registration_menu_opens_the_registration_liff_page() -> None:
    source = (ROOT / "config" / "line_menu.json").read_text(encoding="utf-8")
    gateway = (ROOT / "line" / "static" / "gateway.html").read_text(encoding="utf-8")

    assert '"id": "service_registration"' in source
    assert '"uri": "?target=registration"' in source
    assert '"uri_source": "liff"' in source
    assert "registration: '/line-registration'" in gateway


def test_registration_page_uses_only_canonical_identity_endpoints() -> None:
    source = (ROOT / "line" / "static" / "register.html").read_text(encoding="utf-8")

    assert "/api/v1/line/identity/runtime-config" in source
    assert "/api/v1/line/identity/registration/apply" in source
    assert "/api/line/register" not in source
    assert "/api/line/config" not in source


def test_staff_schedule_page_wires_the_approved_self_service_contracts() -> None:
    source = (ROOT / "line" / "static" / "staff_schedule.html").read_text(
        encoding="utf-8"
    )

    assert "/api/v1/line/staff-self-service/leave-requests" in source
    assert "/api/v1/line/staff-self-service/service-day-logs" in source
    assert "/api/v1/line/staff-self-service/service-day-media" in source
    assert '"Idempotency-Key": idempotencyKey' in source
    assert 'development_line_user_id: lineIdToken ? "" : developmentLineUserId' in source
    assert 'params.get("userId")' in source
    assert '"line_user_id"' not in source
    assert "item.is_work_day === true && Number(item.assignment_id) > 0" in source
    assert "assignment_id: Number(selected.assignment_id)" in source
    assert "service_date: selected.service_date" in source
    assert 'formData.append("photo", photo)' in source
    assert "uploadData.data?.media_id" in source
    assert "meal_photo_media_ids: mediaIds" in source
    assert "待辦，不是正式核准" in source
