"""
File: test_group_helper_application.py
Description: 驗證案件群組月嫂小幫手五大流程、LIFF 合意延期預檢與提案、專員結案及零推播額度契約。
"""

from __future__ import annotations

from contextlib import nullcontext
from datetime import date, datetime, timezone
import json
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.dependencies.service_start import get_service_start_application
from api.routes import staff_leave_intake
from domains.line.delivery import LineMessageKind
from domains.line.identities import (
    LineGroupId,
    LineSourceIdentity,
    LineSourceType,
    LineUserId,
    LineWebhookEventId,
)
from domains.line.order_group import LineOrderGroupBindingStatus
from domains.scheduling.service_start import ServiceStartConflict, ServiceStartDecision
from infrastructure.mysql.customer_service_repository import _REMINDER_SOURCE_CASE
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.line.delivery_contracts import REPLY_ONLY_WEBHOOK_SOURCE
from subsystems.line.group_helper_application import (
    POSTPONEMENT_DRAFT_FAMILY,
    POSTPONEMENT_NOTICE_FAMILY,
    LineGroupHelperApplication,
)
from subsystems.line.service_start_messages import GROUP_ASSISTANCE_DIRECTIONS, HELPER_TEXT_DEFAULTS


def _make_inbox(
    event_id: str,
    payload: dict[str, Any],
    *,
    source_type: LineSourceType = LineSourceType.GROUP,
    group_id: str | None = "G-case-1",
    user_id: str = "U-staff-1",
    occurred_at: datetime | None = None,
) -> SimpleNamespace:
    event = SimpleNamespace(
        event_id=LineWebhookEventId(event_id),
        source=LineSourceIdentity(source_type, group_id, LineUserId(user_id)),
        occurred_at=occurred_at or datetime(2026, 6, 5, 2, 0, tzinfo=timezone.utc),
        payload_json=json.dumps(payload, ensure_ascii=False),
    )
    return SimpleNamespace(event=event)


class _FakeReceiptRepo:
    def __init__(self) -> None:
        self.items: dict[str, Any] = {}

    def get(self, key: Any) -> Any:
        return self.items.get(key.value)

    def append(self, receipt: Any) -> None:
        self.items[receipt.key.value] = receipt


class _FakeDeliveryRepo:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    def enqueue(self, req: Any) -> Any:
        self.requests.append(req)
        return req


class _FakeOrderGroupsRepo:
    def __init__(self, binding_status: LineOrderGroupBindingStatus = LineOrderGroupBindingStatus.ACTIVE) -> None:
        self.status = binding_status
        self.group_id = "G-case-1"
        self.version = 1

    def get_by_group(self, group_id: str) -> Any:
        if group_id != self.group_id:
            return None
        return SimpleNamespace(
            case_no="C-2026-01", status=self.status,
            group_id=LineGroupId(group_id), version=SimpleNamespace(value=self.version),
        )

    def get_invitation(self, case_no: str, *, lock: bool = False) -> Any:
        if case_no == "C-2026-01":
            return SimpleNamespace(binding=self.get_by_group(self.group_id))
        return None


class _FakeCustomerServiceRepo:
    def __init__(self) -> None:
        self.created: list[Any] = []
        self.resolved_cases: list[tuple[str, str, str]] = []

    def create_or_append(self, cmd: Any) -> int:
        self.created.append(cmd)
        return len(self.created)

    def resolve_open_for_case(self, case_no: str, actor_ref: str, event_id: str) -> None:
        self.resolved_cases.append((case_no, actor_ref, event_id))


class _FakeArrangement:
    def __init__(self, *, conflict: bool = False, conflict_message: str = "") -> None:
        self.conflict = conflict
        self.conflict_message = conflict_message or "此補班日已有其他案件排班或不可服務紀錄（檔期衝突），請重新與客戶協調其他日期！"
        self.preview_calls: list[tuple[str, int, int, tuple[Any, ...]]] = []

    def preview_leave_defer(self, case_no: str, staff_id: int, assignment_id: int, dates: tuple[Any, ...]) -> dict[str, Any]:
        self.preview_calls.append((case_no, staff_id, assignment_id, dates))
        if self.conflict:
            return {
                "conflict": True,
                "code": "staff_occupancy_conflict",
                "message": self.conflict_message,
                "total_service_days_conserved": True,
                "original_dates": [str(d.original_date) for d in dates],
                "new_dates": [str(d.new_date) for d in dates],
            }
        return {
            "conflict": False,
            "code": None,
            "message": "檔期無衝突，服務總天數與補助時數守恆，可送出延期確認。",
            "total_service_days_conserved": True,
            "original_dates": [str(d.original_date) for d in dates],
            "new_dates": [str(d.new_date) for d in dates],
        }


class _FakeServiceStartWorkflow:
    def __init__(self, *, arrangement: _FakeArrangement | None = None) -> None:
        self.arrangement = arrangement or _FakeArrangement()
        self.start_calls: list[tuple[Any, bool]] = []
        self.leave_calls: list[tuple[Any, bool]] = []
        self.start_result_status = "applied"
        self.leave_result_status = "applied"
        self.raise_on_start: ServiceStartConflict | None = None
        self.leave_eligible = True

    def selected_leave_case(self, staff_id: int, case_no: str, *, lock: bool = False) -> tuple[Any, Any]:
        items = ()
        if self.leave_eligible and staff_id == 7 and case_no == "C-2026-01":
            items = (SimpleNamespace(
                assignment_id=22, service_dates=tuple(f"2026-06-{day}" for day in range(12, 19)),
            ),)
        return items, None

    def submit_in_current_unit_of_work(self, submission: Any, *, enqueue_group_schedule: bool = True) -> Any:
        self.start_calls.append((submission, enqueue_group_schedule))
        if self.raise_on_start is not None:
            raise self.raise_on_start
        return SimpleNamespace(
            status=self.start_result_status,
            result={
                "actual_start_date": submission.start_date.isoformat(),
                "actual_end_date": "2026-07-04",
            },
        )

    def submit_leave_in_current_unit_of_work(self, submission: Any, *, enqueue_group_schedule: bool = True) -> Any:
        self.leave_calls.append((submission, enqueue_group_schedule))
        return SimpleNamespace(status=self.leave_result_status, result={})


class _FakeGroupHelperUoW:
    def __init__(
        self,
        *,
        is_started: bool = False,
        service_commenced: bool | None = None,
        schedule_rows: tuple[dict[str, Any], ...] = (),
        service_completed: bool = False,
        order_information_sections: tuple[Any, ...] | None = None,
        client_name: str | None = None,
    ) -> None:
        self._connection = None
        self.configurations = SimpleNamespace(
            get=lambda _kind: SimpleNamespace(revision=SimpleNamespace(value=0), definition_json="{}")
        )
        self.receipts = _FakeReceiptRepo()
        self.delivery_tasks = _FakeDeliveryRepo()
        self.order_groups = _FakeOrderGroupsRepo()
        self.customer_service = _FakeCustomerServiceRepo()
        self.service_start_workflow = _FakeServiceStartWorkflow()
        self._helper_proposals: dict[tuple[str, str], dict[str, Any]] = {}
        self.is_started = is_started
        self.service_commenced = is_started if service_commenced is None else service_commenced
        self.schedule_rows = schedule_rows
        self.service_completed = service_completed
        self.order_information_sections = order_information_sections
        self.client_name = client_name or "林小姐"

    def group_helper_context(self, case_no: str, user_id: str) -> dict[str, Any] | None:
        if case_no != "C-2026-01":
            return None
        ctx: dict[str, Any] = {
            "case_no": case_no,
            "order_status": "訂單完成" if self.service_completed else "matched" if not self.is_started else "in_service",
            "order_version": 3,
            "client_id": 88,
            "client_name": self.client_name,
            "service_days": 25,
            "service_type": "25日",
            "planned_start_date": date(2026, 6, 1),
            "actual_end_date": date(2026, 6, 25),
            "staff_id": 7,
            "staff_name": "王淑芬",
            "segment_id": 11,
            "assignment_id": 22,
            "scheduling_version": 4,
            "is_started": self.is_started,
            "has_confirmed_start": self.is_started,
            "service_commenced": self.service_commenced,
            "schedule_rows": self.schedule_rows,
            "is_staff": user_id == "U-staff-1",
            "can_open_satisfaction_survey": self.service_completed and user_id in {"U-staff-1", "U-staff-2"},
            "is_customer": user_id == "U-customer-1",
            "is_admin": user_id == "U-admin-1",
            "admin_user_id": 5 if user_id == "U-admin-1" else None,
        }
        if self.order_information_sections is not None:
            ctx["order_information_sections"] = self.order_information_sections
        return ctx


def _assert_all_reply_only(uow: _FakeGroupHelperUoW) -> None:
    assert uow.delivery_tasks.requests
    for req in uow.delivery_tasks.requests:
        assert req.source_aggregate_type == REPLY_ONLY_WEBHOOK_SOURCE


def _make_app(*, now: datetime | None = None, custom_aliases: dict[str, list[str]] | None = None) -> LineGroupHelperApplication:
    fixed_now = now or datetime(2026, 6, 5, 2, 0, tzinfo=timezone.utc)
    provider = None
    if custom_aliases is not None:
        provider = lambda: (1, custom_aliases)
    return LineGroupHelperApplication(
        lambda: fixed_now,
        aliases_provider=provider,
    )


@pytest.mark.parametrize(("confirmed_start", "completed", "user_id", "visible"), [
    (False, False, "U-staff-1", False),
    (True, False, "U-staff-1", False),
    (True, False, "U-customer-1", False),
    (False, True, "U-staff-1", True),
    (False, True, "U-staff-2", True),
    (False, True, "U-customer-1", False),
])
def test_satisfaction_survey_shows_for_staff_only_after_completion(confirmed_start, completed, user_id, visible) -> None:
    uow = _FakeGroupHelperUoW(is_started=confirmed_start, service_commenced=False, service_completed=completed)
    assert _make_app().handle_message(_make_inbox(
        "evt-survey-menu", {"message": {"type": "text", "text": "小幫手"}}, user_id=user_id,
    ), uow)
    card = json.loads(uow.delivery_tasks.requests[0].payload_json)
    actions = [row["action"]["data"] for row in card["contents"]["body"]["contents"] if "action" in row]
    assert ("group-helper:satisfaction-survey:C-2026-01" in actions) is visible
    if confirmed_start and not completed:
        assert "已約定開工" in json.dumps(card, ensure_ascii=False)
    if visible:
        assert "在案件群組回覆滿意度調查訊息" in json.dumps(card, ensure_ascii=False)
    _assert_all_reply_only(uow)


@pytest.mark.parametrize(("status", "has_agreed_date", "staff_reference", "visible"), [
    ("訂單成立", True, "7", False),
    ("訂單成立", False, "7", False),
    ("訂單成立", True, "8", False),
    ("訂單取消", True, "7", False),
    ("服務中", True, "7", False),
    ("訂單完成", True, "7", True),
])
def test_satisfaction_survey_runtime_context_uses_order_state_and_effective_staff(status, has_agreed_date, staff_reference, visible) -> None:
    single_rows = iter((
        {"status": status, "actual_start_date": date(2026, 6, 10) if has_agreed_date else None, "client_id": 88},
        {"1": 1} if has_agreed_date else None,
    ))
    row_sets = iter((
        [{"staff_id": 7, "staff_name": "月嫂七", "assignment_id": 1, "scheduling_version": 1}],
        [],
        [{"staff_id": 7, "is_work_day": True}],
        [{"subject_type": "staff", "subject_reference": staff_reference}],
    ))
    cursor = SimpleNamespace(execute=lambda *_: None, fetchone=lambda: next(single_rows), fetchall=lambda: next(row_sets))
    connection = SimpleNamespace(cursor=lambda: nullcontext(cursor))

    ctx = _make_app()._load_mysql_context(connection, object(), "C-2026-01", "U-staff-1")

    assert ctx["can_open_satisfaction_survey"] is visible


def test_satisfaction_survey_replies_to_same_group_with_saved_copy() -> None:
    from subsystems.line.webhook_identity_handlers import LineWebhookIdentityHandlers

    text = "謝謝您的使用，歡迎填寫問卷。\nhttps://survey.example.test/response"
    uow = _FakeGroupHelperUoW(service_completed=True)
    uow.configurations.get = lambda _kind: SimpleNamespace(revision=SimpleNamespace(value=1), definition_json=json.dumps({
        "templates": [{"id": "LINE-COPY-helper-satisfaction-survey", "name": "滿意度調查問卷",
                       "message_type": "text", "content": text, "enabled": True, "variables": []}],
    }))
    now = datetime(2026, 6, 5, 2, 0, tzinfo=timezone.utc)
    handlers = LineWebhookIdentityHandlers(lambda: now, None, group_helper_application=_make_app(now=now))
    assert handlers.handle_reply_postback(_make_inbox(
        "evt-survey", {"postback": {"data": "group-helper:satisfaction-survey:C-2026-01"}},
    ), uow)
    reply, = uow.delivery_tasks.requests
    assert reply.message_kind is LineMessageKind.TEXT and reply.recipient.identity.value == "G-case-1"
    assert json.loads(reply.payload_json) == {"type": "text", "text": text}
    _assert_all_reply_only(uow)


@pytest.mark.parametrize(("confirmed_start", "completed", "case_no", "group_id", "user_id"), [
    (False, False, "C-2026-01", "G-case-1", "U-staff-1"),
    (True, False, "C-2026-01", "G-case-1", "U-staff-1"),
    (True, True, "C-2026-01", "G-case-1", "U-customer-1"),
    (True, True, "C-2026-01", "G-case-1", "U-unassigned"),
    (True, True, "C-2026-02", "G-case-1", "U-staff-1"),
    (True, True, "C-2026-01", "G-unbound", "U-staff-1"),
])
def test_satisfaction_survey_rejects_unfinished_case_wrong_actor_or_forwarded_click(confirmed_start, completed, case_no, group_id, user_id) -> None:
    uow = _FakeGroupHelperUoW(is_started=confirmed_start, service_commenced=False, service_completed=completed)
    assert _make_app().handle_postback(_make_inbox(
        "evt-survey-rejected", {"postback": {"data": f"group-helper:satisfaction-survey:{case_no}"}},
        group_id=group_id, user_id=user_id,
    ), uow)
    assert not uow.delivery_tasks.requests


def test_satisfaction_survey_default_replies_plain_text_without_link() -> None:
    uow = _FakeGroupHelperUoW(service_completed=True)
    assert _make_app().handle_postback(_make_inbox(
        "evt-survey-unconfigured", {"postback": {"data": "group-helper:satisfaction-survey:C-2026-01"}},
    ), uow)
    reply, = uow.delivery_tasks.requests
    assert json.loads(reply.payload_json) == {"type": "text", "text": "感謝您使用工會的服務，歡迎提供滿意度回饋。"}
    _assert_all_reply_only(uow)


def test_menu_aliases_pre_start_shows_datetimepicker_and_post_start_hides_confirm_start() -> None:
    app = _make_app()
    for idx, alias in enumerate(("小幫手", "工會", "月嫂選單", "服務選單")):
        uow = _FakeGroupHelperUoW(is_started=False)
        handled = app.handle_message(
            _make_inbox(f"evt-menu-{idx}", {"type": "message", "message": {"type": "text", "text": alias}}),
            uow,
        )
        assert handled is True
        assert len(uow.delivery_tasks.requests) == 1
        req = uow.delivery_tasks.requests[0]
        assert req.message_kind is LineMessageKind.FLEX
        payload = json.loads(req.payload_json)
        items = payload["contents"]["body"]["contents"]
        assert items[0]["action"]["type"] == "datetimepicker"
        assert items[0]["action"]["mode"] == "date"
        assert items[0]["action"]["data"] == "group-helper:confirm-start-date:C-2026-01"
        guidance, = (item for item in items if item.get("text") == GROUP_ASSISTANCE_DIRECTIONS)
        assert "action" not in guidance
        assert payload["contents"]["header"]["contents"][0]["contents"][1]["contents"][0]["text"] == "待確認開工"
        _assert_all_reply_only(uow)

    # 正式開工後保留服務排程與留言指引，問卷等到完工才出現。
    started_uow = _FakeGroupHelperUoW(is_started=True)
    handled_started = app.handle_reply(
        _make_inbox("evt-menu-started", {"type": "message", "message": {"type": "text", "text": "小幫手"}}),
        started_uow,
    )
    assert handled_started is True
    started_payload = json.loads(started_uow.delivery_tasks.requests[0].payload_json)
    started_items = started_payload["contents"]["body"]["contents"]
    guidance, = (item for item in started_items if item.get("text") == GROUP_ASSISTANCE_DIRECTIONS)
    assert "action" not in guidance
    action_data = [item["action"].get("data", "") for item in started_items if "action" in item]
    assert not any(d.startswith("group-helper:confirm-start-date") for d in action_data)
    assert "group-helper:service-schedule" in action_data
    assert "group-helper:satisfaction-survey:C-2026-01" not in action_data
    assert started_payload["contents"]["header"]["contents"][0]["contents"][1]["contents"][0]["text"] == "正式服務中"
    _assert_all_reply_only(started_uow)


def test_non_staff_non_group_and_unbound_group_are_ignored() -> None:
    app = _make_app()
    uow = _FakeGroupHelperUoW(is_started=False)

    # Customer can open helper menu as well
    assert (
        app.handle_message(
            _make_inbox(
                "evt-cust-menu",
                {"type": "message", "message": {"type": "text", "text": "小幫手"}},
                user_id="U-customer-1",
            ),
            uow,
        )
        is True
    )
    assert len(uow.delivery_tasks.requests) == 1
    uow.delivery_tasks.requests.clear()

    # Stranger non-member ignored
    assert (
        app.handle_message(
            _make_inbox(
                "evt-stranger-menu",
                {"type": "message", "message": {"type": "text", "text": "小幫手"}},
                user_id="U-stranger",
            ),
            uow,
        )
        is False
    )
    # 1:1 non-group message ignored
    assert (
        app.handle_message(
            _make_inbox(
                "evt-1on1",
                {"type": "message", "message": {"type": "text", "text": "小幫手"}},
                source_type=LineSourceType.USER,
                group_id="U-staff-1",
            ),
            uow,
        )
        is False
    )
    # Unbound group ignored
    assert (
        app.handle_message(
            _make_inbox(
                "evt-unbound",
                {"type": "message", "message": {"type": "text", "text": "小幫手"}},
                group_id="G-other",
            ),
            uow,
        )
        is False
    )
    # Non-admin customer sending close command ignored
    assert (
        app.handle_message(
            _make_inbox(
                "evt-cust-close",
                {"type": "message", "message": {"type": "text", "text": "已處理結案"}},
                user_id="U-customer-1",
            ),
            uow,
        )
        is False
    )
    assert uow.delivery_tasks.requests == []


def test_workflow1_confirm_start_date_full_flow_zero_push() -> None:
    app = _make_app()
    uow = _FakeGroupHelperUoW(is_started=False)

    # 1. Caregiver picks date via native datetimepicker
    assert (
        app.handle_postback(
            _make_inbox(
                "evt-pick",
                {
                    "type": "postback",
                    "postback": {
                        "data": "group-helper:confirm-start-date:C-2026-01",
                        "params": {"date": "2026-06-10"},
                    },
                },
                user_id="U-staff-1",
            ),
            uow,
        )
        is True
    )
    assert uow._helper_proposals[("group_helper_start_proposal", "C-2026-01")]["start_date"] == "2026-06-10"
    assert uow._helper_proposals[("group_helper_start_proposal", "C-2026-01")]["proposed_by"] == "staff"
    assert uow.delivery_tasks.requests[-1].message_kind is LineMessageKind.FLEX
    assert "2026-06-10" in uow.delivery_tasks.requests[-1].payload_json
    assert "月嫂已發起" in uow.delivery_tasks.requests[-1].payload_json

    # 2. Caregiver clicking agree on their own proposal has no response (silent ignore to keep chat clean)
    pre_len = len(uow.delivery_tasks.requests)
    assert (
        app.handle_postback(
            _make_inbox(
                "evt-staff-agree",
                {"type": "postback", "postback": {"data": "confirm-start:agree"}},
                user_id="U-staff-1",
            ),
            uow,
        )
        is True
    )
    assert len(uow.delivery_tasks.requests) == pre_len
    assert uow.service_start_workflow.start_calls == []

    # 3. Customer clicks agree -> canonical writer with enqueue_group_schedule=False
    assert (
        app.handle_postback(
            _make_inbox(
                "evt-cust-agree",
                {"type": "postback", "postback": {"data": "confirm-start:agree"}},
                user_id="U-customer-1",
            ),
            uow,
        )
        is True
    )
    assert len(uow.service_start_workflow.start_calls) == 1
    submission, enqueue_flag = uow.service_start_workflow.start_calls[0]
    assert enqueue_flag is False
    assert submission.decision is ServiceStartDecision.ACCEPTED
    assert submission.start_date == date(2026, 6, 10)
    assert uow._helper_proposals[("group_helper_start_proposal", "C-2026-01")]["cleared"] is True
    assert "正式開工" in json.loads(uow.delivery_tasks.requests[-1].payload_json)["text"]

    # 4. Reselect clears active proposal and informs role
    assert (
        app.handle_postback(
            _make_inbox(
                "evt-reselect",
                {"type": "postback", "postback": {"data": "confirm-start:reselect"}},
                user_id="U-staff-1",
            ),
            uow,
        )
        is True
    )
    assert uow._helper_proposals[("group_helper_start_proposal", "C-2026-01")]["cleared"] is True
    reply_msg = json.loads(uow.delivery_tasks.requests[-1].payload_json)["text"]
    assert "月嫂" in reply_msg
    assert "已取消本次提議" in reply_msg
    _assert_all_reply_only(uow)


def test_customer_proposes_start_date_and_caregiver_agrees() -> None:
    app = _make_app()
    uow = _FakeGroupHelperUoW(is_started=False)

    # 1. Customer initiates proposal via date picker
    assert (
        app.handle_postback(
            _make_inbox(
                "evt-cust-pick",
                {
                    "type": "postback",
                    "postback": {
                        "data": "group-helper:confirm-start-date:C-2026-01",
                        "params": {"date": "2026-06-15"},
                    },
                },
                user_id="U-customer-1",
            ),
            uow,
        )
        is True
    )
    assert uow._helper_proposals[("group_helper_start_proposal", "C-2026-01")]["proposed_by"] == "customer"
    card_json = uow.delivery_tasks.requests[-1].payload_json
    assert "客戶已發起" in card_json
    assert "請月嫂確認" in card_json

    # 2. Customer clicking agree on their own proposal -> silent ignore
    pre_len = len(uow.delivery_tasks.requests)
    assert (
        app.handle_postback(
            _make_inbox(
                "evt-cust-agree-own",
                {"type": "postback", "postback": {"data": "confirm-start:agree"}},
                user_id="U-customer-1",
            ),
            uow,
        )
        is True
    )
    assert len(uow.delivery_tasks.requests) == pre_len
    assert uow.service_start_workflow.start_calls == []

    # 3. Caregiver agrees -> commits start date
    assert (
        app.handle_postback(
            _make_inbox(
                "evt-staff-agree-cust",
                {"type": "postback", "postback": {"data": "confirm-start:agree"}},
                user_id="U-staff-1",
            ),
            uow,
        )
        is True
    )
    assert len(uow.service_start_workflow.start_calls) == 1
    assert uow.service_start_workflow.start_calls[0][0].start_date == date(2026, 6, 15)
    _assert_all_reply_only(uow)


def test_pre_commenced_confirmed_schedule_keeps_confirm_start_and_hides_survey() -> None:
    app = _make_app()
    # is_started=True but service_commenced=False: schedule confirmed before actual start date
    uow = _FakeGroupHelperUoW(is_started=True, service_commenced=False)

    handled = app.handle_message(
        _make_inbox("evt-menu-pre-commenced", {"type": "message", "message": {"type": "text", "text": "小幫手"}}),
        uow,
    )
    assert handled is True
    payload = json.loads(uow.delivery_tasks.requests[0].payload_json)
    items = payload["contents"]["body"]["contents"]
    actions = [item["action"]["data"] for item in items if "action" in item]
    assert "group-helper:confirm-start-date:C-2026-01" in actions
    assert "group-helper:satisfaction-survey:C-2026-01" not in actions
    assert payload["contents"]["header"]["contents"][0]["contents"][1]["contents"][0]["text"] == "已約定開工"
    _assert_all_reply_only(uow)


@pytest.mark.parametrize("dedicated_liff", [False, True])
def test_workflow2_postponement_liff_conflict_and_in_group_agreement_zero_push(monkeypatch, dedicated_liff) -> None:
    if dedicated_liff:
        monkeypatch.setenv("LINE_STAFF_SCHEDULE_LIFF_ID", "synthetic-schedule-liff")
    else:
        monkeypatch.delenv("LINE_STAFF_SCHEDULE_LIFF_ID", raising=False)
    monkeypatch.setenv("LINE_LIFF_ID", "synthetic-shared-liff")
    app = _make_app()
    uow = _FakeGroupHelperUoW(is_started=True)

    # 1. Each menu opening returns the same case-specific LIFF entry.
    def open_entry(event_id):
        return app.handle_postback(
            _make_inbox(
                event_id,
                {"type": "postback", "postback": {"data": "group-helper:mutual-postponement"}},
                user_id="U-staff-1",
            ),
            uow,
        )

    assert open_entry("evt-postpone-open") is True
    entry_request = uow.delivery_tasks.requests[-1]
    assert entry_request.message_kind is LineMessageKind.FLEX
    card = json.loads(entry_request.payload_json)
    button, = card["contents"]["footer"]["contents"]
    assert button["style"] == "primary"
    assert button["action"]["type"] == "uri"
    assert button["action"]["label"] == "開啟延期申請"
    url = urlsplit(button["action"]["uri"])
    expected_path = "/synthetic-schedule-liff/" if dedicated_liff else "/synthetic-shared-liff/line-staff-schedule"
    assert (url.scheme, url.netloc, url.path) == ("https", "liff.line.me", expected_path)
    assert parse_qs(url.query) == {
        "case_no": ["C-2026-01"],
        "mode": ["postpone"], "group_reply": ["1"],
    }
    body = json.dumps(card["contents"]["body"], ensure_ascii=False)
    assert "C-2026-01" in body
    assert "可從原群組開啟同一張卡" in body
    assert "https://" not in body + card["altText"]
    assert open_entry("evt-postpone-reopen") is True
    assert json.loads(uow.delivery_tasks.requests[-1].payload_json) == card
    assert not uow._helper_proposals

    # 2. Occupancy conflict blocks card creation
    uow.service_start_workflow.arrangement.conflict = True
    assert (
        app.handle_message(
            _make_inbox(
                "evt-postpone-conflict",
                {"type": "message", "message": {"type": "text", "text": "雙方合意延期：2026-06-12→2026-06-15"}},
                user_id="U-staff-1",
            ),
            uow,
        )
        is True
    )
    assert ("group_helper_postpone_proposal", "C-2026-01") not in uow._helper_proposals
    assert "檔期衝突" in json.loads(uow.delivery_tasks.requests[-1].payload_json)["text"]

    # 3. Valid proposal without conflict emits Flex confirmation card
    uow.service_start_workflow.arrangement.conflict = False
    assert (
        app.handle_message(
            _make_inbox(
                "evt-postpone-ok",
                {"type": "message", "message": {"type": "text", "text": "雙方合意延期：2026-06-12→2026-06-15"}},
                user_id="U-staff-1",
            ),
            uow,
        )
        is True
    )
    saved = uow._helper_proposals[("group_helper_postpone_proposal", "C-2026-01")]
    assert saved["dates"] == [{"original_date": "2026-06-12", "new_date": "2026-06-15"}]
    assert uow.delivery_tasks.requests[-1].message_kind is LineMessageKind.FLEX
    approve = f"postponement:agree:{saved['proposal_ref']}"

    # 4. Caregiver clicking agree on their own proposal has no response (silent ignore to keep chat clean)
    pre_len = len(uow.delivery_tasks.requests)
    assert (
        app.handle_postback(
            _make_inbox(
                "evt-postpone-staff-agree",
                {"type": "postback", "postback": {"data": approve}},
                user_id="U-staff-1",
            ),
            uow,
        )
        is True
    )
    assert len(uow.delivery_tasks.requests) == pre_len
    assert uow.service_start_workflow.leave_calls == []
    for user_id, action in [
        ("U-admin-1", approve),
        ("U-admin-1", f"postponement:reject:{saved['proposal_ref']}"),
    ]:
        app.handle_postback(_make_inbox(
            f"unauthorized-decision-{user_id}-{action}",
            {"type": "postback", "postback": {"data": action}},
            user_id=user_id,
        ), uow)
        assert uow.service_start_workflow.leave_calls == []
        assert uow._helper_proposals[("group_helper_postpone_proposal", "C-2026-01")] == saved

    # 4b. Customer agrees -> canonical writer with enqueue_group_schedule=False
    assert (
        app.handle_postback(
            _make_inbox(
                "evt-postpone-agree",
                {"type": "postback", "postback": {"data": approve}},
                user_id="U-customer-1",
            ),
            uow,
        )
        is True
    )
    assert len(uow.service_start_workflow.leave_calls) == 1
    leave_cmd, enqueue_flag = uow.service_start_workflow.leave_calls[0]
    assert enqueue_flag is False
    assert leave_cmd.decision == "defer"
    assert leave_cmd.dates[0].original_date == date(2026, 6, 12)
    assert leave_cmd.dates[0].new_date == date(2026, 6, 15)
    assert uow._helper_proposals[("group_helper_postpone_proposal", "C-2026-01")]["cleared"] is True

    # A new multi-date proposal after the first decision can be rejected independently.
    assert (
        app.handle_message(
            _make_inbox(
                "evt-postpone-multi",
                {"type": "message", "message": {"type": "text", "text": "雙方合意延期：2026-06-14、2026-06-15→2026-06-20、2026-06-21"}},
                user_id="U-staff-1",
            ),
            uow,
        )
        is True
    )
    assert uow.delivery_tasks.requests[-1].message_kind is LineMessageKind.FLEX
    assert "2026-06-14、2026-06-15" in uow.delivery_tasks.requests[-1].payload_json
    multi_saved = uow._helper_proposals[("group_helper_postpone_proposal", "C-2026-01")]

    assert (
        app.handle_postback(
            _make_inbox(
                "evt-postpone-reject",
                {"type": "postback", "postback": {"data": f"postponement:reject:{multi_saved['proposal_ref']}"}},
                user_id="U-customer-1",
            ),
            uow,
        )
        is True
    )
    assert uow._helper_proposals[("group_helper_postpone_proposal", "C-2026-01")]["cleared"] is True
    assert "維持不變" in json.loads(uow.delivery_tasks.requests[-1].payload_json)["text"]
    _assert_all_reply_only(uow)


@pytest.mark.parametrize("has_line_actor", [True, False])
def test_caregiver_withdraws_only_own_latest_postponement(has_line_actor: bool) -> None:
    app = _make_app()
    uow = _FakeGroupHelperUoW(is_started=True)
    case_no = "C-2026-01"
    proposal_key = ("group_helper_postpone_proposal", case_no)
    current = {
        "proposal_ref": "a" * 32,
        "staff_id": 7,
        "group_binding_version": 1,
        "dates": [{"original_date": "2026-06-12", "new_date": "2026-06-15"}],
    }
    if has_line_actor:
        current["line_actor_fingerprint"] = fingerprint_payload({"line_user_id": "U-staff-1"}).value
    uow._helper_proposals[proposal_key] = current
    uow._helper_proposals[(POSTPONEMENT_DRAFT_FAMILY, case_no)] = {"draft_revision": 3}
    original_context = uow.group_helper_context

    def context(case: str, actor: str) -> dict[str, Any] | None:
        result = original_context(case, actor)
        if result is not None and actor in {"U-other-staff", "U-other-line"}:
            return {**result, "is_staff": True, "staff_id": 8 if actor == "U-other-staff" else 7}
        return result

    uow.group_helper_context = context

    def withdraw(actor: str, event_id: str, ref: str = current["proposal_ref"], group_id: str = "G-case-1") -> bool:
        return app.handle_postback(_make_inbox(
            event_id, {"type": "postback", "postback": {"data": f"postponement:reject:{ref}"}},
            user_id=actor, group_id=group_id,
        ), uow)

    assert withdraw("U-staff-1", "forwarded-card", group_id="G-other")
    for actor in ("U-admin-1", "U-other-staff", "U-outsider"):
        assert withdraw(actor, f"unauthorized-{actor}")
    if has_line_actor:
        assert withdraw("U-other-line", "different-line-user")
    assert not uow.delivery_tasks.requests
    assert uow._helper_proposals[proposal_key] == current

    assert withdraw("U-staff-1", "stale-card", ref="b" * 32)
    assert "已失效" in uow.delivery_tasks.requests[-1].payload_json
    assert uow._helper_proposals[proposal_key] == current

    assert withdraw("U-staff-1", "current-card")
    reply = uow.delivery_tasks.requests[-1]
    assert reply.recipient.identity.value == "G-case-1"
    assert "月嫂已撤回本次提議" in json.loads(reply.payload_json)["text"]
    assert uow._helper_proposals[proposal_key] == {"cleared": True, "draft_revision": 3}
    assert uow.service_start_workflow.leave_calls == []
    _assert_all_reply_only(uow)


def test_customer_blocked_from_initiating_mutual_postponement() -> None:
    app = _make_app()
    uow = _FakeGroupHelperUoW(is_started=True)

    # 1. Customer clicks mutual postponement button -> blocked with explicit message
    assert (
        app.handle_postback(
            _make_inbox(
                "evt-cust-postpone-open",
                {"type": "postback", "postback": {"data": "group-helper:mutual-postponement"}},
                user_id="U-customer-1",
            ),
            uow,
        )
        is True
    )
    reply_text = json.loads(uow.delivery_tasks.requests[-1].payload_json)["text"]
    assert reply_text == "「雙方合意延期」功能僅供月嫂操作，由月嫂開啟選擇請假與補班日期"

    # 2. Customer types text command -> blocked with explicit message
    assert (
        app.handle_message(
            _make_inbox(
                "evt-cust-postpone-text",
                {"type": "message", "message": {"type": "text", "text": "雙方合意延期：2026-06-12→2026-06-15"}},
                user_id="U-customer-1",
            ),
            uow,
        )
        is True
    )
    reply_text2 = json.loads(uow.delivery_tasks.requests[-1].payload_json)["text"]
    assert reply_text2 == "「雙方合意延期」功能僅供月嫂操作，由月嫂開啟選擇請假與補班日期"
    _assert_all_reply_only(uow)


def test_liff_leave_results_preview_and_propose_routes_enforce_conflict_and_zero_push(
    monkeypatch: Any,
) -> None:
    app = FastAPI()
    app.include_router(staff_leave_intake.router)
    arrangement = _FakeArrangement(conflict=False)
    fake_service_start = _FakeServiceStartWorkflow(arrangement=arrangement)
    app.dependency_overrides[get_service_start_application] = lambda: fake_service_start
    monkeypatch.setattr(
        staff_leave_intake,
        "_verified_staff_context",
        lambda _body: (LineUserId("U-staff-1"), {"staff_id": 7, "staff_name": "王淑芬"}),
    )

    saved_calls: list[tuple[str, str, str, dict[str, Any]]] = []
    committed: list[bool] = []
    uow_stub = _FakeGroupHelperUoW(is_started=True)
    uow_stub.commit = lambda: committed.append(True)
    uow_stub.service_start_workflow = fake_service_start
    uow_stub._connection = None
    monkeypatch.setattr(staff_leave_intake, "open_line_unit_of_work", lambda: nullcontext(uow_stub))

    def _build_on_line_connection(connection: Any) -> _FakeServiceStartWorkflow:
        assert connection is uow_stub._connection
        return fake_service_start

    monkeypatch.setattr(staff_leave_intake, "build_service_start_application", _build_on_line_connection)

    save_group_helper_proposal = staff_leave_intake.save_group_helper_proposal

    def _spy_save(_uow: Any, family: str, case_no: str, event_ref: str, payload: dict[str, Any]) -> dict[str, Any]:
        if family == POSTPONEMENT_DRAFT_FAMILY:
            saved_calls.append((family, case_no, event_ref, payload))
        return save_group_helper_proposal(_uow, family, case_no, event_ref, payload)

    monkeypatch.setattr(staff_leave_intake, "save_group_helper_proposal", _spy_save)

    client = TestClient(app)
    base_body = {
        "flow_id": "flow-999",
        "case_no": "C-2026-01",
        "assignment_id": 22,
        "dates": [{"original_date": "2026-06-12", "new_date": "2026-06-15"}],
    }

    fake_service_start.leave_eligible = False
    for suffix in ("preview", "propose"):
        denied = client.post(f"/api/v1/line/staff-self-service/leave-results/{suffix}", json=base_body)
        assert denied.status_code == 409
        assert denied.json()["detail"]["error"]["code"] == "leave_result_forbidden"
    assert saved_calls == [] and committed == [] and arrangement.preview_calls == []
    fake_service_start.leave_eligible = True

    # 1. Conflict detected in /preview and blocked with 409 in /propose
    arrangement.conflict = True
    preview_res = client.post("/api/v1/line/staff-self-service/leave-results/preview", json=base_body)
    assert preview_res.status_code == 200
    assert preview_res.json()["data"]["conflict"] is True
    assert "檔期衝突" in preview_res.json()["data"]["message"]

    propose_conflict_res = client.post("/api/v1/line/staff-self-service/leave-results/propose", json=base_body)
    assert propose_conflict_res.status_code == 409
    assert propose_conflict_res.json()["detail"]["error"]["code"] == "staff_occupancy_conflict"
    assert saved_calls == []
    assert committed == []

    # 2. Non-conflicted 1-day /propose persists proposal, returns group_message, 0 Push
    arrangement.conflict = False
    propose_ok_res = client.post("/api/v1/line/staff-self-service/leave-results/propose", json=base_body)
    assert propose_ok_res.status_code == 200
    ok_data = propose_ok_res.json()["data"]
    assert ok_data["conflict"] is False
    assert ok_data["total_service_days_conserved"] is True
    assert ok_data["group_record_queued"] is False
    assert ok_data["group_message"] == (
        "雙方合意延期申請已送出，請確認是否同意日期調整。\n提案編號：C-2026-01-1"
    )
    assert len(saved_calls) == 1
    assert saved_calls[0][0] == POSTPONEMENT_DRAFT_FAMILY
    assert saved_calls[0][1] == "C-2026-01"
    assert committed == [True]
    assert uow_stub.delivery_tasks.requests == []
    active_key = ("group_helper_postpone_proposal", "C-2026-01")
    assert active_key not in uow_stub._helper_proposals

    helper = _make_app()
    single = saved_calls[0][3]
    assert uow_stub._helper_proposals[(POSTPONEMENT_NOTICE_FAMILY, "C-2026-01", "1")] == {
        "proposal_ref": single["proposal_ref"],
    }
    message = {"type": "message", "message": {"type": "text", "text": ok_data["group_message"]}}
    foreign_notice = ok_data["group_message"].replace("C-2026-01-1", "C-2026-02-1")
    assert not helper.handle_message(_make_inbox("foreign-case-notice", {
        "type": "message", "message": {"type": "text", "text": foreign_notice},
    }), uow_stub)
    assert active_key not in uow_stub._helper_proposals
    assert not uow_stub.delivery_tasks.requests
    uow_stub.order_groups.group_id = "G-replacement"
    uow_stub.order_groups.version = 2
    assert helper.handle_message(_make_inbox("replaced-group-send", message, group_id="G-replacement"), uow_stub)
    assert active_key not in uow_stub._helper_proposals
    assert uow_stub.delivery_tasks.requests == []
    uow_stub.order_groups.group_id = "G-case-1"
    uow_stub.order_groups.version = 1
    fake_service_start.leave_eligible = False
    assert helper.handle_message(_make_inbox("now-ineligible-group-send", message), uow_stub)
    assert active_key not in uow_stub._helper_proposals
    assert uow_stub.delivery_tasks.requests[-1].message_kind is LineMessageKind.TEXT
    fake_service_start.leave_eligible = True
    assert helper.handle_message(_make_inbox("single-group-send", message), uow_stub)
    assert helper.handle_message(_make_inbox("single-duplicate-send", message), uow_stub)
    card, = (req for req in uow_stub.delivery_tasks.requests if req.message_kind is LineMessageKind.FLEX)
    assert card.recipient.identity.value == "G-case-1"
    assert card.correlation_id.value == "line-event:single-group-send"
    assert f"postponement:agree:{single['proposal_ref']}" in card.payload_json

    # The menu stays an edit entry even while a confirmation card is pending.
    assert helper.handle_postback(_make_inbox("edit-group-proposal", {
        "type": "postback", "postback": {"data": "group-helper:mutual-postponement"},
    }), uow_stub)
    assert "mode=postpone" in uow_stub.delivery_tasks.requests[-1].payload_json

    delayed_res = client.post("/api/v1/line/staff-self-service/leave-results/propose", json={
        **base_body, "dates": [{"original_date": "2026-06-12", "new_date": "2026-06-19"}],
    })
    assert delayed_res.status_code == 200
    delayed_message = {"type": "message", "message": {"type": "text", "text": delayed_res.json()["data"]["group_message"]}}
    assert not helper.handle_message(_make_inbox("delayed-wrong-group", delayed_message, group_id="G-other"), uow_stub)
    assert uow_stub._helper_proposals[active_key]["proposal_ref"] == single["proposal_ref"]

    # Multi-day submit uses the same single-step group trigger and replaces the pending proposal.
    multi_body = {
        **base_body,
        "dates": [
            {"original_date": "2026-06-12", "new_date": "2026-06-20"},
            {"original_date": "2026-06-13", "new_date": "2026-06-21"},
        ],
    }
    multi_res = client.post("/api/v1/line/staff-self-service/leave-results/propose", json=multi_body)
    assert multi_res.status_code == 200
    multi_message = multi_res.json()["data"]["group_message"]
    multi = saved_calls[-1][3]
    assert len(multi["dates"]) == 2
    assert multi["proposal_ref"] != single["proposal_ref"]
    assert uow_stub._helper_proposals[active_key]["proposal_ref"] == single["proposal_ref"]
    assert helper.handle_message(_make_inbox("multi-group-send", {
        "type": "message", "message": {"type": "text", "text": multi_message},
    }), uow_stub)
    card = uow_stub.delivery_tasks.requests[-1]
    assert card.message_kind is LineMessageKind.FLEX
    assert f"postponement:agree:{multi['proposal_ref']}" in card.payload_json
    assert card.recipient.identity.value == "G-case-1"
    assert helper.handle_message(_make_inbox("delayed-after-new-card", delayed_message), uow_stub)
    assert "已失效" in uow_stub.delivery_tasks.requests[-1].payload_json
    assert uow_stub._helper_proposals[active_key]["proposal_ref"] == multi["proposal_ref"]

    for index, old_action in enumerate(("postponement:agree", f"postponement:agree:{single['proposal_ref']}", f"postponement:reject:{single['proposal_ref']}")):
        assert helper.handle_postback(_make_inbox(f"old-card-{index}", {
            "type": "postback", "postback": {"data": old_action},
        }, user_id="U-customer-1"), uow_stub)
        assert "已失效" in uow_stub.delivery_tasks.requests[-1].payload_json
        assert not fake_service_start.leave_calls
    assert helper.handle_postback(_make_inbox("new-card", {
        "type": "postback", "postback": {"data": f"postponement:agree:{multi['proposal_ref']}"},
    }, user_id="U-customer-1"), uow_stub)
    command, push_schedule = fake_service_start.leave_calls[0]
    assert len(command.dates) == 2 and push_schedule is False
    assert helper.handle_message(_make_inbox("delayed-after-approval", delayed_message), uow_stub)
    assert uow_stub._helper_proposals[active_key]["cleared"] is True
    assert len(fake_service_start.leave_calls) == 1

    compatible = client.post("/api/v1/line/staff-self-service/leave-results/propose", json={
        **base_body, "dates": [{"original_date": "2026-06-12", "new_date": "2026-06-22"}],
    })
    assert compatible.status_code == 200
    legacy_ref = saved_calls[-1][3]["proposal_ref"]
    assert helper.handle_message(_make_inbox("legacy-group-send", {
        "type": "message", "message": {"type": "text", "text": f"雙方合意延期 提案 {legacy_ref}"},
    }), uow_stub)
    assert uow_stub._helper_proposals[active_key]["proposal_ref"] == legacy_ref
    assert f"postponement:agree:{legacy_ref}" in uow_stub.delivery_tasks.requests[-1].payload_json
    _assert_all_reply_only(uow_stub)


@pytest.mark.parametrize("receipt_format", ["numbered", "opaque_draft", "legacy_active"])
def test_liff_postponement_replays_original_result_after_proposal_changes(
    monkeypatch: Any, receipt_format: str,
) -> None:
    arrangement = _FakeArrangement()
    application = _FakeServiceStartWorkflow(arrangement=arrangement)
    committed: list[bool] = []
    uow = SimpleNamespace(
        _connection=None,
        _helper_proposals={},
        receipts=_FakeReceiptRepo(),
        order_groups=_FakeOrderGroupsRepo(),
        commit=lambda: committed.append(True),
    )
    monkeypatch.setattr(staff_leave_intake, "open_line_unit_of_work", lambda: nullcontext(uow))
    monkeypatch.setattr(staff_leave_intake, "build_service_start_application", lambda _connection: application)
    staff = {"staff_id": 7}
    monkeypatch.setattr(staff_leave_intake, "_verified_staff_context", lambda _body: (LineUserId("U-staff-1"), staff))
    dates = [
        {"original_date": "2026-06-12", "new_date": "2026-06-15"},
        {"original_date": "2026-06-13", "new_date": "2026-06-16"},
    ]
    body = {
        "flow_id": "flow-999",
        "case_no": "C-2026-01",
        "assignment_id": 22,
        "dates": dates,
        "idempotency_key": "staff-proposal-1",
    }
    family = "group_helper_postpone_proposal"

    def propose(payload: dict[str, Any]) -> dict[str, Any]:
        request = staff_leave_intake.StaffLeaveDeferProposeRequest.model_validate(payload)
        return staff_leave_intake.propose_leave_defer(request).model_dump()

    original = propose(body)
    if receipt_format != "numbered":
        draft = uow._helper_proposals[POSTPONEMENT_DRAFT_FAMILY, body["case_no"]]
        historical_payload = {key: value for key, value in draft.items() if key != "group_message"}
        uow._helper_proposals.clear()
        uow.receipts.items.clear()
        if receipt_format == "legacy_active":
            historical_payload.pop("liff_result")
            staff_leave_intake.save_group_helper_proposal(
                uow, family, body["case_no"], body["idempotency_key"], historical_payload,
            )
        else:
            staff_leave_intake.save_group_helper_proposal(
                uow, POSTPONEMENT_DRAFT_FAMILY, body["case_no"], draft["proposal_ref"], historical_payload,
            )
        original["data"]["group_message"] = f"雙方合意延期 提案 {draft['proposal_ref']}"
    staff_leave_intake.save_group_helper_proposal(uow, family, body["case_no"], "group-confirmed", {"cleared": True})
    arrangement.conflict = True

    assert propose({**body, "dates": list(reversed(dates))}) == original
    changed_dates = [dates[0], {**dates[1], "new_date": "2026-06-17"}]
    with pytest.raises(HTTPException) as conflict:
        propose({**body, "dates": changed_dates})
    assert conflict.value.status_code == 409
    assert conflict.value.detail["error"]["code"] == "staff_leave_proposal_idempotency_conflict"

    staff["staff_id"] = 8
    with pytest.raises(HTTPException) as other_staff:
        propose(body)
    assert other_staff.value.status_code == 409
    assert len(arrangement.preview_calls) == 1
    assert committed == [True]
    assert len(uow.receipts.items) == (3 if receipt_format == "numbered" else 2)
    assert uow._helper_proposals[family, body["case_no"]] == {"cleared": True}


def test_workflow3_service_schedule_pre_start_and_post_start_progress() -> None:
    app = _make_app(now=datetime(2026, 6, 5, 2, 0, tzinfo=timezone.utc))

    # Pre-start: explicit notice that start date is unconfirmed (expected schedule only)
    pre_uow = _FakeGroupHelperUoW(is_started=False)
    assert (
        app.handle_postback(
            _make_inbox("evt-sched-pre", {"type": "postback", "postback": {"data": "group-helper:service-schedule"}}),
            pre_uow,
        )
        is True
    )
    pre_text = json.loads(pre_uow.delivery_tasks.requests[0].payload_json)["text"]
    assert "尚未確認開工日" in pre_text
    assert "預期排程" in pre_text
    _assert_all_reply_only(pre_uow)

    # Post-start: served count <= today (2026-06-05 -> 4 served days out of 6 work days) + rest days
    schedule_rows = (
        {"work_date": date(2026, 6, 1), "is_work_day": 1},
        {"work_date": date(2026, 6, 2), "is_work_day": 1},
        {"work_date": date(2026, 6, 3), "is_work_day": 1},
        {"work_date": date(2026, 6, 4), "is_work_day": 0},
        {"work_date": date(2026, 6, 5), "is_work_day": 1},
        {"work_date": date(2026, 6, 6), "is_work_day": 1},
        {"work_date": date(2026, 6, 7), "is_work_day": 1},
    )
    post_uow = _FakeGroupHelperUoW(is_started=True, schedule_rows=schedule_rows)
    assert (
        app.handle_postback(
            _make_inbox("evt-sched-post", {"type": "postback", "postback": {"data": "group-helper:service-schedule"}}),
            post_uow,
        )
        is True
    )
    post_req = post_uow.delivery_tasks.requests[0]
    assert post_req.message_kind is LineMessageKind.FLEX
    post_payload = json.loads(post_req.payload_json)
    assert post_payload["type"] == "flex"
    assert "排班日曆" in post_payload["altText"]
    card_str = json.dumps(post_payload, ensure_ascii=False)
    assert "已服務 4 天／總計 6 天（剩餘 2 天）" in card_str
    assert "排休日：2026-06-04" in card_str
    assert "2026 年 6 月" in card_str
    _assert_all_reply_only(post_uow)


def test_workflow3_service_schedule_multi_caregivers_calendar_card() -> None:
    app = _make_app(now=datetime(2026, 6, 5, 2, 0, tzinfo=timezone.utc))
    schedule_rows = (
        {"work_date": date(2026, 6, 1), "is_work_day": 1, "staff_name": "林月嫂"},
        {"work_date": date(2026, 6, 2), "is_work_day": 1, "staff_name": "林月嫂"},
        {"work_date": date(2026, 6, 3), "is_work_day": 1, "staff_name": "林月嫂"},
        {"work_date": date(2026, 6, 4), "is_work_day": 0},
        {"work_date": date(2026, 6, 5), "is_work_day": 1, "staff_name": "張月嫂"},
        {"work_date": date(2026, 6, 6), "is_work_day": 1, "staff_name": "張月嫂"},
        {"work_date": date(2026, 6, 7), "is_work_day": 1, "staff_name": "張月嫂"},
    )
    post_uow = _FakeGroupHelperUoW(is_started=True, schedule_rows=schedule_rows)
    assert (
        app.handle_postback(
            _make_inbox("evt-sched-multi", {"type": "postback", "postback": {"data": "group-helper:service-schedule"}}),
            post_uow,
        )
        is True
    )
    req = post_uow.delivery_tasks.requests[0]
    assert req.message_kind is LineMessageKind.FLEX
    payload = json.loads(req.payload_json)
    card_str = json.dumps(payload, ensure_ascii=False)
    assert "林月嫂 (3天)" in card_str
    assert "張月嫂 (3天)" in card_str
    assert "休息日 (1天)" in card_str
    assert "#10B981" in card_str  # 林月嫂
    assert "#3B82F6" in card_str  # 張月嫂
    assert "#FEF3C7" in card_str  # 休息日

    def _verify_flex_boxes(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "box":
                assert "contents" in node, f"Box missing contents: {node}"
                assert node.get("alignItems") != "baseline", f"Invalid alignItems in box: {node}"
            for v in node.values():
                _verify_flex_boxes(v)
        elif isinstance(node, list):
            for item in node:
                _verify_flex_boxes(item)

    _verify_flex_boxes(payload)
    _assert_all_reply_only(post_uow)


def test_workflow4_old_staff_assistance_replies_in_group_without_mutating_tickets() -> None:
    assert "group-helper-assistance:" in _REMINDER_SOURCE_CASE
    assert "'service'" in _REMINDER_SOURCE_CASE

    app = _make_app(custom_aliases={"staff_assistance_close": ["本案已結案"]})
    uow = _FakeGroupHelperUoW(is_started=True)

    assert (
        app.handle_postback(
            _make_inbox("evt-assist-1", {"type": "postback", "postback": {"data": "group-helper:staff-assistance"}}),
            uow,
        )
        is True
    )
    assert uow.customer_service.created == []
    [reply] = uow.delivery_tasks.requests
    assert json.loads(reply.payload_json)["text"] == GROUP_ASSISTANCE_DIRECTIONS

    assert (
        app.handle_message(
            _make_inbox(
                "evt-close-1",
                {"type": "message", "message": {"type": "text", "text": "本案已結案"}},
                user_id="U-admin-1",
            ),
            uow,
        )
        is False
    )
    assert uow.customer_service.resolved_cases == []
    assert uow.delivery_tasks.requests == [reply]
    _assert_all_reply_only(uow)


def test_workflow5_guidelines_and_faq_replies() -> None:
    app = _make_app()
    uow = _FakeGroupHelperUoW(is_started=False)

    assert (
        app.handle_postback(
            _make_inbox("evt-guide", {"type": "postback", "postback": {"data": "group-helper:group-guidelines"}}),
            uow,
        )
        is True
    )
    assert uow.delivery_tasks.requests[-1].message_kind is LineMessageKind.FLEX

    for topic in ("ingredients", "hours", "subsidy"):
        assert (
            app.handle_postback(
                _make_inbox(f"evt-faq-{topic}", {"type": "postback", "postback": {"data": f"group-faq:{topic}"}}),
                uow,
            )
            is True
        )
        reply_text = json.loads(uow.delivery_tasks.requests[-1].payload_json)["text"]
        assert reply_text == HELPER_TEXT_DEFAULTS[f"helper-faq-{topic}"]

    _assert_all_reply_only(uow)


def test_webhook_identity_handlers_routes_group_helper_without_name_error() -> None:
    from subsystems.line.webhook_identity_handlers import LineWebhookIdentityHandlers

    fixed_now = datetime(2026, 6, 5, 2, 0, tzinfo=timezone.utc)
    helper = _make_app(now=fixed_now)
    handlers = LineWebhookIdentityHandlers(
        lambda: fixed_now,
        lambda flow_id, purpose: f"https://example.test/{purpose}?flow_id={flow_id}",
        group_helper_application=helper,
    )
    uow = _FakeGroupHelperUoW(is_started=False)

    handlers.handle_message(
        _make_inbox("evt-wh-msg", {"type": "message", "message": {"type": "text", "text": "小幫手"}}),
        uow,
    )
    handlers.handle_reply_message(
        _make_inbox("evt-wh-reply-msg", {"type": "message", "message": {"type": "text", "text": "小幫手"}}),
        uow,
    )
    handlers.handle_postback(
        _make_inbox("evt-wh-pb", {"type": "postback", "postback": {"data": "group-helper:group-guidelines"}}),
        uow,
    )
    handlers.handle_reply_postback(
        _make_inbox("evt-wh-reply-pb", {"type": "postback", "postback": {"data": "group-faq:subsidy"}}),
        uow,
    )
    assert len(uow.delivery_tasks.requests) == 4
    _assert_all_reply_only(uow)


def test_group_helper_menu_includes_case_information_action() -> None:
    app = _make_app()
    uow = _FakeGroupHelperUoW(is_started=False)
    assert app.handle_reply(
        _make_inbox("evt-menu-case-info", {"type": "message", "message": {"type": "text", "text": "小幫手"}}),
        uow,
    ) is True
    payload = json.loads(uow.delivery_tasks.requests[0].payload_json)
    items = payload["contents"]["body"]["contents"]
    actions = [item["action"] for item in items if "action" in item]
    info_action = next((a for a in actions if a.get("data") == "group-helper:case-information"), None)
    assert info_action is not None
    assert info_action.get("label") == "案件資訊"
    _assert_all_reply_only(uow)


def test_group_helper_case_information_postback_and_text_reply() -> None:
    from subsystems.orders.order_information import CandidateInformationSection

    sample_sections = (
        CandidateInformationSection(
            "服務約定",
            (
                ("案件編號 (case_no)", "C-2026-01"),
                ("服務人員姓名", "王淑芬"),
                ("客戶名稱", "林小姐"),
                ("預計服務開始日", "2026-06-01"),
                ("預計服務結束日", "2026-06-25"),
                ("每日服務時段", "09:00–17:30"),
                ("每日服務時數", "8.0"),
                ("服務方式", "週休2日"),
                ("希望服務天數", "25"),
                ("服務地址", "新竹市東區範例路 1 號"),
                ("下廚需求", "需要下廚"),
                ("胎數", "單胞胎"),
            ),
        ),
        CandidateInformationSection(
            "客戶付款約定",
            (
                ("訂金金額", "NT$ 6,000"),
                ("預計訂金繳款日", "2026-05-15"),
                ("第一期金額", "NT$ 12,000"),
                ("預計第一期繳款日", "2026-06-01"),
                ("第二期金額", "NT$ 0"),
                ("預計第二期繳款日", "不適用"),
                ("樓層費", "NT$ 0"),
                ("樓層費預計繳款日", "不適用"),
                ("客戶應付總額", "NT$ 18,000"),
            ),
        ),
        CandidateInformationSection(
            "其他約定",
            (
                ("特殊休假日", "待確認"),
                ("注意事項", "希望人好相處的~謝謝"),
            ),
        ),
    )

    app = _make_app()
    uow = _FakeGroupHelperUoW(is_started=False, order_information_sections=sample_sections)

    # 1. 客戶點擊 Postback 按鈕
    assert (
        app.handle_postback(
            _make_inbox(
                "evt-case-info-pb",
                {"type": "postback", "postback": {"data": "group-helper:case-information"}},
                user_id="U-customer-1",
            ),
            uow,
        )
        is True
    )
    req = uow.delivery_tasks.requests[-1]
    assert req.message_kind is LineMessageKind.FLEX
    payload = json.loads(req.payload_json)
    assert payload["type"] == "flex"
    assert "C-2026-01" in payload["altText"]
    bubble = payload["contents"]
    assert bubble["header"]["contents"][1]["text"] == "服務條件與費用約定"
    assert "王淑芬" in bubble["header"]["contents"][2]["text"]

    body_nodes = bubble["body"]["contents"]
    section_titles = [node["contents"][1]["text"] for node in body_nodes if node.get("layout") == "horizontal"]
    assert "服務約定" in section_titles
    assert "客戶付款約定" in section_titles
    assert "其他約定" in section_titles

    # 2. 不支援文字指令觸發（傳送「案件資訊」或「服務條件與費用」不回應）
    assert (
        app.handle_message(
            _make_inbox(
                "evt-case-info-txt",
                {"type": "message", "message": {"type": "text", "text": "案件資訊"}},
                user_id="U-staff-1",
            ),
            uow,
        )
        is False
    )
    assert (
        app.handle_message(
            _make_inbox(
                "evt-case-info-txt2",
                {"type": "message", "message": {"type": "text", "text": "服務條件與費用"}},
                user_id="U-customer-1",
            ),
            uow,
        )
        is False
    )
    assert len(uow.delivery_tasks.requests) == 1

    # 3. 無 sections 時優雅降級
    empty_uow = _FakeGroupHelperUoW(is_started=False, order_information_sections=())
    assert (
        app.handle_postback(
            _make_inbox(
                "evt-case-info-empty",
                {"type": "postback", "postback": {"data": "group-helper:case-information"}},
                user_id="U-customer-1",
            ),
            empty_uow,
        )
        is True
    )
    empty_payload = json.loads(empty_uow.delivery_tasks.requests[-1].payload_json)
    assert "目前無此案件之服務條件與費用約定資料" in str(empty_payload)


def test_multi_caregiver_context_recognition_and_stress_test() -> None:
    """壓力測試：多月嫂案件之身分辨識、各月嫂專屬綁定與合併顯示。"""
    app = _make_app()
    # 模擬案件 115000179：2 位月嫂（陳月嫂 staff_id=101、林月嫂 staff_id=102）
    formal_rows = [
        {"assignment_id": 201, "staff_id": 101, "staff_name": "陳月嫂", "scheduling_version": 3},
        {"assignment_id": 202, "staff_id": 102, "staff_name": "林月嫂", "scheduling_version": 3},
    ]
    segment_rows = [
        {"segment_id": 301, "staff_id": 101, "staff_name": "陳月嫂", "assigned_start_date": "2027-04-10"},
        {"segment_id": 302, "staff_id": 102, "staff_name": "林月嫂", "assigned_start_date": "2027-04-25"},
    ]
    schedule_rows = [
        {"work_date": date(2027, 4, 10), "is_work_day": True, "staff_id": 101, "staff_name": "陳月嫂"},
        {"work_date": date(2027, 4, 25), "is_work_day": True, "staff_id": 102, "staff_name": "林月嫂"},
    ]

    def create_mock_conn(user_line_id: str, bindings_list: list[dict]):
        single_rows = iter((
            {
                "case_no": "115000179", "status": "服務中", "actual_start_date": date(2027, 4, 10),
                "actual_end_date": date(2027, 5, 7), "client_id": 888, "client_name": "劉之君",
                "service_days": 20, "service_type": "週休2日", "lifecycle_version": 5,
            },
            {"1": 1},  # has_applied_start
        ))
        row_sets = iter((
            formal_rows,
            segment_rows,
            schedule_rows,
            bindings_list,
        ))
        cursor = SimpleNamespace(
            execute=lambda *_: None,
            fetchone=lambda: next(single_rows),
            fetchall=lambda: next(row_sets),
        )
        return SimpleNamespace(cursor=lambda: nullcontext(cursor))

    # 情境 1：第 1 位月嫂（陳月嫂 staff_id=101）操作
    conn1 = create_mock_conn("U-caregiver-chen", [{"subject_type": "staff", "subject_reference": "101"}])
    ctx1 = app._load_mysql_context(conn1, object(), "115000179", "U-caregiver-chen")
    assert ctx1 is not None
    assert ctx1["is_staff"] is True
    assert ctx1["is_customer"] is False
    assert ctx1["staff_id"] == 101
    assert ctx1["assignment_id"] == 201
    assert ctx1["staff_name"] == "陳月嫂、林月嫂"

    # 情境 2：第 2 位月嫂（林月嫂 staff_id=102）操作
    conn2 = create_mock_conn("U-caregiver-lin", [{"subject_type": "staff", "subject_reference": "102"}])
    ctx2 = app._load_mysql_context(conn2, object(), "115000179", "U-caregiver-lin")
    assert ctx2 is not None
    assert ctx2["is_staff"] is True
    assert ctx2["is_customer"] is False
    assert ctx2["staff_id"] == 102
    assert ctx2["assignment_id"] == 202
    assert ctx2["staff_name"] == "陳月嫂、林月嫂"

    # 情境 3：客戶本人（劉之君 client_id=888）操作
    conn3 = create_mock_conn("U-client-liu", [{"subject_type": "customer", "subject_reference": "888"}])
    ctx3 = app._load_mysql_context(conn3, object(), "115000179", "U-client-liu")
    assert ctx3 is not None
    assert ctx3["is_staff"] is False
    assert ctx3["is_customer"] is True
    assert ctx3["staff_name"] == "陳月嫂、林月嫂"

    # 情境 4：群組外部無關人員操作
    conn4 = create_mock_conn("U-stranger", [])
    ctx4 = app._load_mysql_context(conn4, object(), "115000179", "U-stranger")
    assert ctx4 is not None
    assert ctx4["is_staff"] is False
    assert ctx4["is_customer"] is False


def test_multi_caregiver_case_information_card_and_payment_terms() -> None:
    """壓力測試：多月嫂案件資訊卡片顯示多位月嫂姓名與全案金額。"""
    from subsystems.line.service_start_messages import case_information_card

    sections = [
        SimpleNamespace(
            title="服務約定",
            rows=[
                ("案件編號(case_no)", "115000179"),
                ("服務人員姓名", "陳月嫂、林月嫂"),
                ("客戶名稱", "劉之君"),
                ("預計服務開始日", "2027-04-10"),
                ("預計服務結束日", "2027-05-07"),
                ("每日服務時段", "09:00–17:30"),
                ("每日服務時數", "8.0"),
                ("服務方式", "週休2日"),
                ("希望服務天數", "20"),
                ("服務地址", "新竹市東區西大路135巷10弄11號"),
            ],
        ),
        SimpleNamespace(
            title="客戶付款約定",
            rows=[
                ("訂金金額", "NT$ 0"),
                ("預計訂金繳款日", "2026-10-24"),
                ("第一期金額", "NT$ 12,000"),
                ("預計第一期繳款日", "2027-04-10"),
                ("第二期金額", "NT$ 0"),
                ("預計第二期繳款日", "不適用"),
                ("樓層費", "NT$ 0"),
                ("樓層費預計繳款日", "不適用"),
                ("客戶應付總額", "NT$ 12,000"),
            ],
        ),
        SimpleNamespace(
            title="其他約定",
            rows=[
                ("特殊休假日", "待確認"),
                ("注意事項", "希望人好相處的~謝謝"),
            ],
        ),
    ]

    bank_info = {
        "bank_name": "永豐銀行",
        "bank_code": "807",
        "virtual_account": "99781699000179",
        "account_note": "115年度前案件（匯入專屬帳號）",
    }
    card = case_information_card(
        "115000179",
        "陳月嫂、林月嫂",
        sections,
        client_name="劉之君",
        bank_account_info=bank_info,
    )
    card_json = json.dumps(card, ensure_ascii=False)

    # 檢驗多月嫂姓名顯示在副標題與內文
    assert "陳月嫂、林月嫂" in card_json
    assert "劉之君" in card_json
    assert "115000179" in card_json

    # 檢驗金額
    assert "NT$ 12,000" in card_json
    assert "第一期金額" in card_json
    assert "客戶應付總額" in card_json

    # 檢驗匯款銀行與虛擬帳號
    assert "永豐銀行（807）" in card_json
    assert "99781699000179" in card_json


def test_multi_caregiver_service_schedule_calendar_rendering() -> None:
    """壓力測試：多月嫂排班日曆色塊、圖例與統計。"""
    from subsystems.line.service_start_messages import service_schedule_calendar_card

    rows = [
        {"work_date": "2027-04-10", "is_work_day": True, "staff_name": "陳月嫂"},
        {"work_date": "2027-04-11", "is_work_day": True, "staff_name": "陳月嫂"},
        {"work_date": "2027-04-12", "is_work_day": False, "staff_name": "陳月嫂"},
        {"work_date": "2027-04-13", "is_work_day": True, "staff_name": "林月嫂"},
        {"work_date": "2027-04-14", "is_work_day": True, "staff_name": "林月嫂"},
    ]

    card = service_schedule_calendar_card("115000179", rows, default_staff_name="指派月嫂", today=date(2027, 4, 11))
    card_json = json.dumps(card, ensure_ascii=False)

    assert "陳月嫂" in card_json
    assert "林月嫂" in card_json
    assert "2027 年 4 月" in card_json
    assert "已服務 2 天" in card_json


def test_staff_liffs_have_no_residual_old_service_start_or_leave_spec() -> None:
    """自動化回歸檢核：月嫂 LIFF 檔案不得殘留舊版回報服務開始或舊請假代班代碼。"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[6]

    order_search_path = root / "line" / "static" / "staff_order_search.html"
    order_search_content = order_search_path.read_text(encoding="utf-8")
    assert "回報服務開始" not in order_search_content
    assert "serviceStartCases" not in order_search_content
    assert "loadServiceStartCases" not in order_search_content
    assert "serviceStartPost" not in order_search_content
    assert "送出協調結果" not in order_search_content

    schedule_path = root / "line" / "static" / "staff_schedule.html"
    schedule_content = schedule_path.read_text(encoding="utf-8")
    assert "serviceStartSection" not in schedule_content
    assert "loadServiceStartCases" not in schedule_content
    assert "serviceStartPost" not in schedule_content
    assert "回報服務開始安排" not in schedule_content
    assert "leaveSection" not in schedule_content
    assert "reloadLeaveCases" not in schedule_content
