"""Contracts for isolated union-staff mobile work surfaces."""

from datetime import date, datetime
import json
from pathlib import Path
import struct
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.routes import line_mobile_admin
from subsystems.anomalies.current_issue_query import CurrentIssueListRequest


ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "requirements.txt").is_file() and (parent / "line").is_dir()
)


def test_union_staff_targets_are_isolated_and_have_real_mobile_queries() -> None:
    source = (ROOT / "line" / "static" / "mobile_admin.html").read_text(
        encoding="utf-8"
    )

    assert 'id="tabCustomer"' not in source
    assert 'id="tabScheduling"' not in source
    assert 'id="tabReview"' not in source
    assert 'anomalies_center: document.getElementById("anomaliesPane")' in source
    assert 'dashboard: document.getElementById("operationsPane")' in source
    assert "/api/v1/line/mobile-admin/current-anomalies" in source
    assert "/api/v1/line/mobile-admin/operations-summary" in source
    assert "/api/v1/line/mobile-admin/client-profile/requests" in source
    assert "/api/v1/line/mobile-admin/staff-leave-requests" in source
    assert "客戶資料異動" in source
    assert "客戶／月嫂身分重綁與異常" in source
    assert "請假、代班與改期" in source
    assert "媒合指派與重新媒合" in source
    assert 'review_type: null' in source
    assert "待辦數量僅包含月嫂身分驗證申請" not in source
    assert "客服、異常與 QA 內容審核不會在這裡重複列入" in source
    assert "不是待確認佇列" in source
    assert 'class="workstream-trigger"' in source
    assert 'id="reviewTotal"' in source
    assert "今日到期" not in source
    assert "--bg:#f7f4ec" in source
    assert "#dbeafe" not in source


def test_union_staff_menu_uses_honest_work_surface_labels() -> None:
    source = (ROOT / "config" / "line_menu.json").read_text(encoding="utf-8")
    definition = json.loads(source)

    for label in ("待辦工作台", "客服中心", "異常中心", "營運摘要"):
        assert f'"label":"{label}"' in source
    for stale_label in ("待確認審核", "重大異常通報", "即時營運看板"):
        assert stale_label not in source
    menu = next(item for item in definition["menus"] if item["id"] == "union_staff_menu")
    assert menu["appearance"]["image_path"] == "line/union_staff_menu_v2.png"
    image = (ROOT / menu["appearance"]["image_path"]).read_bytes()
    assert image[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", image[16:24]) == (2500, 1686)


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
