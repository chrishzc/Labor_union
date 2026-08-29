"""Stage 7 canonical matching postback dispatch contracts."""

from datetime import datetime, timezone
from types import SimpleNamespace

from domains.line.identities import LineSourceType, LineUserId
from subsystems.line.matching_postback_application import (
    LineMatchingPostbackApplication,
)

NOW = datetime(2026, 8, 9, tzinfo=timezone.utc)


class _MatchingApplicationSpy:
    def __init__(self) -> None:
        self.calls = []

    def record_line_response_in_unit_of_work(self, unit_of_work, **arguments):
        self.calls.append((unit_of_work, arguments))


class _ScheduleConfirmationSpy:
    def __init__(self) -> None:
        self.reason_calls = []
        self.postback_calls = []

    def confirm_line_postback(self, token, decision, line_user_id, event_key):
        self.postback_calls.append((token, decision, line_user_id, event_key))

    def confirm_line_rejection_reason(self, line_user_id, reason, event_key):
        self.reason_calls.append((line_user_id, reason, event_key))
        return True


def _inbox(data: str, *, source_type=LineSourceType.USER):
    event = SimpleNamespace(
        event_id=SimpleNamespace(value="webhook-event-1"),
        event_type="postback",
        occurred_at=NOW,
        payload_json='{"postback":{"data":"' + data + '"}}',
        source=SimpleNamespace(
            source_type=source_type,
            user_id=LineUserId("U-caregiver"),
        ),
    )
    return SimpleNamespace(event=event)


def test_matching_postback_passes_durable_event_identity_to_application() -> None:
    spy = _MatchingApplicationSpy()
    handler = LineMatchingPostbackApplication(spy)
    unit_of_work = object()

    handler.handle(
        _inbox("matching:safe-token-12345678901234567890:willing"),
        unit_of_work,
    )

    assert len(spy.calls) == 1
    _, arguments = spy.calls[0]
    assert arguments["decision"] == "willing"
    assert arguments["idempotency_key"].value == "matching-postback:webhook-event-1"


def test_non_matching_or_non_user_postback_is_ignored() -> None:
    spy = _MatchingApplicationSpy()
    handler = LineMatchingPostbackApplication(spy)

    handler.handle(_inbox("other-action"), object())
    handler.handle(
        _inbox(
            "matching:safe-token-12345678901234567890:willing",
            source_type=LineSourceType.GROUP,
        ),
        object(),
    )

    assert spy.calls == []


def test_schedule_rejection_reason_message_uses_the_durable_event_identity() -> None:
    handler = LineMatchingPostbackApplication(_MatchingApplicationSpy())
    schedule_spy = _ScheduleConfirmationSpy()
    unit_of_work = SimpleNamespace(matching_schedule_confirmations=schedule_spy)

    handled = handler.handle_message(
        _inbox("other-action"),
        unit_of_work,
        LineUserId("U-caregiver"),
        "家中已有安排",
    )

    assert handled is True
    assert schedule_spy.reason_calls == [
        (
            LineUserId("U-caregiver"),
            "家中已有安排",
            "matching-schedule-rejection-reason:webhook-event-1",
        )
    ]


def test_schedule_rejection_postback_uses_the_bound_line_user_and_event_identity() -> None:
    handler = LineMatchingPostbackApplication(_MatchingApplicationSpy())
    schedule_spy = _ScheduleConfirmationSpy()
    unit_of_work = SimpleNamespace(matching_schedule_confirmations=schedule_spy)

    handler.handle(
        _inbox("schedule:safe-token-12345678901234567890:rejected"),
        unit_of_work,
    )

    assert schedule_spy.postback_calls == [
        (
            "safe-token-12345678901234567890",
            "rejected",
            LineUserId("U-caregiver"),
            "matching-schedule-postback:webhook-event-1",
        )
    ]
