"""
File: registry.py
Description: 定義 canonical anomaly 契約並將來源事實歸約為 current-state 警示。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Mapping

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer

_IDENTITY_MAXIMUM_LENGTH = 191
_FINANCE_SOURCE_DOMAINS = frozenset(
    {"client_finance", "finance_import", "government_subsidy", "staff_payables"}
)


class AnomalySeverity(StrEnum):
    WARNING = "warning"
    BLOCKING = "blocking"


class AnomalyProjectionKind(StrEnum):
    CURRENT_STATE = "current_state"
    FINANCE_OCCURRENCE = "finance_occurrence"


class AlertWorkflowStatus(StrEnum):
    OPEN = "open"
    CLAIMED = "claimed"
    RESOLVED = "resolved"


@dataclass(frozen=True, slots=True)
class RecoveryActionDescriptor:
    """Declarative recovery contract; it never carries derived money or an endpoint."""

    action_key: str
    owning_domain: str
    preview_operation: str
    requires_preview: bool
    label: str = ""
    form_schema_key: str = "recovery.unsupported.v1"
    source_binding_keys: tuple[str, ...] = ()
    source_bindings: Mapping[str, str | int] | None = None
    required_operator_inputs: tuple[str, ...] = ()
    apply_operation: str | None = None
    required_capability: str | None = None
    completion_predicate: str = "source_predicate_cleared"
    action_contract_version: int = 1

    def __post_init__(self) -> None:
        _validate_identity(self.action_key, "recovery action key")
        _validate_identity(self.owning_domain, "recovery owning domain")
        _validate_identity(self.preview_operation, "recovery preview operation")
        _validate_identity(self.form_schema_key, "recovery form schema key")
        _validate_identity(self.completion_predicate, "recovery completion predicate")
        if self.action_contract_version < 1:
            raise ValueError("recovery action contract version must be positive")
        if self.source_binding_keys != tuple(sorted(set(self.source_binding_keys))):
            raise ValueError("recovery source binding keys must be sorted and unique")
        if self.required_operator_inputs != tuple(sorted(set(self.required_operator_inputs))):
            raise ValueError("recovery operator inputs must be sorted and unique")
        for key in self.source_binding_keys + self.required_operator_inputs:
            _validate_identity(key, "recovery action field")
        if self.source_bindings is not None:
            if set(self.source_bindings) != set(self.source_binding_keys):
                raise ValueError("recovery source bindings must match declared keys")
            for key, value in self.source_bindings.items():
                _validate_identity(key, "recovery source binding key")
                if isinstance(value, bool) or not isinstance(value, (str, int)):
                    raise ValueError("recovery source binding value is invalid")
        if not self.label:
            object.__setattr__(self, "label", self.action_key)
        _validate_identity(self.label, "recovery action label")
        if self.apply_operation is not None:
            _validate_identity(self.apply_operation, "recovery apply operation")
        if self.required_capability is not None:
            _validate_identity(self.required_capability, "recovery capability")

    @property
    def action_code(self) -> str:
        """Temporary read compatibility for callers not yet migrated to action_key."""
        return self.action_key

    @property
    def command_name(self) -> str:
        """Temporary read compatibility for callers not yet migrated to preview_operation."""
        return self.preview_operation


# Compatibility alias prevents old projection readers from becoming untyped raw links.
DomainActionLink = RecoveryActionDescriptor


@dataclass(frozen=True, slots=True)
class AnomalyDefinition:
    code: str
    source_domain: str
    fingerprint_fields: tuple[str, ...]
    severity: AnomalySeverity
    projection_kind: AnomalyProjectionKind
    available_actions: tuple[RecoveryActionDescriptor, ...]
    no_automated_recovery: bool = False
    display_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_identity(self.code, "anomaly code")
        _validate_identity(self.source_domain, "source domain")
        if self.fingerprint_fields != tuple(
            sorted(set(self.fingerprint_fields))
        ):
            raise ValueError("fingerprint fields must be sorted and unique")
        if self.display_fields != tuple(sorted(set(self.display_fields))):
            raise ValueError("display fields must be sorted and unique")
        if not isinstance(self.no_automated_recovery, bool):
            raise TypeError("no automated recovery must be boolean")
        if self.source_domain in _FINANCE_SOURCE_DOMAINS:
            _validate_finance_recovery_contract(self)


@dataclass(frozen=True, slots=True)
class DesiredAlertState:
    definition_code: str
    source_identity: str
    source_version: int
    active: bool
    fingerprint_values: Mapping[str, str]

    def __post_init__(self) -> None:
        _validate_identity(self.definition_code, "anomaly code")
        _validate_identity(self.source_identity, "source identity")
        require_nonnegative_integer(self.source_version, "source version")
        if not isinstance(self.active, bool):
            raise TypeError("desired alert active flag must be bool")


@dataclass(frozen=True, slots=True)
class CurrentAlertProjection:
    fingerprint: PreviewFingerprint
    definition_code: str
    source_identity: str
    source_version: int
    predicate_active: bool
    workflow_status: AlertWorkflowStatus
    workflow_version: int


class AnomalyDefinitionRegistry:
    def __init__(self, definitions: tuple[AnomalyDefinition, ...]) -> None:
        self._definitions = {item.code: item for item in definitions}
        if len(self._definitions) != len(definitions):
            raise ValueError("anomaly definition codes must be unique")
        _validate_recovery_action_keys(definitions)

    def require(self, code: str) -> AnomalyDefinition:
        try:
            return self._definitions[code]
        except KeyError as exc:
            raise ValueError("anomaly_definition_not_found") from exc

    def fingerprint(self, desired: DesiredAlertState) -> PreviewFingerprint:
        definition = self.require(desired.definition_code)
        _validate_fingerprint_values(definition, desired.fingerprint_values)
        return fingerprint_payload(
            {
                "definition_code": definition.code,
                "source_identity": desired.source_identity,
                "fingerprint_values": dict(desired.fingerprint_values),
            }
        )

    def available_actions(self, code: str) -> tuple[RecoveryActionDescriptor, ...]:
        return self.require(code).available_actions


def reduce_current_alert(
    registry: AnomalyDefinitionRegistry,
    desired: DesiredAlertState,
    current: CurrentAlertProjection | None,
) -> CurrentAlertProjection | None:
    fingerprint = registry.fingerprint(desired)
    if current is None:
        return _new_projection(desired, fingerprint) if desired.active else None
    _validate_current_identity(current, desired, fingerprint)
    workflow_status = _reduced_status(current.workflow_status, desired.active)
    changed = _projection_changed(current, desired, workflow_status)
    return replace(
        current,
        source_version=desired.source_version,
        predicate_active=desired.active,
        workflow_status=workflow_status,
        workflow_version=current.workflow_version + (1 if changed else 0),
    )


def claim_alert(
    current: CurrentAlertProjection,
    expected_version: int,
) -> CurrentAlertProjection:
    _require_workflow_version(current, expected_version)
    if not current.predicate_active or current.workflow_status is not AlertWorkflowStatus.OPEN:
        raise ValueError("anomaly_claim_conflict")
    return replace(
        current,
        workflow_status=AlertWorkflowStatus.CLAIMED,
        workflow_version=current.workflow_version + 1,
    )


def resolve_alert_workflow(
    current: CurrentAlertProjection,
    expected_version: int,
    reason: str,
) -> CurrentAlertProjection:
    _require_workflow_version(current, expected_version)
    require_canonical_text(reason, "resolution reason", 500)
    return replace(
        current,
        workflow_status=AlertWorkflowStatus.RESOLVED,
        workflow_version=current.workflow_version + 1,
    )


def default_anomaly_registry() -> AnomalyDefinitionRegistry:
    return AnomalyDefinitionRegistry(
        (
            _schedule_coverage_definition(),
            _staff_payout_overdue_definition(),
            _staff_payout_late_change_definition(),
            _staff_payout_bank_master_definition(),
            _government_subsidy_no_unique_batch_definition(),
            _government_subsidy_ambiguous_allocation_definition(),
            _government_subsidy_integrity_definition(),
            _government_subsidy_reversal_definition(),
            _government_subsidy_assignment_drift_definition(),
            _government_subsidy_overpayment_definition(),
            _government_return_outbound_overage_definition(),
            _client_over_refund_recovery_open_definition(),
            _client_refund_underpayment_definition(),
            _staff_overpayment_recovery_open_definition(),
            _staff_payout_difference_definition("staff_payout_underpayment"),
            _staff_payout_difference_definition("staff_payout_overpayment"),
            _beclass_validation_definition(),
            _beclass_identity_conflict_definition(),
            _finance_manual_review_definition(),
            _client_refund_return_definition(),
            _finance_integrity_definition(),
            _hcm_validation_definition(),
            _historical_order_review_definition(),
            _order_matching_stage_definition("ORDER-001"),
            _order_matching_stage_definition("ORDER-002"),
            _order_matching_stage_definition("ORDER-003"),
            _order_matching_stage_definition("ORDER-004"),
            _beclass_missing_definition(),
            _resume_not_sent_definition(),
            _client_receivable_overdue_definition(),
            _client_payable_overdue_definition(),
            _subsidy_return_overdue_definition(),
            _subsidy_advance_due_definition(),
            _schedule_holiday_undecided_definition(),
            _schedule_replaced_assignment_definition(),
            _schedule_overlap_definition(),
            _schedule_holiday_preference_conflict_definition(),
            _client_missing_line_definition(),
            _staff_missing_line_definition(),
            _line_notification_delivery_definition(),
            _line_task_no_reply_definition(),
            _line_identity_conflict_definition(),
        )
    )


def _order_matching_stage_definition(code: str) -> AnomalyDefinition:
    return AnomalyDefinition(
        code=code,
        source_domain="order_matching",
        fingerprint_fields=("case_no",),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(
            DomainActionLink(
                "navigate_to_matching",
                "order_matching",
                "NavigateToMultiCaregiverMatching",
                False,
            ),
        ),
        display_fields=("case_no",),
    )


def _beclass_missing_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="BECLASS-001",
        source_domain="beclass_completeness",
        fingerprint_fields=("case_no",),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(),
        display_fields=("case_no",),
    )


def _historical_order_review_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="HISTORICAL-ORDER-001",
        source_domain="orders",
        fingerprint_fields=("review_identity",),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(),
        no_automated_recovery=True,
        display_fields=("issue_codes", "masked_case_identity", "review_identity"),
    )


def _resume_not_sent_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="DOC-SEND-001",
        source_domain="document_delivery",
        fingerprint_fields=("case_no",),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(
            DomainActionLink(
                "send_resume",
                "document_delivery",
                "SendResumeToClient",
                False,
            ),
        ),
        display_fields=("case_no",),
    )


def _client_receivable_overdue_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="RECEIVABLE-001",
        source_domain="client_receivable",
        fingerprint_fields=("case_no",),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(),
        display_fields=("action", "case_no", "overdue_obligations"),
    )


def _subsidy_return_overdue_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="RETURN-001",
        source_domain="subsidy_return",
        fingerprint_fields=("case_no",),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(),
        display_fields=("action", "case_no", "overdue_obligations"),
    )


def _client_payable_overdue_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="CLIENTPAYABLE-001",
        source_domain="client_payable",
        fingerprint_fields=("case_no",),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(),
        display_fields=("action", "case_no", "overdue_obligations"),
    )


def _subsidy_advance_due_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="SUBSIDYADVANCE-001",
        source_domain="client_finance",
        fingerprint_fields=("case_no",),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(),
        no_automated_recovery=True,
        display_fields=("action", "advance_candidates", "case_no"),
    )


def _schedule_holiday_undecided_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="SCHEDULE-001",
        source_domain="scheduling",
        fingerprint_fields=("holiday_date", "staff_id"),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(),
        display_fields=("case_no", "holiday_date", "staff_id", "staff_name"),
    )


def _schedule_replaced_assignment_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="SCHEDULE-002",
        source_domain="scheduling",
        fingerprint_fields=("assignment_id",),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(),
        display_fields=("assignment_id", "case_no", "staff_id"),
    )


def _schedule_overlap_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="SCHEDULE-003",
        source_domain="scheduling",
        fingerprint_fields=("assignment_id_a", "assignment_id_b"),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(),
        display_fields=("assignment_id_a", "assignment_id_b", "staff_id", "staff_name"),
    )


def _schedule_holiday_preference_conflict_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="SCHEDULE-005",
        source_domain="scheduling",
        fingerprint_fields=("staff_id", "work_date"),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(),
        display_fields=("case_no", "staff_id", "staff_name", "work_date"),
    )


def _client_missing_line_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="LINE-001",
        source_domain="line_binding",
        fingerprint_fields=("case_no",),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(),
        display_fields=("case_no",),
    )


def _staff_missing_line_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="LINE-005",
        source_domain="line_binding",
        fingerprint_fields=("case_no",),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(),
        display_fields=("case_no",),
    )


def _line_notification_delivery_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="LINE-006",
        source_domain="line_notification",
        fingerprint_fields=("case_no", "notification_reason"),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(
            DomainActionLink(
                "review_notification_timeline",
                "line_notification",
                "QueryLineNotificationTimeline",
                False,
            ),
        ),
        display_fields=("case_no", "notification_reason"),
    )


def _line_task_no_reply_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="LINE-002",
        source_domain="line_binding",
        fingerprint_fields=("task_id",),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(),
        display_fields=("task_id", "to_user_id"),
    )


def _line_identity_conflict_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="LINE-004",
        source_domain="line_binding",
        fingerprint_fields=("line_user_id",),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(),
        display_fields=("line_user_id",),
    )


def _schedule_coverage_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="SCHEDULE-006",
        source_domain="scheduling",
        fingerprint_fields=("case_no", "generation"),
        severity=AnomalySeverity.BLOCKING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(
            DomainActionLink(
                "correct_official_service_dates",
                "scheduling",
                "PreviewCorrectOfficialServiceDates",
                True,
            ),
        ),
        display_fields=(
            "affected_obligation_identities",
            "affected_order_identities",
            "amount_delta_ntd",
            "domain_blockers",
            "finance_import_batch_id",
            "finance_import_row_id",
            "integrity_blocker_active",
            "reason_codes",
            "root_condition_active",
        ),
    )


def _staff_payout_overdue_definition() -> AnomalyDefinition:
    return _staff_payables_definition(
        code="PAYOUT-001",
        fingerprint_fields=("obligation_identity",),
        display_fields=(
            "amount_due_ntd",
            "balance_ntd",
            "due_date",
            "obligation_identity",
            "staff_id",
        ),
        severity=AnomalySeverity.WARNING,
        action_code="review_overdue_staff_payable",
    )


def _staff_payout_late_change_definition() -> AnomalyDefinition:
    return _staff_payables_definition(
        code="PAYOUT-002",
        fingerprint_fields=("obligation_identity", "source_event_identity"),
        display_fields=(
            "after_amount_ntd",
            "before_amount_ntd",
            "obligation_identity",
            "original_due_date",
            "source_event_identity",
            "staff_id",
        ),
        severity=AnomalySeverity.BLOCKING,
        action_code="review_late_staff_payable_change",
    )


def _staff_payout_bank_master_definition() -> AnomalyDefinition:
    return _staff_payables_definition(
        code="PAYOUT-003",
        fingerprint_fields=("staff_id",),
        display_fields=(
            "bank_account_issue",
            "obligation_identities",
            "staff_id",
        ),
        severity=AnomalySeverity.BLOCKING,
        action_code="review_staff_bank_account",
    )


def _staff_payables_definition(
    *,
    code: str,
    fingerprint_fields: tuple[str, ...],
    display_fields: tuple[str, ...],
    severity: AnomalySeverity,
    action_code: str,
) -> AnomalyDefinition:
    return AnomalyDefinition(
        code=code,
        source_domain="staff_payables",
        fingerprint_fields=fingerprint_fields,
        severity=severity,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(
            DomainActionLink(
                action_code,
                "staff_payables",
                "QueryStaffPayables",
                False,
            ),
        ),
        display_fields=display_fields,
    )


def _government_subsidy_no_unique_batch_definition():
    return _government_subsidy_definition(
        "GOVSUB-001",
        ("bank_fact_identity",),
        ("bank_fact_identity", "candidate_batch_ids"),
        "review_government_subsidy_receipt",
        "PreviewGovernmentSubsidyReceipt",
        True,
    )


def _government_subsidy_ambiguous_allocation_definition():
    return _government_subsidy_definition(
        "GOVSUB-002",
        ("bank_fact_identity", "batch_id"),
        ("bank_fact_identity", "batch_id", "item_outstanding"),
        "allocate_government_subsidy_receipt",
        "PreviewGovernmentSubsidyReceipt",
        True,
    )


def _government_subsidy_integrity_definition():
    return _government_subsidy_definition(
        "GOVSUB-003",
        ("batch_id", "integrity_revision"),
        ("batch_id", "integrity_blockers", "integrity_revision"),
        "review_government_subsidy_integrity",
        "QueryGovernmentSubsidyBatch",
        False,
    )


def _government_subsidy_reversal_definition():
    return _government_subsidy_definition(
        "GOVSUB-004",
        ("reversal_bank_fact_identity", "source_receipt_id"),
        (
            "remaining_reversible_ntd",
            "reversal_bank_fact_identity",
            "source_receipt_id",
        ),
        "review_government_subsidy_reversal",
        "PreviewGovernmentSubsidyReversal",
        True,
    )


def _government_subsidy_assignment_drift_definition():
    return _government_subsidy_definition(
        "GOVSUB-005",
        ("assignment_id", "batch_id", "claim_item_id"),
        (
            "assignment_id",
            "batch_id",
            "claim_item_id",
            "drift_fields",
        ),
        "review_government_subsidy_claim_facts",
        "QueryGovernmentSubsidyBatch",
        False,
    )


def _government_subsidy_overpayment_definition():
    return AnomalyDefinition(
        code="GOVSUB-006",
        source_domain="government_subsidy",
        fingerprint_fields=("overpayment_identity",),
        severity=AnomalySeverity.BLOCKING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(
            RecoveryActionDescriptor(
                action_key="dispose_government_subsidy_overpayment",
                label="處置政府補助溢撥",
                owning_domain="government_subsidy",
                preview_operation="PreviewGovernmentSubsidyOverpaymentDisposition",
                apply_operation="ApplyGovernmentSubsidyOverpaymentDisposition",
                requires_preview=True,
                form_schema_key="government_subsidy.overpayment.disposition.v1",
                source_binding_keys=("overpayment_identity", "overpayment_version"),
                required_operator_inputs=("disposition", "evidence_reference", "reason"),
                required_capability="government_subsidy.overpayment.disposition",
                completion_predicate="government_subsidy_overpayment_disposed",
            ),
        ),
        display_fields=("overpayment_identity",),
    )


def _government_return_outbound_overage_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="GOVSUB-007",
        source_domain="government_subsidy",
        fingerprint_fields=("payable_identity",),
        severity=AnomalySeverity.BLOCKING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(),
        no_automated_recovery=True,
        display_fields=("bank_amount_ntd", "excess_amount_ntd", "overpayment_identity", "payable_identity"),
    )


def _client_over_refund_recovery_open_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="client_over_refund_recovery_open",
        source_domain="client_finance",
        fingerprint_fields=("recovery_identity",),
        severity=AnomalySeverity.BLOCKING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(
            RecoveryActionDescriptor(
                action_key="collect_client_over_refund_recovery",
                label="收回客戶退款超額追償",
                owning_domain="client_finance",
                preview_operation="PreviewCollectMatchedClientOverRefundRecovery",
                apply_operation="ApplyCollectMatchedClientOverRefundRecovery",
                requires_preview=True,
                form_schema_key="client_finance.over_refund_recovery.collection.v1",
                source_binding_keys=(
                    "account_version",
                    "case_no",
                    "finance_import_row_identity",
                    "matching_identity",
                    "matching_version",
                    "recovery_identity",
                    "recovery_version",
                ),
                required_operator_inputs=("evidence", "reason"),
                required_capability="client_finance.recovery.collect",
                completion_predicate="client_over_refund_recovery_remaining_updated",
            ),
        ),
        display_fields=("recovery_identity",),
    )


def _client_refund_underpayment_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="client_refund_underpayment", source_domain="client_finance",
        fingerprint_fields=("underpayment_identity",), severity=AnomalySeverity.BLOCKING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE, available_actions=(),
        no_automated_recovery=True,
        display_fields=("underpayment_identity",),
    )


def _staff_overpayment_recovery_open_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="staff_overpayment_recovery_open", source_domain="staff_payables",
        fingerprint_fields=("recovery_identity",), severity=AnomalySeverity.BLOCKING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(RecoveryActionDescriptor(
            action_key="collect_staff_overpayment_recovery", label="收回月嫂超額付款追償",
            owning_domain="staff_payables", preview_operation="PreviewCollectMatchedStaffOverpaymentRecovery",
            apply_operation="ApplyCollectMatchedStaffOverpaymentRecovery", requires_preview=True,
            form_schema_key="staff_payables.overpayment_recovery.collection.v1",
            source_binding_keys=("finance_import_row_identity", "matching_identity", "matching_version", "recovery_identity", "recovery_version", "staff_id", "staff_payables_version"),
            required_operator_inputs=("evidence", "reason"), required_capability="staff_payables.recovery.collect",
            completion_predicate="staff_overpayment_recovery_remaining_updated",
        ),), display_fields=("recovery_identity", "staff_id"),
    )


def _staff_payout_difference_definition(code: str) -> AnomalyDefinition:
    return AnomalyDefinition(
        code=code, source_domain="staff_payables", fingerprint_fields=("payout_difference_identity",),
        severity=AnomalySeverity.BLOCKING, projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(), no_automated_recovery=True,
        display_fields=("payout_difference_identity", "staff_id"),
    )




def _government_subsidy_definition(
    code,
    fingerprint_fields,
    display_fields,
    action_code,
    command_name,
    requires_preview,
):
    return AnomalyDefinition(
        code=code,
        source_domain="government_subsidy",
        fingerprint_fields=fingerprint_fields,
        severity=AnomalySeverity.BLOCKING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(
            DomainActionLink(
                action_code,
                "government_subsidy",
                command_name,
                requires_preview,
            ),
        ),
        display_fields=display_fields,
    )


def _beclass_validation_definition() -> AnomalyDefinition:
    return _beclass_import_definition(
        code="IMPORT-001",
        severity=AnomalySeverity.BLOCKING,
        action_code="review_import_validation",
    )


def _beclass_identity_conflict_definition() -> AnomalyDefinition:
    return _beclass_import_definition(
        code="IMPORT-003",
        severity=AnomalySeverity.WARNING,
        action_code="review_import_identity_conflict",
    )


def _beclass_import_definition(
    *,
    code: str,
    severity: AnomalySeverity,
    action_code: str,
) -> AnomalyDefinition:
    return AnomalyDefinition(
        code=code,
        source_domain="case_import",
        fingerprint_fields=("entity_kind", "review_item_id"),
        severity=severity,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(
            DomainActionLink(
                action_code,
                "case_import",
                "QueryBeClassImportReviewItem",
                False,
            ),
        ),
        display_fields=(
            "entity_kind",
            "error_codes",
            "masked_identifier",
            "review_item_id",
            "source_row",
            "source_sheet",
            "version",
        ),
    )


def _finance_manual_review_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="finance_import_manual_review",
        source_domain="finance_import",
        fingerprint_fields=("finance_import_row_id",),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.FINANCE_OCCURRENCE,
        available_actions=(
            RecoveryActionDescriptor(
                action_key="classify_and_post_bank_row",
                label="分類並正式入帳銀行流水",
                owning_domain="finance_import",
                preview_operation="PreviewCorrectAndPostFinanceImportRow",
                apply_operation="CorrectAndPostFinanceImportRow",
                requires_preview=True,
                form_schema_key="finance_import.correction.v1",
                source_binding_keys=("finance_import_row_identity", "source_version"),
                required_operator_inputs=(
                    "classification_type",
                    "evidence",
                    "reason",
                    "target_obligation_identities",
                ),
                required_capability="finance_import.correct_and_post",
                completion_predicate="finance_import_manual_review_cleared",
            ),
        ),
        display_fields=(
            "affected_obligation_identities",
            "affected_order_identities",
            "amount_delta_ntd",
            "domain_blockers",
            "finance_import_batch_id",
            "finance_import_row_id",
            "integrity_blocker_active",
            "reason_codes",
            "root_condition_active",
        ),
    )


def _client_refund_return_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="CLIENTREFUND-001",
        source_domain="finance_import",
        fingerprint_fields=(
            "finance_import_row_id",
            "original_refund_ledger_entry_id",
        ),
        severity=AnomalySeverity.BLOCKING,
        projection_kind=AnomalyProjectionKind.FINANCE_OCCURRENCE,
        available_actions=(
            RecoveryActionDescriptor(
                action_key="classify_client_refund_return",
                label="處理客戶退款退匯",
                owning_domain="finance_import",
                preview_operation="PreviewCorrectAndPostClientRefundReturn",
                apply_operation="CorrectAndPostClientRefundReturn",
                requires_preview=True,
                form_schema_key="finance_import.correction.v1",
                source_binding_keys=("finance_import_row_identity", "source_version"),
                required_operator_inputs=(
                    "evidence",
                    "reason",
                    "refund_ledger_entry_identity",
                    "target_obligation_identities",
                ),
                required_capability="finance_import.correct_and_post",
                completion_predicate="client_refund_return_cleared",
            ),
        ),
    )


def _finance_integrity_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="IMPORT-006",
        source_domain="finance_import",
        fingerprint_fields=("batch_id",),
        severity=AnomalySeverity.BLOCKING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(
            DomainActionLink(
                "retry_projector",
                "anomalies",
                "RetryAnomalyProjector",
                False,
            ),
        ),
    )


def _new_projection(desired, fingerprint) -> CurrentAlertProjection:
    return CurrentAlertProjection(
        fingerprint=fingerprint,
        definition_code=desired.definition_code,
        source_identity=desired.source_identity,
        source_version=desired.source_version,
        predicate_active=True,
        workflow_status=AlertWorkflowStatus.OPEN,
        workflow_version=0,
    )


def _reduced_status(current_status, desired_active):
    if not desired_active:
        return AlertWorkflowStatus.RESOLVED
    if current_status is AlertWorkflowStatus.RESOLVED:
        return AlertWorkflowStatus.OPEN
    return current_status


def _projection_changed(current, desired, workflow_status):
    return (
        current.source_version != desired.source_version
        or current.predicate_active != desired.active
        or current.workflow_status is not workflow_status
    )


def _validate_current_identity(current, desired, fingerprint) -> None:
    if current.fingerprint != fingerprint:
        raise ValueError("anomaly_projection_data_integrity_violation")
    if current.definition_code != desired.definition_code:
        raise ValueError("anomaly_projection_data_integrity_violation")
    if current.source_identity != desired.source_identity:
        raise ValueError("anomaly_projection_data_integrity_violation")


def _validate_fingerprint_values(definition, values) -> None:
    if set(values) != set(definition.fingerprint_fields):
        raise ValueError("anomaly_source_fact_invalid")
    for field, value in values.items():
        _validate_identity(field, "fingerprint field")
        _validate_identity(value, "fingerprint value")


def _require_workflow_version(current, expected_version) -> None:
    require_nonnegative_integer(expected_version, "expected workflow version")
    if current.workflow_version != expected_version:
        raise ValueError("anomaly_version_conflict")


def _validate_identity(value: str, field_name: str) -> None:
    require_canonical_text(value, field_name, _IDENTITY_MAXIMUM_LENGTH)


def _validate_recovery_action_keys(definitions: tuple[AnomalyDefinition, ...]) -> None:
    contracts: dict[tuple[str, int], RecoveryActionDescriptor] = {}
    for definition in definitions:
        for action in definition.available_actions:
            identity = (action.action_key, action.action_contract_version)
            previous = contracts.get(identity)
            if previous is not None and previous != action:
                raise ValueError("recovery action contract key is ambiguous")
            contracts[identity] = action


def _validate_finance_recovery_contract(definition: AnomalyDefinition) -> None:
    has_actions = bool(definition.available_actions)
    if has_actions == definition.no_automated_recovery:
        raise ValueError("finance recovery contract must declare actions or state-only")


def _hcm_validation_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="IMPORT-004",
        source_domain="case_import",
        fingerprint_fields=("case_no",),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(),
    )
