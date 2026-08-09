import json

from line import worker


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
