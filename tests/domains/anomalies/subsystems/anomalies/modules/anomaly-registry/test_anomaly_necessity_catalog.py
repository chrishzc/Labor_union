"""
File: test_anomaly_necessity_catalog.py
Description: 驗證 current-state successor 只註冊唯一的 LINE-006 current issue。
"""

import pytest

from domains.anomalies.registry import default_anomaly_registry


EXPECTED_CURRENT_CODES = {
    "LINE-006",
}


def test_default_registry_has_exact_necessity_partition() -> None:
    registry = default_anomaly_registry()

    assert set(registry.codes()) == EXPECTED_CURRENT_CODES
    assert len(registry.codes()) == 1
    assert len(registry.active_codes()) == 1
    assert registry.target_active_codes() == registry.active_codes()
    assert registry.work_item_codes() == ()
    assert registry.retired_codes() == ()
    assert registry.audit_only_codes() == ()
    assert registry.reclassification_codes() == ()


def test_owner_work_items_are_not_runtime_anomaly_definitions() -> None:
    registry = default_anomaly_registry()

    for code in (
        "GOVSUB-006",
        "client_over_refund_recovery_open",
        "client_refund_underpayment",
        "staff_overpayment_recovery_open",
        "staff_payout_underpayment",
        "staff_payout_overpayment",
        "finance_import_manual_review",
        "HISTORICAL-ORDER-001",
    ):
        assert code not in registry.codes()


def test_retired_definition_cannot_be_resolved_from_current_registry() -> None:
    with pytest.raises(ValueError, match="anomaly_definition_not_found"):
        default_anomaly_registry().require("GOVSUB-007")
