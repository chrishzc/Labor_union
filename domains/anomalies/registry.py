"""
File: registry.py
Description: 定義 canonical anomaly 契約與有限 owner recovery action descriptors。
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


class AlertWorkflowStatus(StrEnum):
    OPEN = "open"
    CLAIMED = "claimed"
    RESOLVED = "resolved"


class AnomalyDefinitionLifecycle(StrEnum):
    ACTIVE = "active"
    WORK_ITEM = "work_item"
    RETIRED = "retired"
    AUDIT_ONLY = "audit_only"


@dataclass(frozen=True, slots=True)
class AutoResolutionContract:
    """Bind automatic alert removal to one approved owner rulebook oracle."""

    owner_rulebook_reference: str
    terminal_predicate: str
    contract_version: int = 1

    def __post_init__(self) -> None:
        require_canonical_text(
            self.owner_rulebook_reference, "auto-resolution rulebook reference", 191
        )
        _validate_identity(self.terminal_predicate, "auto-resolution terminal predicate")
        if self.contract_version < 1:
            raise ValueError("auto-resolution contract version must be positive")


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
    lifecycle: AnomalyDefinitionLifecycle = AnomalyDefinitionLifecycle.ACTIVE

    def __post_init__(self) -> None:
        _validate_identity(self.code, "anomaly code")
        _validate_identity(self.source_domain, "source domain")
        if not isinstance(self.lifecycle, AnomalyDefinitionLifecycle):
            raise TypeError("anomaly definition lifecycle must be AnomalyDefinitionLifecycle")
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

    @property
    def target_lifecycle(self) -> AnomalyDefinitionLifecycle:
        """Return the approved product target, not migration cutover state."""
        return self.lifecycle


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
        unknown_contracts = set(_AUTO_RESOLUTION_CONTRACTS) - set(self._definitions)
        if unknown_contracts:
            raise ValueError("auto-resolution contract references an unknown anomaly code")

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

    def codes(self) -> tuple[str, ...]:
        return tuple(sorted(self._definitions))

    def active_codes(self) -> tuple[str, ...]:
        """Return target-active codes; this is not a producer-cutover receipt."""
        return self._codes_for_lifecycle(AnomalyDefinitionLifecycle.ACTIVE)

    def target_active_codes(self) -> tuple[str, ...]:
        """Explicit alias used where target and operational state may diverge."""
        return self.active_codes()

    def work_item_codes(self) -> tuple[str, ...]:
        return self._codes_for_lifecycle(AnomalyDefinitionLifecycle.WORK_ITEM)

    def retired_codes(self) -> tuple[str, ...]:
        return self._codes_for_lifecycle(AnomalyDefinitionLifecycle.RETIRED)

    def audit_only_codes(self) -> tuple[str, ...]:
        return self._codes_for_lifecycle(AnomalyDefinitionLifecycle.AUDIT_ONLY)

    def reclassification_codes(self) -> tuple[str, ...]:
        """Return target-non-active codes eligible for the approved migration."""
        return tuple(
            sorted(
                {
                    *self.work_item_codes(),
                    *self.retired_codes(),
                    *self.audit_only_codes(),
                }
            )
        )

    def _codes_for_lifecycle(
        self, lifecycle: AnomalyDefinitionLifecycle
    ) -> tuple[str, ...]:
        return tuple(
            sorted(
                definition.code
                for definition in self._definitions.values()
                if definition.lifecycle is lifecycle
            )
        )

    def auto_resolution_contract(self, code: str) -> AutoResolutionContract | None:
        self.require(code)
        return _AUTO_RESOLUTION_CONTRACTS.get(code)


def reduce_current_alert(
    registry: AnomalyDefinitionRegistry,
    desired: DesiredAlertState,
    current: CurrentAlertProjection | None,
) -> CurrentAlertProjection | None:
    fingerprint = registry.fingerprint(desired)
    if current is None:
        return _new_projection(desired, fingerprint) if desired.active else None
    _validate_current_identity(current, desired, fingerprint)
    effective_desired = _rulebook_guarded_desired(registry, current, desired)
    workflow_status = _reduced_status(
        current.workflow_status, effective_desired.active
    )
    changed = _projection_changed(current, effective_desired, workflow_status)
    return replace(
        current,
        source_version=effective_desired.source_version,
        predicate_active=effective_desired.active,
        workflow_status=workflow_status,
        workflow_version=current.workflow_version + (1 if changed else 0),
    )


def _rulebook_guarded_desired(
    registry: AnomalyDefinitionRegistry,
    current: CurrentAlertProjection,
    desired: DesiredAlertState,
) -> DesiredAlertState:
    if auto_resolution_blocked(registry, current, desired):
        return replace(desired, active=True)
    return desired


def auto_resolution_blocked(
    registry: AnomalyDefinitionRegistry,
    current: CurrentAlertProjection,
    desired: DesiredAlertState,
) -> bool:
    return (
        current.predicate_active
        and not desired.active
        and registry.auto_resolution_contract(desired.definition_code) is None
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
            _line_notification_delivery_definition(),
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
        lifecycle=AnomalyDefinitionLifecycle.WORK_ITEM,
    )


def _beclass_missing_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="BECLASS-001",
        source_domain="beclass_completeness",
        fingerprint_fields=("case_no",),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(
            RecoveryActionDescriptor(
                action_key="import_client_beclass_counterpart",
                label="匯入對應的客戶BeClass資料",
                owning_domain="case_import",
                preview_operation="PreviewClientBeClassWorkbook",
                apply_operation="ApplyClientBeClassWorkbook",
                requires_preview=True,
                form_schema_key="case_import.client_beclass_workbook.v1",
                source_binding_keys=("case_no", "source_version"),
                required_operator_inputs=("workbook",),
                completion_predicate="case_import_pairing_unique_and_consistent",
            ),
        ),
        display_fields=("case_no",),
    )


def _historical_order_review_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="HISTORICAL-ORDER-001",
        source_domain="orders",
        fingerprint_fields=("review_identity",),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(
            RecoveryActionDescriptor(
                action_key="reimport_corrected_historical_order_review",
                owning_domain="orders",
                preview_operation="PreviewHistoricalOrderReviewRemediation",
                apply_operation="ApplyHistoricalOrderReviewRemediation",
                requires_preview=True,
                label="上傳更正後的單筆歷史訂單",
                form_schema_key="orders.historical_review_remediation.v1",
                source_binding_keys=("review_identity", "review_version"),
                required_operator_inputs=("evidence", "reason", "workbook"),
                required_capability="orders.historical_review.remediate",
                completion_predicate="historical_order_prior_review_disposition_recorded",
                action_contract_version=1,
            ),
        ),
        no_automated_recovery=True,
        display_fields=("issue_codes", "masked_case_identity", "review_identity"),
    )


def _historical_baseline_roots_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="HISTORICAL-BASELINE-ROOTS-001",
        source_domain="historical_baseline",
        fingerprint_fields=("umbrella_identity",),
        severity=AnomalySeverity.BLOCKING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(),
        display_fields=(
            "active_count",
            "case_no",
            "earliest_blocked_step",
            "projection_fingerprint",
            "repair_referrals",
        ),
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
        lifecycle=AnomalyDefinitionLifecycle.WORK_ITEM,
    )


def _client_receivable_overdue_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="RECEIVABLE-001",
        source_domain="client_receivable",
        fingerprint_fields=("case_no",),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(
            RecoveryActionDescriptor(
                action_key="reconcile_client_receivable",
                label="核銷逾期客戶應收",
                owning_domain="client_finance",
                preview_operation="PreviewClientReceiptReconciliation",
                apply_operation="ApplyClientReceiptReconciliation",
                requires_preview=True,
                form_schema_key="client_finance.receivable_reconciliation.v1",
                source_binding_keys=("account_version", "case_no"),
                required_operator_inputs=(
                    "bank_fact_identities",
                    "obligation_identities",
                    "payment_stage",
                    "reason",
                ),
                completion_predicate="client_receivable_overdue_obligations_cleared",
            ),
        ),
        display_fields=("action", "case_no", "overdue_obligations", "resolution_condition"),
    )


def _subsidy_return_overdue_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="RETURN-001",
        source_domain="subsidy_return",
        fingerprint_fields=("case_no",),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(
            RecoveryActionDescriptor(
                action_key="settle_client_subsidy_return",
                label="核銷逾期客戶補助退還",
                owning_domain="client_finance",
                preview_operation="PreviewClientSubsidyReturn",
                apply_operation="ApplyClientSubsidyReturn",
                requires_preview=True,
                form_schema_key="client_finance.subsidy_return.v1",
                source_binding_keys=("account_version", "case_no"),
                required_operator_inputs=("bank_fact_identities", "obligation_identities", "reason"),
                completion_predicate="client_subsidy_return_overdue_obligations_cleared",
            ),
        ),
        display_fields=("action", "case_no", "overdue_obligations", "resolution_condition"),
    )


def _client_payable_overdue_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="CLIENTPAYABLE-001",
        source_domain="client_payable",
        fingerprint_fields=("case_no",),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(
            RecoveryActionDescriptor(
                action_key="settle_client_payable",
                label="核銷逾期客戶退款應付",
                owning_domain="client_finance",
                preview_operation="PreviewClientRefund",
                apply_operation="ApplyClientRefund",
                requires_preview=True,
                form_schema_key="client_finance.client_payable_refund.v1",
                source_binding_keys=("account_version", "case_no"),
                required_operator_inputs=("bank_fact_identities", "obligation_identities", "reason"),
                completion_predicate="client_payable_overdue_obligations_cleared",
            ),
        ),
        display_fields=("action", "case_no", "overdue_obligations", "resolution_condition"),
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
        lifecycle=AnomalyDefinitionLifecycle.WORK_ITEM,
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
        available_actions=(
            RecoveryActionDescriptor(
                action_key="rebuild_replacement_assignment_plan",
                label="重建尚未開始服務的人力配置",
                owning_domain="scheduling",
                preview_operation="PreviewAssignmentPlan",
                apply_operation="ApplyAssignmentPlan",
                requires_preview=True,
                form_schema_key="scheduling.assignment_plan.v1",
                source_binding_keys=("assignment_id", "case_no", "source_version"),
                required_operator_inputs=("reason", "segments"),
                completion_predicate="scheduling_replacement_lineage_complete",
            ),
            RecoveryActionDescriptor(
                action_key="complete_replacement_leave_substitution",
                label="完成已開始服務的請假代班",
                owning_domain="scheduling",
                preview_operation="PreviewLeaveSubstitutionBatch",
                apply_operation="ApplyLeaveSubstitutionBatch",
                requires_preview=True,
                form_schema_key="scheduling.leave_substitution.v1",
                source_binding_keys=("assignment_id", "case_no", "source_version"),
                required_operator_inputs=("items", "reason"),
                completion_predicate="scheduling_replacement_lineage_complete",
            ),
        ),
        display_fields=("assignment_id", "case_no", "staff_id"),
    )


def _schedule_overlap_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="SCHEDULE-003",
        source_domain="scheduling",
        fingerprint_fields=("assignment_id_a", "assignment_id_b"),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(
            RecoveryActionDescriptor(
                action_key="rebuild_overlapping_assignment_plan",
                label="修正重疊的人力配置",
                owning_domain="scheduling",
                preview_operation="PreviewAssignmentPlan",
                apply_operation="ApplyAssignmentPlan",
                requires_preview=True,
                form_schema_key="scheduling.assignment_overlap_correction.v1",
                source_binding_keys=(
                    "assignment_id_a",
                    "assignment_id_b",
                    "case_no_a",
                    "case_no_b",
                    "source_version",
                ),
                required_operator_inputs=("correction_case_no", "reason", "segments"),
                completion_predicate="scheduling_assignment_pair_no_longer_overlaps",
            ),
        ),
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
        lifecycle=AnomalyDefinitionLifecycle.RETIRED,
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
            RecoveryActionDescriptor(
                action_key="manual_replay_failed_notification",
                label="重新發送失敗的LINE通知",
                owning_domain="line_notification",
                preview_operation="PreviewLineNotificationManualReplay",
                apply_operation="ApplyLineNotificationManualReplay",
                requires_preview=True,
                form_schema_key="line_notification.manual_replay.v1",
                source_binding_keys=("case_no", "notification_reason", "source_version"),
                required_operator_inputs=("reason", "source_event_id"),
                required_capability="line.config.manage",
                completion_predicate="line_notification_failed_sources_have_terminal_replay_successors",
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
        lifecycle=AnomalyDefinitionLifecycle.WORK_ITEM,
    )


def _line_identity_conflict_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="LINE-004",
        source_domain="line_binding",
        fingerprint_fields=("line_user_id",),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(
            RecoveryActionDescriptor(
                action_key="replace_same_type_line_identity_subject",
                label="將LINE身分改綁至目前案件",
                owning_domain="line_identity",
                preview_operation="PreviewLineIdentitySubjectReplacement",
                apply_operation="ApplyLineIdentitySubjectReplacement",
                requires_preview=True,
                form_schema_key="line_identity.same_type_replacement.v1",
                source_binding_keys=(
                    "line_user_id",
                    "source_version",
                    "subject_type",
                ),
                required_operator_inputs=("reason", "target_subject_reference"),
                required_capability="line.identity.binding.manage",
                completion_predicate=(
                    "line_identity_same_type_projection_unique_and_root_consistent"
                ),
            ),
        ),
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
            RecoveryActionDescriptor(
                action_key="rebuild_assignment_plan",
                label="重建正式人力配置",
                owning_domain="scheduling",
                preview_operation="PreviewAssignmentPlan",
                apply_operation="ApplyAssignmentPlan",
                requires_preview=True,
                form_schema_key="scheduling.assignment_plan.v1",
                source_binding_keys=("case_no", "source_version"),
                required_operator_inputs=("reason", "segments"),
                completion_predicate="scheduling_effective_generation_complete",
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
    return AnomalyDefinition(
        code="PAYOUT-001",
        source_domain="staff_payables",
        fingerprint_fields=("obligation_identity",),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(
            RecoveryActionDescriptor(
                action_key="reconcile_overdue_staff_payable",
                label="核銷逾期月嫂應付款",
                owning_domain="staff_payables",
                preview_operation="PreviewStaffPayout",
                apply_operation="ApplyStaffPayout",
                requires_preview=True,
                form_schema_key="staff_payables.payout_reconciliation.v1",
                source_binding_keys=("obligation_identity", "staff_id"),
                required_operator_inputs=("finance_import_row_ids", "reason"),
                required_capability="staff_payables.payout.apply",
                completion_predicate="staff_payable_obligation_settled",
                action_contract_version=1,
            ),
        ),
        display_fields=(
            "amount_due_ntd",
            "balance_ntd",
            "due_date",
            "obligation_identity",
            "staff_id",
        ),
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
    return AnomalyDefinition(
        code="GOVSUB-001",
        source_domain="government_subsidy",
        fingerprint_fields=("bank_fact_identity",),
        severity=AnomalySeverity.BLOCKING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(RecoveryActionDescriptor(
            action_key="review_government_subsidy_receipt", label="核對並入帳政府補助款",
            owning_domain="government_subsidy", preview_operation="PreviewGovernmentSubsidyReceipt",
            apply_operation="ApplyGovernmentSubsidyReceipt", requires_preview=True,
            form_schema_key="government_subsidy.receipt.v1",
            source_binding_keys=("bank_fact_identity", "finance_import_row_id", "source_version"),
            required_operator_inputs=("allocations", "batch_id", "reason"),
            completion_predicate="government_subsidy_receipt_fully_reconciled",
        ),),
        display_fields=("bank_fact_identity", "candidate_batch_ids"),
    )


def _government_subsidy_ambiguous_allocation_definition():
    return AnomalyDefinition(
        code="GOVSUB-002", source_domain="government_subsidy",
        fingerprint_fields=("bank_fact_identity", "batch_id"), severity=AnomalySeverity.BLOCKING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(RecoveryActionDescriptor(
            action_key="allocate_government_subsidy_receipt", label="指定政府補助款分配",
            owning_domain="government_subsidy", preview_operation="PreviewGovernmentSubsidyReceipt",
            apply_operation="ApplyGovernmentSubsidyReceipt", requires_preview=True,
            form_schema_key="government_subsidy.receipt_allocation.v1",
            source_binding_keys=("bank_fact_identity", "batch_id", "finance_import_row_id", "source_version"),
            required_operator_inputs=("allocations", "reason"),
            completion_predicate="government_subsidy_receipt_allocation_conserved",
        ),),
        display_fields=("bank_fact_identity", "batch_id", "item_outstanding"),
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
    return AnomalyDefinition(
        code="GOVSUB-004", source_domain="government_subsidy",
        fingerprint_fields=("reversal_bank_fact_identity", "source_receipt_id"),
        severity=AnomalySeverity.BLOCKING, projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(RecoveryActionDescriptor(
            action_key="review_government_subsidy_reversal", label="核對政府補助沖銷",
            owning_domain="government_subsidy", preview_operation="PreviewGovernmentSubsidyReversal",
            apply_operation="ApplyGovernmentSubsidyReversal", requires_preview=True,
            form_schema_key="government_subsidy.reversal.v1",
            source_binding_keys=("finance_import_row_id", "reversal_bank_fact_identity", "source_receipt_id", "source_version"),
            required_operator_inputs=("allocations", "reason"),
            completion_predicate="government_subsidy_reversal_fully_reconciled",
        ),),
        display_fields=("remaining_reversible_ntd", "reversal_bank_fact_identity", "source_receipt_id"),
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
                required_operator_inputs=(
                    "disposition",
                    "evidence_reference",
                    "offset_amounts",
                    "offset_targets",
                    "reason",
                    "return_due_date",
                ),
                required_capability="government_subsidy.overpayment.disposition",
                completion_predicate="government_subsidy_overpayment_disposed",
            ),
        ),
        display_fields=(
            "amount_delta_ntd",
            "domain_blockers",
            "finance_import_row_id",
            "integrity_blocker_active",
            "overpayment_identity",
            "reason_codes",
            "root_condition_active",
        ),
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
                required_operator_inputs=("evidence_reference", "reason"),
                required_capability="client_finance.recovery.collect",
                completion_predicate="client_over_refund_recovery_remaining_updated",
            ),
            RecoveryActionDescriptor(
                action_key="match_client_over_refund_recovery",
                label="配對客戶退款超額追償入款",
                owning_domain="client_finance",
                preview_operation="PreviewClientOverRefundRecoveryMatching",
                apply_operation="ApplyClientOverRefundRecoveryMatching",
                requires_preview=True,
                form_schema_key="client_finance.over_refund_recovery.matching.v1",
                source_binding_keys=(
                    "account_version",
                    "case_no",
                    "recovery_identity",
                    "recovery_version",
                ),
                required_operator_inputs=(
                    "evidence_reference",
                    "finance_import_row_identity",
                    "reason",
                ),
                required_capability="client_finance.recovery.collect",
                completion_predicate="client_over_refund_recovery_matching_established",
            ),
            RecoveryActionDescriptor(
                action_key="adjust_client_over_refund_recovery",
                label="調整客戶退款超額追償",
                owning_domain="client_finance",
                preview_operation="PreviewClientOverRefundRecoveryAdjustment",
                apply_operation="ApplyClientOverRefundRecoveryAdjustment",
                requires_preview=True,
                form_schema_key="client_finance.over_refund_recovery.adjustment.v1",
                source_binding_keys=(
                    "account_version",
                    "case_no",
                    "recovery_identity",
                    "recovery_version",
                ),
                required_operator_inputs=(
                    "adjustment_amount",
                    "evidence_reference",
                    "reason",
                ),
                required_capability="client_finance.recovery.adjust",
                completion_predicate="client_over_refund_recovery_remaining_updated",
            ),
        ),
        display_fields=(
            "amount_delta_ntd",
            "case_no",
            "domain_blockers",
            "finance_import_row_id",
            "integrity_blocker_active",
            "reason_codes",
            "recovery_identity",
            "root_condition_active",
        ),
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
        available_actions=(
            RecoveryActionDescriptor(
                action_key="collect_staff_overpayment_recovery",
                label="收回月嫂超額付款追償",
                owning_domain="staff_payables",
                preview_operation="PreviewCollectMatchedStaffOverpaymentRecovery",
                apply_operation="ApplyCollectMatchedStaffOverpaymentRecovery",
                requires_preview=True,
                form_schema_key="staff_payables.overpayment_recovery.collection.v1",
                source_binding_keys=(
                    "finance_import_row_identity",
                    "matching_identity",
                    "matching_version",
                    "recovery_identity",
                    "recovery_version",
                    "staff_id",
                    "staff_payables_version",
                ),
                required_operator_inputs=("evidence_reference", "reason"),
                required_capability="staff_payables.recovery.collect",
                completion_predicate="staff_overpayment_recovery_remaining_updated",
            ),
            RecoveryActionDescriptor(
                action_key="match_staff_overpayment_recovery",
                label="配對月嫂超額付款追償入款",
                owning_domain="staff_payables",
                preview_operation="PreviewStaffOverpaymentRecoveryMatching",
                apply_operation="ApplyStaffOverpaymentRecoveryMatching",
                requires_preview=True,
                form_schema_key="staff_payables.overpayment_recovery.matching.v1",
                source_binding_keys=(
                    "recovery_identity",
                    "recovery_version",
                    "staff_id",
                    "staff_payables_version",
                ),
                required_operator_inputs=(
                    "evidence_reference",
                    "finance_import_row_identity",
                    "reason",
                ),
                required_capability="staff_payables.recovery.collect",
                completion_predicate="staff_overpayment_recovery_matching_established",
            ),
            RecoveryActionDescriptor(
                action_key="adjust_staff_overpayment_recovery",
                label="調整月嫂超額付款追償",
                owning_domain="staff_payables",
                preview_operation="PreviewStaffOverpaymentRecoveryAdjustment",
                apply_operation="ApplyStaffOverpaymentRecoveryAdjustment",
                requires_preview=True,
                form_schema_key="staff_payables.overpayment_recovery.adjustment.v1",
                source_binding_keys=(
                    "recovery_identity",
                    "recovery_version",
                    "staff_id",
                    "staff_payables_version",
                ),
                required_operator_inputs=(
                    "adjustment_amount",
                    "evidence_reference",
                    "reason",
                ),
                required_capability="staff_payables.recovery.adjust",
                completion_predicate="staff_overpayment_recovery_remaining_updated",
            ),
        ),
        display_fields=(
            "amount_delta_ntd",
            "domain_blockers",
            "finance_import_row_id",
            "integrity_blocker_active",
            "reason_codes",
            "recovery_identity",
            "root_condition_active",
            "staff_id",
        ),
    )


def _staff_payout_difference_definition(
    code: str,
    *,
    lifecycle: AnomalyDefinitionLifecycle = AnomalyDefinitionLifecycle.ACTIVE,
) -> AnomalyDefinition:
    return AnomalyDefinition(
        code=code, source_domain="staff_payables", fingerprint_fields=("payout_difference_identity",),
        severity=AnomalySeverity.BLOCKING, projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(), no_automated_recovery=True,
        display_fields=("payout_difference_identity", "staff_id"),
        lifecycle=lifecycle,
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
    return AnomalyDefinition(
        code="IMPORT-003",
        source_domain="case_import",
        fingerprint_fields=("entity_kind", "review_item_id"),
        severity=AnomalySeverity.WARNING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(),
        display_fields=("entity_kind", "error_codes", "masked_identifier", "review_item_id", "source_row", "source_sheet", "version"),
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


def _finance_integrity_definition() -> AnomalyDefinition:
    return AnomalyDefinition(
        code="IMPORT-006",
        source_domain="finance_import",
        fingerprint_fields=("batch_id",),
        severity=AnomalySeverity.BLOCKING,
        projection_kind=AnomalyProjectionKind.CURRENT_STATE,
        available_actions=(),
        no_automated_recovery=True,
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


_AUTO_RESOLUTION_CONTRACTS = {}


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
