from ui.api_clients.matching_schedule_confirmation_api_client import (
    MatchingScheduleConfirmationApiClient,
    MatchingScheduleConfirmationApiError,
)


class _Response:
    def __init__(self, status_code, body) -> None:
        self.status_code = status_code
        self._body = body

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        return self._body


class _Session:
    def __init__(self, response) -> None:
        self.response = response
        self.calls = []

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.response


def _success_body():
    return {
        "success": True,
        "data": {
            "case_no": "CASE-68",
            "plan_id": 18,
            "confirmed_service_date_version": 2,
            "snapshot_id": 4,
            "snapshot_status": "sent",
            "recipients": [
                {
                    "recipient_snapshot_id": 8,
                    "audience_type": "customer",
                    "segment_id": None,
                    "delivery_status": "queued",
                    "confirmation_status": "rejected",
                    "confirmation_source": "line",
                    "confirmation_reason": "服務時段不合適",
                    "confirmation_occurred_at_utc": "2026-08-12T09:30:00Z",
                }
            ],
            "gate_passed": False,
        },
    }


def test_schedule_confirmation_client_validates_the_response_view():
    session = _Session(_Response(200, _success_body()))
    client = MatchingScheduleConfirmationApiClient(
        base_url="http://api.test",
        headers={"Authorization": "Bearer test"},
        session=session,
    )

    state = client.query("CASE-68", 18)

    assert state.recipients[0].audience_type == "customer"
    assert state.recipients[0].confirmation_reason == "服務時段不合適"
    assert state.recipients[0].confirmation_occurred_at_utc.isoformat() == "2026-08-12T09:30:00+00:00"
    assert session.calls[0][0] == ("GET", "http://api.test/api/v1/orders/CASE-68/matching-plans/18/schedule-confirmation")


def test_schedule_confirmation_client_rejects_invalid_success_payload():
    client = MatchingScheduleConfirmationApiClient(
        base_url="http://api.test",
        headers={},
        session=_Session(_Response(200, {"success": True, "data": {}})),
    )

    try:
        client.query("CASE-68", 18)
    except MatchingScheduleConfirmationApiError as error:
        assert error.code == "matching_schedule_confirmation_invalid_response"
    else:
        raise AssertionError("invalid response must fail closed")


def test_schedule_confirmation_client_explains_missing_confirmed_service_dates():
    client = MatchingScheduleConfirmationApiClient(
        base_url="http://api.test",
        headers={},
        session=_Session(
            _Response(409, {"detail": {"code": "confirmed_service_dates_required"}})
        ),
    )

    try:
        client.query("CASE-68", 18)
    except MatchingScheduleConfirmationApiError as error:
        assert error.code == "confirmed_service_dates_required"
        assert str(error) == "尚未在訂單管理確認服務日期，不能發送日期表。"
    else:
        raise AssertionError("missing confirmed dates must fail closed")


def test_schedule_confirmation_client_explains_missing_recipient_line_binding():
    client = MatchingScheduleConfirmationApiClient(
        base_url="http://api.test",
        headers={},
        session=_Session(
            _Response(
                409,
                {
                    "detail": {
                        "code": "matching_schedule_recipient_line_binding_required:customer,caregiver:22"
                    }
                },
            )
        ),
    )

    try:
        client.send("CASE-68", 18, idempotency_key="send-68")
    except MatchingScheduleConfirmationApiError as error:
        assert error.code.startswith("matching_schedule_recipient_line_binding_required")
        assert str(error) == "客戶或月嫂尚未完成 LINE 綁定，不能發送日期表。"
    else:
        raise AssertionError("unbound recipients must fail closed")
