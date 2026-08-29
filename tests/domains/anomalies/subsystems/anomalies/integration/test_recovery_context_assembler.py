"""
File: test_recovery_context_assembler.py
Description: 驗證 recovery descriptor 的精確契約與 root binding fail-closed 組裝。
"""

import pytest

from domains.anomalies.recovery_context import RecoveryContextFacts, assemble_recovery_action
from domains.anomalies.registry import RecoveryActionDescriptor, default_anomaly_registry
from domains.anomalies.root_fact_projection import finance_manual_review_recovery_actions
from subsystems.anomalies.root_fact_projection_workflow import _bound_registry_actions


def _descriptor() -> RecoveryActionDescriptor:
    return RecoveryActionDescriptor(
        action_key="collect_staff_overpayment_recovery",
        label="結清月嫂超額付款追償",
        owning_domain="staff_payables",
        preview_operation="PreviewStaffOverpaymentRecoveryCollection",
        apply_operation="ApplyStaffOverpaymentRecoveryCollection",
        requires_preview=True,
        form_schema_key="staff_payables.recovery_collection.v1",
        source_binding_keys=("finance_import_row_identity", "recovery_identity"),
        required_operator_inputs=("evidence", "reason"),
        required_capability="staff_payables.recovery.collect",
    )


def test_assembler_refuses_missing_owner_binding_or_version() -> None:
    descriptor = _descriptor()
    assert assemble_recovery_action(descriptor, None) is None
    assert assemble_recovery_action(
        descriptor,
        RecoveryContextFacts(descriptor.action_key, {"recovery_identity": "r-1"}, {"staff_payables": 1}),
    ) is None
    assert assemble_recovery_action(
        descriptor,
        RecoveryContextFacts(descriptor.action_key, {"finance_import_row_identity": "11", "recovery_identity": "r-1"}, {}),
    ) is None


def test_assembler_materializes_only_complete_typed_bindings() -> None:
    descriptor = _descriptor()
    action = assemble_recovery_action(
        descriptor,
        RecoveryContextFacts(descriptor.action_key, {"finance_import_row_identity": "11", "recovery_identity": "r-1"}, {"staff_payables": 4, "recovery": 2}),
    )
    assert action is not None
    assert action.source_bindings == {"finance_import_row_identity": "11", "recovery_identity": "r-1"}


def test_assembler_selects_declared_subset_from_richer_root_bindings() -> None:
    descriptor = _descriptor()
    action = assemble_recovery_action(
        descriptor,
        RecoveryContextFacts(
            descriptor.action_key,
            {
                "finance_import_row_identity": "11",
                "recovery_identity": "r-1",
                "unknown_root_field": "must-not-leak",
            },
            {"recovery_version": 2},
        ),
    )

    assert action is not None
    assert action.source_bindings == {
        "finance_import_row_identity": "11",
        "recovery_identity": "r-1",
    }
    assert "unknown_root_field" not in action.source_bindings


def test_assembler_rejects_unknown_declared_or_missing_root_binding() -> None:
    descriptor = RecoveryActionDescriptor(
        action_key="recovery_test_action",
        owning_domain="client_finance",
        preview_operation="PreviewRecoveryTestAction",
        apply_operation="ApplyRecoveryTestAction",
        requires_preview=True,
        source_binding_keys=("recovery_identity", "required_root_field"),
    )

    assert assemble_recovery_action(
        descriptor,
        RecoveryContextFacts(
            descriptor.action_key,
            {"recovery_identity": "r-1", "unrelated_root_field": "x"},
            {"recovery_version": 2},
        ),
    ) is None


@pytest.mark.parametrize(
    ("code", "expected_without_matching", "expected_with_matching"),
    (
        (
            "client_over_refund_recovery_open",
            {"match_client_over_refund_recovery", "adjust_client_over_refund_recovery"},
            {
                "collect_client_over_refund_recovery",
                "match_client_over_refund_recovery",
                "adjust_client_over_refund_recovery",
            },
        ),
        (
            "staff_overpayment_recovery_open",
            {"match_staff_overpayment_recovery", "adjust_staff_overpayment_recovery"},
            {
                "collect_staff_overpayment_recovery",
                "match_staff_overpayment_recovery",
                "adjust_staff_overpayment_recovery",
            },
        ),
    ),
)
def test_open_recovery_exposes_matching_and_adjustment_but_collection_needs_match(
    code, expected_without_matching, expected_with_matching
) -> None:
    definition = default_anomaly_registry().require(code)
    base_bindings = (
        {
            "account_version": 4,
            "case_no": "115000001",
            "recovery_identity": "recovery-1",
            "recovery_version": 3,
        }
        if code.startswith("client_")
        else {
            "recovery_identity": "recovery-1",
            "recovery_version": 3,
            "staff_id": 7,
            "staff_payables_version": 9,
        }
    )

    without_matching = _bound_registry_actions(
        definition.available_actions,
        {"source_version": 9, "recovery_bindings": base_bindings},
    )
    assert {action.action_key for action in without_matching} == expected_without_matching

    with_matching = _bound_registry_actions(
        definition.available_actions,
        {
            "source_version": 9,
            "recovery_bindings": {
                **base_bindings,
                "finance_import_row_identity": "7",
                "matching_identity": "matching-1",
                "matching_version": 1,
            },
        },
    )
    assert {action.action_key for action in with_matching} == expected_with_matching


def test_finance_recovery_registry_contracts_are_exact() -> None:
    registry = default_anomaly_registry()
    government = registry.require("GOVSUB-006").available_actions
    assert len(government) == 1
    disposition = government[0]
    assert (
        disposition.owning_domain,
        disposition.form_schema_key,
        disposition.preview_operation,
        disposition.apply_operation,
        disposition.required_capability,
        disposition.action_contract_version,
    ) == (
        "government_subsidy",
        "government_subsidy.overpayment.disposition.v1",
        "PreviewGovernmentSubsidyOverpaymentDisposition",
        "ApplyGovernmentSubsidyOverpaymentDisposition",
        "government_subsidy.overpayment.disposition",
        1,
    )
    assert disposition.required_operator_inputs == (
        "disposition",
        "evidence_reference",
        "offset_amounts",
        "offset_targets",
        "reason",
        "return_due_date",
    )

    expected = {
        "client_over_refund_recovery_open": {
            "match_client_over_refund_recovery": (
                "client_finance",
                "client_finance.over_refund_recovery.matching.v1",
                "PreviewClientOverRefundRecoveryMatching",
                "ApplyClientOverRefundRecoveryMatching",
                "client_finance.recovery.collect",
            ),
            "adjust_client_over_refund_recovery": (
                "client_finance",
                "client_finance.over_refund_recovery.adjustment.v1",
                "PreviewClientOverRefundRecoveryAdjustment",
                "ApplyClientOverRefundRecoveryAdjustment",
                "client_finance.recovery.adjust",
            ),
        },
        "staff_overpayment_recovery_open": {
            "match_staff_overpayment_recovery": (
                "staff_payables",
                "staff_payables.overpayment_recovery.matching.v1",
                "PreviewStaffOverpaymentRecoveryMatching",
                "ApplyStaffOverpaymentRecoveryMatching",
                "staff_payables.recovery.collect",
            ),
            "adjust_staff_overpayment_recovery": (
                "staff_payables",
                "staff_payables.overpayment_recovery.adjustment.v1",
                "PreviewStaffOverpaymentRecoveryAdjustment",
                "ApplyStaffOverpaymentRecoveryAdjustment",
                "staff_payables.recovery.adjust",
            ),
        },
    }
    for code, contracts in expected.items():
        descriptors = {
            descriptor.action_key: descriptor
            for descriptor in registry.require(code).available_actions
        }
        for action_key, contract in contracts.items():
            descriptor = descriptors[action_key]
            assert (
                descriptor.owning_domain,
                descriptor.form_schema_key,
                descriptor.preview_operation,
                descriptor.apply_operation,
                descriptor.required_capability,
                descriptor.action_contract_version,
            ) == (*contract, 1)
            assert descriptor.required_operator_inputs in {
                ("evidence_reference", "finance_import_row_identity", "reason"),
                ("adjustment_amount", "evidence_reference", "reason"),
            }


def test_manual_review_exposes_typed_recovery_matching_stages() -> None:
    actions = finance_manual_review_recovery_actions("finance-import-row:17", 4)

    assert [action.action_key for action in actions] == [
        "classify_and_post_bank_row",
        "match_client_over_refund_recovery",
        "apply_client_refund_overage",
        "apply_client_receipt_overage",
        "match_staff_overpayment_recovery",
        "apply_staff_payout_difference",
        "reconcile_government_overpayment_return",
    ]
    for action in actions:
        assert action.source_bindings == {
            "finance_import_row_identity": "finance-import-row:17",
            "source_version": 4,
        }
