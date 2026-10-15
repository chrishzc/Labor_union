"""Public typed API contract for official date correction."""

from datetime import date, datetime, timezone
from dataclasses import replace
from types import SimpleNamespace
import pytest
from fastapi import HTTPException

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.official_service_date_correction import (
    get_official_service_date_correction_workflow,
)
from api.routes.official_service_date_correction import router
from api.routes.official_service_date_correction import _call
from subsystems.orders.official_service_date_correction_workflow import (
    OfficialAssignmentDates,
    OfficialDateFacts,
    OfficialDateHistoryRecord,
    OfficialDateMonetaryImpactBlocked,
)


class _Workflow:
    def query(self, case_no):
        return OfficialDateFacts(
            case_no, 1, "訂單完成", date(2026, 9, 19), date(2026, 9, 20),
            True, 2, 8, 1, 11, 1,
            (OfficialAssignmentDates(13, 7, 1, "completed",
                                     (date(2026, 9, 19), date(2026, 9, 20)), "王月嫂"),),
        )

    def preview(self, *_args):
        raise ValueError("official_date_version_conflict")

    def apply(self, *_args, **_kwargs):
        raise RuntimeError("scheduling_version_conflict")


def _client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_system_admin] = lambda: SimpleNamespace(username="admin")
    app.dependency_overrides[get_official_service_date_correction_workflow] = _Workflow
    return TestClient(app)


def test_query_exposes_effective_assignment_dates_and_lock():
    response = _client().get("/api/v1/orders/ISSUE-346/official-service-dates")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["generation_id"] == 11
    assert data["service_data_locked"] is True
    assert data["assignments"][0]["service_dates"] == ["2026-09-19", "2026-09-20"]
    assert data["monetary_blockers"] == []


def test_query_exposes_original_completion_and_full_correction_reason_without_raw_snapshot():
    client = _client()
    facts = replace(_Workflow().query("ISSUE-346"), history=(
        OfficialDateHistoryRecord(45, "original_completion", datetime(2026, 9, 20, tzinfo=timezone.utc),
                                  "fixture", (), (date(2026, 9, 19), date(2026, 9, 20))),
        OfficialDateHistoryRecord(48, "service_date_corrected", datetime(2026, 9, 21, tzinfo=timezone.utc),
                                  "admin", (date(2026, 9, 19), date(2026, 9, 20)),
                                  (date(2026, 9, 19), date(2026, 9, 21)), "更正誤登日期；保留原完工與帳務。"),
    ))
    client.app.dependency_overrides[get_official_service_date_correction_workflow] = lambda: SimpleNamespace(query=lambda _case: facts)
    records = client.get("/api/v1/orders/ISSUE-346/official-service-dates").json()["data"]["history"]
    assert [record["event_id"] for record in records] == [45, 48]
    assert records[0]["after_dates"] == ["2026-09-19", "2026-09-20"]
    assert records[1]["reason"] == "更正誤登日期；保留原完工與帳務。"
    assert records[1]["after_dates"] == ["2026-09-19", "2026-09-21"]
    assert records[1]["recorded_at"].endswith("Z")
    assert "facts_snapshot" not in records[1]


@pytest.mark.parametrize("code,reason,target", [
    ("special_pay", "已有特殊薪資紀錄", "payroll"),
    ("payroll_adjustments", "已有薪資調整分攤", "payroll"),
    ("subsidy_return", "已有補助退還義務", "subsidy"),
    ("source_rate_snapshot_missing_or_ambiguous", "薪資快照缺漏或不唯一", "case_profile"),
    ("double_pay", "原正式服務日含雙倍薪", "payroll"),
    ("floor_fee", "原排班已分配樓層費", "case_profile"),
])
def test_query_and_fresh_preview_explain_the_actual_monetary_blocker(code, reason, target):
    client = _client()
    facts = replace(_Workflow().query("ISSUE-346"), monetary_change_blocker=True, monetary_blockers=(code,))
    client.app.dependency_overrides[get_official_service_date_correction_workflow] = lambda: SimpleNamespace(query=lambda _case: facts)
    data = client.get("/api/v1/orders/ISSUE-346/official-service-dates").json()["data"]
    assert data["monetary_blockers"][0]["code"] == code
    assert reason in data["monetary_blockers"][0]["message"]
    assert data["monetary_blockers"][0]["repair_target"] == target
    def blocked():
        raise OfficialDateMonetaryImpactBlocked((code,))
    with pytest.raises(HTTPException) as caught:
        _call(blocked)
    assert caught.value.status_code == 409
    assert reason in caught.value.detail["error"]["message"]


def test_stale_preview_and_writer_version_conflict_are_typed():
    assignments = [{"assignment_id": 13, "service_dates": ["2026-09-19", "2026-09-21"]}]
    client = _client()
    preview = client.post(
        "/api/v1/orders/ISSUE-346/official-service-dates/preview",
        json={"assignments": assignments},
    )
    assert preview.status_code == 409
    assert preview.json()["detail"]["error"]["category"] == "conflict"
    apply = client.post(
        "/api/v1/orders/ISSUE-346/official-service-dates/apply",
        headers={"Idempotency-Key": "test-issue346", "X-Correlation-ID": "test-issue346"},
        json={"assignments": assignments, "expected_order_version": 1,
              "expected_scheduling_version": 1, "preview_fingerprint": "a" * 64,
              "reason": "date correction"},
    )
    assert apply.status_code == 409
    assert apply.json()["detail"]["error"]["code"] == "scheduling_version_conflict"


@pytest.mark.parametrize('code,reason', [
    ('official_date_no_change', '與目前正式服務日期相同'),
    ('official_date_dates_not_canonical', '不能重複或留白'),
    ('official_date_service_days_changed', '天數與原紀錄不一致'),
    ('official_date_actual_start_change_unsupported', '不能改變實際開始日'),
    ('official_date_future_completed_service_blocked', '不能晚於今天'),
    ('official_date_occupancy_conflict', '其他案件的正式排班衝突'),
    ('official_date_version_conflict', '已被更新'),
])
def test_date_blockers_explain_the_cause_and_next_action(code, reason):
    def blocked():
        raise ValueError(code)
    with pytest.raises(HTTPException) as caught:
        _call(blocked)
    error = caught.value.detail['error']
    assert error['code'] == code
    assert reason in error['message']
    assert '請' in error['message']
