from domains.anomalies.recovery_context import RecoveryContextFacts, assemble_recovery_action
from domains.anomalies.registry import RecoveryActionDescriptor
from domains.anomalies.root_fact_projection import finance_manual_review_recovery_actions


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
