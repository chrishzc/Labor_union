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

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.service_start import get_service_start_application
from api.routes import staff_leave_intake
from domains.customer_service.ticket import CustomerServiceCategory
from domains.line.delivery import LineMessageKind
from domains.line.identities import (
    LineSourceIdentity,
    LineSourceType,
    LineUserId,
    LineWebhookEventId,
)
from domains.line.identity_flow import LineIdentityFlowPurpose
from domains.line.order_group import LineOrderGroupBindingStatus
from domains.scheduling.service_start import ServiceStartConflict, ServiceStartDecision
from infrastructure.mysql.customer_service_repository import _REMINDER_SOURCE_CASE
from subsystems.line.delivery_contracts import REPLY_ONLY_WEBHOOK_SOURCE
from subsystems.line.group_helper_application import LineGroupHelperApplication
from subsystems.line.service_start_messages import HELPER_TEXT_DEFAULTS


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

    def get_by_group(self, group_id: str) -> Any:
        if group_id != "G-case-1":
            return None
        return SimpleNamespace(case_no="C-2026-01", status=self.status)


class _FakeIdentityFlowRepo:
    def __init__(self) -> None:
        self.commands: list[Any] = []

    def open(self, cmd: Any) -> Any:
        self.commands.append(cmd)
        return SimpleNamespace(flow_id=SimpleNamespace(value="flow-999"))


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
    ) -> None:
        self._connection = None
        self.configurations = SimpleNamespace(
            get=lambda _kind: SimpleNamespace(revision=SimpleNamespace(value=0), definition_json="{}")
        )
        self.receipts = _FakeReceiptRepo()
        self.delivery_tasks = _FakeDeliveryRepo()
        self.order_groups = _FakeOrderGroupsRepo()
        self.identity_flows = _FakeIdentityFlowRepo()
        self.customer_service = _FakeCustomerServiceRepo()
        self.service_start_workflow = _FakeServiceStartWorkflow()
        self._helper_proposals: dict[tuple[str, str], dict[str, Any]] = {}
        self.is_started = is_started
        self.service_commenced = is_started if service_commenced is None else service_commenced
        self.schedule_rows = schedule_rows
        self.service_completed = service_completed

    def group_helper_context(self, case_no: str, user_id: str) -> dict[str, Any] | None:
        if case_no != "C-2026-01":
            return None
        return {
            "case_no": case_no,
            "order_status": "訂單完成" if self.service_completed else "matched" if not self.is_started else "in_service",
            "order_version": 3,
            "client_id": 88,
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
            "can_share_satisfaction_survey": self.service_completed and user_id in {"U-staff-1", "U-staff-2"},
            "is_customer": user_id == "U-customer-1",
            "is_admin": user_id == "U-admin-1",
            "admin_user_id": 5 if user_id == "U-admin-1" else None,
        }


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


@pytest.mark.parametrize(("completed", "user_id", "visible"), [
    (True, "U-staff-1", True),
    (True, "U-staff-2", True),
    (True, "U-customer-1", False),
    (False, "U-staff-1", False),
])
def test_satisfaction_survey_only_shows_for_staff_after_completion(completed, user_id, visible) -> None:
    uow = _FakeGroupHelperUoW(service_completed=completed)
    assert _make_app().handle_message(_make_inbox(
        "evt-survey-menu", {"message": {"type": "text", "text": "小幫手"}}, user_id=user_id,
    ), uow)
    card = json.loads(uow.delivery_tasks.requests[0].payload_json)
    actions = [row["action"]["data"] for row in card["contents"]["body"]["contents"]]
    assert ("group-helper:satisfaction-survey:C-2026-01" in actions) is visible
    _assert_all_reply_only(uow)


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


@pytest.mark.parametrize(("completed", "case_no", "group_id", "user_id"), [
    (False, "C-2026-01", "G-case-1", "U-staff-1"),
    (True, "C-2026-01", "G-case-1", "U-customer-1"),
    (True, "C-2026-01", "G-case-1", "U-unassigned"),
    (True, "C-2026-02", "G-case-1", "U-staff-1"),
    (True, "C-2026-01", "G-unbound", "U-staff-1"),
])
def test_satisfaction_survey_rejects_unfinished_case_wrong_actor_or_forwarded_click(completed, case_no, group_id, user_id) -> None:
    uow = _FakeGroupHelperUoW(service_completed=completed)
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
    assert json.loads(reply.payload_json) == {"type": "text", "text": "本案服務已完成，感謝您使用工會的服務。"}
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
        assert len(items) == 5
        assert items[0]["action"]["type"] == "datetimepicker"
        assert items[0]["action"]["mode"] == "date"
        assert items[0]["action"]["data"] == "group-helper:confirm-start-date:C-2026-01"
        assert payload["contents"]["header"]["contents"][0]["contents"][1]["contents"][0]["text"] == "待確認開工"
        _assert_all_reply_only(uow)

    # Option A: 已確認開工後，自動隱藏【確認開工日】，保留【服務排程】等其餘四項
    started_uow = _FakeGroupHelperUoW(is_started=True)
    handled_started = app.handle_reply(
        _make_inbox("evt-menu-started", {"type": "message", "message": {"type": "text", "text": "小幫手"}}),
        started_uow,
    )
    assert handled_started is True
    started_payload = json.loads(started_uow.delivery_tasks.requests[0].payload_json)
    started_items = started_payload["contents"]["body"]["contents"]
    assert len(started_items) == 4
    action_data = [item["action"].get("data", "") for item in started_items]
    assert not any(d.startswith("group-helper:confirm-start-date") for d in action_data)
    assert "group-helper:service-schedule" in action_data
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


def test_pre_commenced_confirmed_schedule_keeps_confirm_start_button() -> None:
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
    # All 5 items remain visible, allowing re-confirming start date before actual work starts
    assert len(items) == 5
    assert items[0]["action"]["data"].startswith("group-helper:confirm-start-date")
    assert payload["contents"]["header"]["contents"][0]["contents"][1]["contents"][0]["text"] == "已約定開工"
    _assert_all_reply_only(uow)


def test_workflow2_postponement_liff_conflict_and_in_group_agreement_zero_push() -> None:
    app = _make_app()
    uow = _FakeGroupHelperUoW(is_started=True)

    # 1. No proposal yet -> replies LIFF URL targeting case & postpone mode
    assert (
        app.handle_postback(
            _make_inbox(
                "evt-postpone-open",
                {"type": "postback", "postback": {"data": "group-helper:mutual-postponement"}},
                user_id="U-staff-1",
            ),
            uow,
        )
        is True
    )
    assert uow.identity_flows.commands[0].purpose is LineIdentityFlowPurpose.STAFF_SELF_SERVICE
    liff_text = json.loads(uow.delivery_tasks.requests[-1].payload_json)["text"]
    assert "flow_id=flow-999" in liff_text
    assert "case_no=C-2026-01" in liff_text
    assert "mode=postpone" in liff_text

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

    # 4. Caregiver clicking agree on their own proposal has no response (silent ignore to keep chat clean)
    pre_len = len(uow.delivery_tasks.requests)
    assert (
        app.handle_postback(
            _make_inbox(
                "evt-postpone-staff-agree",
                {"type": "postback", "postback": {"data": "postponement:agree"}},
                user_id="U-staff-1",
            ),
            uow,
        )
        is True
    )
    assert len(uow.delivery_tasks.requests) == pre_len
    assert uow.service_start_workflow.leave_calls == []

    # 4b. Customer agrees -> canonical writer with enqueue_group_schedule=False
    assert (
        app.handle_postback(
            _make_inbox(
                "evt-postpone-agree",
                {"type": "postback", "postback": {"data": "postponement:agree"}},
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

    # 5. Saved multi-date proposal picked up by tapping mutual-postponement menu button, then rejected cleanly
    uow._helper_proposals[("group_helper_postpone_proposal", "C-2026-01")] = {
        "case_no": "C-2026-01",
        "staff_id": 7,
        "assignment_id": 22,
        "dates": [
            {"original_date": "2026-06-14", "new_date": "2026-06-20"},
            {"original_date": "2026-06-15", "new_date": "2026-06-21"},
        ],
        "leave_start_date": "2026-06-14、2026-06-15",
        "leave_end_date": "2026-06-20、2026-06-21",
    }
    assert (
        app.handle_postback(
            _make_inbox(
                "evt-postpone-multi",
                {"type": "postback", "postback": {"data": "group-helper:mutual-postponement"}},
                user_id="U-staff-1",
            ),
            uow,
        )
        is True
    )
    assert uow.delivery_tasks.requests[-1].message_kind is LineMessageKind.FLEX
    assert "2026-06-14、2026-06-15" in uow.delivery_tasks.requests[-1].payload_json

    assert (
        app.handle_postback(
            _make_inbox(
                "evt-postpone-reject",
                {"type": "postback", "postback": {"data": "postponement:reject"}},
                user_id="U-customer-1",
            ),
            uow,
        )
        is True
    )
    assert uow._helper_proposals[("group_helper_postpone_proposal", "C-2026-01")]["cleared"] is True
    assert "維持不變" in json.loads(uow.delivery_tasks.requests[-1].payload_json)["text"]
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
    uow_stub = SimpleNamespace(
        _connection=None,
        _helper_proposals={},
        receipts=_FakeReceiptRepo(),
        delivery_tasks=_FakeDeliveryRepo(),
        commit=lambda: committed.append(True),
    )
    monkeypatch.setattr(staff_leave_intake, "open_line_unit_of_work", lambda: nullcontext(uow_stub))

    def _spy_save(_uow: Any, family: str, case_no: str, event_ref: str, payload: dict[str, Any]) -> None:
        saved_calls.append((family, case_no, event_ref, payload))

    monkeypatch.setattr(staff_leave_intake, "save_group_helper_proposal", _spy_save)

    client = TestClient(app)
    base_body = {
        "flow_id": "flow-999",
        "case_no": "C-2026-01",
        "assignment_id": 22,
        "dates": [{"original_date": "2026-06-12", "new_date": "2026-06-15"}],
    }

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
    assert ok_data["group_message"] == "雙方合意延期：2026-06-12→2026-06-15"
    assert len(saved_calls) == 1
    assert saved_calls[0][0] == "group_helper_postpone_proposal"
    assert saved_calls[0][1] == "C-2026-01"
    assert committed == [True]
    assert uow_stub.delivery_tasks.requests == []

    # 3. Multi-day /propose saves all pairs and sets group_message=None so group menu button loads full batch
    multi_body = {
        **base_body,
        "dates": [
            {"original_date": "2026-06-12", "new_date": "2026-06-20"},
            {"original_date": "2026-06-13", "new_date": "2026-06-21"},
        ],
    }
    multi_res = client.post("/api/v1/line/staff-self-service/leave-results/propose", json=multi_body)
    assert multi_res.status_code == 200
    assert multi_res.json()["data"]["group_message"] is None
    assert len(saved_calls[-1][3]["dates"]) == 2


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
    _assert_all_reply_only(post_uow)


def test_workflow4_staff_assistance_admin_close_and_source_mapping() -> None:
    assert "group-helper-assistance:" in _REMINDER_SOURCE_CASE
    assert "'service'" in _REMINDER_SOURCE_CASE

    app = _make_app(custom_aliases={"staff_assistance_close": ["本案已結案"]})
    uow = _FakeGroupHelperUoW(is_started=True)

    # Caregiver/customer requests staff assistance
    assert (
        app.handle_postback(
            _make_inbox("evt-assist-1", {"type": "postback", "postback": {"data": "group-helper:staff-assistance"}}),
            uow,
        )
        is True
    )
    assert len(uow.customer_service.created) == 1
    ticket_cmd = uow.customer_service.created[0]
    assert ticket_cmd.category is CustomerServiceCategory.SERVICE_PROGRESS
    assert ticket_cmd.event_key == "group-helper-assistance:evt-assist-1"
    assert ticket_cmd.case_no == "C-2026-01"
    assert ticket_cmd.client_id == 88
    assert HELPER_TEXT_DEFAULTS["helper-staff-assistance-ack"].format(case_no="C-2026-01") in json.loads(
        uow.delivery_tasks.requests[-1].payload_json
    )["text"]

    # Admin sends configured close alias -> closes ticket & replies confirmation
    assert (
        app.handle_message(
            _make_inbox(
                "evt-close-1",
                {"type": "message", "message": {"type": "text", "text": "本案已結案"}},
                user_id="U-admin-1",
            ),
            uow,
        )
        is True
    )
    assert uow.customer_service.resolved_cases == [("C-2026-01", "line:U-admin-1", "evt-close-1")]
    assert HELPER_TEXT_DEFAULTS["helper-staff-assistance-closed"].format(case_no="C-2026-01") in json.loads(
        uow.delivery_tasks.requests[-1].payload_json
    )["text"]
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
