"""
File: test_anomaly_necessity_catalog.py
Description: 驗證異常定義生命週期的精確 33+7+1+1 分區。
"""

from domains.anomalies.registry import (
    AnomalyDefinitionLifecycle,
    default_anomaly_registry,
)


EXPECTED_WORK_ITEM_CODES = {
    "DOC-SEND-001",
    "LINE-002",
    "ORDER-001",
    "ORDER-002",
    "ORDER-003",
    "ORDER-004",
    "SUBSIDYADVANCE-001",
}


def test_default_registry_has_exact_necessity_partition() -> None:
    registry = default_anomaly_registry()

    assert len(registry.codes()) == 42
    assert len(registry.active_codes()) == 33
    assert registry.target_active_codes() == registry.active_codes()
    assert set(registry.work_item_codes()) == EXPECTED_WORK_ITEM_CODES
    assert registry.retired_codes() == ("SCHEDULE-005",)
    assert registry.audit_only_codes() == ("staff_payout_overpayment",)
    assert set(registry.reclassification_codes()) == {
        *EXPECTED_WORK_ITEM_CODES,
        "SCHEDULE-005",
        "staff_payout_overpayment",
    }
    assert len(registry.reclassification_codes()) == 9

    partitions = (
        set(registry.active_codes()),
        set(registry.work_item_codes()),
        set(registry.retired_codes()),
        set(registry.audit_only_codes()),
    )
    assert all(
        left.isdisjoint(right)
        for index, left in enumerate(partitions)
        for right in partitions[index + 1 :]
    )
    assert set().union(*partitions) == set(registry.codes())


def test_unclassified_definitions_remain_active_by_default() -> None:
    registry = default_anomaly_registry()

    definition = registry.require("HISTORICAL-ORDER-001")
    assert definition.lifecycle is AnomalyDefinitionLifecycle.ACTIVE
    assert definition.target_lifecycle is AnomalyDefinitionLifecycle.ACTIVE
    assert definition.code in registry.active_codes()
