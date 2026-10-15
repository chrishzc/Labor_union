"""Case-shared weekly documents have no invented staff or assignment identity."""
from datetime import date, datetime
import json

import pytest
from subsystems.orders.order_information import build_weekly_information, bind_weekly_information
from subsystems.scheduling.proposed_weekly_service_projection import project_order_weekly_service
from subsystems.scheduling.matching_line_cards import candidate_contact_information_card
from subsystems.scheduling.candidate_contact_pool_workflow import _typed_candidate_projection

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
