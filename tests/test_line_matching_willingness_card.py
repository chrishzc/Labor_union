import json

import pytest

from line import worker
from subsystems.line.delivery_contracts import LineProviderOutcomeType


class _Response:
    status_code = 200
    text = "ok"


def test_matching_willingness_card_sends_canonical_postback_actions(monkeypatch):
    sent = []
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "test-token")
    monkeypatch.setattr(
        worker.requests,
        "post",
        lambda *args, **kwargs: sent.append(kwargs["json"]) or _Response(),
    )
    task = {
        "id": 1,
        "task_type": "matching_willingness_card",
        "to_user_id": "U-staff",
        "line_request_id": "request-1",
        "message_content": "訂單資訊-1\n服務區段：2026-08-01～2026-08-10",
        "payload_json": json.dumps({
            "case_no": "CASE-1",
            "plan_id": 7,
            "segment_id": 71,
            "info_type": 1,
        }),
    }

    assert worker._execute_task(task) == (True, False, "", "")
    actions = sent[0]["messages"][0]["template"]["actions"]
    assert [action["data"] for action in actions] == [
        "action=willing&case_no=CASE-1&plan_id=7&segment_id=71",
        "action=unwilling&case_no=CASE-1&plan_id=7&segment_id=71",
    ]


@pytest.mark.parametrize("token", ["", "mock_token", "your_token_here"])
def test_missing_provider_token_is_a_terminal_configuration_failure(monkeypatch, token):
    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", token)
    task = {
        "id": 2,
        "task_type": "line_push",
        "to_user_id": "U-staff",
        "message_content": "test",
    }

    assert worker._execute_task(task) == (
        False,
        False,
        "line_channel_access_token_not_configured",
        "LINE channel access token is not configured",
    )


def test_unpatched_compatibility_hook_uses_the_canonical_adapter(monkeypatch):
    calls = []

    class _Adapter:
        def __init__(self, token, *, session=None):
            calls.append((token, session))

        def send(self, request):
            calls.append(request)
            return type("Outcome", (), {"outcome_type": LineProviderOutcomeType.SUCCESS})()

    monkeypatch.setenv("LINE_CHANNEL_ACCESS_TOKEN", "test-token")
    monkeypatch.setattr(worker, "LineMessagingApiAdapter", _Adapter)
    monkeypatch.setattr(worker.requests, "post", None)

    result = worker._execute_task(
        {
            "id": 3,
            "task_type": "line_push",
            "to_user_id": "U-staff",
            "message_content": "test",
        }
    )

    assert result == (True, False, "", "")
    assert calls[0] == ("test-token", None)
