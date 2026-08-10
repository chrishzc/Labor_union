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
