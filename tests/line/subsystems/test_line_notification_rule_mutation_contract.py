"""
File: test_line_notification_rule_mutation_contract.py
Description: 驗證通知規則 mutation 的封閉 grammar、preview fingerprint 與 idempotency 輸入契約。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from api.schemas.line_notification_rules import (
    ApplyLineNotificationManualReplayRequest,
    PreviewLineNotificationRulesRequest,
    SaveLineNotificationRulesRequest,
)


def _definition(*, event_code: str = "deposit_confirmed", enabled: bool = True):
    return {
        "rules": [{
            "id": "deposit_notice",
            "event_code": event_code,
            "recipient_selector": "case_group",
            "template_id": "deposit_notice",
            "enabled": enabled,
            "schedule": {"kind": "immediate"},
            "frequency": {"kind": "once"},
            "predicates": [],
        }]
    }


def test_preview_materializes_defaults_and_rejects_extra_fields() -> None:
    payload = PreviewLineNotificationRulesRequest.model_validate({
        "expected_revision": 3,
        "definition": {"rules": [{
            "id": "deposit_notice",
            "event_code": "deposit_confirmed",
            "recipient_selector": "case_group",
            "template_id": "deposit_notice",
            "schedule": {"kind": "immediate"},
        }]},
    })
    rule = payload.definition.rules[0]
    assert rule.enabled is False
    assert rule.frequency.kind == "once"
    assert rule.predicates == ()

    invalid = _definition()
    invalid["rules"][0]["sql"] = "SELECT 1"
    with pytest.raises(ValidationError):
        PreviewLineNotificationRulesRequest.model_validate({
            "expected_revision": 3,
            "definition": invalid,
        })


def test_save_requires_sha256_preview_fingerprint_and_forbids_extra_input() -> None:
    valid = {
        "expected_revision": 3,
        "preview_fingerprint": "f" * 64,
        "definition": _definition(),
        "reason": "啟用收款通知",
        "idempotency_key": "notification-save-1",
        "correlation_id": "notification-save-1",
    }
    assert SaveLineNotificationRulesRequest.model_validate(valid).preview_fingerprint == "f" * 64
    with pytest.raises(ValidationError):
        SaveLineNotificationRulesRequest.model_validate({**valid, "unexpected": True})
    with pytest.raises(ValidationError):
        SaveLineNotificationRulesRequest.model_validate({**valid, "preview_fingerprint": "short"})


@pytest.mark.parametrize("field", ["reason", "idempotency_key", "correlation_id"])
def test_save_rejects_whitespace_only_mutation_text(field: str) -> None:
    valid = {
        "expected_revision": 3,
        "preview_fingerprint": "f" * 64,
        "definition": _definition(),
        "reason": "啟用收款通知",
        "idempotency_key": "notification-save-1",
        "correlation_id": "notification-save-1",
    }
    with pytest.raises(ValidationError):
        SaveLineNotificationRulesRequest.model_validate({**valid, field: " \t\n"})


@pytest.mark.parametrize("field", ["reason", "idempotency_key", "correlation_id"])
def test_manual_replay_rejects_whitespace_only_mutation_text(field: str) -> None:
    valid = {
        "reason": "核准重送",
        "idempotency_key": "manual-replay-1",
        "correlation_id": "manual-replay-1",
    }
    with pytest.raises(ValidationError):
        ApplyLineNotificationManualReplayRequest.model_validate({**valid, field: " \t\n"})


def test_unknown_event_is_only_accepted_as_disabled_shadow() -> None:
    disabled = PreviewLineNotificationRulesRequest.model_validate({
        "expected_revision": 3,
        "definition": _definition(event_code="future_owner_event", enabled=False),
    })
    assert disabled.definition.rules[0].event_code == "future_owner_event"
    with pytest.raises(ValidationError):
        PreviewLineNotificationRulesRequest.model_validate({
            "expected_revision": 3,
            "definition": _definition(event_code="future_owner_event", enabled=True),
        })
