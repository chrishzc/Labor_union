"""
File: test_anomaly_necessity_catalog.py
Description: 驗證 current-state successor 只註冊仍具真實營運情境的 2 個 current issue codes。
"""

from domains.anomalies.registry import default_anomaly_registry


EXPECTED_CURRENT_CODES = {
    "GOVSUB-007",
    "LINE-006",
}


def test_default_registry_has_exact_necessity_partition() -> None:
    registry = default_anomaly_registry()

    assert set(registry.codes()) == EXPECTED_CURRENT_CODES
    assert len(registry.codes()) == 2
    assert len(registry.active_codes()) == 2
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
