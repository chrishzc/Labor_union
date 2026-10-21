"""Case-shared weekly documents have no invented staff or assignment identity."""
from datetime import date, datetime
import json

import pytest
from subsystems.orders.order_information import build_weekly_information, bind_weekly_information
from subsystems.scheduling.proposed_weekly_service_projection import project_order_weekly_service
from subsystems.scheduling.matching_line_cards import candidate_contact_information_card
from subsystems.scheduling.candidate_contact_pool_workflow import _typed_candidate_projection
from domains.scheduling.matching_communication import MatchingDecisionNotReadyError
from infrastructure.mysql.matching_notification_repository import (
    MySqlMatchingNotificationRepository, _CONFIRMATION_SCHEDULE_FACTS_SQL,
    _CUSTOMER_PROFILE_FACTS_SQL, _CURRENT_RESUMES_SQL,
)


def confirmation_repository(monkeypatch, saved, periods, required_days=None):
    segments = tuple(dict(
        segment_id=index, staff_id=index, case_no="CASE-1", client_name="測試客戶",
        staff_name=f"測試月嫂{index}", assigned_start_date=start, assigned_end_date=end,
        service_hours_per_day=8.5, weekly_rest_days="[5,6]", custom_rest_dates="[]",
        service_days=len(saved) if required_days is None else required_days,
        service_dates=json.dumps(saved),
    ) for index, (start, end) in enumerate(periods, start=1))

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def execute(self, sql, params):
            if sql == _CONFIRMATION_SCHEDULE_FACTS_SQL:
                # The reader must retrieve all saved dates before allocating to caregivers.
                assert "BETWEEN segment.assigned_start_date" not in sql
                assert "orders.service_days" in sql
                self.rows = segments
            elif sql == _CUSTOMER_PROFILE_FACTS_SQL:
                self.rows = tuple({"id": row["staff_id"], "name": row["staff_name"]} for row in segments)
            elif sql == _CURRENT_RESUMES_SQL:
                self.rows = ()
            else:
                raise AssertionError(sql)

        def fetchall(self):
            return self.rows

    class Connection:
        def cursor(self):
            return Cursor()

    monkeypatch.setattr(
        "infrastructure.mysql.matching_notification_repository.MySqlOrderInformationRepository.preview_matching_plan_information",
        lambda *_args, **_kwargs: (),
    )
    return MySqlMatchingNotificationRepository(Connection())


@pytest.mark.parametrize("saved,periods", [
    (["2026-10-05", "2026-10-10", "2026-10-12"], [("2026-10-05", "2026-10-09")]),
    (["2026-10-12", "2026-10-17"], [("2026-10-05", "2026-10-09")]),
    (["2026-10-05", "2026-10-10", "2026-10-12"], [
        ("2026-10-05", "2026-10-10"), ("2026-10-11", "2026-10-12"),
    ]),
])
def test_customer_preview_and_send_use_all_saved_dates_including_weekends(monkeypatch, saved, periods):
    repository = confirmation_repository(monkeypatch, saved, periods)
    preview = repository.customer_confirmation_preview("CASE-1", 1)
    package = repository.customer_confirmation_package("CASE-1", 1)
    common = project_order_weekly_service(frozenset(date.fromisoformat(value) for value in saved), 8.5)

    assert preview["weekly_service_ready"] and not preview["blockers"]
    assert preview["weekly_service_rows"] == package["weekly_service_rows"]
    for key in ("weekly_work_days", "weekly_hours"):
        assert sum(row[key] for row in preview["weekly_service_rows"]) == sum(row[key] for row in common)
        for week in common:
            assert sum(row[key] for row in preview["weekly_service_rows"]
                       if row["week_start_date"] == week["week_start_date"]) == week[key]
    assert {row["staff_id"] for row in preview["weekly_service_rows"]} == set(range(1, len(periods) + 1))


@pytest.mark.parametrize("saved,periods,required,reason", [
    ([], [("2026-10-05", "2026-10-09")], 2, "請先試算並保存"),
    (["2026-10-05"], [("2026-10-05", "2026-10-09")], 2, "與約定天數不同"),
    (["2026-10-05", "2026-10-10", "2026-10-12"], [
        ("2026-10-05", "2026-10-09"), ("2026-10-12", "2026-10-12"),
    ], 3, "未完整且唯一涵蓋"),
    (["2026-10-05", "2026-10-10", "2026-10-12"], [
        ("2026-10-05", "2026-10-10"), ("2026-10-10", "2026-10-12"),
    ], 3, "未完整且唯一涵蓋"),
    (["2026-10-12"], [("2026-10-05", "2026-10-09"), ("2026-10-12", "2026-10-12")], 1, "未完整且唯一涵蓋"),
])
def test_customer_preview_and_send_reject_unsaved_incomplete_or_ambiguous_dates(monkeypatch, saved, periods, required, reason):
    repository = confirmation_repository(monkeypatch, saved, periods, required)
    preview = repository.customer_confirmation_preview("CASE-1", 1)
    assert not preview["weekly_service_ready"]
    assert preview["weekly_service_rows"] == () and preview["weekly_service_row_count"] == 0
    assert any(reason in blocker for blocker in preview["blockers"])
    with pytest.raises(MatchingDecisionNotReadyError, match=reason):
        repository.customer_confirmation_package("CASE-1", 1)

def weekly(basis="confirmed"):
    rows = project_order_weekly_service(frozenset((date(2026, 10, 4), date(2026, 10, 5))), 8.5)
    return {"rows": rows, "date_basis": basis, "warnings": [], "required_service_days": 2, "projected_service_days": 2}

def test_saved_weekly_document_is_common_but_preview_is_recipient_bound():
    common = build_weekly_information("CASE-1", date(2026, 10, 4), weekly())
    assert common.send_allowed
    assert len(common.line_sections[0].rows) == 2
    assert "8.5" in common.line_sections[0].rows[0][1]
    a = bind_weekly_information(common, 3, "月嫂甲", "UA")
    b = bind_weekly_information(common, 4, "月嫂乙", "UB")
    assert a.line_sections == b.line_sections and a.text == b.text
    assert a.preview_fingerprint != b.preview_fingerprint

@pytest.mark.parametrize("basis", ["draft", "planned"])
def test_unsaved_dates_cannot_be_sent(basis):
    common = build_weekly_information("CASE-1", date(2026, 10, 4), weekly(basis))
    assert not common.send_allowed
    with pytest.raises(ValueError, match="candidate_weekly_service_dates_not_ready"):
        bind_weekly_information(common, 3, "月嫂甲", "UA")

def test_third_document_does_not_create_willingness_callbacks_or_overwrite_other_records():
    common = build_weekly_information("CASE-1", date(2026, 10, 4), weekly())
    card = json.loads(candidate_contact_information_card("CASE-1", 3, tuple((s.title, s.rows) for s in common.line_sections), "ref", None))
    assert "postback" not in json.dumps(card)
    assert "願意承接" not in json.dumps(card, ensure_ascii=False)
    events = [dict(id=1, event_type="info_1_sent", occurred_at=datetime(2026, 10, 1), payload={"delivery_status": "sent", "line_task_id": 5}),
              dict(id=2, event_type="willingness_changed", occurred_at=datetime(2026, 10, 2), payload={"willingness": "willing"}),
              dict(id=3, event_type="info_3_sent", occurred_at=datetime(2026, 10, 3), payload={"delivery_status": "queued", "line_task_id": 6})]
    willingness, reason, event_id, information = _typed_candidate_projection(events)
    assert willingness == "willing" and event_id == 2 and reason is None
    assert information.information_1.event_id == 1 and information.information_2 is None
    assert information.information_3.event_id == 3 and information.information_3.line_task_id == 6

@pytest.mark.parametrize("kind", [1, 2, 3])
@pytest.mark.parametrize("actual,expected", [("pending", "queued"), ("processing", "pending"), ("sent", "sent"), ("failed", "failed"), ("retryable_failed", "retryable_failed"), ("cancelled", "cancelled")])
def test_current_delivery_uses_line_task_fact_and_retains_exact_receipt(kind, actual, expected):
    sent = datetime(2026, 10, 14, 9)
    event = dict(id=8, event_type=f"info_{kind}_sent", occurred_at=datetime(2026, 10, 13),
        payload={"delivery_status": "queued", "line_task_id": 19},
        current_delivery_status=actual, current_sent_at_utc=sent if actual == "sent" else None)
    _will, _reason, _event_id, information = _typed_candidate_projection([event])
    delivery = getattr(information, f"information_{kind}")
    assert delivery.status == expected and delivery.event_id == 8 and delivery.line_task_id == 19
    assert delivery.sent_at == (sent if actual == "sent" else event["occurred_at"])
    assert event["payload"]["delivery_status"] == "queued"  # original event stays immutable
