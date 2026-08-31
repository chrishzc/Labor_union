"""
File: test_anomaly_necessity_catalog.py
Description: 驗證 current-state successor 只註冊仍具真實營運情境的 9 個 current issue codes。
"""

from domains.anomalies.registry import default_anomaly_registry


EXPECTED_CURRENT_CODES = {
    "SCHEDULE-006",
    "GOVSUB-001",
    "GOVSUB-002",
    "GOVSUB-004",
    "BECLASS-001",
    "SCHEDULE-002",
    "SCHEDULE-003",
    "LINE-006",
    "LINE-004",
}


def test_default_registry_has_exact_necessity_partition() -> None:
    registry = default_anomaly_registry()

    assert set(registry.codes()) == EXPECTED_CURRENT_CODES
    assert len(registry.codes()) == 9
    assert len(registry.active_codes()) == 9
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
