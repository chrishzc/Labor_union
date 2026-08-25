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


def test_identity_page_safely_extracts_typed_errors_for_flow_commands() -> None:
    source = (ROOT / "line" / "static" / "identity.html").read_text(encoding="utf-8")
    helper = source.split("function safeIdentityErrorMessage(result, fallback)", 1)[1].split(
        "async function ensureLineIdToken()", 1
    )[0]
    open_flow = source.split("async function openIdentityFlow(purpose)", 1)[1].split(
        "function configureCustomerChoice(definition)", 1
    )[0]
    validate_flow = source.split("async function validateIdentityFlow(purpose)", 1)[1].split(
        "async function initialize()", 1
    )[0]

    assert 'typeof result?.detail === "string" ? result.detail : null' in helper
    assert "result?.detail?.message" in helper
    assert "result?.detail?.error?.message" in helper
    assert "result?.error?.message" in helper
    assert 'candidate => typeof candidate === "string" && candidate.trim()' in helper
    assert "return message ? message.trim() : fallback;" in helper
    assert "JSON.stringify" not in helper
    assert "safeIdentityErrorMessage(result," in open_flow
    assert "safeIdentityErrorMessage(result," in validate_flow


def test_identity_preview_maps_machine_statuses_to_business_labels() -> None:
    source = (ROOT / "line" / "static" / "identity.html").read_text(encoding="utf-8")
    preview_text = source.split("function identityPreviewText(endpoint, preview)", 1)[1].split(
        "async function submitForm", 1
    )[0]

    assert 'matched: "已找到可綁定資料"' in source
    assert 'requires_review: "需要工會人員確認"' in source
    assert "Object.hasOwn(identityPreviewStatusLabels, preview.status)" in source
    assert "檢查結果：${identityPreviewStatusLabels[preview.status]}" in preview_text
    assert "預覽狀態：${preview.status}" not in preview_text


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


def test_default_service_registration_menu_uses_the_canonical_identity_entry() -> None:
    source = (ROOT / "config" / "line_menu.json").read_text(encoding="utf-8")
    identity = (ROOT / "line" / "static" / "identity.html").read_text(encoding="utf-8")

    assert '"id": "service_registration"' in source
    assert '"uri": "?entry=registration"' in source
    assert '"uri": "?target=registration"' not in source
    assert '"uri_source": "liff"' in source
    assert 'return entry === "registration";' in identity


def test_gateway_and_mobile_admin_use_canonical_liff_config_without_url_identity_bypass() -> None:
    gateway = (ROOT / "line" / "static" / "gateway.html").read_text(encoding="utf-8")
    mobile_admin = (ROOT / "line" / "static" / "mobile_admin.html").read_text(encoding="utf-8")

    assert "/api/v1/line/identity/runtime-config" in gateway
    assert "/api/v1/line/identity/runtime-config" in mobile_admin
    assert "/api/line/config" not in gateway
    assert "/api/config/liff/runtime" not in gateway
    assert "urlUserId" not in gateway
    assert "?userId=" not in gateway
    assert "/api/line/config" not in mobile_admin


def test_identity_page_routes_mobile_admin_targets_without_opening_staff_flow() -> None:
    source = (ROOT / "line" / "static" / "identity.html").read_text(encoding="utf-8")
    mobile_admin_route = source.split("function requestedMobileAdminPage()", 1)[1].split(
        "function hasSensitiveFlowContext()", 1
    )[0]
    initialize_source = source.split("async function initialize()", 1)[1]

    assert 'customer_service: "/line-mobile-admin?target=customer_service"' in mobile_admin_route
    assert 'staff_review: "/line-mobile-admin?target=staff_review"' in mobile_admin_route
    assert "location.replace(mobileAdminPage);" in initialize_source
    assert initialize_source.index("location.replace(mobileAdminPage);") < initialize_source.index(
        "openStaffPage(staffPage)"
    )


def test_liff_targets_route_to_existing_pages_or_fail_closed() -> None:
    gateway = (ROOT / "line" / "static" / "gateway.html").read_text(encoding="utf-8")
    identity = (ROOT / "line" / "static" / "identity.html").read_text(encoding="utf-8")
    staff_route = identity.split("function requestedStaffPage()", 1)[1].split(
        "function requestedMobileAdminPage()", 1
    )[0]
    standalone_route = identity.split("function requestedStandalonePage()", 1)[1].split(
        "function requestedUnavailableTarget()", 1
    )[0]
    unavailable_route = identity.split("function requestedUnavailableTarget()", 1)[1].split(
        "function hasSensitiveFlowContext()", 1
    )[0]
    initialize_source = identity.split("async function initialize()", 1)[1]

    assert "staff_leave_apply: '/line-staff-schedule'" in gateway
    assert "profile_update: '/static/profile_update.html'" in gateway
    assert 'staff_leave_apply: "/line-staff-schedule"' in staff_route
    assert 'profile_update: "/static/profile_update.html"' in standalone_route
    for target in ("staff_payout", "anomalies_center", "dashboard"):
        assert f"{target}:" in unavailable_route
        assert f"/line-identity?target={target}" in gateway
    assert "showUnavailableTarget(unavailableTarget);" in initialize_source
    assert initialize_source.index("showUnavailableTarget(unavailableTarget);") < initialize_source.index(
        "showRegistrationEntry();"
    )
    assert "此入口不會改用其他流程" in unavailable_route


def test_registration_page_uses_only_canonical_identity_endpoints() -> None:
    source = (ROOT / "line" / "static" / "register.html").read_text(encoding="utf-8")

    assert "/api/v1/line/identity/runtime-config" in source
    assert "/api/v1/line/identity/registration/preview" in source
    assert "/api/v1/line/identity/registration/apply" in source
    assert "function canUseDevelopmentIdentityFallback(error)" not in source
    assert 'development_line_user_id: ""' in source
    assert "developmentLineUserId" not in source
    assert "const code = detail?.code || detail?.error?.code || result?.error?.code;" in source
    assert "/api/line/register" not in source
    assert "/api/line/config" not in source


def test_registration_initialization_error_disables_every_form_control() -> None:
    source = (ROOT / "line" / "static" / "register.html").read_text(encoding="utf-8")
    failure_source = source.split("function showInitializationError(error)", 1)[1].split(
        'document.addEventListener("DOMContentLoaded"', 1
    )[0]

    assert "status.textContent = error.message || '頁面初始化失敗，請回到 LINE 重新開啟。';" in failure_source
    assert (
        "#registerForm input, #registerForm select, #registerForm textarea, "
        "#registerForm button"
    ) in failure_source
    assert "control => control.disabled = true" in failure_source


def test_active_liff_pages_do_not_accept_query_string_user_id() -> None:
    for name in (
        "identity.html",
        "register.html",
        "staff_order_search.html",
        "staff_schedule.html",
        "mobile_admin.html",
    ):
        source = (ROOT / "line" / "static" / name).read_text(encoding="utf-8")
        assert 'get("userId")' not in source


def test_staff_schedule_page_uses_strict_leave_flow_but_keeps_service_log_locked() -> None:
    source = (ROOT / "line" / "static" / "staff_schedule.html").read_text(
        encoding="utf-8"
    )

    assert "/api/v1/line/staff-self-service/leave-requests/preview" in source
    assert "/api/v1/line/staff-self-service/leave-requests/apply" in source
    assert "/query`" in source
    assert "/api/v1/line/staff-self-service/service-day-logs" not in source
    assert "/api/v1/line/staff-self-service/service-day-media" not in source
    assert "尚缺 Preview／Apply／receipt" in source
    assert "請聯絡工會人員人工處理" in source
    assert 'development_line_user_id: ""' in source
    assert 'params.get("userId")' not in source
    assert '"line_user_id"' not in source
    assert "function requireStaffSchedule" in source
    assert 'id="submitLeave"' in source
    assert 'disabled>預覽請假待辦</button>' in source
    assert 'id="submitLog" class="primary" disabled' in source
    assert 'addEventListener("click", submitLeave)' in source
    assert 'addEventListener("click", submitServiceDayLog)' not in source
    assert "重新登入 LINE" in source
    assert 'redirect.searchParams.set("target", "staff_schedule")' in source
    assert 'liff.login({redirectUri: redirect.toString()})' in source


def test_active_liff_pages_offer_manual_reauthentication_without_url_identity() -> None:
    identity = (ROOT / "line" / "static" / "identity.html").read_text(encoding="utf-8")
    assert "重新登入 LINE" in identity
    assert "liff.logout()" in identity
    assert 'liff.login({redirectUri: location.href})' in identity
    assert 'params.get("userId")' not in identity

    targets = {
        "staff_order_search.html": "staff_order_search",
        "staff_schedule.html": "staff_schedule",
    }
    for name, target in targets.items():
        source = (ROOT / "line" / "static" / name).read_text(encoding="utf-8")
        assert "重新登入 LINE" in source
        assert "liff.logout()" in source
        assert 'new URL("/line-identity", location.origin)' in source
        assert f'redirect.searchParams.set("target", "{target}")' in source
        assert "liff.login({redirectUri: redirect.toString()})" in source
        assert "liff.login({redirectUri: location.href})" not in source
        assert 'params.get("userId")' not in source

    mobile_admin = (ROOT / "line" / "static" / "mobile_admin.html").read_text(encoding="utf-8")
    assert "重新登入 LINE" in mobile_admin
    assert "liff.logout()" in mobile_admin
    assert 'new URL("/line-identity", location.origin)' in mobile_admin
    assert 'targetFromUrl() === "staff_review" ? "staff_review" : "customer_service"' in mobile_admin
    assert "liff.login({redirectUri: redirect.toString()})" in mobile_admin
    assert "liff.login({redirectUri: location.href})" not in mobile_admin
    assert 'params.get("userId")' not in mobile_admin
