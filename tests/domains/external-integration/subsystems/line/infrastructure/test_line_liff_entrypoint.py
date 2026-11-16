"""
File: test_line_liff_entrypoint.py
Description: 驗證 LIFF 身分入口、Rich Menu 導向與月嫂自助服務靜態契約。
"""

import json
from pathlib import Path
import subprocess

import pytest
from fastapi import HTTPException

from api.routes import line_identity
from api.schemas.line_identity import LineIdentityFlowValidationRequest
from domains.line.identities import LineUserId
from domains.line.identity_flow import LineIdentityFlowConflict
from api.dependencies import line_worker_operation


ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "requirements.txt").is_file() and (parent / "subsystems").is_dir()
)


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
    assert "location.assign(`/line-bind?flow_id=${encodeURIComponent(flowId)}`)" in source


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
    labels_block = source.split("const identityPreviewStatusLabels = {", 1)[1].split("};", 1)[0]
    require_preview = source.split("function requireIdentityPreview(result)", 1)[1].split(
        "async function submitForm", 1
    )[0]

    assert 'authentication_pending: "等待套用時驗證管理員帳號"' in labels_block
    assert 'matched: "已找到可綁定資料"' in labels_block
    assert 'requires_review: "需要工會人員確認"' in labels_block
    assert "Object.hasOwn(identityPreviewStatusLabels, preview.status)" in require_preview
    assert "預覽狀態：" not in source


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


def test_gateway_restores_choices_after_cached_browser_back() -> None:
    source = (ROOT / "line/static/gateway.html").read_text(encoding="utf-8")
    script = source.split("<script>", 1)[1].split("</script>", 1)[0]
    runner = """
const assert = require('node:assert/strict');
const vm = require('node:vm');
let restore;
let hasChoices = true;
let renderCount = 0;
const overlay = {style: {display: 'flex'}};
const nodes = {
  loaderOverlay: overlay,
  loaderText: {textContent: 'initializing'},
  actionsContainer: {hasChildNodes: () => hasChoices},
};
const context = vm.createContext({
  URLSearchParams,
  window: {
    location: {search: '', href: '/line-gateway'},
    addEventListener: (name, fn) => { if (name === 'pageshow') restore = fn; },
  },
  document: {getElementById: id => nodes[id]},
});
vm.runInContext(SOURCE, context);
vm.runInContext('renderActions = () => onRender()', context);
context.onRender = () => { renderCount++; };

restore({persisted: true});
assert.equal(overlay.style.display, 'flex');  // Initialization still owns its loading state.
vm.runInContext("navigateTo('/line-bind?entry=existing_case')", context);
assert.equal(nodes.loaderText.textContent, '正在為您跳轉...');
restore({persisted: false});
assert.equal(overlay.style.display, 'flex');
restore({persisted: true});
assert.equal(overlay.style.display, 'none');
assert.equal(renderCount, 0);  // Keep the previously selected branch.

hasChoices = false;
vm.runInContext("navigateTo('/line-bind')", context);
restore({persisted: true});
assert.equal(overlay.style.display, 'none');
assert.equal(renderCount, 1);  // A direct-entry redirect had no rendered choices yet.
""".replace("SOURCE", json.dumps(script))
    subprocess.run(["node"], input=runner, text=True, encoding="utf-8", check=True, timeout=10)


def test_gateway_and_mobile_admin_use_canonical_liff_config_without_url_identity_bypass() -> None:
    gateway = (ROOT / "line" / "static" / "gateway.html").read_text(encoding="utf-8")
    mobile_admin = (ROOT / "line" / "static" / "mobile_admin.html").read_text(encoding="utf-8")

    assert "/api/v1/line/identity/runtime-config" in gateway
    assert "/api/v1/line/identity/runtime-config" in mobile_admin
    assert "/api/line/config" not in gateway
    assert "/api/config/liff/runtime?page=gateway" in gateway
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
    assert 'scheduling_review: "/line-mobile-admin?target=scheduling_review"' in mobile_admin_route
    assert 'staff_review: "/line-mobile-admin?target=staff_review"' in mobile_admin_route
    assert 'order_tracking: "/line-mobile-admin?target=order_tracking"' in mobile_admin_route
    assert 'anomalies_center: "/line-mobile-admin?target=anomalies_center"' in mobile_admin_route
    assert 'dashboard: "/line-mobile-admin?target=dashboard"' in mobile_admin_route
    assert "location.replace(mobileAdminPage);" in initialize_source
    assert initialize_source.index("location.replace(mobileAdminPage);") < initialize_source.index(
        "openStaffPage(staffPage)"
    )


def test_liff_targets_route_to_existing_pages() -> None:
    gateway = (ROOT / "line" / "static" / "gateway.html").read_text(encoding="utf-8")
    identity = (ROOT / "line" / "static" / "identity.html").read_text(encoding="utf-8")
    staff_route = identity.split("function requestedStaffPage()", 1)[1].split(
        "function requestedMobileAdminPage()", 1
    )[0]
    standalone_route = identity.split("function requestedStandalonePage()", 1)[1].split(
        "function hasSensitiveFlowContext()", 1
    )[0]
    mobile_admin_route = identity.split("function requestedMobileAdminPage()", 1)[1].split(
        "function requestedStandalonePage()", 1
    )[0]

    assert "staff_leave_apply: '/line-identity?target=staff_leave_apply'" not in gateway
    assert "non_citizen_registration: '/line-non-citizen-registration'" in gateway
    assert 'id="register-non-citizen"' in identity
    assert 'location.assign("/line-non-citizen-registration")' in identity
    assert "profile_update: '/line-profile-guard'" not in gateway
    assert 'staff_leave_apply: "/line-staff-schedule"' not in staff_route
    assert 'if (target === "staff_leave_apply")' in identity
    assert '請從案件群組的小幫手發起「雙方合意延期」' in identity
    assert 'profile_update: "/line-profile-guard"' not in standalone_route
    assert 'staff_baby_log' not in staff_route
    assert 'staff_payout: "/line-staff-payout"' in staff_route
    assert 'staff_baby_log' not in gateway
    assert "staff_payout: '/line-identity?target=staff_payout'" in gateway
    assert 'faq: "/line-service-help?tab=faq"' in standalone_route
    assert 'ai_assistant: "/line-service-help?tab=ai"' in standalone_route
    for target in ("order_tracking", "anomalies_center", "dashboard"):
        assert f"{target}:" in mobile_admin_route
        assert f"/line-mobile-admin?target={target}" in gateway
    assert "requestedUnavailableTarget" not in identity


def test_active_liff_pages_do_not_accept_query_string_user_id() -> None:
    for name in (
        "identity.html",
        "register.html",
        "staff_order_search.html",
        "staff_schedule.html",
        "staff_payout.html",
        "mobile_admin.html",
    ):
        source = (ROOT / "line" / "static" / name).read_text(encoding="utf-8")
        assert 'get("userId")' not in source


def test_staff_schedule_page_uses_mutual_postponement_without_legacy_leave_submission() -> None:
    source=(ROOT/'line/static/staff_schedule.html').read_text(encoding='utf-8')
    assert '/api/v1/line/staff-self-service/leave-results/' in source
    assert "leaveResultPost('submit'" not in source
    assert "leaveResultPost('cases'," in source
    assert "leaveResultPost('preview'," in source
    assert "leaveResultPost('propose'," in source
    assert '需要安排代班' not in source and '已協調順延' not in source
    assert '/leave-requests/preview' not in source and 'confirmLeave' not in source
    assert '我的不接案日期' in source
    assert 'development_line_user_id: ""' in source
    assert 'params.get("userId")' not in source
    assert 'redirect.searchParams.set("target", "staff_schedule")' in source
    assert 'liff.login({redirectUri: redirect.toString()})' in source


@pytest.mark.parametrize("fail_send", [False, True], ids=["one-tap", "retry-same-message"])
def test_staff_schedule_postpone_can_send_revised_proposal_from_same_page(fail_send: bool) -> None:
    source = (ROOT / "line/static/staff_schedule.html").read_text(encoding="utf-8")
    script = source.split("<script>", 1)[1].split(
        'document.getElementById("loadSchedule").addEventListener', 1
    )[0]
    runner = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const nodes = new Map();
const node = () => ({ style: {}, append() {}, appendChild() {}, replaceChildren() {} });
const messages = [];
let lineContext = 'external';
let writeScope = true;
const expectRetry = FAIL_SEND;
let failSend = expectRetry;
const context = vm.createContext({
  document: {
    createElement: node,
    getElementById(id) {
      if (!nodes.has(id)) nodes.set(id, node());
      return nodes.get(id);
    },
  },
  AbortController, crypto,
  liff: {
    isInClient: () => lineContext !== 'external',
    getContext: () => ({type: lineContext, scope: writeScope ? ['chat_message.write'] : []}),
    async sendMessages(payload) {
      assert.equal(payload.length, 1);
      assert.equal(payload[0].type, 'text');
      messages.push(payload[0].text);
      if (failSend) throw new Error('LINE did not acknowledge delivery');
    },
  },
});
const evaluate = (script) => vm.runInContext(script, context);
evaluate(SOURCE);
evaluate(`
  postponeCase = {case_no: 'TEST', assignment_id: 12, service_dates: ['2027-01-05', '2027-01-08']};
  requirePostponeGroupReply = true;
  postponeSelectedDates = new Set(postponeCase.service_dates);
  postponeCalendar = {calendarWeekdays: ['日', '一', '二', '三', '四', '五', '六']};
  renderPostponeCalendar = () => {};
  let closeCount = 0;
  closeLiffWindow = () => { closeCount++; };
  const calls = [];
  leaveResultPost = (path, payload, signal) =>
    new Promise((resolve, reject) => calls.push({path, payload, signal, resolve, reject}));
  handlePostponeDateClick('2027-01-06');
`);
const settle = () => new Promise(setImmediate);

(async () => {
  assert.equal(nodes.get('postponeConservationText').textContent, '3 / 2 天');
  assert.equal(nodes.get('postponeBalanceBadge').textContent, '多選 1 天');
  assert.equal(evaluate('calls.length'), 0);
  evaluate("handlePostponeDateClick('2027-01-06')");
  assert.equal(nodes.get('postponeBalanceBadge').textContent, '日期未變更');
  assert.equal(evaluate('calls.length'), 0);
  evaluate("handlePostponeDateClick('2027-01-05')");
  assert.equal(nodes.get('postponeConservationText').textContent, '1 / 2 天');
  assert.equal(nodes.get('postponeBalanceBadge').textContent, '尚缺 1 天');
  assert.equal(evaluate('calls.length'), 0);
  evaluate("handlePostponeDateClick('2027-01-05'); handlePostponeDateClick('2027-01-06'); handlePostponeDateClick('2027-01-05');");
  assert.equal(evaluate('calls.map(call => call.path).join()'), 'preview');
  evaluate(`
    handlePostponeDateClick('2027-01-06');
    handlePostponeDateClick('2027-01-07');
    calls[0].resolve({conflict: false});
  `);
  await settle();
  assert.equal(evaluate('calls[0].signal.aborted'), true);
  assert.equal(nodes.get('postponeSubmitBtn').disabled, true);
  await evaluate('submitPostponeProposal()');
  assert.equal(evaluate('calls.map(call => call.path).join()'), 'preview,preview');

  evaluate('calls[1].resolve({conflict: false})');
  await settle();
  assert.equal(nodes.get('postponeSubmitBtn').disabled, false);
  for (const unavailableContext of ['external', 'utou']) {
    lineContext = unavailableContext;
    await evaluate('submitPostponeProposal()');
    assert.equal(evaluate('calls.map(call => call.path).join()'), 'preview,preview');
    assert.match(nodes.get('postponeActionNotice').textContent, /從原 LINE 案件群組/);
  }
  lineContext = 'group';
  writeScope = false;
  await evaluate('submitPostponeProposal()');
  assert.equal(evaluate('calls.map(call => call.path).join()'), 'preview,preview');
  writeScope = true;
  evaluate(`
    void submitPostponeProposal();
    handlePostponeDateClick('2027-01-07');
    void submitPostponeProposal();
  `);
  assert.equal(evaluate('calls.map(call => call.path).join()'), 'preview,preview,propose');
  assert.equal(evaluate('calls[2].payload.dates[0].new_date'), '2027-01-07');
  assert.equal(nodes.get('postponeSubmitBtn').disabled, true);
  evaluate("calls[2].resolve({conflict: false, case_no: 'TEST', assignment_id: 12, group_message: '延期提案通知'})");
  await settle();
  assert.deepEqual(messages, ['延期提案通知']);
  if (expectRetry) {
    assert.equal(nodes.get('postponeSubmitBtn').disabled, false);
    assert.equal(nodes.get('postponeSubmitBtn').textContent, '重試送出延期訊息');
    assert.equal(evaluate('closeCount'), 0);
    assert.match(nodes.get('postponeActionNotice').textContent, /已儲存.*重試送出同一筆/);
    evaluate("handlePostponeDateClick('2027-01-07')");
    assert.equal(evaluate("postponeSelectedDates.has('2027-01-07')"), true);

    failSend = false;
    await evaluate('Promise.all([submitPostponeProposal(), submitPostponeProposal()])');
    assert.deepEqual(messages, ['延期提案通知', '延期提案通知']);
  }
  assert.equal(evaluate('calls.map(call => call.path).join()'), 'preview,preview,propose');
  assert.equal(evaluate('closeCount'), 0);
  assert.equal(nodes.get('postponeSubmitBtn').disabled, true);
  assert.equal(nodes.get('postponeReturnToGroup').hidden, false);
  assert.match(nodes.get('postponeActionNotice').textContent, /延期訊息已送出.*繼續改日期/);
  assert.equal(evaluate("postponeSelectedDates.has('2027-01-07')"), true);
  await evaluate('submitPostponeProposal()');
  evaluate("handlePostponeDateClick('2027-01-07'); handlePostponeDateClick('2027-01-07');");
  assert.equal(nodes.get('postponeSubmitBtn').disabled, true);
  assert.equal(evaluate('calls.length'), 3);

  evaluate("handlePostponeDateClick('2027-01-07'); handlePostponeDateClick('2027-01-09');");
  assert.equal(evaluate('calls[3].path'), 'preview');
  evaluate('calls[3].resolve({conflict: false})');
  await settle();
  assert.equal(nodes.get('postponeSubmitBtn').disabled, false);
  evaluate('void submitPostponeProposal()');
  assert.equal(evaluate('calls[4].path'), 'propose');
  assert.equal(evaluate('calls[4].payload.dates[0].new_date'), '2027-01-09');
  assert.notEqual(evaluate('calls[2].payload.idempotency_key'), evaluate('calls[4].payload.idempotency_key'));
  evaluate("calls[4].resolve({conflict: false, case_no: 'TEST', assignment_id: 12, group_message: '新版延期提案通知'})");
  await settle();
  assert.equal(messages.at(-1), '新版延期提案通知');
  assert.equal(evaluate('closeCount'), 0);

  evaluate("handlePostponeDateClick('2027-01-09'); handlePostponeDateClick('2027-01-10');");
  evaluate("calls[5].reject({httpStatus: 409, code: 'leave_result_dates_changed'})");
  await settle();
  assert.equal(nodes.get('postponeSubmitBtn').disabled, true);
  assert.equal(nodes.get('postponeRetryPreview').hidden, false);
  assert.equal(nodes.get('postponeRetryPreview').textContent, '讀取最新排班');
  assert.match(nodes.get('postponeActionNotice').textContent, /正式排班已變更/);
  evaluate("let refreshCount = 0; loadPostponeCase = async () => { refreshCount++; };");
  await evaluate('retryPostponeCheck()');
  assert.equal(evaluate('refreshCount'), 1);

  lineContext = 'external';
  evaluate(`
    requirePostponeGroupReply = false;
    postponeCheck = {status: 'ready', intent: calls[2].payload};
    void submitPostponeProposal();
  `);
  evaluate("calls[6].resolve({conflict: false, case_no: 'TEST', assignment_id: 12, group_message: null})");
  await settle();
  assert.equal(evaluate('closeCount'), 0);
  assert.match(nodes.get('postponeActionNotice').textContent, /已儲存.*手動回到原 LINE 群組/);
})().catch((error) => { console.error(error); process.exitCode = 1; });
""".replace("FAIL_SEND", json.dumps(fail_send)).replace("SOURCE", json.dumps(script))
    subprocess.run(["node"], input=runner, text=True, encoding="utf-8", check=True, timeout=10)


def test_postponement_page_distinguishes_order_status_from_role_block() -> None:
    source = (ROOT / "line/static/staff_schedule.html").read_text(encoding="utf-8")
    script = source.split("<script>", 1)[1].split(
        'document.getElementById("loadSchedule").addEventListener', 1
    )[0]
    runner = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const nodes = new Map();
const context = vm.createContext({
  document: {
    getElementById(id) {
      if (!nodes.has(id)) nodes.set(id, {});
      return nodes.get(id);
    },
  },
});
const evaluate = script => vm.runInContext(script, context);
evaluate(SOURCE);
evaluate(`
  focusCaseNo = 'TEST-ORDER';
  let response;
  let workbench;
  leaveResultPost = async (path, request) => {
    if (path !== 'cases' || request.case_no !== focusCaseNo) throw new Error('case not requested');
    return response;
  };
  setupPostponeWorkbench = async (item) => {
    workbench = item;
    showPostponeSection("postponeWorkbench");
  };
`);

(async () => {
  await evaluate("response = {items: [], availability: {code: 'order_status', order_status: '洽談中'}}; loadPostponeCase()");
  assert.equal(nodes.get('roleBlockedSection').hidden, true);
  assert.equal(nodes.get('postponeUnavailableSection').hidden, false);
  assert.match(nodes.get('postponeUnavailableDescription').textContent, /洽談中.*訂單成立後/);

  await evaluate("response = {items: [], availability: {code: 'not_assigned'}}; loadPostponeCase()");
  assert.equal(nodes.get('roleBlockedSection').hidden, false);
  assert.equal(nodes.get('postponeUnavailableSection').hidden, true);

  await evaluate("response = {items: []}; loadPostponeCase()");
  assert.equal(nodes.get('roleBlockedSection').hidden, true);
  assert.equal(nodes.get('postponeUnavailableSection').hidden, false);
  assert.match(nodes.get('postponeUnavailableDescription').textContent, /沒有可調整的服務日/);

  await evaluate("response = {items: [{case_no: 'TEST-ORDER'}], availability: {code: 'eligible'}}; loadPostponeCase()");
  assert.equal(evaluate('workbench.case_no'), 'TEST-ORDER');
  assert.equal(nodes.get('postponeWorkbench').hidden, false);
  assert.equal(nodes.get('postponeUnavailableSection').hidden, true);
})().catch((error) => { console.error(error); process.exitCode = 1; });
""".replace("SOURCE", json.dumps(script))
    subprocess.run(["node"], input=runner, text=True, encoding="utf-8", check=True, timeout=10)


def test_staff_baby_log_page_is_retired() -> None:
    assert not (ROOT / "line" / "static" / "staff_baby_log.html").exists()
    assert not hasattr(line_identity, "staff_baby_log_page")
    assert not any(
        getattr(route, "path", None) == "/line-staff-baby-log"
        for route in line_identity.page_router.routes
    )


def test_active_liff_pages_offer_manual_reauthentication_without_url_identity() -> None:
    identity = (ROOT / "line" / "static" / "identity.html").read_text(encoding="utf-8")
    assert "重新登入 LINE" in identity
    assert "liff.logout()" in identity
    assert 'liff.login({redirectUri: location.href})' in identity
    assert 'params.get("userId")' not in identity

    targets = {
        "staff_order_search.html": "staff_order_search",
        "staff_schedule.html": "staff_schedule",
        "staff_payout.html": "staff_payout",
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
    assert 'supportedTargets.includes(target) ? target : targetFromUrl()' in mobile_admin
    assert any(
        fallback in mobile_admin
        for fallback in (
            'supportedTargets.includes(requested) ? requested : "staff_review"',
            'supportedTargets.includes(requested) ? requested : "customer_service"',
        )
    )
    assert "liff.login({redirectUri: redirect.toString()})" in mobile_admin
    assert "liff.login({redirectUri: location.href})" not in mobile_admin
    assert 'params.get("userId")' not in mobile_admin


def test_line_bind_page_route_serves_bind_html() -> None:
    response = line_identity.bind_page()
    assert response.status_code == 200
    assert response.path.name == "bind.html"


def test_line_profile_pages_are_retired_and_not_routed() -> None:
    """Customer self-service profile update is fully retired with no routes or files."""
    assert not (ROOT / "line/static/profile_update.html").exists()
    assert not (ROOT / "line/static/profile_guard.html").exists()
    assert not hasattr(line_identity, "profile_update_page")
    assert not hasattr(line_identity, "profile_guard_page")
    routes = {route.path for route in line_identity.page_router.routes}
    assert "/line-profile-update" not in routes
    assert "/line-profile-guard" not in routes


def test_customer_order_update_form_is_retired() -> None:
    assert not (ROOT / "line/static/order_update.html").exists()

    menu = json.loads((ROOT / "config/line_menu.json").read_text(encoding="utf-8"))
    customer = next(item for item in menu["menus"] if item["id"] == "customer_menu")
    assert {"order_update", "profile_update"}.isdisjoint(
        button["id"] for button in customer["buttons"]
    )

    gateway = (ROOT / "line/static/gateway.html").read_text(encoding="utf-8")
    identity = (ROOT / "line/static/identity.html").read_text(encoding="utf-8")
    assert "/line-order-update" not in gateway
    assert "/line-order-update" not in identity


def test_customer_order_change_application_routes_are_retired() -> None:
    from fastapi.routing import iter_route_contexts

    from api.main import app
    from api.nas_apps import line_app
    from api.routes.line_order_change import retired_order_change_ticket_apply

    removed_routes = (
        ("GET", "/line-order-update"),
        ("POST", "/api/v1/line/order-change/query"),
        ("POST", "/api/v1/line/order-change/preview"),
        ("POST", "/api/v1/line/order-change/requests"),
        ("GET", "/api/v1/orders/change-requests"),
        ("GET", "/api/v1/orders/change-requests/legacy"),
        ("POST", "/api/v1/orders/change-requests/{request_id}/complete"),
    )
    for application in (app, line_app()):
        endpoints = {
            (method, route.path): route.endpoint
            for route in iter_route_contexts(application.routes)
            for method in route.methods or ()
        }
        assert set(removed_routes).isdisjoint(endpoints)
        assert endpoints[("POST", "/api/v1/line/order-change/apply")] is retired_order_change_ticket_apply

    with pytest.raises(HTTPException) as retired:
        retired_order_change_ticket_apply()

    assert retired.value.status_code == 410
    error = retired.value.detail["error"]
    assert error["code"] == "order_change_ticket_apply_retired"
    assert "官方帳號聊天室" in error["message"]


def test_new_staff_page_routes_serve_split_assets() -> None:
    payout = line_identity.staff_payout_page()
    assert payout.status_code == 200
    assert payout.path.name == "staff_payout.html"

    assert not hasattr(line_identity, "staff_baby_log_page")


def test_studio_preview_routes_serve_gateway_and_non_citizen_registration() -> None:
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    app = FastAPI()
    app.include_router(line_identity.public_router)
    with TestClient(app) as client:
        gateway = client.get("/api/v1/line/identity/studio-preview/gateway?studio_preview=1")
        assert gateway.status_code == 200
        assert "服務確認入口" in gateway.text

        non_citizen = client.get(
            "/api/v1/line/identity/studio-preview/non-citizen-registration?studio_preview=1"
        )
        assert non_citizen.status_code == 200
        assert '<body data-registration-kind="non_citizen">' in non_citizen.text


def test_studio_preview_pages_resolve_runtime_config_under_prefix() -> None:
    for filename, script_index, pathname, expected in (
        ("gateway.html", 1, "/test/api/v1/line/identity/studio-preview/gateway", "/test/api/config/liff/runtime?page=gateway"),
        ("gateway.html", 1, "/line-gateway", "/api/config/liff/runtime?page=gateway"),
        ("register.html", 1, "/test/api/v1/line/identity/studio-preview/non-citizen-registration", "/test/api/config/liff/runtime?page=non_citizen_registration"),
        ("register.html", 1, "/line-non-citizen-registration", "/api/config/liff/runtime?page=non_citizen_registration"),
    ):
        source = (ROOT / "line" / "static" / filename).read_text(encoding="utf-8")
        assert "studio-preview" in source
        fetched_urls: str = expected
        runner = f"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const calls = [];
const context = vm.createContext({{
  URLSearchParams,
  URL,
  crypto: {{ randomUUID: () => 'uuid-test' }},
  sessionStorage: {{ getItem: () => '', setItem: () => undefined }},
  fetch: async (url) => {{ calls.push(url); return {{ ok: false, status: 500, json: async () => ({{}}) }}; }},
  document: {{
    body: {{ dataset: {{ registrationKind: 'non_citizen' }}, style: {{}}, classList: {{ add: () => undefined }} }},
    documentElement: {{ style: {{ setProperty: () => undefined }} }},
    addEventListener: () => undefined,
    getElementById: () => ({{ style: {{}}, textContent: '', hidden: false, disabled: false, value: '', addEventListener: () => undefined, replaceChildren: () => undefined, previousElementSibling: {{ textContent: '' }} }}),
    querySelectorAll: () => [],
  }},
  window: {{
    location: {{ pathname: {json.dumps(pathname)}, search: '?studio_preview=1', href: {json.dumps(pathname + '?studio_preview=1')} }},
    addEventListener: () => undefined,
  }},
  location: {{ pathname: {json.dumps(pathname)}, search: '?studio_preview=1', href: {json.dumps(pathname + '?studio_preview=1')} }},
  console: {{ error: () => undefined, warn: () => undefined }},
}});
vm.runInContext({json.dumps(source.split('<script>')[script_index].split('</script>', 1)[0])}, context);
(async () => {{
  await (typeof context.initLiff === 'function' ? context.initLiff() : context.initializeLiff());
  assert.equal(calls[0], {json.dumps(fetched_urls)});
}})().catch((error) => {{ console.error(error); process.exit(1); }});
"""
        subprocess.run(["node"], input=runner, text=True, encoding="utf-8", check=True, timeout=10)


def test_root_endpoint_serves_gateway_html_for_purpose_and_schedule_liff_params(monkeypatch) -> None:
    from fastapi import FastAPI
    from starlette.testclient import TestClient
    from line import line_bot

    app = FastAPI()
    app.include_router(line_bot.router)
    monkeypatch.setattr(line_bot, "get_db_connection", lambda: type("C", (), {"close": lambda self: None})())

    with TestClient(app) as client:
        for query in (
            "purpose=admin_binding&flow_id=flow-123",
            "purpose=customer_binding&flow_id=flow-456",
            "flow_id=flow-789&case_no=C-2026-01&mode=postpone",
            "case_no=C-2026-01&mode=postpone&group_reply=1",
        ):
            res = client.get(f"/?{query}", headers={"Accept": "*/*"})
            assert res.status_code == 200
            assert "text/html" in res.headers["content-type"]
            assert "og:title" in res.text
            assert '"status":"healthy"' not in res.text

        health = client.get("/", headers={"Accept": "application/json"})
        assert health.status_code == 200
        assert health.json()["status"] == "healthy"

        for params in ({"target": "ai_assistant"}, {"liff.state": "/?target=ai_assistant"}):
            res = client.get("/", params=params)
            assert res.status_code == 200
            assert res.history == []
            assert 'id="qaFlow"' in res.text
            assert "await liff.init" in res.text
            assert res.headers["cache-control"] == "no-cache, no-store, must-revalidate"


def test_gateway_and_identity_route_all_guide_targets_without_dropping_context() -> None:
    gateway = (ROOT / "line" / "static" / "gateway.html").read_text(encoding="utf-8")
    identity = (ROOT / "line" / "static" / "identity.html").read_text(encoding="utf-8")

    assert "targetPaths.deposit_payment" in gateway
    assert "registration: '/line-identity?entry=registration'" in gateway
    assert "if (flowPurpose && flowId)" in gateway
    assert "/line-identity?${flowQuery.toString()}" in gateway
    assert "/line-staff-schedule?${scheduleQuery.toString()}" in gateway

    assert 'target === "deposit_payment"' in identity
    assert "`/line-deposit-payment?case_no=${encodeURIComponent(caseNo)}`" in identity
    assert "if (!purposeParam && flowIdParam && (modeParam || caseNoParam))" in identity
    assert 'if (caseNo) target.searchParams.set("case_no", caseNo);' in identity
    assert 'if (mode) target.searchParams.set("mode", mode);' in identity

    gateway_script = gateway.split("<script>", 1)[1].split("</script>", 1)[0]
    runner = """
const assert = require('node:assert/strict');
const vm = require('node:vm');
async function check(search, retired = false) {
  let redirected = null;
  const nodes = {
    pageLogo: {textContent: ''},
    pageTitle: {textContent: ''},
    pageSubtitle: {textContent: ''},
    loaderOverlay: {style: {display: 'flex'}},
    loaderText: {textContent: ''},
    actionsContainer: {replaceChildren: () => undefined, hasChildNodes: () => false},
    previewDestination: {textContent: ''},
  };
  const ctx = vm.createContext({
    URLSearchParams,
    document: {
      documentElement: {style: {setProperty: () => undefined}},
      body: {style: {}, classList: {add: () => undefined}},
      head: {append: () => undefined},
      getElementById: id => nodes[id] || {style: {}, textContent: ''},
    },
    window: {
      location: {search, href: 'https://example.test/' + search, pathname: '/'},
      addEventListener: () => undefined,
      liff: {init: async () => undefined, isLoggedIn: () => true, getIDToken: () => 'tok'},
    },
    fetch: async (url) => {
      if (url.includes('/api/config/liff/runtime')) {
        return {ok: true, json: async () => ({theme: {}, page: {title: 't', subtitle: 's', content: {}, actions: []}})};
      }
      return {ok: true, json: async () => ({data: {liff_id: '2010579869-5e4mcSmT'}})};
    },
    console: {error: () => undefined},
  });
  Object.defineProperty(ctx.window.location, 'href', {
    get: () => redirected || ('https://example.test/' + search),
    set: (v) => { redirected = v; },
  });
  vm.runInContext(SOURCE, ctx);
  await ctx.initLiff();
  if (retired) assert.match(nodes.loaderText.textContent, /案件群組.*雙方合意延期/);
  return redirected;
}
(async () => {
  assert.equal(await check('?purpose=admin_binding&flow_id=f1'), '/line-identity?purpose=admin_binding&flow_id=f1');
  assert.equal(await check('?liff.state=' + encodeURIComponent('/?purpose=staff_verification&flow_id=f2')), '/line-identity?purpose=staff_verification&flow_id=f2');
  assert.equal(await check('?flow_id=f3&case_no=C-1&mode=postpone'), '/line-staff-schedule?flow_id=f3&case_no=C-1&mode=postpone');
  assert.equal(await check('?flow_id=f3&case_no=C-1&mode=postpone&group_reply=1'), '/line-staff-schedule?flow_id=f3&case_no=C-1&mode=postpone&group_reply=1');
  assert.equal(await check('?case_no=C-1&mode=postpone&group_reply=1'), '/line-staff-schedule?case_no=C-1&mode=postpone&group_reply=1');
  assert.equal(await check('?liff.state=' + encodeURIComponent('/?case_no=C-1&mode=postpone&group_reply=1')), '/line-staff-schedule?case_no=C-1&mode=postpone&group_reply=1');
  assert.equal(await check('?target=staff_schedule&case_no=C-1&mode=postpone'), '/line-identity?target=staff_schedule&case_no=C-1&mode=postpone');
  assert.equal(await check('?target=staff_leave_apply', true), null);
  assert.equal(await check('?liff.state=' + encodeURIComponent('/?target=staff_leave_apply'), true), null);
  assert.equal(await check('?target=deposit_payment&case_no=C-1'), '/line-deposit-payment?case_no=C-1');
  assert.equal(await check('?entry=registration'), '/line-identity?entry=registration');
})().catch((e) => { console.error(e); process.exit(1); });
""".replace("SOURCE", json.dumps(gateway_script))
    subprocess.run(["node"], input=runner, text=True, encoding="utf-8", check=True, timeout=10)
