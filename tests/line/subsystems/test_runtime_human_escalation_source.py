"""
File: test_runtime_human_escalation_source.py
Description: 驗證 M4 escalation source 的連續失敗、遮罩與空 runtime allowlist。
"""

from __future__ import annotations

import pytest

from subsystems.line.runtime_human_escalation_source import (
    BindingFailureEvent,
    HumanEscalationSourceError,
    RUNTIME_CRITICAL_CAPABILITY_ALLOWLIST,
    binding_failure_threshold_2,
    normalize_complaint_text,
    normalize_runtime_critical,
)
from domains.customer_service.escalation import MaskedContext, TriggerCode, validate_trigger


def _event(sequence: int, *, scope: str = "binding:opaque") -> BindingFailureEvent:
    return BindingFailureEvent("identity.v1", scope, f"evt-{sequence}", sequence, fingerprint=f"fp-{sequence}")


def test_binding_threshold_requires_adjacent_same_scope() -> None:
    assert not binding_failure_threshold_2((_event(1),))
    assert binding_failure_threshold_2((_event(1), _event(2)))
    assert not binding_failure_threshold_2((_event(1), _event(3)))
    assert not binding_failure_threshold_2((_event(1), _event(2, scope="other")))
    assert not binding_failure_threshold_2(
        (
            _event(1),
            BindingFailureEvent("identity.v1", "binding:opaque", "ok-2", 2, success=True, fingerprint="fp-ok"),
            _event(3),
        )
    )
    assert binding_failure_threshold_2(
        (
            _event(1),
            BindingFailureEvent("identity.v1", "binding:opaque", "ok-2", 2, success=True, fingerprint="fp-ok"),
            _event(3),
            _event(4),
        )
    )


def test_complaint_is_masked_and_category_is_not_guessed() -> None:
    result = normalize_complaint_text("  我要客訴：姓名 王小美  ")
    assert result == {
        "summary_code": "complaint_explicit",
        "policy_version": "complaint.v1",
        "category": "other",
        "redaction_version": "m4-mask.v1",
    }
    assert normalize_complaint_text("只是覺得很生氣") is None


def test_complaint_mask_maps_directly_to_customer_service_domain_context() -> None:
    payload = normalize_complaint_text("我要客訴：姓名 王小美")
    assert payload is not None
    context = MaskedContext.from_mapping(payload)
    validate_trigger(TriggerCode.COMPLAINT, "line_inbox", "complaint.v1", context)
    assert set(context.as_dict()) == {
        "summary_code", "policy_version", "category", "redaction_version"
    }


def test_runtime_critical_allowlist_accepts_only_line_worker_delivery() -> None:
    assert RUNTIME_CRITICAL_CAPABILITY_ALLOWLIST == frozenset(
        {("LINE Worker", "line_delivery")}
    )
    accepted = normalize_runtime_critical(
        {
            "event_identity": "evt-runtime",
            "resulting_status": "critical",
            "component": "LINE Worker",
            "capability_scope": "line_delivery",
        }
    )
    assert accepted.component == "LINE Worker"
    assert accepted.capability_scope == "line_delivery"

    for component, capability in (
        ("Database", "line_delivery"),
        ("LINE Worker", "database"),
        ("Media Worker", "line_delivery"),
        ("Knowledge Worker", "knowledge"),
    ):
        with pytest.raises(HumanEscalationSourceError):
            normalize_runtime_critical(
                {
                    "event_identity": "evt-runtime-rejected",
                    "resulting_status": "critical",
                    "component": component,
                    "capability_scope": capability,
                }
            )
