"""
File: test_finance_anomaly_registry_contract.py
Description: 驗證 Finance 異常定義的 recovery 與安全顯示欄位契約。
"""

import pytest

from domains.anomalies.registry import (
    AnomalyDefinition,
    AnomalyProjectionKind,
    AnomalySeverity,
    default_anomaly_registry,
)


def test_every_finance_definition_explicitly_declares_actions_or_state_only() -> None:
    registry = default_anomaly_registry()

    finance_definitions = [
        definition
        for definition in registry._definitions.values()
        if definition.source_domain
        in {"client_finance", "finance_import", "government_subsidy", "staff_payables"}
    ]

    assert finance_definitions
    assert all(
        bool(definition.available_actions) != definition.no_automated_recovery
        for definition in finance_definitions
    )


def test_finance_definition_cannot_leave_recovery_mode_implicit() -> None:
    with pytest.raises(ValueError, match="finance recovery contract"):
        AnomalyDefinition(
            code="FINANCE-TEST",
            source_domain="client_finance",
            fingerprint_fields=("identity",),
            severity=AnomalySeverity.WARNING,
            projection_kind=AnomalyProjectionKind.CURRENT_STATE,
            available_actions=(),
        )


def test_finance_manual_review_is_an_owner_work_item_not_an_anomaly_definition() -> None:
    assert "finance_import_manual_review" not in default_anomaly_registry().codes()
