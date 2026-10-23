"""Contracts for isolated union-staff mobile work surfaces."""

from datetime import date, datetime
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from PIL import Image

from api.dependencies.order_terms import get_order_terms_application
from api.routes import line_mobile_admin, order_terms
from subsystems.anomalies.current_issue_query import CurrentIssueListRequest


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


def test_mobile_todo_runtime_refreshes_pending_counts_and_removes_answered_cards():
    import subprocess
    script = r'''
import fs from 'node:fs'; import vm from 'node:vm'; import assert from 'node:assert/strict';
const source=fs.readFileSync('line/static/mobile_admin.html','utf8');
const extract=h=>{const i=source.indexOf(h);assert(i>=0);return source.slice(i,source.indexOf('\n}\n',i)+2)};
class Element {
  constructor(tag='div'){this.tag=tag;this.dataset={};this.children=[];this.listeners={};this.value='';this.textContent='';this.classList={add(){},remove(){}}}
  append(...x){this.children.push(...x)} appendChild(x){this.children.push(x);return x}
  replaceChildren(...x){this.children=[...x]} addEventListener(k,f){this.listeners[k]=f} setAttribute(){}
}
const nodes=new Map(); const get=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id)};
const ctx=vm.createContext({document:{getElementById:get,createElement:t=>new Element(t)},crypto});
for(const id of ['identityReviewCount','profileReviewCount','leaveReviewCount','matchingFollowupCount','candidateInformationCount','customerRecommendationCount','depositCount','groupTodoCount'])get(id).dataset.pendingCount='0';
vm.runInContext(`let reviewQuerySequence=0,candidateInformationQuerySequence=0,candidateInformationPage=1; const target='staff_review';
 const reviewPageState={page:1,pageSize:50}; let pendingTotal=1;
 let questionReads=0;
 const postJson=async(url,body)=>url.endsWith('identity-reviews')?{items:body.review_status==='pending'&&pendingTotal?[{}]:[],total:body.review_status==='pending'?pendingTotal:0,page:body.page,page_size:body.page_size}:url.endsWith('candidate-information')?(questionReads++,{items:[],total:0,page:1,page_size:25}):url.endsWith('/recontact/apply')?[]:{status:'queued'};
 const reviewCard=()=>({});const showEmpty=()=>{};const showStatus=()=>{};const openMatchingFollowup=()=>{};`,ctx);
for(const header of ['function updateReviewTotal()','function setWorkstreamCount(','function requireReviewPage(','function requireTodoPage(','function renderPagination(','async function loadIdentityReviews()','async function loadCandidateInformation()','function candidateInformationCard('])vm.runInContext(extract(header),ctx);
get('reviewStatus').value='pending';await vm.runInContext('loadIdentityReviews()',ctx);assert.equal(get('identityReviewCount').textContent,'1');
vm.runInContext('pendingTotal=0',ctx);get('reviewStatus').value='approved';await vm.runInContext('loadIdentityReviews()',ctx);assert.equal(get('identityReviewCount').textContent,'0');
get('candidateInformationCount').dataset.pendingCount='1';
const card=vm.runInContext("candidateInformationCard({question_id:1,pool_id:1,case_no:'PUBLIC',staff_name:'Public staff',issues:[],request_kind:'information_question',review_completed:false,customer_available:false})",ctx);
get('candidateInformationQuestions').appendChild(card);
const all=n=>[n,...n.children.flatMap(x=>x instanceof Element?all(x):[])];
all(card).find(x=>x.tag==='textarea').value='Public answer';
await all(card).find(x=>x.textContent==='發送給月嫂').listeners.click();
assert.equal(get('candidateInformationCount').textContent,'0');
assert.equal(get('candidateInformationQuestions').children.filter(x=>x.tag==='article').length,0);
assert.equal(get('reviewTotal').textContent,'0');
vm.runInContext("let matchingOperation={pool_id:1,case_no:'PUBLIC',customer_answer_event_id:1};let matchingRecontactPreview=[{candidate_id:1,preview_fingerprint:'public'}];let reminderReads=0;const loadMatchingFollowups=async()=>{reminderReads++};const renderMatchingOperation=()=>{};",ctx);
vm.runInContext(extract('async function applyMatchingRecontact()'),ctx);
await vm.runInContext('applyMatchingRecontact()',ctx);
assert.equal(vm.runInContext('questionReads',ctx),2);
assert.equal(vm.runInContext('reminderReads',ctx),1);
'''
    subprocess.run(['node', '--input-type=module', '-e', script], cwd=ROOT, check=True, capture_output=True, text=True, timeout=20)


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


def test_candidate_information_staff_routes_require_matching_read_and_send(monkeypatch):
    from api.schemas.line_candidate_contact import CandidateInformationStaffQueryRequest, CandidateInformationStaffSendRequest
    from subsystems.line.capabilities import LineCapability
    capabilities = []
    commands = []
    monkeypatch.setattr(line_mobile_admin, "_mobile_admin_context", lambda token, capability: (
        capabilities.append(capability) or SimpleNamespace(id=3), None
    ))
    class Application:
        def __init__(self, factory):
            pass

        def query_staff_questions(self, *, page, page_size):
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

        def send_staff_information(self, *args):
            commands.append(args)
            return {"status": "queued", "event_id": 51}

    monkeypatch.setattr(line_mobile_admin, "CandidateContactResponseApplication", Application)
    line_mobile_admin.candidate_information_questions(CandidateInformationStaffQueryRequest(line_id_token="test-token"))
    line_mobile_admin.candidate_information_send(10, CandidateInformationStaffSendRequest(
        line_id_token="test-token", recipient="caregiver", message_text="人員輸入", idempotency_key="send-key"
    ))
    assert capabilities == [LineCapability.MATCHING_READ, LineCapability.MATCHING_SEND]
    assert commands[0][:4] == (10, "caregiver", "人員輸入", "admin:3")


def test_candidate_information_denied_staff_cannot_reach_the_writer(monkeypatch):
    from api.schemas.line_candidate_contact import CandidateInformationStaffSendRequest
    def deny(*args):
        raise HTTPException(403, "capability required")
    def unexpected(*args):
        pytest.fail("unauthorized request reached the application")
    monkeypatch.setattr(line_mobile_admin, "_mobile_admin_context", deny)
    monkeypatch.setattr(line_mobile_admin, "CandidateContactResponseApplication", unexpected)
    with pytest.raises(HTTPException) as error:
        line_mobile_admin.candidate_information_send(10, CandidateInformationStaffSendRequest(
            line_id_token="test-token", recipient="customer", message_text="人員輸入", idempotency_key="send-key"
        ))
    assert error.value.status_code == 403


def test_mobile_and_admin_terms_routes_share_the_same_owner_application_dependency() -> None:
    endpoints = (
        line_mobile_admin.matching_followup_terms_preview,
        line_mobile_admin.matching_followup_terms_apply,
        order_terms.preview_order_terms,
        order_terms.apply_order_terms,
    )

    for endpoint in endpoints:
        dependency = inspect.signature(endpoint).parameters["application"].default
        assert dependency.dependency is get_order_terms_application


def test_union_staff_targets_are_isolated_and_have_real_mobile_queries() -> None:
    source = (ROOT / "line" / "static" / "mobile_admin.html").read_text(
        encoding="utf-8"
    )

    assert 'id="tabCustomer"' not in source
    assert 'id="tabScheduling"' not in source
    assert 'id="tabReview"' not in source
    assert 'order_tracking: document.getElementById("orderTrackingPane")' in source
    assert 'targetAliases = Object.freeze({anomalies_center: "order_tracking"})' in source
    assert 'dashboard: document.getElementById("operationsPane")' in source
    assert "/api/v1/line/mobile-admin/current-anomalies" not in source
    assert "/api/v1/line/mobile-admin/order-statuses" in source
    assert "/api/v1/line/mobile-admin/operations-summary" in source
    assert "/api/v1/line/mobile-admin/client-profile/requests" in source
    assert "/api/v1/line/mobile-admin/staff-leave-requests" in source
    assert "/api/v1/line/mobile-admin/matching-followups" in source
    assert "客戶資料異動" in source
    assert "客戶／月嫂身分重綁與異常" in source
    assert "請假、代班與改期" in source
    assert "月嫂回覆提醒" in source
    assert "月嫂確認與條件協調" in source
    assert "待提醒" in source
    assert "開啟正式排班調整" not in source
    assert 'review_type: null' in source
    assert "待辦數量僅包含月嫂身分驗證申請" not in source
    assert "客服、異常與 QA 內容審核不會在這裡重複列入" in source
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
        "待辦工作台", "客服中心", "狀態追蹤", "營運摘要",
    ]
    for stale_label in ("待確認審核", "重大異常通報", "異常中心", "即時營運看板"):
        assert stale_label not in source
    assert menu["appearance"]["image_path"] == "line/union_staff_menu_v3.jpg"
    with Image.open(ROOT / menu["appearance"]["image_path"]) as image:
        assert image.format == "JPEG"
        assert image.size == (2500, 1686)


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


@pytest.mark.parametrize('role', ['line_agent', 'line_manager', 'system_admin'])
def test_matching_review_accepts_verified_union_staff_with_matching_capability(monkeypatch, role):
    captured = []
    def context(token, capability):
        captured.append(capability)
        return SimpleNamespace(role=role), SimpleNamespace(actor_id='union:1')
    monkeypatch.setattr(line_mobile_admin, '_mobile_admin_context', context)
    principal, actor = line_mobile_admin._matching_followup_editor_context('verified-token')
    assert principal.role == role and actor.actor_id == 'union:1'
    assert captured == [line_mobile_admin.LineCapability.MATCHING_OVERRIDE]


def test_matching_review_denied_identity_cannot_reach_the_orders_writer(monkeypatch):
    from api.schemas.line_candidate_contact import CandidateInformationStaffQueryRequest
    def deny(*args):
        raise HTTPException(403, 'unbound or missing capability')
    monkeypatch.setattr(line_mobile_admin, '_mobile_admin_context', deny)
    with pytest.raises(HTTPException) as error:
        line_mobile_admin._matching_followup_editor_context('untrusted-token')
    assert error.value.status_code == 403


def test_matching_review_preserves_canonical_orders_conflict(monkeypatch):
    from shared_kernel.errors import TypedError, ErrorCategory
    from shared_kernel.identities import ActorContext, CorrelationId
    from subsystems.orders.terms_workflow import TermsWorkflowError
    monkeypatch.setattr(line_mobile_admin, '_matching_followup_editor_context', lambda *_: (
        SimpleNamespace(role='line_agent'), ActorContext('union:1')
    ))
    class Review:
        def __init__(self, *args):
            pass
        def approve(self, *args):
            raise TermsWorkflowError(TypedError(ErrorCategory.CONFLICT, 'orders_version_conflict',
                '案件已更新，請重新讀取。', CorrelationId('test-review')))
    monkeypatch.setattr(line_mobile_admin, 'CandidateAdjustmentReviewApplication', Review)
    payload = line_mobile_admin._MobileMatchingTermsApplyRequest(
        line_id_token='verified-token', case_no='CASE-TEST', customer_answer_event_id=22,
        expected_order_version=1, idempotency_key='test-approval', proposed_terms={
            'planned_start_date': '2026-11-01', 'service_days': 14, 'service_hours_per_day': 6,
            'requires_cooking': False, 'floor_fee_ntd': 0,
            'service_time': {'start_time': '09:00:00', 'end_time': '15:00:00', 'end_day_offset': 0},
        },
    )
    with pytest.raises(HTTPException) as error:
        line_mobile_admin.matching_followup_terms_apply(100, payload, SimpleNamespace(connection=object(), workflow=object()))
    assert error.value.status_code == 409
    assert error.value.detail['error']['code'] == 'orders_version_conflict'


def test_matching_recontact_uses_accepted_answer_as_stable_idempotency_anchor(
    monkeypatch,
) -> None:
    captured = []
    operation = SimpleNamespace(
        pool_id=14,
        case_no="CASE-14",
        customer_answer_event_id=31,
        recontact_allowed=True,
        candidates=(
            SimpleNamespace(candidate_id=7, staff_name="王月嫂"),
            SimpleNamespace(candidate_id=8, staff_name="李月嫂"),
        ),
    )
    monkeypatch.setattr(
        line_mobile_admin,
        "_matching_followup_editor_context",
        lambda *_: (
            SimpleNamespace(role="system_admin"),
            SimpleNamespace(actor_id="admin:root"),
        ),
    )
    monkeypatch.setattr(line_mobile_admin, "_matching_operation", lambda *_: operation)
    monkeypatch.setattr(
        line_mobile_admin.candidate_contact_pool_workflow,
        "send_recontact_information",
        lambda case_no, candidate_id, info_type, actor, event_key, fingerprint: captured.append(
            (case_no, candidate_id, info_type, actor, event_key, fingerprint)
        )
        or {"status": "queued", "event_id": candidate_id + 100, "line_task_id": candidate_id + 200},
    )
    monkeypatch.setattr(line_mobile_admin, "publish_line_wakeup_best_effort", lambda: None)

    response = line_mobile_admin.matching_followup_recontact_apply(
        14,
        line_mobile_admin._MobileMatchingRecontactApplyRequest(
            line_id_token="verified-token",
            case_no="CASE-14",
            customer_answer_event_id=31,
            items=[
                {"candidate_id": 8, "preview_fingerprint": "b" * 64},
                {"candidate_id": 7, "preview_fingerprint": "a" * 64},
            ],
        ),
    )

    assert [item[1] for item in captured] == [7, 8]
    assert captured[0][4] == "mobile-matching-followup:14:31:7:info1"
    assert captured[1][4] == "mobile-matching-followup:14:31:8:info1"
    assert response.data[0]["candidate_id"] == 7
    assert response.data[1]["candidate_id"] == 8


def test_mobile_followup_surface_has_two_step_terms_and_recontact_controls() -> None:
    source = (ROOT / "line" / "static" / "mobile_admin.html").read_text(
        encoding="utf-8"
    )

    assert "審核通過並更新案件條件" in source
    assert "不通過，繼續協調" in source
    assert "客戶更新後的條件" in source
    assert "/terms/apply" in source
    assert "/recontact/preview" in source and "/recontact/apply" in source
    assert 'previewMatchingTerms' not in source
    assert '群組通知' not in source
    assert 'matchingApprovalIntent' in source
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
