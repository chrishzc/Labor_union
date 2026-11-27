"""Contracts for isolated union-staff mobile work surfaces."""

from datetime import date, datetime
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from PIL import Image

from api.routes import line_mobile_admin
from subsystems.anomalies.current_issue_query import CurrentIssueListRequest


@pytest.mark.parametrize('stage', ['deposit', 'first', 'second'])
def test_mobile_payment_reminders_delegate_exact_period_and_preserve_conflicts(monkeypatch, stage):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.dependencies.payment_overdue_reminders import get_payment_overdue_reminders
    from subsystems.access.authentication_session import AdminPrincipal
    from subsystems.line.payment_overdue_reminders import PaymentOverdueTodo, PaymentOverdueReminderConflict
    from subsystems.client_finance.overdue_payment_query import OverdueClientPayment
    from subsystems.line.capabilities import LineCapability
    from api.dependencies.admin_auth import admin_actor_context
    principal = AdminPrincipal(7, 'union-test', '合成工會人員', 'admin')
    capabilities, calls = [], []
    monkeypatch.setattr(line_mobile_admin, '_mobile_admin_context', lambda token, capability: (
        capabilities.append((token, capability)) or principal, admin_actor_context(principal)))
    payment = OverdueClientPayment('SYNTHETIC', stage, 'synthetic:'+stage, 3, 9, date(2026,10,1), 1200)
    class Application:
        def list(self, page, size):
            calls.append(('query',page,size))
            return ((PaymentOverdueTodo(payment, 1, '客戶私人聊天室' if stage=='deposit' else '案件群組', True, None, None),), 26)
        def send(self, expected, key, actor):
            assert expected == payment and key == 'same-operation' and actor.actor_id == 'admin:7'
            calls.append(('send',stage))
            raise PaymentOverdueReminderConflict('payment_overdue_changed')
    app=FastAPI();app.include_router(line_mobile_admin.router)
    app.dependency_overrides[get_payment_overdue_reminders]=lambda:Application()
    with TestClient(app) as client:
        response=client.post('/api/v1/line/mobile-admin/payment-overdue-reminders',json={'line_id_token':'synthetic-liff','page':2,'page_size':25})
        assert response.status_code == 200 and response.json()['data']['total']==26
        assert calls==[('query',2,25)], 'query must not create reminder tasks'
        snapshot=response.json()['data']['items'][0]['payment']
        response=client.post('/api/v1/line/mobile-admin/payment-overdue-reminders/send',json={**snapshot,'line_id_token':'synthetic-liff','idempotency_key':'same-operation'})
        assert response.status_code==409 and '款項或收件對象已更新' in response.text
    assert [capability for _,capability in capabilities] == [LineCapability.CUSTOMER_SERVICE_HANDLE]*2


def test_mobile_log_reminders_share_owner_gap_and_receipt_without_exposing_liff_token(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from subsystems.access.authentication_session import AdminPrincipal
    from api.dependencies.admin_auth import admin_actor_context
    from subsystems.line.capabilities import LineCapability
    principal=AdminPrincipal(7,'union-test','合成人員','admin'); capabilities=[]
    monkeypatch.setattr(line_mobile_admin,'_mobile_admin_context',lambda token,capability:(capabilities.append(capability) or principal,admin_actor_context(principal)))
    app=FastAPI();app.include_router(line_mobile_admin.router)
    with TestClient(app) as client:
        response=client.post('/api/v1/line/mobile-admin/log-reminders',json={'line_id_token':'synthetic-liff'})
        assert response.status_code==410 and response.json()['detail']['error']['code']=='service_day_log_reminder_retired'
        send_resp=client.post('/api/v1/line/mobile-admin/log-reminders/send',json={'line_id_token':'synthetic-liff','case_no':'C1','staff_id':1,'missing_from':'2026-10-01','missing_through':'2026-10-04','idempotency_key':'op'})
        assert send_resp.status_code==410 and send_resp.json()['detail']['error']['code']=='service_day_log_reminder_retired'
    assert capabilities==[LineCapability.ORDER_GROUP_READ,LineCapability.CUSTOMER_SERVICE_HANDLE]


@pytest.mark.parametrize('route', ['payment-overdue-reminders','payment-overdue-reminders/send'])
def test_mobile_reminder_denied_binding_never_reaches_owner(monkeypatch,route):
    def deny(*_):raise HTTPException(403,'synthetic forbidden')
    monkeypatch.setattr(line_mobile_admin,'_mobile_admin_context',deny)
    class Application:
        def list(self,*_):pytest.fail('denied query reached owner')
        def send(self,*_):pytest.fail('denied send reached owner')
    body={'line_id_token':'synthetic-liff'}
    if route=='payment-overdue-reminders/send':
        body.update(case_no='SYNTHETIC',payment_stage='deposit',obligation_identity='deposit:SYNTHETIC',projection_version=1,obligation_event_id=1,due_date='2026-10-01',remaining_amount_ntd=1200,idempotency_key='operation')
        request=line_mobile_admin._MobileOverdueReminderSend(**body); function=line_mobile_admin.mobile_send_payment_overdue_reminder
    else:
        request=line_mobile_admin._MobileTodoPageRequest(**body)
        function=line_mobile_admin.mobile_payment_overdue_reminders
    with pytest.raises(HTTPException) as error:function(request,Application())
    assert error.value.status_code==403


ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "requirements.txt").is_file() and (parent / "line").is_dir()
)


def test_leave_pending_page_is_complete_and_processed_requests_leave_the_total(monkeypatch):
    import sqlite3
    from api.routes import staff_leave_management
    raw = sqlite3.connect(':memory:')
    raw.row_factory = sqlite3.Row
    raw.executescript('CREATE TABLE staff(id INTEGER,name TEXT); INSERT INTO staff VALUES(1,"Public staff"); '
                       'CREATE TABLE scheduling_staff_leave_request_aggregates(id INTEGER,staff_id INTEGER,leave_start_date TEXT,'
                       'leave_end_date TEXT,request_reason TEXT,request_status TEXT,aggregate_version INTEGER,created_at TEXT);')
    for index in range(110):
        raw.execute('INSERT INTO scheduling_staff_leave_request_aggregates VALUES (?,1,"2026-11-01","2026-11-02",'
                    '"Public request",?,1,"2026-10-23")', (index + 1, 'pending' if index % 2 else 'accepted_for_processing'))
    raw.execute('INSERT INTO scheduling_staff_leave_request_aggregates VALUES (111,1,"2026-11-01","2026-11-02",'
                '"Completed","resolved",2,"2026-10-23")')
    class Cursor:
        def __enter__(self): self.cursor = raw.cursor(); return self
        def __exit__(self, *_): self.cursor.close()
        def execute(self, sql, args): self.cursor.execute(sql.replace('%s', '?'), args)
        def fetchone(self): return dict(self.cursor.fetchone())
        def fetchall(self): return [dict(row) for row in self.cursor.fetchall()]
    monkeypatch.setattr(staff_leave_management, 'get_connection', lambda: SimpleNamespace(cursor=Cursor, close=lambda: None))
    seen = []
    for page in range(1, 6):
        result = staff_leave_management.query_pending_staff_leave_page(page=page, page_size=25).data
        assert result.total == 110
        seen.extend(item.id for item in result.items)
    assert len(seen) == len(set(seen)) == 110 and 111 not in seen
    raw.execute("UPDATE scheduling_staff_leave_request_aggregates SET request_status='resolved' WHERE id=1")
    result = staff_leave_management.query_pending_staff_leave_page(page=1, page_size=25).data
    assert result.total == 109 and 1 not in [item.id for item in result.items]
    raw.close()


def test_mobile_todo_runtime_refreshes_pending_identity_counts():
    import subprocess
    script = r'''
import fs from 'node:fs'; import vm from 'node:vm'; import assert from 'node:assert/strict';
const source=fs.readFileSync('line/static/mobile_admin.html','utf8').replace(/\r\n/g,'\n');
const extract=h=>{const i=source.indexOf(h);assert(i>=0);return source.slice(i,source.indexOf('\n}\n',i)+2)};
class Element {
  constructor(tag='div'){this.tag=tag;this.isConnected=true;this.dataset={};this.children=[];this.listeners={};this.value='';this.textContent='';this.classList={add(){},remove(){}}}
  append(...x){this.children.push(...x)} appendChild(x){this.children.push(x);return x}
  replaceChildren(...x){this.children=[...x]} addEventListener(k,f){this.listeners[k]=f} setAttribute(){}
}
const nodes=new Map(); const get=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id)};
const ctx=vm.createContext({document:{getElementById:get,createElement:t=>new Element(t)},crypto});
for(const id of ['identityReviewCount','leaveReviewCount','serviceStartCount','matchingFollowupCount','customerRecommendationCount','depositCount','groupTodoCount','paymentOverdueCount','logReminderCount'])get(id).dataset.pendingCount='0';
vm.runInContext(`let reviewQuerySequence=0; const target='staff_review';
 let notificationSequence=0;let notificationSelection=null;const focusNotificationItems=(source,items)=>items;const reviewPageState={page:1,pageSize:50}; let pendingTotal=1;
 const postJson=async(url,body)=>url.endsWith('identity-reviews')?{items:body.review_status==='pending'&&pendingTotal?[{}]:[],total:body.review_status==='pending'?pendingTotal:0,page:body.page,page_size:body.page_size}:{status:'queued'};
 const reviewCard=()=>({});const showEmpty=()=>{};const showStatus=()=>{};`,ctx);
vm.runInContext(source.slice(source.indexOf('function notificationText('),source.indexOf('function updateNotificationCards(')),ctx);
vm.runInContext(extract('function notificationButton('),ctx);
for(const header of ['function notificationViewCurrent(','function updateReviewTotal()','function setWorkstreamCount(','function requireReviewPage(','function requireTodoPage(','function renderPagination(','async function loadIdentityReviews()'])vm.runInContext(extract(header),ctx);
get('reviewStatus').value='pending';await vm.runInContext('loadIdentityReviews()',ctx);assert.equal(get('identityReviewCount').textContent,'1');
vm.runInContext('pendingTotal=0',ctx);get('reviewStatus').value='approved';await vm.runInContext('loadIdentityReviews()',ctx);assert.equal(get('identityReviewCount').textContent,'0');
assert.equal(get('reviewTotal').textContent,'0');
'''
    subprocess.run(['node', '--input-type=module', '-e', script], cwd=ROOT, check=True, capture_output=True, text=True, timeout=20)


def test_mobile_group_todo_guides_binding_and_copies_each_reply() -> None:
    import subprocess

    script = r'''
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

class Element {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.dataset = {};
    this.listeners = {};
    this.textContent = '';
    this.isConnected = true;
  }
  append(...children) {
    this.children.push(...children.map(child => typeof child === 'string'
      ? {tag: '#text', children: [], textContent: child}
      : child));
  }
  appendChild(child) { this.append(child); return child; }
  replaceChildren(...children) { this.children = children; }
  addEventListener(event, listener) { this.listeners[event] = listener; }
}

const nodes = new Map();
const get = id => {
  if (!nodes.has(id)) nodes.set(id, new Element('div'));
  return nodes.get(id);
};
const caseNo = '115000157';
const copied = [];
let clipboardDenied = false;
const context = vm.createContext({
  document: {getElementById: get, createElement: tag => new Element(tag), querySelectorAll: () => []},
  location: {search: ''},
  URLSearchParams,
  navigator: {clipboard: {writeText: async value => {
    if (clipboardDenied) throw new Error('clipboard denied');
    copied.push(value);
  }}},
  fetch: async (url) => {
    assert.equal(url, '/api/v1/line/mobile-admin/order-group-todos');
    return {ok: true, json: async () => ({data: {
      items: [{case_no: caseNo, deposit_amount_ntd: 3000}], total: 1, total_pages: 1, page: 1,
    }})};
  },
});
const html = fs.readFileSync('line/static/mobile_admin.html', 'utf8');
const source = html.split('<script>')[1].split('</script>')[0];
vm.runInContext(source.replace(/^init\(\);$/m, ''), context);
await vm.runInContext('loadGroupTodos()', context);

const descendants = node => [node, ...node.children.flatMap(descendants)];
const visibleText = node => descendants(node).map(child => child.textContent).join(' ');
const card = get('groupTodos').children[0];
assert(card);
assert.match(visibleText(card), /同一位.*同一個.*群組/);
const list = descendants(card).find(node => node.tag === 'ol');
assert(list, '群組綁定需要依序顯示三個步驟');
const [start, number, url] = list.children;
assert.equal(list.children.length, 3);
assert.match(visibleText(start), /綁定群組/);
assert.match(visibleText(number), new RegExp(caseNo));
assert.match(visibleText(url), /右上角.*設定.*邀請.*邀請網址/);
assert.match(visibleText(url), /綁定成功後，系統會依資格將客戶與已綁定 LINE 的指派月嫂的私人邀請排入發送。/);
assert.doesNotMatch(visibleText(card), /綁定訂單|複製設定格式|發送邀請/);

const copyButton = (step, label) => descendants(step).find(node => node.tag === 'button' && node.textContent === label);
const copyStart = copyButton(start, '複製綁定群組');
const copyNumber = copyButton(number, '複製案件編號');
assert(copyStart);
assert(copyNumber);
await copyStart.listeners.click();
await copyNumber.listeners.click();
assert.deepEqual(copied, ['綁定群組', caseNo]);

clipboardDenied = true;
await copyNumber.listeners.click();
assert.deepEqual(copied, ['綁定群組', caseNo]);
assert.match(get('status').textContent, /手動複製.*115000157/);
assert.equal(get('status').className, 'error');
'''
    subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT, check=True, capture_output=True, text=True, timeout=20,
    )


def test_mobile_substitute_todo_opens_management_schedule_for_the_same_case():
    import subprocess

    script = r'''
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

class Element {
  constructor(tag) { this.tag = tag; this.children = []; }
  append(...children) { this.children.push(...children); }
  replaceChildren() { this.children = []; }
  setAttribute() {}
}

const source = fs.readFileSync('line/static/mobile_admin.html', 'utf8');
const start = source.indexOf('function serviceStartTodoCard(');
assert(start >= 0);
const context = vm.createContext({
  document: { createElement: tag => new Element(tag) },
  sessionStorage: { getItem: () => null },
  URLSearchParams,
});
vm.runInContext(source.slice(start, source.indexOf('</script>', start)), context);
const item = {
  request_id: 8, case_no: 'CASE&1', workflow_kind: 'leave', status: 'substitute_required',
  staff_name: '原月嫂', leave_dates: [{original_date: '2027-01-05'}],
  willingness: 'willing', joined: false,
};
const card = context.serviceStartTodoCard(item, [], 'https://management.test/test/');
const body = card.children[0].children;
assert(body.some(node => node.textContent.includes('2027-01-05')));
const schedule = body.find(node => node.tag === 'a');
assert.equal(schedule.href, 'https://management.test/test/#order-workbench-v2?case=CASE%261&work=service&substitute=8');
assert.equal(schedule.textContent, '前往多月嫂排班');
assert(!body.some(node => ['button', 'input', 'select'].includes(node.tag)));
const unavailable = context.serviceStartTodoCard(item, [], null).children[0].children;
assert(!unavailable.some(node => node.tag === 'a'));
assert(unavailable.some(node => node.textContent.includes('管理端連結暫時不可用')));
'''
    subprocess.run(
        ["node", "--input-type=module", "-e", script],
        cwd=ROOT, check=True, capture_output=True, text=True, timeout=20,
    )


@pytest.mark.parametrize(("origin", "prefix", "expected"), [
    (None, None, "https://chrishzc.com/test/"),
    ("https://management.test/test/", None, "https://management.test/test/"),
    ("https://management.test", "/office", "https://management.test/office/"),
    ("https://management.test/actual/", "/office", "https://management.test/actual/"),
    ("http://management.test/test/", None, None),
    ("//management.test/test/", None, None),
    ("https://user@management.test/test/", None, None),
    ("https://management.test/test/?next=elsewhere", None, None),
    ("https://management.test/test/#elsewhere", None, None),
    ("https://management.test/../test/", None, None),
    ("https://management.test", "//other.test", None),
])
def test_verified_mobile_profile_exposes_only_a_trusted_management_entry(monkeypatch, origin, prefix, expected):
    from api.routes import line_mobile_admin as routes

    monkeypatch.delenv("PUBLIC_ORIGIN", raising=False)
    monkeypatch.delenv("WINDOWS_REMOTE_PREFIX", raising=False)
    if origin is not None:
        monkeypatch.setenv("PUBLIC_ORIGIN", origin)
    if prefix is not None:
        monkeypatch.setenv("WINDOWS_REMOTE_PREFIX", prefix)
    principal = SimpleNamespace(id=9, display_name="測試工會人員", role="line_manager")
    monkeypatch.setattr(routes, "_mobile_admin_context", lambda _token: (principal, None))
    response = routes.profile(routes._LiffAuthRequest(line_id_token="test-line-id-token"))
    assert routes._MobileAdminProfileView.model_validate(response.data).management_entry_url == expected


def test_customer_recommendation_followups_are_staff_authorized_and_read_only(monkeypatch):
    from subsystems.scheduling.matching_notification_contracts import CustomerRecommendationFollowup
    from subsystems.line.capabilities import LineCapability
    calls = []
    item = CustomerRecommendationFollowup("CASE-TEST", 10, "awaiting_signing", None, 55)
    class Uow:
        matching_notifications = SimpleNamespace(customer_recommendation_followups=lambda now, **kwargs: (item,),
                                                 customer_recommendation_followup_count=lambda now: 1)
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def commit(self):
            raise AssertionError("followup query must remain read-only")
    monkeypatch.setattr(line_mobile_admin, "_mobile_admin_context", lambda token, capability: calls.append(capability))
    monkeypatch.setattr(line_mobile_admin, "open_line_unit_of_work", Uow)
    response = line_mobile_admin.customer_recommendation_followups(line_mobile_admin._MobileTodoPageRequest(line_id_token="synthetic-token"))
    assert calls == [LineCapability.MATCHING_READ]
    page = line_mobile_admin._CustomerRecommendationFollowupPageView.model_validate(response.data)
    assert page.total == 1 and page.items[0].status == "awaiting_signing" and page.items[0].ticket_id == 55
    assert page.page == 1 and page.page_size == 25


def test_unbound_customer_cannot_query_recommendation_staff_tasks(monkeypatch):
    def denied(*_):
        raise HTTPException(403, "union staff binding required")
    def forbidden():
        raise AssertionError("unauthorized identity must not reach the query")
    monkeypatch.setattr(line_mobile_admin, "_mobile_admin_context", denied)
    monkeypatch.setattr(line_mobile_admin, "open_line_unit_of_work", forbidden)
    with pytest.raises(HTTPException) as caught:
        line_mobile_admin.customer_recommendation_followups(line_mobile_admin._LiffAuthRequest(line_id_token="synthetic-token"))
    assert caught.value.status_code == 403


def test_union_staff_targets_are_isolated_and_have_real_mobile_queries() -> None:
    source = (ROOT / "line" / "static" / "mobile_admin.html").read_text(
        encoding="utf-8"
    )

    assert 'id="tabCustomer"' not in source
    assert 'id="tabScheduling"' not in source
    assert 'id="tabReview"' not in source
    assert 'order_tracking: document.getElementById("orderTrackingPane")' in source
    assert 'targetAliases = Object.freeze({anomalies_center: "order_tracking", customer_service: "staff_review"})' in source
    assert 'dashboard: document.getElementById("operationsPane")' in source
    assert "/api/v1/line/mobile-admin/current-anomalies" not in source
    assert "/api/v1/line/mobile-admin/customer-service/" not in source
    assert 'id="customerPane"' not in source
    assert "/api/v1/line/mobile-admin/order-statuses" in source
    assert "/api/v1/line/mobile-admin/operations-summary" in source
    assert "/api/v1/line/mobile-admin/client-profile/requests" not in source
    assert "/api/v1/line/mobile-admin/staff-leave-requests" not in source
    assert "/api/v1/line/mobile-admin/matching-followups" in source
    assert "客戶資料異動" not in source
    assert "客戶／月嫂身分重綁與異常" in source
    assert "服務開始、延期、代班與換人" in source
    assert "月嫂回覆提醒" in source
    assert "月嫂確認與條件協調" not in source
    assert "待提醒" in source
    assert "開啟正式排班調整" not in source
    assert 'review_type: null' in source
    assert "待辦數量僅包含月嫂身分驗證申請" not in source
    assert "/api/v1/line/mobile-admin/notification-tasks" in source
    assert 'id="notificationSources"' in source
    assert 'id="notificationOperations"' in source
    assert "openNotificationItem" in source
    assert "這不是案件條件修改後的下一步" in source
    assert 'class="workstream-trigger"' in source
    assert 'id="reviewTotal"' in source
    assert "今日到期" not in source
    assert "--bg:#f7f4ec" in source
    assert "#dbeafe" not in source


def test_union_staff_menu_uses_honest_work_surface_labels() -> None:
    source = (ROOT / "config" / "line_menu.json").read_text(encoding="utf-8")
    definition = json.loads(source)

    menu = next(item for item in definition["menus"] if item["id"] == "union_staff_menu")
    assert [button["label"] for button in menu["buttons"]] == [
        "待辦工作台", "狀態追蹤", "營運摘要",
    ]
    assert menu["buttons"][0]["bounds"] == {"x": 0, "y": 0, "width": 2500, "height": 843}
    for stale_label in ("待確認審核", "重大異常通報", "異常中心", "即時營運看板"):
        assert stale_label not in source
    assert menu["appearance"]["image_path"] == "line/union_staff_menu_v3.jpg"
    with Image.open(ROOT / menu["appearance"]["image_path"]) as image:
        assert image.format == "JPEG"
        assert image.size == (2500, 1686)


def test_mobile_legacy_customer_service_checks_binding_then_returns_gone(monkeypatch):
    from subsystems.line.capabilities import LineCapability

    calls = []
    monkeypatch.setattr(line_mobile_admin, "_mobile_admin_context", lambda token, cap: calls.append((token, cap)))
    monkeypatch.setattr(line_mobile_admin, "open_line_unit_of_work", lambda: pytest.fail("retired API opened a unit of work"))

    with pytest.raises(HTTPException) as caught:
        line_mobile_admin.retired_mobile_customer_service(
            line_mobile_admin._LiffAuthRequest(line_id_token="synthetic-token")
        )

    assert calls == [("synthetic-token", LineCapability.CUSTOMER_SERVICE_READ)]
    assert caught.value.status_code == 410
    assert caught.value.detail["code"] == "customer_service_retired"


def test_mobile_order_tracking_is_read_only_and_prompts_formal_plan_after_willingness(
    monkeypatch,
) -> None:
    captured = []
    now = datetime.fromisoformat("2026-09-11T11:30:00+08:00")
    stages = tuple(
        SimpleNamespace(
            ordinal=ordinal,
            code=(
                "caregiver_willingness_reply"
                if ordinal == 4
                else f"stage_{ordinal}"
            ),
            label="等待月嫂意願回覆" if ordinal == 4 else f"階段 {ordinal}",
            status="completed" if ordinal < 4 else "in_progress",
            occurred_at=now if ordinal == 4 else None,
        )
        for ordinal in range(1, 14)
    )
    page = SimpleNamespace(
        items=(
            SimpleNamespace(
                case_no="CASE-WILLING-1",
                lifecycle_status=SimpleNamespace(value="洽談中"),
                current_core_stage_ordinal=4,
                core_stages=stages,
            ),
        ),
        next_cursor=None,
    )
    monkeypatch.setattr(
        line_mobile_admin,
        "_mobile_admin_context",
        lambda _token, capability: captured.append(("capability", capability))
        or (SimpleNamespace(), object()),
    )
    monkeypatch.setattr(
        line_mobile_admin,
        "query_core_stage_page",
        lambda application, request: captured.append((application, request)) or page,
    )
    monkeypatch.setattr(
        line_mobile_admin.candidate_contact_pool_workflow,
        "query_pool",
        lambda case_no: SimpleNamespace(
            candidates=(SimpleNamespace(status="active", willingness="willing"),)
        ),
    )
    application = SimpleNamespace()

    response = line_mobile_admin.order_statuses(
        line_mobile_admin._MobileOrderTrackingRequest(
            line_id_token="verified-token",
            page_size=20,
        ),
        application,
    )

    assert captured[0] == (
        "capability",
        line_mobile_admin.LineCapability.MATCHING_READ,
    )
    request = captured[1][1]
    assert request.workbench_scope == "in_progress"
    assert request.lifecycle_scope.value == "all"
    assert response.data == {
        "items": [
            {
                "case_no": "CASE-WILLING-1",
                "lifecycle_status": "洽談中",
                "current_stage_ordinal": 4,
                "current_stage_code": "caregiver_willingness_reply",
                "current_stage_label": "等待月嫂意願回覆",
                "current_stage_status": "in_progress",
                "completed_stage_count": 3,
                "next_action": "月嫂已回覆願意，請建立正式媒合方案並寄送月嫂履歷。",
                "has_willing_candidate": True,
                "updated_at": now,
            }
        ],
        "next_cursor": None,
    }


def test_mobile_anomalies_exposes_only_current_line_notification_issues(monkeypatch) -> None:
    captured = []
    issue = SimpleNamespace(
        issue_key="ci_" + "a" * 64,
        definition_code="LINE-006",
        owner_domain="external-integration",
        severity="blocking",
        blocking=True,
        episode_started_at=datetime.fromisoformat("2026-09-07T08:00:00+08:00"),
        last_verified_at=datetime.fromisoformat("2026-09-09T09:30:00+08:00"),
    )
    application = SimpleNamespace(
        query=lambda request: captured.append(request)
        or SimpleNamespace(items=(issue,), next_cursor=None)
    )
    monkeypatch.setattr(
        line_mobile_admin,
        "_mobile_admin_context",
        lambda *_: (SimpleNamespace(), object()),
    )

    response = line_mobile_admin.current_anomalies(
        line_mobile_admin._MobileCurrentAnomalyListRequest(
            line_id_token="verified-token"
        ),
        application,
    )

    assert captured == [
        CurrentIssueListRequest(definition_code="LINE-006", limit=50)
    ]
    assert response.data == {
        "items": [
            {
                "issue_key": "ci_" + "a" * 64,
                "definition_code": "LINE-006",
                "severity": "blocking",
                "blocking": True,
                "episode_started_at": datetime.fromisoformat(
                    "2026-09-07T08:00:00+08:00"
                ),
                "last_verified_at": datetime.fromisoformat(
                    "2026-09-09T09:30:00+08:00"
                ),
            }
        ],
        "next_cursor": None,
    }
    assert "owner_domain" not in response.data["items"][0]


def test_mobile_operations_summary_is_current_business_week_and_summary_only(
    monkeypatch,
) -> None:
    captured = []
    report = SimpleNamespace(
        start_date=date(2026, 9, 7),
        end_date=date(2026, 9, 9),
        generated_at=datetime.fromisoformat("2026-09-09T10:00:00+08:00"),
        summary=SimpleNamespace(
            application_count=8,
            general_eligible_count=3,
            subsidized_eligible_count=2,
            rejection_unpartitioned_count=1,
            order_established_count=4,
            incomplete_count=1,
        ),
        case_rows=(object(),),
    )
    query = SimpleNamespace(
        query=lambda start_date, end_date: captured.append((start_date, end_date))
        or report
    )
    monkeypatch.setattr(
        line_mobile_admin,
        "_mobile_admin_context",
        lambda *_: (SimpleNamespace(), object()),
    )
    monkeypatch.setattr(
        line_mobile_admin,
        "SystemBusinessClock",
        lambda: SimpleNamespace(today=lambda: date(2026, 9, 9)),
    )

    response = line_mobile_admin.operations_summary(
        line_mobile_admin._LiffAuthRequest(line_id_token="verified-token"),
        query,
    )

    assert captured == [(date(2026, 9, 7), date(2026, 9, 9))]
    assert response.data == {
        "start_date": date(2026, 9, 7),
        "end_date": date(2026, 9, 9),
        "generated_at": datetime.fromisoformat("2026-09-09T10:00:00+08:00"),
        "summary": {
            "application_count": 8,
            "general_eligible_count": 3,
            "subsidized_eligible_count": 2,
            "rejection_unpartitioned_count": 1,
            "order_established_count": 4,
            "incomplete_count": 1,
        },
    }
    assert "case_rows" not in response.data


def test_mobile_matching_followups_requires_matching_read_and_projects_safe_counts(
    monkeypatch,
) -> None:
    captured = []
    completed_at = datetime.fromisoformat("2026-09-11T10:00:00+08:00")
    monkeypatch.setattr(
        line_mobile_admin,
        "_mobile_admin_context",
        lambda _token, capability: captured.append(capability)
        or (SimpleNamespace(), object()),
    )
    monkeypatch.setattr(
        line_mobile_admin,
        "query_manual_followups",
        lambda _factory, _now, *, limit, page: SimpleNamespace(
            items=(
                SimpleNamespace(
                    pool_id=14,
                    case_no="CASE-SAFE-14",
                    candidate_count=3,
                    reminder_count=3,
                    reminder_due_at=completed_at,
                ),
            ),
            total=1,
        ),
    )

    response = line_mobile_admin.matching_followups(
        line_mobile_admin._MobileTodoPageRequest(line_id_token="verified-token")
    )

    assert captured == [line_mobile_admin.LineCapability.MATCHING_READ]
    assert response.data == {
        "items": [
            {
                "pool_id": 14,
                "case_no": "CASE-SAFE-14",
                "candidate_count": 3,
                "reminder_count": 3,
                "reminder_due_at": completed_at,
            }
        ],
        "total": 1,
        "page": 1,
        "page_size": 25,
    }


def test_mobile_followup_surface_only_shows_internal_reminders():
    source = (ROOT / "line" / "static" / "mobile_admin.html").read_text(encoding="utf-8")
    assert "/api/v1/line/mobile-admin/matching-followups" in source
    assert "月嫂回覆提醒" in source
    assert "/candidate-information" not in source and "/recontact/" not in source
    assert "/terms/apply" not in source
    assert "正式排班重建工具" in source


def test_mobile_operations_summary_fails_closed_when_owner_query_is_unavailable(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        line_mobile_admin,
        "_mobile_admin_context",
        lambda *_: (SimpleNamespace(), object()),
    )
    query = SimpleNamespace(
        query=lambda *_: (_ for _ in ()).throw(RuntimeError("storage unavailable"))
    )

    with pytest.raises(HTTPException) as captured:
        line_mobile_admin.operations_summary(
            line_mobile_admin._LiffAuthRequest(line_id_token="verified-token"),
            query,
        )

    assert captured.value.status_code == 500
    assert (
        captured.value.detail["error"]["code"]
        == "mobile_operations_summary_internal_error"
    )
    assert "storage unavailable" not in str(captured.value.detail)


def test_mobile_tracking_compares_database_and_aware_instants_in_utc():
    from datetime import timezone
    stages=(SimpleNamespace(ordinal=1,code='intake_validation',label='進件',status='in_progress',occurred_at=datetime(2026,10,26,10)),
            SimpleNamespace(ordinal=2,code='matching_pool',label='媒合',status='completed',occurred_at=datetime.fromisoformat('2026-10-26T17:00:00+08:00')))
    item=SimpleNamespace(case_no='SYNTHETIC',core_stages=stages,current_core_stage_ordinal=1,
                         lifecycle_status=SimpleNamespace(value='洽談中'))
    assert line_mobile_admin._mobile_order_tracking_item(item)['updated_at']==datetime(2026,10,26,10,tzinfo=timezone.utc)
