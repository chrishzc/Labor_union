"""Public typed API contract for official date correction."""

from datetime import date, datetime, timedelta, timezone
from dataclasses import replace
from types import SimpleNamespace
import pytest
from fastapi import HTTPException

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import TypeAdapter, ValidationError

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.official_service_date_correction import (
    get_official_service_date_correction_workflow,
)
from api.routes.official_service_date_correction import (
    AttributionBatchApplyBody, AttributionBatchPreviewBody, AttributionApplyBody,
    AttributionPreviewBody, _call, router,
)
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.orders.official_service_date_correction_workflow import (
    AttributionDayMove,
    OfficialAssignmentDates,
    OfficialDateFacts,
    OfficialDateHistoryRecord,
    OfficialDateMonetaryImpactBlocked,
    OfficialServiceDateCorrectionWorkflow,
    ServiceAttributionChange,
    SubstituteRequestLink,
)


def test_repository_ignores_legacy_pay_marker_but_keeps_payroll_adjustment_blocker(monkeypatch):
    from unittest.mock import MagicMock
    from infrastructure.mysql import official_service_date_correction_repository as repository

    day = date(2026, 9, 19)
    monkeypatch.setattr(repository, "select_order", lambda *_args, **_kwargs: {
        "lifecycle_version": 1, "status": "訂單完成", "actual_start_date": day,
        "service_data_locked": True, "service_days": 1, "service_hours_per_day": 8,
    })
    monkeypatch.setattr(repository, "select_scheduling_aggregate", lambda *_args, **_kwargs: {
        "effective_generation_id": 11, "aggregate_version": 1,
    })
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.side_effect = [
        [{"id": 13, "staff_id": 7, "assignment_sequence": 1, "status": "completed",
          "floor_fee_allocated": 0, "staff_name": "月嫂"}],
        [{"assignment_id": 13, "staff_id": 7, "work_date": day,
          "is_work_day": True, "is_double_pay": True}],
    ]
    cursor.fetchone.side_effect = [
        {"generation_number": 1}, {"actual_end_date": day}, {"total": 1},
        {"total": 1}, {"total": 0}, None, None,
    ]

    facts = repository.MySqlOfficialServiceDateCorrectionRepository(connection).load("CASE-1")

    assert facts.monetary_blockers == ("payroll_adjustments",)
    statements = " ".join(call.args[0] for call in cursor.execute.call_args_list)
    assert "is_double_pay" not in statements
    assert "payroll_special_pay_events" not in statements


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


def test_batch_attribution_previews_and_commits_one_generation_for_four_staff(monkeypatch):
    from unittest.mock import MagicMock
    from subsystems.orders import official_service_date_correction_workflow as module

    days = tuple(date(2026, 9, day) for day in range(14, 20))
    facts = replace(_Workflow().query("ISSUE-346"), service_days=6, actual_start_date=days[0],
                    actual_end_date=days[-1], assignments=tuple(
                        OfficialAssignmentDates(13 + i, 7 + i, i + 1, "completed", days[i * 2:i * 2 + 2])
                        for i in range(3)
                    ))
    payroll = SimpleNamespace(blockers=(), actions=(), fingerprint=fingerprint_payload({"payroll": 1}),
                              payroll=SimpleNamespace(assignments=()))
    monkeypatch.setattr(module, "build_payroll_handover_impact", lambda *_args, **_kwargs: payroll)
    monkeypatch.setattr(module, "_scope_attribution_payroll", lambda value, _affected: value)
    repository = MagicMock()
    terms = SimpleNamespace(payroll=SimpleNamespace(source_terms=()), order=SimpleNamespace(terms=None))
    repository.load_attribution.return_value = facts, terms, (), (), module.AttributionFundingFacts()
    repository.replay_attribution.return_value = None
    unit_of_work = MagicMock()
    workflow = OfficialServiceDateCorrectionWorkflow(repository, unit_of_work)
    change = ServiceAttributionChange(0, 0, (), "confirmed", moves=(
        AttributionDayMove(13, 10, days[1], days[1]),
        AttributionDayMove(14, 10, days[3], days[3]),
    ))

    preview = workflow.preview_attribution(facts.case_no, change)
    assert {item.staff_id: item.service_dates for item in preview.scheduling.assignments} == {
        7: (days[0],), 8: (days[2],), 9: days[4:], 10: (days[1], days[3]),
    }
    repository.persist_attribution.assert_not_called()
    kwargs = dict(expected_order_version=1, expected_scheduling_version=1,
                  preview_fingerprint=preview.fingerprint.value, actor="admin",
                  reason="confirmed", idempotency_key="batch-1", correlation_id="correlation-1")
    with pytest.raises(ValueError, match="official_date_preview_stale"):
        workflow.apply_attribution(facts.case_no, replace(change, moves=change.moves[:1]), **kwargs)
    repository.persist_attribution.assert_not_called()
    receipt = workflow.apply_attribution(facts.case_no, change, **kwargs)
    repository.persist_attribution.assert_called_once()
    unit_of_work.return_value.__enter__.return_value.commit.assert_called_once()
    repository.replay_attribution.return_value = receipt
    assert workflow.apply_attribution(facts.case_no, change, **kwargs) == receipt
    repository.persist_attribution.assert_called_once()


def test_batch_request_contract_accepts_moves_and_rejects_mixed_request():
    body = {"scope": "served", "evidence": "confirmed", "moves": [
        {"source_assignment_id": 13, "staff_id": 8, "source_date": "2026-09-19",
         "replacement_date": "2026-09-19", "target_assignment_id": 14},
    ]}
    preview = TypeAdapter(AttributionPreviewBody | AttributionBatchPreviewBody)
    apply = TypeAdapter(AttributionApplyBody | AttributionBatchApplyBody)
    expected = (AttributionDayMove(13, 8, date(2026, 9, 19), date(2026, 9, 19), 14),)
    assert preview.validate_python(body).change().moves == expected
    assert apply.validate_python({**body, "reason": "confirmed", "expected_order_version": 1,
                                  "expected_scheduling_version": 1, "preview_fingerprint": "a" * 64}).change().moves == expected
    with pytest.raises(ValidationError):
        preview.validate_python({**body, "staff_id": 8})
    with pytest.raises(ValidationError):
        preview.validate_python({**body, "substitute_request_id": 41})
    linked = {**body, "scope": "upcoming", "substitute_request_id": 41, "expected_substitute_request_version": 3}
    assert preview.validate_python(linked).change().substitute == SubstituteRequestLink(41, 3)


def test_pending_substitute_attribution_validates_dates_and_closes_in_the_schedule_transaction(monkeypatch):
    from unittest.mock import MagicMock
    from zoneinfo import ZoneInfo
    from subsystems.orders import official_service_date_correction_workflow as module

    day = datetime.now(ZoneInfo("Asia/Taipei")).date() + timedelta(days=1)
    untouched = day + timedelta(days=1)
    facts = replace(_Workflow().query("ISSUE-346"), order_status="服務中", service_data_locked=False,
                    actual_start_date=day, actual_end_date=untouched, assignments=(
                        OfficialAssignmentDates(13, 7, 1, "active", (day, untouched)),
                    ))
    payroll = SimpleNamespace(blockers=(), actions=(), fingerprint=fingerprint_payload({"payroll": 1}),
                              payroll=SimpleNamespace(assignments=()))
    monkeypatch.setattr(module, "build_payroll_handover_impact", lambda *_args, **_kwargs: payroll)
    monkeypatch.setattr(module, "_scope_attribution_payroll", lambda value, _affected: value)
    operations = MagicMock()
    repository, current_unit = operations.repository, operations.unit
    units = MagicMock()
    units.return_value.__enter__.return_value = current_unit
    terms = SimpleNamespace(payroll=SimpleNamespace(source_terms=()), order=SimpleNamespace(terms=None))
    repository.load_attribution.return_value = facts, terms, (), (), module.AttributionFundingFacts()
    repository.load_substitute_request.return_value = (7, (day,))
    repository.replay_attribution.return_value = None
    workflow = OfficialServiceDateCorrectionWorkflow(repository, units)
    link = SubstituteRequestLink(41, 3)
    change = ServiceAttributionChange(0, 0, (), "月嫂已同意當日代班", scope="upcoming", substitute=link,
                                      moves=(AttributionDayMove(13, 8, day, day),))

    preview = workflow.preview_attribution(facts.case_no, change)
    assert {item.staff_id: item.service_dates for item in preview.scheduling.assignments} == {
        7: (untouched,), 8: (day,),
    }
    repository.load_substitute_request.assert_called_once_with(facts.case_no, link, lock=False)
    repository.persist_attribution.assert_not_called()
    repository.complete_substitute_request.assert_not_called()
    for invalid in (
        replace(change, scope="served"),
        replace(change, moves=(AttributionDayMove(13, 8, day, untouched),)),
        replace(change, moves=(AttributionDayMove(13, 7, day, day),)),
        replace(change, moves=(AttributionDayMove(13, 8, day, day), AttributionDayMove(13, 8, untouched, untouched))),
    ):
        with pytest.raises(ValueError, match="service_attribution_substitute_dates_conflict"):
            workflow.preview_attribution(facts.case_no, invalid)

    kwargs = dict(expected_order_version=1, expected_scheduling_version=1,
                  preview_fingerprint=preview.fingerprint.value, actor="admin",
                  reason="臨時代班", idempotency_key="batch-1", correlation_id="correlation-1")
    repository.load_substitute_request.side_effect = ValueError("service_attribution_substitute_request_conflict")
    with pytest.raises(ValueError, match="service_attribution_substitute_request_conflict"):
        workflow.apply_attribution(facts.case_no, change, **kwargs)
    repository.load_substitute_request.assert_called_with(facts.case_no, link, lock=True)
    repository.persist_attribution.assert_not_called()
    current_unit.commit.assert_not_called()
    repository.load_substitute_request.side_effect = None
    repository.complete_substitute_request.side_effect = RuntimeError("completion failed")
    with pytest.raises(RuntimeError, match="completion failed"):
        workflow.apply_attribution(facts.case_no, change, **kwargs)
    current_unit.commit.assert_not_called()
    repository.complete_substitute_request.side_effect = None
    operations.reset_mock()
    receipt = workflow.apply_attribution(facts.case_no, change, **kwargs)
    assert [step[0] for step in operations.mock_calls][-3:] == [
        "repository.persist_attribution", "repository.complete_substitute_request", "unit.commit",
    ]
    repository.complete_substitute_request.assert_called_once_with(facts.case_no, link, actor="admin", key="batch-1")
    repository.replay_attribution.return_value = receipt
    assert workflow.apply_attribution(facts.case_no, change, **kwargs) == receipt
    repository.complete_substitute_request.assert_called_once()


def test_mysql_substitute_attribution_queries_exact_pending_leave_without_candidate_or_group():
    from unittest.mock import MagicMock
    from infrastructure.mysql.service_start_repository import MySqlServiceStartRepository

    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = {"staff_id": 7, "execution_dates": {
        "kind": "leave-v1", "dates": [{"original_date": "2026-11-18"}, {"original_date": "2026-11-17"}],
    }}
    repository = MySqlServiceStartRepository(connection)
    assert repository.pending_leave_attribution("ISSUE-346", 41, 3, lock=True) == (
        7, (date(2026, 11, 17), date(2026, 11, 18)),
    )
    statement, params = cursor.execute.call_args.args
    assert params == (41, "ISSUE-346", 3)
    assert "id=%s AND case_no=%s AND aggregate_version=%s AND status='substitute_required'" in statement
    assert statement.endswith("FOR UPDATE")
    cursor.fetchone.return_value = None
    with pytest.raises(ValueError, match="service_attribution_substitute_request_conflict"):
        repository.pending_leave_attribution("WRONG-CASE", 41, 3, lock=False)


@pytest.mark.parametrize("lock", [False, True], ids=["preview", "apply"])
def test_attribution_rejects_retired_staff_even_when_staff_status_is_active(monkeypatch, lock):
    from unittest.mock import MagicMock
    from infrastructure.mysql import official_service_date_correction_repository as module

    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.side_effect = [None] * (2 if lock else 1) + [{"status": "active", "lifecycle_state": "retired"}]
    repository = module.MySqlOfficialServiceDateCorrectionRepository(connection)
    monkeypatch.setattr(repository, "load", lambda *_args, **_kwargs: _Workflow().query("ISSUE-346"))
    monkeypatch.setattr(module, "preflight_staff_ids", lambda *_args: (7,))
    monkeypatch.setattr(module, "load_preview_facts", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(module, "load_locked_facts", lambda *_args: None)
    day = date(2026, 9, 19)
    change = ServiceAttributionChange(0, 0, (), "confirmed", moves=(AttributionDayMove(13, 8, day, day),))

    with pytest.raises(ValueError, match="service_attribution_retired_staff_blocked"):
        repository.load_attribution("ISSUE-346", change, lock=lock)

    statement = cursor.execute.call_args.args[0]
    assert "staff_lifecycle_states" in statement
    assert statement.endswith("FOR UPDATE") is lock


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
    ("payroll_adjustments", "已有薪資調整分攤", "payroll"),
    ("subsidy_return", "已有補助退還義務", "subsidy"),
    ("source_rate_snapshot_missing_or_ambiguous", "薪資快照缺漏或不唯一", "case_profile"),
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
