"""Typed anomaly definition registry and current-state reducer."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Mapping

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer

_IDENTITY_MAXIMUM_LENGTH = 191


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
class DomainActionLink:
    action_code: str
    owning_domain: str
    command_name: str
    requires_preview: bool


@dataclass(frozen=True, slots=True)
class AnomalyDefinition:
    code: str
    source_domain: str
    fingerprint_fields: tuple[str, ...]
    severity: AnomalySeverity
    projection_kind: AnomalyProjectionKind
    available_actions: tuple[DomainActionLink, ...]
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

    def available_actions(self, code: str) -> tuple[DomainActionLink, ...]:
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
            _beclass_validation_definition(),
            _beclass_identity_conflict_definition(),
            _finance_manual_review_definition(),
            _client_refund_return_definition(),
            _finance_integrity_definition(),
        )
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
            DomainActionLink(
                "correct_and_post",
                "finance_import",
                "PreviewCorrectAndPostFinanceImportRow",
                True,
            ),
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
            DomainActionLink(
                "correct_refund_return",
                "finance_import",
                "PreviewCorrectAndPostClientRefundReturn",
                True,
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
