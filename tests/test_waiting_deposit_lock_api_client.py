from __future__ import annotations

from dataclasses import dataclass

from ui.api_clients.waiting_deposit_lock_api_client import (
    WaitingDepositLockApiClient,
)


@dataclass
class _Response:
    payload: dict
    status_code: int = 200

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def json(self) -> dict:
        return self.payload


class _Session:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[dict] = []

    def request(self, method, url, *, headers, json, timeout):
        self.calls.append(
            {"method": method, "url": url, "headers": headers, "json": json}
        )
        return _Response(self.payload)


def test_acquire_preview_uses_canonical_endpoint_and_response() -> None:
    session = _Session({"success": True, "data": _acquire_preview()})
    client = _client(session)

    preview = client.preview_acquisition("C-1", 7)

    assert preview.plan_id == 7
    assert session.calls[0]["url"].endswith(
        "/C-1/matching-plans/7/waiting-deposit-lock/acquire/preview"
    )


def test_release_apply_sends_fingerprint_reason_and_command_identity() -> None:
    session = _Session({"success": True, "data": _release_receipt()})
    client = _client(session)

    receipt = client.apply_release(
        "C-1", 7, 9, _fingerprint(), reason="customer cancelled",
        idempotency_key="lock-release-1", correlation_id="correlation-1",
    )

    assert receipt.lock_status == "released"
    assert session.calls[0]["json"] == {
        "preview_fingerprint": _fingerprint(),
        "reason": "customer cancelled",
    }
    assert session.calls[0]["headers"]["Idempotency-Key"] == "lock-release-1"


def _client(session: _Session) -> WaitingDepositLockApiClient:
    return WaitingDepositLockApiClient(
        base_url="http://api.test",
        headers={"X-Internal-API-Key": "test"},
        session=session,
    )


def _acquire_preview() -> dict:
    return {
        "case_no": "C-1", "plan_id": 7, "service_day_count": 1,
        "buffer_day_count": 7, "occupancy": [], "conflicts": [],
        "apply_allowed": True, "preview_fingerprint": _fingerprint(),
    }


def _release_receipt() -> dict:
    return {
        "result": "created", "case_no": "C-1", "plan_id": 7,
        "lock_id": 9, "plan_status": "proposed", "lock_status": "released",
        "lock_rows": [],
    }


def _fingerprint() -> str:
    return "a" * 64
