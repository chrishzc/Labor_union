"""Exercise customer binding decisions with local DOM, fetch and LIFF substitutes."""

import json
from pathlib import Path
import subprocess

import pytest


ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "pyproject.toml").is_file())


def _run_page(status, actions="await handleFormSubmit(event);", *, apply_status="bound", preview_ok=True, in_client=True, survey_complete=True):
    source = (ROOT / "line/static/bind.html").read_text(encoding="utf-8").split("<script>", 1)[1].split("</script>", 1)[0]
    settings = json.dumps({"status": status, "apply_status": apply_status, "preview_ok": preview_ok, "in_client": in_client, "survey_complete": survey_complete})
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
const location = {search: '?flow_id=flow-test', origin: 'https://line.example.test', replace: url => redirects.push(url)};
const context = vm.createContext({
  document: {getElementById: get, querySelectorAll: () => [], createElement: () => new Element()},
  window: {addEventListener(){}, location, close(){}},
  URL, URLSearchParams, console, setTimeout: callback => callback(), crypto: {randomUUID: () => 'request-test'},
  sessionStorage: {getItem: k => storage.get(k) || null, setItem: (k,v) => storage.set(k,v), removeItem: k => storage.delete(k)},
  liff: {isInClient: () => settings.in_client, getContext: () => ({type: 'utou'}),
    isApiAvailable: () => true, sendMessages: async values => messages.push(values), closeWindow: () => closes++},
  fetch: async (url, options) => {
    calls.push({url, body: JSON.parse(options.body)});
    if (url.endsWith('/preview')) return {ok: settings.preview_ok, json: async () => ({data: {
      status: settings.status, expected_version: 3, preview_fingerprint: 'a'.repeat(64),
      candidate: settings.status === 'not_found' ? null : {has_completed_survey: settings.survey_complete, currently_bound: false},
    }})};
    if (url.endsWith('/apply')) return {ok: settings.apply_status !== 'conflict', json: async () => ({data: {status: settings.apply_status, receipt_identity:'public-receipt', preview_fingerprint:'a'.repeat(64), review_request_id:9}})};
    throw new Error('Unexpected request: ' + url);
  },
});
vm.runInContext(SOURCE, context);
const event = {preventDefault(){}};
context.event = event;
(async () => {
  await vm.runInContext('(async () => { currentIdToken = "test-id-token"; ACTIONS })()', context);
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


def test_rebind_cancel_does_not_apply_or_replace_any_binding():
    result = _run_page("requires_review", "await handleFormSubmit(event); cancelRebind();")
    assert len(result["calls"]) == 1
    assert result["elements"]["formContent"]["display"] == "block"
    assert result["elements"]["rebindContent"]["display"] == "none"
    assert result["elements"]["statusMessage"]["text"] == "已取消申請，原綁定維持不變。"


def test_rebind_only_applies_after_explicit_request_using_the_original_preview():
    result = _run_page("requires_review", "await handleFormSubmit(event); await confirmRebind();", apply_status="pending_review")
    assert [item["url"] for item in result["calls"]] == [
        "/api/v1/line/identity/customer/preview", "/api/v1/line/identity/customer/apply",
    ]
    assert result["calls"][1]["body"]["preview_fingerprint"] == "a" * 64
    assert result["calls"][1]["body"]["expected_version"] == 3
    assert result["elements"]["successTitle"]["text"] == "申請已送出"
    assert "核准前保留原綁定" in result["elements"]["successDesc"]["text"]
    assert result["messages"] == []


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


def test_human_call_requires_the_explicit_button_action():
    result = _run_page("matched", "await handleFormSubmit(event); await callStaff();", preview_ok=False)
    assert result["messages"] == [[{"type": "text", "text": "呼叫專員"}]]
    assert result["closes"] == 1


def test_unavailable_human_call_does_not_claim_a_request_was_created():
    result = _run_page("matched", "await handleFormSubmit(event); await callStaff();", preview_ok=False, in_client=False)
    assert result["messages"] == []
    assert result["closes"] == 0
    assert result["elements"]["statusMessage"]["text"] == "請返回官方 LINE 聊天室輸入「呼叫專員」。"


def test_stale_rebind_result_does_not_show_success():
    result = _run_page("requires_review", "await handleFormSubmit(event); await confirmRebind();", apply_status="conflict")
    assert result["elements"]["successContent"]["display"] == "none"
    assert result["elements"]["rebindContent"]["display"] == "block"
    assert result["elements"]["rebindStatusMessage"]["text"] == "目前無法完成綁定，請重新核對資料。"


@pytest.mark.parametrize("status,survey_complete,redirect", [("not_found", True, True), ("matched", False, True), ("matched", True, False)])
def test_only_successful_lookup_can_enter_the_registration_form(status, survey_complete, redirect):
    result = _run_page(status, survey_complete=survey_complete)
    if redirect:
        assert result["redirects"][0].startswith("https://line.example.test/line-registration?")
        assert len(result["calls"]) == 1
    else:
        assert result["redirects"] == []


@pytest.mark.parametrize("stale", [False, True])
def test_rebind_owner_only_creates_review_and_preserves_original_binding(stale):
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    from domains.line.identities import LineIdentityFlowId, LineReviewRequestId, LineUserId
    from domains.line.identity_binding import LineBindingSubjectType, LineIdentityBindingStatus
    from domains.line.identity_flow import LineIdentityFlowPurpose, LineIdentityFlowSnapshot, LineIdentityFlowStatus
    from shared_kernel.identities import CorrelationId, ExpectedVersion
    from subsystems.line.identity_application import LineIdentityApplication, LineIdentityConflictError
    from subsystems.line.identity_contracts import CustomerIdentityProof, LineIdentityCandidate

    now = datetime(2026, 10, 22, tzinfo=timezone.utc)
    user = LineUserId("U-rebind-test")
    flow_id = LineIdentityFlowId("flow-rebind-test")
    binding = SimpleNamespace(version=ExpectedVersion(2), status=LineIdentityBindingStatus.BOUND, subject_reference="original-client")
    target = LineIdentityCandidate(LineBindingSubjectType.CUSTOMER, "requested-client", LineUserId("U-original-owner"))
    proof = CustomerIdentityProof("測試媽媽", "0900000000")
    reviews, consumed, deliveries, commits = [], [], [], []

    class Uow:
        identities = SimpleNamespace(get=lambda *_: binding)
        customers = SimpleNamespace(resolve_customer=lambda *_: target)
        identity_flows = SimpleNamespace(
            get=lambda *_: LineIdentityFlowSnapshot(flow_id, LineIdentityFlowPurpose.CUSTOMER_BINDING, user,
                LineIdentityFlowStatus.ACTIVE, now + timedelta(minutes=15), "rebind-test"),
            consume=lambda *args: consumed.append(args),
        )
        delivery_tasks = SimpleNamespace(enqueue=lambda task: deliveries.append(task))

        def __init__(self):
            self.reviews = SimpleNamespace(create=self.create_review)

        def create_review(self, command):
            reviews.append(command)
            return SimpleNamespace(snapshot=SimpleNamespace(request_id=LineReviewRequestId(9)))

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def commit(self):
            commits.append(True)

    application = LineIdentityApplication(Uow, lambda: now)
    preview = application.preview_customer(flow_id, user, proof)
    assert preview.status.value == "requires_review"
    if stale:
        binding.version = ExpectedVersion(3)
        with pytest.raises(LineIdentityConflictError):
            application.apply_customer(flow_id, user, proof, preview.expected_version,
                preview.preview_fingerprint, CorrelationId("rebind-stale-test"))
        assert reviews == consumed == deliveries == commits == []
    else:
        result = application.apply_customer(flow_id, user, proof, preview.expected_version,
            preview.preview_fingerprint, CorrelationId("rebind-review-test"))
        assert result.status.value == "pending_review"
        assert len(reviews) == len(consumed) == len(deliveries) == len(commits) == 1
    assert binding.subject_reference == "original-client"
    assert binding.status is LineIdentityBindingStatus.BOUND
    assert target.currently_bound_line_user_id == LineUserId("U-original-owner")
