"""Exercise customer binding decisions with local DOM, fetch and LIFF substitutes."""

import json
from pathlib import Path
import subprocess

import pytest


ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "pyproject.toml").is_file())
REBIND_BLOCKED_MESSAGE = "拒絕重新綁定，請聯絡工會人員確認身分解除舊綁定。在用新帳號綁定"


def _run_page(status, actions="await handleFormSubmit(event);", *, apply_status="bound", preview_ok=True, in_client=True, survey_complete=True, existing_case=False, case_no=None, rebind_blocked_at=None):
    source = (ROOT / "line/static/bind.html").read_text(encoding="utf-8").split("<script>", 1)[1].split("</script>", 1)[0]
    settings = json.dumps({"status": status, "apply_status": apply_status, "preview_ok": preview_ok, "in_client": in_client, "survey_complete": survey_complete, "existing_case": existing_case, "case_no": case_no, "rebind_blocked_at": rebind_blocked_at, "rebind_blocked_message": REBIND_BLOCKED_MESSAGE})
    harness = r"""
const vm = require('node:vm');
const settings = SETTINGS;
const elements = new Map();
class Element {
  constructor() {
    this.value = ''; this.textContent = ''; this.disabled = false;
    this.style = {display: 'none'};
    this.classList = {add(){}, remove(){}, toggle(){}};
  }
  closest() {return this;}
  querySelector() {return null;}
  appendChild() {}
  focus() {}
}
const get = id => {if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id);};
get('userName').value = '測試媽媽'; get('userPhone').value = '0900000000';
get('lineUserId').value = 'U-test'; get('formContent').style.display = 'block';
const calls = [], messages = [], redirects = [];
let closes = 0;
const storage = new Map();
const search = '?flow_id=flow-test' + (settings.existing_case ? '&entry=existing_case' : '');
const location = {search, origin: 'https://line.example.test', replace: url => redirects.push(url)};
const context = vm.createContext({
  document: {getElementById: get, querySelectorAll: () => [], createElement: () => new Element()},
  window: {addEventListener(){}, location, close(){}},
  URL, URLSearchParams, console, setTimeout: callback => callback(), crypto: {randomUUID: () => 'request-test'},
  sessionStorage: {getItem: k => storage.get(k) || null, setItem: (k,v) => storage.set(k,v), removeItem: k => storage.delete(k)},
  liff: {isInClient: () => settings.in_client, getContext: () => ({type: 'utou'}),
    isApiAvailable: () => true, sendMessages: async values => messages.push(values), closeWindow: () => closes++},
  fetch: async (url, options) => {
    calls.push({url, body: JSON.parse(options.body)});
    if (settings.rebind_blocked_at && url.endsWith('/' + settings.rebind_blocked_at)) return {ok: false, status: 409, json: async () => ({detail: {error: {
      code: 'line_customer_rebind_blocked', message: settings.rebind_blocked_message,
    }}})};
    if (url.endsWith('/preview')) return {ok: settings.preview_ok, json: async () => ({data: {
      status: settings.status, expected_version: 3, preview_fingerprint: 'a'.repeat(64),
      candidate: settings.status === 'not_found' ? null : {
        has_completed_survey: settings.survey_complete, currently_bound: false, case_no: settings.case_no,
      },
    }})};
    if (url.endsWith('/apply')) return {ok: settings.apply_status !== 'conflict', json: async () => ({data: {status: settings.apply_status, receipt_identity:'public-receipt', preview_fingerprint:'a'.repeat(64), review_request_id:9}})};
    throw new Error('Unexpected request: ' + url);
  },
});
vm.runInContext(SOURCE, context);
const event = {preventDefault(){}};
context.event = event;
(async () => {
  await vm.runInContext('(async () => { currentIdToken = "test-id-token"; runtimePage = {success_title:"綁定成功",success_description:"綁定成功，專屬選單將稍後更新。"}; ACTIONS })()', context);
  const output = {calls, messages, redirects, closes, elements: {}};
  for (const [id, element] of elements) output.elements[id] = {text: element.textContent, display: element.style.display};
  process.stdout.write(JSON.stringify(output));
})().catch(error => {console.error(error); process.exitCode = 1;});
"""
    # Only fixed fixture data is injected; all request and SDK effects are local substitutes.
    harness = harness.replace("SETTINGS", settings).replace("SOURCE", json.dumps(source)).replace("ACTIONS", actions)
    result = subprocess.run(["node"], input=harness, text=True, encoding="utf-8", capture_output=True, timeout=10, cwd=ROOT)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_already_bound_returns_without_apply_or_an_invented_case_number():
    result = _run_page("already_bound")
    assert len(result["calls"]) == 1
    assert result["calls"][0]["url"].endswith("/preview")
    assert result["elements"]["successDesc"]["text"] == "您已完成綁定，可直接返回 LINE 使用。"
    assert result["redirects"] == result["messages"] == []


@pytest.mark.parametrize("existing_case", [False, True])
def test_rebind_blocked_at_preview_shows_exact_guidance_without_apply(existing_case):
    result = _run_page("matched", rebind_blocked_at="preview", existing_case=existing_case, case_no="A115001")
    assert [item["url"] for item in result["calls"]] == ["/api/v1/line/identity/customer/preview"]
    assert result["elements"]["formContent"]["display"] == "block"
    assert result["elements"]["successContent"]["display"] == "none"
    assert "rebindConfirmButton" not in result["elements"]
    assert result["elements"]["statusMessage"]["text"] == REBIND_BLOCKED_MESSAGE
    assert result["redirects"] == result["messages"] == []


def test_matched_binding_does_not_claim_menu_delivery_or_fabricate_case_number():
    result = _run_page("matched")
    assert result["elements"]["successDesc"]["text"].startswith("綁定成功，專屬選單將稍後更新。")
    assert len(result["calls"]) == 2


def test_failed_preview_does_not_redirect_or_automatically_call_human_service():
    result = _run_page("matched", "await handleFormSubmit(event); await handleFormSubmit(event);", preview_ok=False)
    assert all(item["url"].endswith("/preview") for item in result["calls"])
    assert result["redirects"] == result["messages"] == []
    assert result["elements"]["bindingFailureActions"]["display"] == "flex"
    assert "工單" not in result["elements"]["statusMessage"]["text"]


@pytest.mark.parametrize("in_client", [False, True])
def test_binding_failure_guides_manual_contact_without_sending_a_message(in_client):
    result = _run_page("matched", preview_ok=False, in_client=in_client)
    assert result["messages"] == []
    assert result["closes"] == 0
    assert result["elements"]["statusMessage"]["text"].endswith("如需協助，請回 LINE 官方帳號聊天室留言。")


def test_stale_rebind_result_does_not_show_success():
    result = _run_page("matched", rebind_blocked_at="apply")
    assert [item["url"] for item in result["calls"]] == [
        "/api/v1/line/identity/customer/preview", "/api/v1/line/identity/customer/apply",
    ]
    assert result["elements"]["successContent"]["display"] == "none"
    assert result["elements"]["statusMessage"]["text"] == REBIND_BLOCKED_MESSAGE


@pytest.mark.parametrize("status,survey_complete,redirect", [("not_found", True, True), ("matched", False, True), ("matched", True, False)])
def test_only_successful_lookup_can_enter_the_registration_form(status, survey_complete, redirect):
    result = _run_page(status, survey_complete=survey_complete)
    if redirect:
        assert result["redirects"][0].startswith("https://line.example.test/line-registration?")
        assert len(result["calls"]) == 1
    else:
        assert result["redirects"] == []


@pytest.mark.parametrize(("status", "call_count"), [("matched", 2), ("already_bound", 1)])
def test_existing_case_can_bind_or_read_back_same_account(status, call_count):
    result = _run_page(status, existing_case=True, case_no="A115001")
    assert len(result["calls"]) == call_count
    assert result["elements"]["successContent"]["display"] == "block"
    assert result["elements"]["successTitle"]["text"] == ("綁定成功" if status == "matched" else "您已完成綁定")
    assert result["redirects"] == result["messages"] == []


@pytest.mark.parametrize(("status", "survey_complete", "preview_ok", "case_no"), [
    ("not_found", True, True, None),
    ("matched", False, True, "A115001"),
    ("matched", True, True, None),
    ("matched", True, False, "A115001"),
])
def test_existing_case_keeps_incomplete_lookup_on_binding_page(status, survey_complete, preview_ok, case_no):
    result = _run_page(status, existing_case=True, case_no=case_no,
                       survey_complete=survey_complete, preview_ok=preview_ok)
    assert result["redirects"] == result["messages"] == []
    assert [call["url"] for call in result["calls"]] == ["/api/v1/line/identity/customer/preview"]
    assert result["elements"]["bindingFailureActions"]["display"] == "flex"


@pytest.mark.parametrize("conflict", ["old_account", "different_customer"])
def test_direct_rebind_is_blocked_before_apply_and_creates_no_review(conflict):
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from fastapi import HTTPException

    from api.routes.line_identity import _translate_identity_errors
    from domains.line.identities import LineIdentityFlowId, LineUserId
    from domains.line.identity_binding import LineBindingSubjectType, LineIdentityBindingStatus
    from domains.line.identity_flow import LineIdentityFlowPurpose, LineIdentityFlowSnapshot, LineIdentityFlowStatus
    from shared_kernel.fingerprints import PreviewFingerprint
    from shared_kernel.identities import CorrelationId, ExpectedVersion
    from subsystems.line.identity_application import LineCustomerRebindBlockedError, LineIdentityApplication
    from subsystems.line.identity_contracts import CustomerIdentityProof, LineIdentityCandidate

    now = datetime(2026, 10, 22, tzinfo=timezone.utc)
    user = LineUserId("U-rebind-test")
    flow_id = LineIdentityFlowId("flow-rebind-test")
    owner = LineUserId("U-original-owner") if conflict == "old_account" else None
    target = LineIdentityCandidate(LineBindingSubjectType.CUSTOMER, "requested-client", owner)
    binding = None if conflict == "old_account" else SimpleNamespace(
        version=ExpectedVersion(2), status=LineIdentityBindingStatus.BOUND, subject_reference="original-client",
    )
    proof = CustomerIdentityProof("測試媽媽", "0900000000")

    def unexpected_write(*_):
        pytest.fail("blocked rebind must not write or create a review")

    class Uow:
        identities = SimpleNamespace(get=lambda *_: binding, bind=unexpected_write)
        customers = SimpleNamespace(resolve_customer=lambda *_: target, bind_customer=unexpected_write)
        identity_flows = SimpleNamespace(
            get=lambda *_: LineIdentityFlowSnapshot(flow_id, LineIdentityFlowPurpose.CUSTOMER_BINDING, user,
                LineIdentityFlowStatus.ACTIVE, now + timedelta(minutes=15), "rebind-test"),
            consume=unexpected_write,
        )
        reviews = SimpleNamespace(create=unexpected_write)
        delivery_tasks = SimpleNamespace(enqueue=unexpected_write)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        commit = unexpected_write

    application = LineIdentityApplication(Uow, lambda: now)
    with pytest.raises(HTTPException) as response:
        _translate_identity_errors(application.preview_customer, flow_id, user, proof)
    assert response.value.status_code == 409
    assert response.value.detail["error"]["code"] == "line_customer_rebind_blocked"
    assert response.value.detail["error"]["message"] == (
        "拒絕重新綁定，請聯絡工會人員確認身分解除舊綁定。在用新帳號綁定"
    )
    with pytest.raises(LineCustomerRebindBlockedError):
        application.apply_customer(flow_id, user, proof, ExpectedVersion(0),
            PreviewFingerprint("a" * 64), CorrelationId("rebind-bypass-test"))

    # Once the original binding has been released, this is an ordinary bind.
    target = LineIdentityCandidate(LineBindingSubjectType.CUSTOMER, "requested-client", None)
    binding = None
    assert application.preview_customer(flow_id, user, proof).status.value == "matched"
