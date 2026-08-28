"""
File: test_payout_overdue_anomaly_action_binding.py
Description: 驗證 PAYOUT-001 動作契約與 current owner identity 綁定的封閉行為。
"""

from types import SimpleNamespace

import pytest

from domains.anomalies.registry import default_anomaly_registry
from subsystems.anomalies.alert_workflow import _detail_actions


def _summary(*, snapshot=None, source_identity="obligation:42", source_domain="staff_payables"):
    return SimpleNamespace(
        projection=SimpleNamespace(
            definition_code="PAYOUT-001",
            source_identity=source_identity,
        ),
        source_domain=source_domain,
        display_snapshot=snapshot,
    )


def test_payout_descriptor_declares_exact_owner_contract() -> None:
    descriptor = default_anomaly_registry().require("PAYOUT-001").available_actions[0]

    assert descriptor.action_key == "reconcile_overdue_staff_payable"
    assert descriptor.owning_domain == "staff_payables"
    assert descriptor.form_schema_key == "staff_payables.payout_reconciliation.v1"
    assert descriptor.preview_operation == "PreviewStaffPayout"
    assert descriptor.apply_operation == "ApplyStaffPayout"
    assert descriptor.source_binding_keys == ("obligation_identity", "staff_id")
    assert descriptor.required_operator_inputs == ("finance_import_row_ids", "reason")
    assert descriptor.completion_predicate == "staff_payable_obligation_settled"
    assert descriptor.requires_preview is True
    assert descriptor.source_bindings is None


def test_payout_binding_uses_current_snapshot_identities() -> None:
    descriptor = default_anomaly_registry().require("PAYOUT-001").available_actions

    actions = _detail_actions(
        descriptor,
        _summary(snapshot={"obligation_identity": "obligation:42", "staff_id": 7}),
    )

    assert len(actions) == 1
    assert actions[0].source_bindings == {
        "obligation_identity": "obligation:42",
        "staff_id": 7,
    }


@pytest.mark.parametrize(
    "snapshot",
    (
        None,
        {},
        {"obligation_identity": "", "staff_id": 7},
        {"obligation_identity": " obligation:42", "staff_id": 7},
        {"obligation_identity": "obligation:42", "staff_id": None},
        {"obligation_identity": "obligation:42", "staff_id": True},
        {"obligation_identity": "obligation:42", "staff_id": "7"},
    ),
)
def test_payout_binding_fails_closed_for_missing_blank_or_wrong_type(snapshot) -> None:
    descriptor = default_anomaly_registry().require("PAYOUT-001").available_actions

    assert _detail_actions(descriptor, _summary(snapshot=snapshot)) == ()


def test_payout_binding_fails_closed_for_identity_drift_or_wrong_owner() -> None:
    descriptor = default_anomaly_registry().require("PAYOUT-001").available_actions

    assert _detail_actions(
        descriptor,
        _summary(
            snapshot={"obligation_identity": "obligation:43", "staff_id": 7}
        ),
    ) == ()
    assert _detail_actions(
        descriptor,
        _summary(
            snapshot={"obligation_identity": "obligation:42", "staff_id": 7},
            source_domain="client_finance",
        ),
    ) == ()
