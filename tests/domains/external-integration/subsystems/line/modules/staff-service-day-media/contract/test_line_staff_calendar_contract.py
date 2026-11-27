"""
File: test_line_staff_calendar_contract.py
Description: 驗證月嫂 LIFF 班表的 typed 狀態與正式 Scheduling 可見語意。
"""

from contextlib import nullcontext
from datetime import date
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.routes import line_staff_self_service
from api.schemas.line_staff_self_service import StaffLiffRequest, StaffScheduleDayView
from domains.line.identities import LineUserId
from domains.scheduling.staff_availability import (
    StaffAvailabilityBlockStatus,
    StaffAvailabilityDomainError,
    StaffAvailabilityErrorCode,
)
from infrastructure.line.liff_token_verifier import InvalidLiffTokenError
from shared_kernel.fingerprints import PreviewFingerprint


ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "requirements.txt").is_file() and (parent / "subsystems").is_dir()
)


def _day(**overrides) -> dict:
    return {
        "work_date": "2026-08-24",
        "status": "available",
        "staff_id": 7,
        "is_work_day": False,
        "is_double_pay": False,
        **overrides,
    }


def test_staff_schedule_day_status_is_closed_and_unavailability_is_typed() -> None:
    unavailable = StaffScheduleDayView.model_validate(
        _day(
            status="staff_unavailability",
            unavailability_block_id=31,
            unavailability_kind="long_leave",
            unavailability_reason="返鄉休息",
        )
    )

    assert unavailable.unavailability_block_id == 31
    assert unavailable.unavailability_kind == "long_leave"
    assert unavailable.unavailability_reason == "返鄉休息"
    with pytest.raises(ValidationError):
        StaffScheduleDayView.model_validate(_day(status="unknown_calendar_state"))


def test_staff_schedule_page_distinguishes_waiting_lock_rest_and_unavailability() -> None:
    source = (ROOT / "line" / "static" / "staff_schedule.html").read_text(
        encoding="utf-8"
    )

    assert "已鎖定／待成立" in source
    assert "正式不可服務" in source
    assert "休息日" in source
    assert "休息/請假" not in source
    assert 'item.status === "waiting_deposit_lock"' in source
    assert 'item.status === "staff_unavailability"' in source


def test_staff_schedule_mutations_use_typed_preview_apply_readback() -> None:
    schedule = (ROOT / "line" / "static" / "staff_schedule.html").read_text(
        encoding="utf-8"
    )
    assert not (ROOT / "line" / "static" / "staff_baby_log.html").exists()

    assert "function requireStaffSchedule" in schedule
    assert ".innerHTML" not in schedule
    assert "/leave-results/" in schedule
    assert "leaveResultPost('propose', {...intent, idempotency_key: idempotencyKey})" in schedule
    assert "leaveResultPost('proposal-status'" in schedule
    assert "leaveResultPost('submit'" not in schedule
    assert "/leave-requests/preview" not in schedule
    assert "confirmLeave" not in schedule
    assert "/service-day-logs/preview" not in schedule


def test_staff_self_service_queries_never_commit() -> None:
    source = (ROOT / "api" / "routes" / "line_staff_self_service.py").read_text(
        encoding="utf-8"
    )

    query_source = source.split("def order_search", 1)[1].split("def _required_staff", 1)[0]
    flow_query_source = source.split("def _verified_staff_self_service_flow", 1)[1].split(
        "def _development_fallback_enabled", 1
    )[0]
    assert "unit_of_work.commit()" not in query_source
    assert "unit_of_work.commit()" not in flow_query_source


def test_staff_liff_invalid_token_returns_staff_specific_typed_error(monkeypatch) -> None:
    verifier = SimpleNamespace(
        verify=lambda _: (_ for _ in ()).throw(InvalidLiffTokenError("provider detail"))
    )
    monkeypatch.setattr(line_staff_self_service, "get_liff_token_verifier", lambda: verifier)

    with pytest.raises(HTTPException) as captured:
        line_staff_self_service._verified_line_user_id(
            StaffLiffRequest(line_id_token="signed-token")
        )

    assert captured.value.status_code == 401
    assert captured.value.detail["error"]["code"] == "liff_token_invalid"
    assert "管理員" not in captured.value.detail["error"]["message"]
    assert "provider detail" not in captured.value.detail["error"]["message"]


@pytest.fixture
def availability_liff(monkeypatch):
    def verify(token):
        if token not in {"signed-staff", "signed-unbound"}:
            raise InvalidLiffTokenError("provider detail")
        return SimpleNamespace(line_user_id=LineUserId(token))

    def staff_subject(line_user_id):
        return {"staff_id": 7} if line_user_id == "signed-staff" else None

    monkeypatch.setattr(line_staff_self_service, "get_liff_token_verifier", lambda: SimpleNamespace(verify=verify))
    monkeypatch.setattr(line_staff_self_service, "open_line_unit_of_work", lambda: nullcontext(
        SimpleNamespace(customer_service=SimpleNamespace(staff_subject=staff_subject))
    ))
    availability = SimpleNamespace(query_records=Mock(), preview=Mock(), apply=Mock())
    app = FastAPI()
    app.include_router(line_staff_self_service.router)
    app.dependency_overrides[line_staff_self_service.get_staff_availability_application] = lambda: availability
    with TestClient(app) as client:
        yield client, availability


_AVAILABILITY_PATH = "/api/v1/line/staff-self-service/availability-blocks"
_AVAILABILITY_INTENT = {
    "line_id_token": "signed-staff", "start_date": "2026-12-04", "end_date": "2026-12-06", "reason": "休假",
}


def _availability_block(block_id, status):
    return SimpleNamespace(
        block_id=block_id, staff_id=7, kind="long_leave", start_date=date(2026, 12, 4),
        end_date=date(2026, 12, 6), status=status, reason="休假",
    )


def test_availability_liff_reads_formal_own_records_with_stable_cursor(availability_liff) -> None:
    client, availability = availability_liff
    availability.query_records.return_value = (
        _availability_block(17, StaffAvailabilityBlockStatus.EFFECTIVE),
        _availability_block(18, StaffAvailabilityBlockStatus.CANCELLED),
    )
    response = client.post(f"{_AVAILABILITY_PATH}/query", json={"line_id_token": "signed-staff", "limit": 2})

    assert response.status_code == 200
    assert response.json()["data"] == {
        "staff_id": 7,
        "items": [{"block_id": 17, "staff_id": 7, "kind": "long_leave", "start_date": "2026-12-04",
                   "end_date": "2026-12-06", "status": "effective", "reason": "休假"}],
        "next_after_id": 18,
    }
    query = availability.query_records.call_args.args[0]
    assert (query.staff_id, query.after_id, query.limit) == (7, 0, 2)
    availability.apply.assert_not_called()


def test_availability_liff_uses_signed_staff_and_existing_apply_contract(availability_liff) -> None:
    client, availability = availability_liff
    availability.preview.return_value = SimpleNamespace(
        candidate=SimpleNamespace(kind="long_leave", start_date=date(2026, 12, 4), end_date=date(2026, 12, 6)),
        staff_id=7, action="create_long_leave", source_version=4, target_block=None, blockers=(), can_apply=True,
        preview_fingerprint=PreviewFingerprint("a" * 64),
    )
    preview = client.post(f"{_AVAILABILITY_PATH}/preview", json=_AVAILABILITY_INTENT)
    assert preview.status_code == 200
    availability.apply.assert_not_called()

    def apply(request):
        return SimpleNamespace(
            staff_id=7, action=request.intent.action, block=_availability_block(17, StaffAvailabilityBlockStatus.EFFECTIVE),
            aggregate_version=5, preview_fingerprint=request.preview_fingerprint, idempotency_key=request.idempotency_key,
        )

    availability.apply.side_effect = apply
    proof = preview.json()["data"]
    key = str(uuid4())
    body = {
        **_AVAILABILITY_INTENT, "expected_version": proof["source_version"],
        "preview_fingerprint": proof["preview_fingerprint"], "idempotency_key": key,
    }
    first = client.post(f"{_AVAILABILITY_PATH}/apply", json=body)
    retried = client.post(f"{_AVAILABILITY_PATH}/apply", json=body)

    assert first.status_code == retried.status_code == 200
    assert first.json()["data"] == retried.json()["data"]
    assert first.json()["data"]["block"]["block_id"] == 17
    assert first.json()["data"]["idempotency_key"] == key
    first_request, retried_request = [call.args[0] for call in availability.apply.call_args_list]
    assert first_request == retried_request
    assert first_request.intent == availability.preview.call_args.args[0].intent
    assert first_request.intent.staff_id == 7
    assert first_request.intent.action == "create_long_leave"
    assert first_request.actor.actor_id == "line-staff:7"
    assert first_request.actor.permission_scope == ()

    availability.apply.side_effect = StaffAvailabilityDomainError(StaffAvailabilityErrorCode.ASSIGNMENT_CONFLICT)
    conflict = client.post(f"{_AVAILABILITY_PATH}/apply", json={**body, "idempotency_key": str(uuid4())})
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["error"]["code"] == "staff_unavailability_assignment_conflict"


@pytest.mark.parametrize("extra", [
    {"staff_id": 8}, {"action": "create_pause"}, {"force_preserve_committed_schedule": True},
    {"development_line_user_id": "fake"}, {"flow_id": "group-flow"},
])
def test_availability_liff_rejects_caller_identity_or_action_fields(availability_liff, extra) -> None:
    client, availability = availability_liff
    response = client.post(f"{_AVAILABILITY_PATH}/preview", json={**_AVAILABILITY_INTENT, **extra})
    assert response.status_code == 422
    availability.preview.assert_not_called()


@pytest.mark.parametrize(("token", "status"), [("other", 401), ("signed-unbound", 403)])
def test_availability_liff_denies_unverified_or_unbound_staff(availability_liff, token, status) -> None:
    client, availability = availability_liff
    response = client.post(f"{_AVAILABILITY_PATH}/apply", json={
        **_AVAILABILITY_INTENT, "line_id_token": token, "idempotency_key": str(uuid4()),
        "expected_version": 0, "preview_fingerprint": "a" * 64,
    })
    assert response.status_code == status
    availability.apply.assert_not_called()


def test_caregiver_liff_pages_senior_friendly_contract() -> None:
    schedule = (ROOT / "line" / "static" / "staff_schedule.html").read_text(encoding="utf-8")
    assert '<section id="unavailabilitySection" class="panel" aria-labelledby="unavailabilityTitle" hidden>' in schedule
    assert 'scheduleMode === \'postpone\'' in schedule
    assert 'document.getElementById("unavailabilitySection").hidden = true;' in schedule
    assert 'id="expiredLinkSection"' in schedule
    assert 'showLinkExpiredView' in schedule
    assert '15 分鐘' in schedule or '15分鐘' in schedule
    assert ".innerHTML" not in schedule

    order_search = (ROOT / "line" / "static" / "staff_order_search.html").read_text(encoding="utf-8")
    assert "tel:" not in order_search
    assert '["客戶電話", item.client_phone]' in order_search

    payout = (ROOT / "line" / "static" / "staff_payout.html").read_text(encoding="utf-8")
    assert "金額守恆與銷帳防錯保證" not in payout
    assert "手續費" in payout
    assert "方案一" in payout

    profile = (ROOT / "line" / "static" / "staff_profile_update.html").read_text(encoding="utf-8")
    assert "bank_branch_code" in profile
    start = profile.index("function formatCanonicalPeriod(")
    end = profile.index("function parseServicePeriods(", start)
    runner = profile[start:end] + """
const assert = require('node:assert/strict');
assert.equal(formatCanonicalPeriod("8小時", "08:30"), "8小時(08:30-17:00)");
assert.equal(formatCanonicalPeriod("4小時", "08:30"), "4小時(08:30-12:30)");
"""
    subprocess.run(["node"], input=runner, text=True, encoding="utf-8", check=True, timeout=10)


def test_staff_availability_ui_requires_original_receipt_and_formal_readback() -> None:
    source = (ROOT / "line" / "static" / "staff_schedule.html").read_text(encoding="utf-8")
    script = source.split("<script>", 1)[1].split(
        'document.getElementById("loadSchedule").addEventListener', 1
    )[0]
    runner = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');

function setup() {
  const nodes = new Map();
  const responses = [];
  const requests = [];
  const node = () => ({
    style: {},
    replaceChildren(...children) { this.children = children; this.textContent = ''; },
    addEventListener(event, handler) { this[event] = handler; },
  });
  const document = {
    createElement: node,
    getElementById(id) {
      if (!nodes.has(id)) nodes.set(id, node());
      return nodes.get(id);
    },
  };
  let keyCount = 0;
  const context = vm.createContext({
    AbortController, clearTimeout, setTimeout, document,
    crypto: {randomUUID: () => 'request-' + ++keyCount},
    fetch: async (url, request) => {
      assert.match(url, /^\/api\/v1\/line\/staff-self-service\/availability-blocks\/(query|preview|apply)$/);
      assert.equal(request.method, 'POST');
      const path = url.split('/').at(-1);
      requests.push([path, JSON.parse(request.body)]);
      const next = responses.shift();
      assert.ok(next, 'unexpected request to ' + path);
      if (next instanceof Error) throw next;
      return await next;
    },
  });
  const evaluate = script => vm.runInContext(script, context);
  evaluate(SOURCE);
  evaluate("lineIdToken = 'verified-staff'; let refreshes = 0; loadSchedule = async () => { refreshes++; };");
  document.getElementById('unavailStartDate').value = '2026-12-04';
  document.getElementById('unavailEndDate').value = '2026-12-06';
  document.getElementById('unavailReason').value = '休假';
  return {evaluate, nodes, responses, requests, keys: () => keyCount};
}
const send = (data, status = 200) => ({ok: status === 200, status, json: async () => data});
const ok = data => send({success: true, data});
const fingerprint = 'a'.repeat(64);
const dates = {start_date: '2026-12-04', end_date: '2026-12-06', reason: '休假'};
const block = {block_id: 31, staff_id: 7, kind: 'long_leave', status: 'effective', ...dates};
const preview = ok({staff_id: 7, action: 'create_long_leave', can_apply: true, source_version: 2,
  preview_fingerprint: fingerprint, candidate_kind: 'long_leave',
  candidate_start_date: dates.start_date, candidate_end_date: dates.end_date});
const receipt = ok({staff_id: 7, action: 'create_long_leave', block, aggregate_version: 3,
  preview_fingerprint: fingerprint, idempotency_key: 'request-1'});
const page = (items, next = null) => ok({staff_id: 7, items, next_after_id: next});
const status = nodes => nodes.get('unavailStatus').textContent;
const settle = () => new Promise(setImmediate);

(async () => {
  const {evaluate, nodes, responses, requests, keys} = setup();
  responses.push(page([], 30), page([block]));
  await evaluate('registerUnavailabilityHandlers()');
  assert.deepEqual(requests, [
    ['query', {line_id_token: 'verified-staff', after_id: 0}],
    ['query', {line_id_token: 'verified-staff', after_id: 30}],
  ]);
  assert.equal(nodes.get('unavailRecordList').children[0].textContent, '2026-12-04 至 2026-12-06｜休假');

  const initialQueryCount = requests.length;
  responses.push(preview, new Error('response lost'));
  await nodes.get('submitUnavailBtn').click();
  assert.match(status(nodes), /尚未確認登記結果/);
  assert.equal(nodes.get('unavailStartDate').disabled, true);
  assert.equal(evaluate('refreshes'), 0);
  assert.equal(keys(), 1);

  responses.push(receipt, page([]));
  await nodes.get('submitUnavailBtn').click();
  assert.match(status(nodes), /無法確認正式紀錄/);
  assert.equal(nodes.get('submitUnavailBtn').textContent, '查詢登記結果');
  assert.equal(evaluate('refreshes'), 0);
  assert.deepEqual(requests.map(([path]) => path).slice(initialQueryCount), ['preview', 'apply', 'apply', 'query']);
  assert.deepEqual(requests[initialQueryCount + 1], requests[initialQueryCount + 2]);
  assert.deepEqual(requests[initialQueryCount + 1][1], {
    line_id_token: 'verified-staff', ...dates, expected_version: 2,
    preview_fingerprint: fingerprint, idempotency_key: 'request-1',
  });

  let finishReadback;
  responses.push(new Promise(resolve => { finishReadback = resolve; }));
  const confirm = nodes.get('submitUnavailBtn').click();
  await settle();
  assert.doesNotMatch(status(nodes), /日期已登記/);
  assert.equal(nodes.get('submitUnavailBtn').disabled, true);
  finishReadback(page([block]));
  await confirm;
  assert.match(status(nodes), /不接案日期已登記/);
  assert.equal(evaluate('refreshes'), 1);
  assert.equal(keys(), 1);
  assert.equal(requests.at(-1)[0], 'query');

  const conflict = setup();
  conflict.responses.push(preview, send({detail: {error: {
    code: 'staff_unavailability_overlap', message: '不接案期間重疊。',
  }}}, 409));
  await conflict.evaluate('submitUnavailability()');
  assert.match(status(conflict.nodes), /既有不接案紀錄重疊/);
  assert.doesNotMatch(status(conflict.nodes), /日期已登記/);
  assert.deepEqual(conflict.requests.map(([path]) => path), ['preview', 'apply']);
  assert.equal(conflict.keys(), 1);

  const readOnly = setup();
  await readOnly.evaluate("scheduleMode = 'postpone'; submitUnavailability()");
  assert.deepEqual(readOnly.requests, []);
})().catch(error => { console.error(error); process.exitCode = 1; });
""".replace("SOURCE", json.dumps(script))
    subprocess.run(["node"], input=runner, text=True, encoding="utf-8", check=True, timeout=10)



def test_postponement_lost_group_acknowledgement_only_queries_original_proposal() -> None:
    source = (ROOT / "line" / "static" / "staff_schedule.html").read_text(encoding="utf-8")
    start = source.index("function postponeGroupStorageKey()")
    end = source.index("function loadPostponeAssignment(", start)
    runner = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const key = '91111111-2222-4333-8444-555555555555';
const caseNo = 'SYNTHETIC';
const intent = {case_no: caseNo, assignment_id: 7, dates: [{original_date:'2027-01-01', new_date:'2027-01-02'}]};
const values = new Map();
const tracked = [];
let providerCalls = 0;
let status = 'draft_saved';
const context = vm.createContext({
  focusCaseNo: caseNo, postponeGroupPending: null, lastSentPostponeSelection: undefined,
  postponeCheck: {status: 'ready', intent, idempotencyKey: key},
  sessionStorage: {
    setItem(name, data) { values.set(name, data); }, getItem(name) { return values.get(name) ?? null; },
    removeItem(name) { values.delete(name); },
  },
  canSendPostponeToGroup: () => true,
  postponeSelectionKey: () => 'original-selection',
  renderPostponeCheck() {}, renderPostponeCalendar() {}, updatePostponePairs() {},
  sentPostponeState: () => ({status: 'sent'}),
  liff: {async sendMessages() { providerCalls += 1; throw Error('lost reply'); }},
  AbortController, setTimeout, clearTimeout,
  async leaveResultPost(path, body) {
    tracked.push(path);
    assert.equal(body.idempotency_key, key);
    assert.equal(body.assignment_id, 7);
    assert.equal(body.case_no, caseNo);
    if (path === 'propose') return {conflict:false, case_no:caseNo, assignment_id:7, group_message:'draft'};
    return {status, case_no: caseNo, assignment_id:7, idempotency_key:key};
  },
});
vm.runInContext(require('node:fs').readFileSync(0, 'utf8'), context);
(async () => {
  await context.submitPostponeProposal();
  assert.equal(context.postponeCheck.status, 'awaiting-group');
  assert.deepEqual([...values.values()].map(JSON.parse), [{assignment_id:7, idempotency_key:key}]);
  context.postponeGroupPending = context.readPendingPostponeGroup();
  await context.submitPostponeProposal();
  assert.equal(context.postponeCheck.status, 'awaiting-group');
  status = 'group_received';
  await context.submitPostponeProposal();
  assert.equal(context.postponeCheck.status, 'sent');
  assert.equal(values.size, 0);
  assert.equal(providerCalls, 1);
  assert.deepEqual(tracked, ['propose', 'proposal-status', 'proposal-status', 'proposal-status']);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    subprocess.run(["node", "-e", runner], input=source[start:end], text=True, encoding="utf-8", check=True)
