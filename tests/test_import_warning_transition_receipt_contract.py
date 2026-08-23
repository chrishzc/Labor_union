"""
File: test_import_warning_transition_receipt_contract.py
Description: 驗證匯入警示 Preview、terminal receipt、replay、衝突與認證查詢契約。
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.import_warning_tracking import (
    get_import_warning_tracking_application,
)
from api.routes.import_warning_tracking import router
from domains.anomalies.import_warning_tracking import ImportWarningTrackingStatus
from subsystems.anomalies.import_warning_tracking_workflow import (
    WarningTransitionPreview,
    WarningTransitionReceipt,
)


_OCCURRENCE = "warning-occurrence:SYNTH-1"
_RECEIPT_IDENTITY = "d" * 64


def _preview() -> WarningTransitionPreview:
    return WarningTransitionPreview(
        occurrence_identity=_OCCURRENCE,
        expected_version=1,
        resulting_status=ImportWarningTrackingStatus.AWAITING_EXTERNAL_CONFIRMATION,
        resulting_version=2,
    )


def _receipt(*, replayed: bool = False) -> WarningTransitionReceipt:
    return WarningTransitionReceipt(
        occurrence_identity=_OCCURRENCE,
        before_status=ImportWarningTrackingStatus.OPEN,
        after_status=ImportWarningTrackingStatus.AWAITING_EXTERNAL_CONFIRMATION,
        resulting_version=2,
        receipt_identity=_RECEIPT_IDENTITY,
        correlation_id="warning-correlation:SYNTH-1",
        replayed=replayed,
    )


class _Application:
    def __init__(self) -> None:
        self.preview_calls = 0
        self.apply_calls = 0
        self.receipt = _receipt()

    def preview(self, _request):
        self.preview_calls += 1
        return _preview()

    def apply(self, _request):
        self.apply_calls += 1
        return replace(self.receipt, replayed=self.apply_calls > 1)

    def query_receipt(self, receipt_identity: str):
        if receipt_identity != _RECEIPT_IDENTITY:
            raise ValueError("import_warning_receipt_not_found")
        return self.receipt


def _client(application: _Application, *, authenticated: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    if authenticated:
        app.dependency_overrides[require_system_admin] = lambda: SimpleNamespace(
            username="operator-SYNTH"
        )
    app.dependency_overrides[get_import_warning_tracking_application] = lambda: application
    return TestClient(app, raise_server_exceptions=False)


def _headers(*, idempotency_key: str = "warning-key:SYNTH-1") -> dict[str, str]:
    return {
        "Idempotency-Key": idempotency_key,
        "X-Correlation-ID": "warning-correlation:SYNTH-1",
    }


def _body() -> dict[str, object]:
    return {
        "expected_version": 1,
        "target_status": "awaiting_external_confirmation",
        "reason_code": "contact_started",
        "note": None,
        "evidence_reference": "evidence-ref:SYNTH-1",
    }


def _assert_receipt_payload(data: dict[str, object], *, replayed: bool) -> None:
    assert set(data) == {
        "occurrence_identity",
        "before_status",
        "after_status",
        "resulting_version",
        "receipt_identity",
        "correlation_id",
        "replayed",
    }
    assert data == {
        "occurrence_identity": _OCCURRENCE,
        "before_status": "open",
        "after_status": "awaiting_external_confirmation",
        "resulting_version": 2,
        "receipt_identity": _RECEIPT_IDENTITY,
        "correlation_id": "warning-correlation:SYNTH-1",
        "replayed": replayed,
    }
    for forbidden in (
        "note",
        "evidence_reference",
        "masked_subject",
        "raw_evidence",
        "source_snapshot",
        "actor",
    ):
        assert forbidden not in data


def test_preview_remains_independent_and_zero_write() -> None:
    application = _Application()
    response = _client(application).post(
        f"/api/v1/import-warning-tracking/tasks/{_OCCURRENCE}/preview",
        headers=_headers(),
        json=_body(),
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "occurrence_identity": _OCCURRENCE,
        "expected_version": 1,
        "resulting_status": "awaiting_external_confirmation",
        "resulting_version": 2,
    }
    assert application.preview_calls == 1
    assert application.apply_calls == 0


def test_apply_returns_terminal_receipt_without_raw_evidence() -> None:
    application = _Application()
    response = _client(application).post(
        f"/api/v1/import-warning-tracking/tasks/{_OCCURRENCE}/apply",
        headers=_headers(),
        json=_body(),
    )

    assert response.status_code == 200
    _assert_receipt_payload(response.json()["data"], replayed=False)
    assert application.apply_calls == 1


def test_same_key_replay_returns_same_receipt_and_marks_replayed() -> None:
    application = _Application()
    client = _client(application)
    path = f"/api/v1/import-warning-tracking/tasks/{_OCCURRENCE}/apply"

    first = client.post(path, headers=_headers(), json=_body())
    replay = client.post(path, headers=_headers(), json=_body())

    assert first.status_code == 200
    assert replay.status_code == 200
    _assert_receipt_payload(first.json()["data"], replayed=False)
    _assert_receipt_payload(replay.json()["data"], replayed=True)
    assert first.json()["data"]["receipt_identity"] == replay.json()["data"]["receipt_identity"]


def test_idempotency_payload_mismatch_is_typed_conflict() -> None:
    application = _Application()

    def mismatch(_request):
        raise ValueError("import_warning_idempotency_mismatch")

    application.apply = mismatch  # type: ignore[method-assign]
    response = _client(application).post(
        f"/api/v1/import-warning-tracking/tasks/{_OCCURRENCE}/apply",
        headers=_headers(),
        json=_body(),
    )

    assert response.status_code == 409
    error = response.json()["detail"]["error"]
    assert error == {
        "category": "idempotency_mismatch",
        "code": "import_warning_idempotency_mismatch",
        "message": "冪等鍵與原始匯入警示指令不一致。",
        "field_errors": [],
        "domain_blockers": [],
        "retryable": False,
        "correlation_id": "warning-correlation:SYNTH-1",
        "current_version": None,
    }


def test_authenticated_receipt_lookup_returns_typed_receipt_and_unknown_is_404() -> None:
    application = _Application()
    client = _client(application)

    response = client.get(
        f"/api/v1/import-warning-tracking/receipts/{_RECEIPT_IDENTITY}"
    )
    unknown = client.get(
        "/api/v1/import-warning-tracking/receipts/"
        + ("e" * 64)
    )

    assert response.status_code == 200
    _assert_receipt_payload(response.json()["data"], replayed=False)
    assert unknown.status_code == 404
    assert set(unknown.json()["detail"]["error"]) == {
        "category", "code", "message", "field_errors", "domain_blockers",
        "retryable", "correlation_id", "current_version",
    }
    assert unknown.json()["detail"]["error"]["code"] == "import_warning_receipt_not_found"


def test_receipt_lookup_requires_authentication() -> None:
    response = _client(_Application(), authenticated=False).get(
        f"/api/v1/import-warning-tracking/receipts/{_RECEIPT_IDENTITY}"
    )

    assert response.status_code in {401, 403}
