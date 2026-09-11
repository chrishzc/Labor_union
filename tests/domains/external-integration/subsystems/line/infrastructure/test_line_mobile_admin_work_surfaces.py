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
    assert "媒合指派與重新媒合" in source
    assert "需人工跟進" in source
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

    for label in ("待辦工作台", "客服中心", "狀態追蹤", "營運摘要"):
        assert f'"label":"{label}"' in source
    for stale_label in ("待確認審核", "重大異常通報", "異常中心", "即時營運看板"):
        assert stale_label not in source
    menu = next(item for item in definition["menus"] if item["id"] == "union_staff_menu")
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
        lambda _factory, _now, *, limit: SimpleNamespace(
            items=(
                SimpleNamespace(
                    pool_id=14,
                    case_no="CASE-SAFE-14",
                    candidate_count=3,
                    no_interest_count=2,
                    timed_out_count=1,
                    action_required="modify_then_recontact",
                    completed_at=completed_at,
                    notification_status="sent",
                    notification_task_id=61,
                ),
            ),
            total=1,
        ),
    )

    response = line_mobile_admin.matching_followups(
        line_mobile_admin._LiffAuthRequest(line_id_token="verified-token")
    )

    assert captured == [line_mobile_admin.LineCapability.MATCHING_READ]
    assert response.data == {
        "items": [
            {
                "pool_id": 14,
                "case_no": "CASE-SAFE-14",
                "candidate_count": 3,
                "no_interest_count": 2,
                "timed_out_count": 1,
                "action_required": "modify_then_recontact",
                "completed_at": completed_at,
                "notification_status": "sent",
                "notification_task_id": 61,
            }
        ],
        "total": 1,
    }


def test_matching_followup_editor_keeps_orders_terms_at_system_admin_boundary(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        line_mobile_admin,
        "_mobile_admin_context",
        lambda *_: (
            SimpleNamespace(role="line_manager"),
            SimpleNamespace(actor_id="admin:manager"),
        ),
    )

    with pytest.raises(HTTPException) as captured:
        line_mobile_admin._matching_followup_editor_context("verified-token")

    assert captured.value.status_code == 403
    assert (
        captured.value.detail["error"]["code"]
        == "mobile_matching_followup_system_admin_required"
    )


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

    assert "處理條件並重新詢問" in source
    assert "/terms/preview" in source
    assert "/terms/apply" in source
    assert "/recontact/preview" in source
    assert "/recontact/apply" in source
    assert "完成正式修改並讀回收據後" in source
    assert "客戶已同意媒合條件調整，由工會修改正式案件資料" in source
    assert "修改後預計結束日期" in source
    assert 'termsButton.textContent = termsCompleted ? "正式修改已完成"' in source
    assert "請直接進行步驟 2 的重新詢問預覽" in source
    assert "if (matchingOperation.terms_change_completed)" in source
    assert "此待辦不會開啟排班重建" in source
    assert "正式排班重建工具" in source
    assert "開啟案件" not in source


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
