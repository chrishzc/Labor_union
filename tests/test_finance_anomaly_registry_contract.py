"""
File: test_finance_anomaly_registry_contract.py
Description: 驗證 Finance 異常定義的 recovery 與安全顯示欄位契約。
"""

import pytest

from api.routes.anomaly_recovery import _occurrence_payload
from api.routes.anomaly_registry import _safe_display_snapshot
from domains.anomalies.registry import (
    AnomalyDefinition,
    AnomalyProjectionKind,
    AnomalySeverity,
    default_anomaly_registry,
)
from domains.anomalies.root_fact_projection import FinanceAnomalyOccurrence
from shared_kernel.fingerprints import PreviewFingerprint


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


def test_finance_manual_review_declares_the_complete_safe_detail_snapshot() -> None:
    definition = default_anomaly_registry().require("finance_import_manual_review")

    assert definition.display_fields == (
        "affected_obligation_identities",
        "affected_order_identities",
        "amount_delta_ntd",
        "domain_blockers",
        "finance_import_batch_id",
        "finance_import_row_id",
        "integrity_blocker_active",
        "reason_codes",
        "root_condition_active",
    )


def test_finance_manual_review_safe_snapshot_accepts_its_registered_fields() -> None:
    definition = default_anomaly_registry().require("finance_import_manual_review")

    snapshot = _safe_display_snapshot(
        definition.code,
        definition.display_fields,
        {
            "affected_obligation_identities": ["client-obligation:42"],
            "affected_order_identities": ["case:116990824"],
            "amount_delta_ntd": 12000,
            "domain_blockers": ["manual_classification_required"],
            "finance_import_batch_id": 38,
            "finance_import_row_id": 94,
            "integrity_blocker_active": False,
            "reason_codes": ["manual_review"],
            "root_condition_active": True,
            "definition_code": definition.code,
            "occurred_at": "2026-08-24T00:00:00+00:00",
            "original_refund_ledger_entry_id": None,
            "recovery_bindings": [],
            "source_version": 1,
        },
    )

    assert [field.key for field in snapshot.fields] == list(definition.display_fields)


def test_finance_occurrence_omits_nullable_refund_identity() -> None:
    occurrence = FinanceAnomalyOccurrence(
        occurrence_fingerprint=PreviewFingerprint("a" * 64),
        definition_code="finance_import_manual_review",
        source_event_identity="finance-import-event:94",
        finance_import_row_id=94,
        finance_import_batch_id=38,
        source_version=1,
        occurred_at=__import__("datetime").datetime(2026, 8, 24),
        bounded_snapshot={
            "amount_delta_ntd": 12000,
            "affected_obligation_identities": [],
            "affected_order_identities": [],
            "domain_blockers": [],
            "finance_import_batch_id": 38,
            "finance_import_row_id": 94,
            "integrity_blocker_active": False,
            "occurred_at": "2026-08-24T00:00:00",
            "original_refund_ledger_entry_id": None,
            "reason_codes": ["manual_review"],
            "root_condition_active": True,
            "source_identity": "finance-import-row:94",
            "source_version": 1,
        },
    )

    view = _occurrence_payload(occurrence)
    assert all(field.key != "original_refund_ledger_entry_id" for field in view.bounded_snapshot.fields)
