"""Case-shared weekly documents have no invented staff or assignment identity."""
from datetime import date, datetime
import hashlib
import json
from types import SimpleNamespace

import pytest
from subsystems.orders.order_information import bind_weekly_information, build_candidate_information, build_weekly_information
from subsystems.scheduling import candidate_contact_pool_workflow as candidate_workflow
from infrastructure.line.messaging_api_adapter import _request_body
from subsystems.scheduling.proposed_weekly_service_projection import project_order_weekly_service
from subsystems.scheduling.matching_line_cards import candidate_contact_information_card
from subsystems.scheduling.candidate_contact_pool_workflow import _typed_candidate_projection
from domains.scheduling.matching_communication import MatchingDecisionNotReadyError
from infrastructure.mysql.matching_notification_repository import (
    MySqlMatchingNotificationRepository, _CONFIRMATION_SCHEDULE_FACTS_SQL,
    _CUSTOMER_PROFILE_FACTS_SQL, _CURRENT_RESUMES_SQL,
)


def test_candidate_changes_use_last_delivered_picture_snapshot():
    from dataclasses import asdict
    from subsystems.line.table_image_contracts import candidate_information_document

    sections = {
        1: ('服務約定', (('預計服務開始日', '2026-11-09'), ('每日服務時數', '9'))),
        2: ('照護需求', (('特殊照護時應注意事項', '早班'),)),
        3: ('每週服務說明', (('第一週', '五天'),)),
    }
    pictures = [{"document": asdict(candidate_information_document('CASE-1', kind, (section,)))}
                for kind, section in sections.items()]
    sections[1] = ('服務約定', (('預計服務開始日', '2026-11-30'), ('每日服務時數', '9')))
    sections[2] = ('照護需求', (('過敏體質', '花生'),))
    cursor = SimpleNamespace(execute=lambda _sql, args: assert_last_sent(args),
                             fetchone=lambda: {'payload_snapshot': {'_table_documents': pictures}})

    def assert_last_sent(args):
        assert args == (12, 'delivered')

    def preview(_case, _candidate, kind, **options):
        assert options == {'require_saved_dates': False}
        title, rows = sections[kind]
        return SimpleNamespace(line_sections=[SimpleNamespace(title=title, rows=rows)])

    events = [
        {'id': 1, 'event_key': 'delivered', 'occurred_at': datetime(2026, 11, 1), 'current_delivery_status': 'sent',
         'payload': {'information_package': True, 'line_task_id': 12}},
        {'id': 2, 'event_key': 'failed-resend', 'occurred_at': datetime(2026, 11, 2), 'current_delivery_status': 'failed',
         'payload': {'information_package': True, 'line_task_id': 13}},
    ]
    repository = SimpleNamespace(preview_candidate_information=preview)
    changes = candidate_workflow._sent_information_changes(cursor, repository, 'CASE-1', 4, events)
    assert [(item.field, item.before, item.after) for item in changes] == [
        ('預計開始日', '2026-11-09', '2026-11-30'),
        ('照護注意事項', '早班', None),
        ('過敏體質', None, '花生'),
    ]
    cursor.fetchone = lambda: {'payload_snapshot': {'type': 'flex'}}
    assert candidate_workflow._sent_information_changes(cursor, repository, 'CASE-1', 4, events) is None
    assert candidate_workflow._sent_information_changes(cursor, repository, 'CASE-1', 4, events[1:]) is None


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
    assert (preview["service_period_start"], preview["service_period_end"]) == (min(saved), max(saved))
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
    card = json.loads(candidate_contact_information_card("CASE-1", 3, tuple((s.title, s.rows) for s in common.line_sections), "ref"))
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


@pytest.fixture
def package_send(monkeypatch):
    start, end = date(2026, 10, 4), date(2026, 10, 5)
    recipient = "U" + "a" * 32
    facts = {"dates_saved": True, "recipient": recipient, "address": "測試市範例路 1 號"}
    queued, events = [], []

    class Cursor:
        lastrowid = 31

        def execute(self, sql, params):
            if sql.startswith("SELECT p.id AS pool_id"):
                self.row = dict(pool_id=9, staff_id=4, line_user_id=facts["recipient"], order_status="negotiating",
                    active_marker=1, candidate_status="active",
                    service_start_date=start, service_end_date=end, order_start_date=start, order_end_date=end)
            elif sql.startswith("SELECT id,pool_id"):
                self.row = next((event for event in events if event["event_key"] == params[0]), None)
            elif sql.startswith("SELECT id FROM caregiver_candidate_contact_events"):
                self.row = next((event for event in events if event["payload"].get("information_package")), None)
            elif sql.startswith("INSERT INTO caregiver_candidate_contact_events"):
                pool_id, candidate_id, event_type, event_key, actor, payload = params
                self.lastrowid = 31 + len(events)
                events.append(dict(id=self.lastrowid, pool_id=pool_id, candidate_id=candidate_id, event_type=event_type,
                    event_key=event_key, actor=actor, payload=json.loads(payload), occurred_at=datetime(2026, 10, 1)))
            else:
                raise AssertionError(sql)

        def fetchone(self):
            return self.row

    class Repository:
        def preview_candidate_information(self, case_no, candidate_id, kind, **_options):
            if kind == 3:
                data = weekly() if facts["dates_saved"] else {"date_basis": "planned", "warnings": (), "rows": ()}
                common = build_weekly_information(case_no, start, data)
                return bind_weekly_information(common, candidate_id, "月嫂甲", facts["recipient"],
                                               require_saved_dates=_options["require_saved_dates"])
            sheet_facts = {"case_no": case_no, "staff_name": "月嫂甲", "address": facts["address"]}
            return build_candidate_information(case_no, candidate_id, kind, sheet_facts, {}, facts["recipient"])

    def enqueue(request):
        queued.append(request)
        task_id = 41 + len(queued)
        return SimpleNamespace(task_id=SimpleNamespace(value=task_id))

    connection, cursor = object(), Cursor()
    monkeypatch.setattr(candidate_workflow, "MySqlOrderInformationRepository", lambda _: Repository())
    monkeypatch.setattr(candidate_workflow, "MySqlLineDeliveryTaskRepository", lambda _: SimpleNamespace(enqueue=enqueue))
    monkeypatch.setattr(candidate_workflow, "_run_in_application_uow", lambda operation: operation(connection, cursor))
    monkeypatch.setattr(candidate_workflow, "candidate_contact_open", lambda *_: True)
    monkeypatch.setattr(candidate_workflow, "_require_current_candidate", lambda *_: {})
    monkeypatch.setattr(candidate_workflow, "configured_message_payload", lambda _connection, _key, card, _values: card)
    monkeypatch.setattr("subsystems.line.table_image_messages.image_url", lambda _key, index, _now: f"https://example.test/image/{index}")

    def preview(*, resend=False):
        return candidate_workflow._information_package_preview(connection, "CASE-1", 3, resend=resend)[0]

    def send(fingerprint, key="initial-package", *, resend=False):
        return candidate_workflow.send_information("CASE-1", 3, "operator", key, fingerprint,
                                                   resend=resend)

    return SimpleNamespace(facts=facts, queued=queued, events=events, preview=preview, send=send)


def test_candidate_information_package_is_one_push_and_one_receipt(package_send):
    preview = package_send.preview()
    assert [document.info_type for document in preview.documents] == [1, 2, 3]
    assert ("服務地址", package_send.facts["address"]) in preview.documents[0].line_sections[0].rows
    receipt = package_send.send(preview.preview_fingerprint)
    assert receipt == {"status": "queued", "event_id": 31, "line_task_id": 42}
    assert package_send.send(preview.preview_fingerprint) == {**receipt, "status": "idempotent_replay"}
    recipient = package_send.facts["recipient"]
    package_send.facts["recipient"] = None
    assert package_send.send(preview.preview_fingerprint) == {**receipt, "status": "idempotent_replay"}
    package_send.facts["recipient"] = recipient
    with pytest.raises(ValueError, match="candidate_information_package_already_queued"):
        package_send.send(preview.preview_fingerprint, "another-key")

    (request,) = package_send.queued
    first_image, second_image, _ = json.loads(request.payload_json)["_table_documents"]
    assert any(row[index:index + 2] == ["服務地址", package_send.facts["address"]]
               for section in first_image["document"]["sections"] for row in section["rows"] for index in (0, 2))
    assert all(package_send.facts["address"] not in row
               for section in second_image["document"]["sections"] for row in section["rows"])
    payload = json.loads(_request_body(request))
    assert payload["to"] == package_send.facts["recipient"]
    (message,) = payload["messages"]
    assert message["contents"]["type"] == "carousel"
    images, reply = message["contents"]["contents"][:3], message["contents"]["contents"][3:]
    assert [image["hero"]["url"] for image in images] == [f"https://example.test/image/{index}" for index in range(3)]
    assert all("footer" not in image for image in images)
    (card,) = reply
    assert any(item.get("text") == "有疑問請直接聯絡工會。" for item in card["body"]["contents"])
    actions = [button["action"] for button in card["footer"]["contents"]]
    assert [action["label"] for action in actions] == list(preview.reply_actions)
    reference = hashlib.sha256(b"initial-package").hexdigest()
    assert actions[0]["data"] == f"candidate-contact:{reference}:willing"
    assert actions[1]["type"] == "postback"
    assert actions[1]["data"] == f"candidate-contact:{reference}:unwilling"
    assert [action["label"] for action in actions] == ["可以接案", "無法接案"]
    assert "_table_documents" not in message
    (event,) = package_send.events
    assert event["event_type"] == "info_1_sent"
    information = _typed_candidate_projection(package_send.events)[-1]
    assert information.information_1 is None
    assert information.package.event_id == receipt["event_id"]
    assert information.package.line_task_id == receipt["line_task_id"]


@pytest.mark.parametrize("previous", [False, True])
def test_resend_accepts_new_commands_without_previous_delivery_or_saved_dates(package_send, previous):
    if previous:
        package_send.send(package_send.preview().preview_fingerprint)
    package_send.facts["address"] = "測試市範例路 2 號"
    package_send.facts["dates_saved"] = False
    preview = package_send.preview(resend=True)
    second = package_send.send(preview.preview_fingerprint, "resend", resend=True)
    assert second["status"] == "queued"
    assert package_send.send(preview.preview_fingerprint, "resend", resend=True) == {
        **second, "status": "idempotent_replay",
    }
    third = package_send.send(preview.preview_fingerprint, "again", resend=True)
    assert third["event_id"] > second["event_id"]
    assert len(package_send.queued) == 2 + previous
    assert "測試市範例路 2 號" in package_send.queued[-1].payload_json
    assert "尚未保存" in package_send.queued[-1].payload_json
    if previous:
        assert "測試市範例路 1 號" in package_send.queued[0].payload_json


@pytest.mark.parametrize("change,value,error", [
    ("dates_saved", False, "candidate_weekly_service_dates_not_ready"),
    ("recipient", "U" + "b" * 32, "candidate_information_preview_stale"),
    ("address", "測試市範例路 2 號", "candidate_information_preview_stale"),
])
def test_candidate_package_rechecks_readiness_before_any_write(package_send, change, value, error):
    preview = package_send.preview()
    package_send.facts[change] = value
    if change == "dates_saved":
        blocked = package_send.preview()
        assert blocked.preview_fingerprint is None
        assert [document.info_type for document in blocked.documents] == [1, 2]
    with pytest.raises(ValueError, match=error):
        package_send.send(preview.preview_fingerprint)
    assert package_send.queued == package_send.events == []
