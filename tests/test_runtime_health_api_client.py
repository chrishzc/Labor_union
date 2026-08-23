"""
File: test_runtime_health_api_client.py
Description: 驗證 LINE runtime client 的 typed response、command identity 與遮罩邊界。
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from ui.api_clients.line_api_client import LineAdminApiError
from ui.api_clients.runtime_health_api_client import (
    AlertTargetMutationReceipt,
    AlertTargetView,
    RuntimeAuditRecordView,
    RuntimeHealthApiClient,
)


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


def _target(*, state="active", version="version-1"):
    return {
        "target_id": 3,
        "target_kind": "group",
        "display_label": "LINE 告警對象 #3",
        "state": state,
        "minimum_status": "warning",
        "current_version": version,
        "updated_at": NOW.isoformat(),
    }


def _receipt(*, state="disabled", version="version-2"):
    return {
        "receipt_id": "receipt:abc",
        "command_family": "line_alert_target",
        "operation": "group_reset",
        "target_id": 3,
        "previous_state": "active",
        "resulting_state": state,
        "current_version": version,
        "replayed": False,
        "correlation_id": "corr-1",
        "committed_at": NOW.isoformat(),
    }


class _Transport:
    def __init__(self):
        self.calls = []

    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        if path == "/api/v1/runtime/line-alert-targets":
            return [_target(state="disabled", version="version-2")]
        if path == "/api/v1/runtime/line-alert-targets/group/reset":
            return _receipt()
        if path == "/api/v1/admin/audits":
            return {
                "items": [
                    {
                        "audit_id": 7,
                        "occurred_at": NOW.isoformat(),
                        "actor_label_masked": "管***",
                        "action_family": "other",
                        "target_label_masked": "line_alert_target:3***",
                        "ip_address_masked": "127.0.0.***",
                        "outcome": "success",
                        "reason_code": "line.alert_target.reset",
                    }
                ],
                "page": 1,
                "page_size": 100,
                "total": 1,
                "total_pages": 1,
            }
        return []


def test_target_query_is_typed_and_rejects_raw_group_identity():
    client = RuntimeHealthApiClient(_Transport())
    target = client.alert_targets("session")[0]

    assert isinstance(target, AlertTargetView)
    assert target.display_label == "LINE 告警對象 #3"
    assert "group_id" not in target.model_dump()
    with pytest.raises(ValidationError) as error:
        AlertTargetView.model_validate({**_target(), "group_id": "C-secret"})
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_reset_sends_full_command_identity_and_returns_receipt():
    transport = _Transport()
    client = RuntimeHealthApiClient(transport)
    receipt = client.reset_group_target(
        "session",
        expected_version="version-1",
        reason="群組輪替",
        idempotency_key="idem-1",
        correlation_id="corr-1",
    )

    assert isinstance(receipt, AlertTargetMutationReceipt)
    assert receipt.receipt_id == "receipt:abc"
    _, path, call = transport.calls[-1]
    assert path.endswith("/line-alert-targets/group/reset")
    assert call["json"] == {
        "expected_version": "version-1",
        "reason": "群組輪替",
        "idempotency_key": "idem-1",
        "correlation_id": "corr-1",
    }
    assert call["extra_headers"] == {
        "Idempotency-Key": "idem-1",
        "X-Correlation-ID": "corr-1",
    }


def test_malformed_success_payload_fails_closed():
    class _Malformed(_Transport):
        def request(self, method, path, **kwargs):
            return [{**_target(), "group_id": "C-secret"}]

    with pytest.raises(LineAdminApiError) as error:
        RuntimeHealthApiClient(_Malformed()).alert_targets("session")
    assert error.value.code == "runtime_alert_target_invalid_response"


def test_audit_query_returns_closed_masked_views_and_rejects_raw_details():
    records = RuntimeHealthApiClient(_Transport()).audit_records(
        "session", action_prefix="line."
    )

    assert isinstance(records[0], RuntimeAuditRecordView)
    assert records[0].actor_label_masked == "管***"
    assert "details" not in records[0].model_dump()

    class _RawAudit(_Transport):
        def request(self, method, path, **kwargs):
            page = super().request(method, path, **kwargs)
            page["items"][0]["details"] = {"token": "secret"}
            return page

    with pytest.raises(LineAdminApiError) as error:
        RuntimeHealthApiClient(_RawAudit()).audit_records("session")
    assert error.value.code == "runtime_audit_invalid_response"
