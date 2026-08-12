"""Root-fact contracts for canonical Anomalies projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domains.anomalies.registry import (
    AnomalyDefinitionRegistry,
    CurrentAlertProjection,
    DesiredAlertState,
    RecoveryActionDescriptor,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

_IDENTITY_MAXIMUM_LENGTH = 191
_BOUNDED_COLLECTION_MAXIMUM_LENGTH = 20


class RootFactEventOrigin(StrEnum):
    DOMAIN_EVENT = "domain_event"
    HISTORICAL_RESCAN = "historical_rescan"


@dataclass(frozen=True, slots=True)
class FinanceManualReviewRootFact:
    source_event_identity: str
    source_version: int
    origin: RootFactEventOrigin
    occurred_at: datetime
    finance_import_row_id: int
    finance_import_batch_id: int
    active: bool
    integrity_blocker_active: bool
    amount_delta_ntd: int
    affected_order_identities: tuple[str, ...] = ()
    affected_obligation_identities: tuple[str, ...] = ()
    domain_blockers: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    definition_code: str = "finance_import_manual_review"
    source_identity_override: str | None = None
    original_refund_ledger_entry_id: int | None = None
    recovery_bindings: tuple[tuple[str, str | int], ...] = ()

    def __post_init__(self) -> None:
        _validate_root_fact_identity(self)
        _validate_root_fact_values(self)
        _validate_root_fact_collections(self)

    @property
    def source_identity(self) -> str:
        if self.source_identity_override is not None:
            return self.source_identity_override
        return f"finance-import-row:{self.finance_import_row_id}"


@dataclass(frozen=True, slots=True)
class FinanceAnomalyOccurrence:
    occurrence_fingerprint: PreviewFingerprint
    definition_code: str
    source_event_identity: str
    finance_import_row_id: int
    finance_import_batch_id: int
    source_version: int
    occurred_at: datetime
    bounded_snapshot: dict[str, object]


# The dynamic recovery context uses the same descriptor contract as the registry.
RecoveryActionLink = RecoveryActionDescriptor


@dataclass(frozen=True, slots=True)
class RootFactProjectionCandidate:
    source_event_identity: str
    event_payload_fingerprint: PreviewFingerprint
    alert_fingerprint: PreviewFingerprint
    desired: DesiredAlertState
    root_fact_snapshot: dict[str, object]
    occurrence: FinanceAnomalyOccurrence | None
    available_actions: tuple[RecoveryActionLink, ...]


@dataclass(frozen=True, slots=True)
class RecoveryContext:
    projection: CurrentAlertProjection
    source_domain: str
    severity: str
    root_fact_snapshot: dict[str, object]
    domain_blocker_active: bool
    projection_freshness: str
    occurrence_timeline: tuple[FinanceAnomalyOccurrence, ...]
    workflow_timeline: tuple[dict[str, object], ...]
    available_actions: tuple[RecoveryActionLink, ...]


def build_finance_manual_review_candidate(
    registry: AnomalyDefinitionRegistry,
    root_fact: FinanceManualReviewRootFact,
) -> RootFactProjectionCandidate:
    desired = _desired_alert(root_fact)
    alert_fingerprint = registry.fingerprint(desired)
    root_fact_snapshot = _root_fact_snapshot(root_fact)
    occurrence = _occurrence(root_fact, root_fact_snapshot)
    return RootFactProjectionCandidate(
        root_fact.source_event_identity,
        _event_payload_fingerprint(root_fact),
        alert_fingerprint,
        desired,
        root_fact_snapshot,
        occurrence,
        _recovery_actions(root_fact),
    )


def recovery_completed(context: RecoveryContext) -> bool:
    return not context.projection.predicate_active


def finance_manual_review_recovery_actions(
    subject_identity: str,
    subject_version: int,
) -> tuple[RecoveryActionLink, ...]:
    require_canonical_text(
        subject_identity,
        "recovery subject identity",
        _IDENTITY_MAXIMUM_LENGTH,
    )
    require_nonnegative_integer(subject_version, "recovery subject version")
    return (
        _finance_correction_action(subject_identity, subject_version),
        _client_over_refund_recovery_matching_action(
            subject_identity,
            subject_version,
        ),
        _client_refund_overage_action(subject_identity, subject_version),
        _client_receipt_overage_action(subject_identity, subject_version),
        _staff_overpayment_recovery_matching_action(
            subject_identity,
            subject_version,
        ),
        _staff_payout_difference_action(
            subject_identity,
            subject_version,
        ),
        _government_return_reconciliation_action(
            subject_identity,
            subject_version,
        ),
    )


def _desired_alert(root_fact: FinanceManualReviewRootFact) -> DesiredAlertState:
    return DesiredAlertState(
        definition_code=root_fact.definition_code,
        source_identity=root_fact.source_identity,
        source_version=root_fact.source_version,
        active=root_fact.active,
        fingerprint_values=_desired_fingerprint_values(root_fact),
    )


def _root_fact_snapshot(root_fact: FinanceManualReviewRootFact) -> dict[str, object]:
    return {
        "finance_import_row_id": root_fact.finance_import_row_id,
        "finance_import_batch_id": root_fact.finance_import_batch_id,
        "occurred_at": root_fact.occurred_at.isoformat(),
        "amount_delta_ntd": root_fact.amount_delta_ntd,
        "affected_order_identities": list(root_fact.affected_order_identities),
        "affected_obligation_identities": list(
            root_fact.affected_obligation_identities
        ),
        "domain_blockers": list(root_fact.domain_blockers),
        "reason_codes": list(root_fact.reason_codes),
        "root_condition_active": root_fact.active,
        "integrity_blocker_active": root_fact.integrity_blocker_active,
        "source_version": root_fact.source_version,
        "definition_code": root_fact.definition_code,
        "original_refund_ledger_entry_id": root_fact.original_refund_ledger_entry_id,
        "recovery_bindings": dict(root_fact.recovery_bindings),
    }


# Kept cohesive because occurrence identity and snapshot share one root event.
def _occurrence(root_fact, snapshot) -> FinanceAnomalyOccurrence | None:
    if root_fact.origin is RootFactEventOrigin.HISTORICAL_RESCAN:
        return None
    if not root_fact.active:
        return None
    fingerprint = fingerprint_payload(
        {
            "definition_code": root_fact.definition_code,
            "source_event_identity": root_fact.source_event_identity,
        }
    )
    return FinanceAnomalyOccurrence(
        fingerprint,
        root_fact.definition_code,
        root_fact.source_event_identity,
        root_fact.finance_import_row_id,
        root_fact.finance_import_batch_id,
        root_fact.source_version,
        root_fact.occurred_at,
        snapshot,
    )


def _event_payload_fingerprint(root_fact) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "source_event_identity": root_fact.source_event_identity,
            "source_version": root_fact.source_version,
            "origin": root_fact.origin.value,
            "source_identity": root_fact.source_identity,
            "root_fact_snapshot": _root_fact_snapshot(root_fact),
        }
    )


def _finance_correction_action(
    subject_identity,
    subject_version,
) -> RecoveryActionLink:
    return RecoveryActionLink(
        action_key="classify_and_post_bank_row",
        label="分類並正式入帳銀行流水",
        owning_domain="finance_import",
        preview_operation="PreviewCorrectAndPostFinanceImportRow",
        apply_operation="CorrectAndPostFinanceImportRow",
        requires_preview=True,
        form_schema_key="finance_import.correction.v1",
        source_binding_keys=("finance_import_row_identity", "source_version"),
        source_bindings={
            "finance_import_row_identity": subject_identity,
            "source_version": subject_version,
        },
        required_operator_inputs=(
            "classification_type",
            "evidence",
            "reason",
            "target_obligation_identities",
        ),
        required_capability="finance_import.correct_and_post",
        completion_predicate="finance_import_manual_review_cleared",
    )


def _client_over_refund_recovery_matching_action(
    subject_identity: str,
    subject_version: int,
) -> RecoveryActionLink:
    return RecoveryActionLink(
        action_key="match_client_over_refund_recovery",
        label="配對客戶退款超額追償入款",
        owning_domain="client_finance",
        preview_operation="PreviewClientOverRefundRecoveryMatching",
        apply_operation="ApplyClientOverRefundRecoveryMatching",
        requires_preview=True,
        form_schema_key="client_finance.over_refund_recovery.matching.v1",
        source_binding_keys=("finance_import_row_identity", "source_version"),
        source_bindings={
            "finance_import_row_identity": subject_identity,
            "source_version": subject_version,
        },
        required_operator_inputs=("case_no", "evidence", "reason", "recovery_identity"),
        required_capability="client_finance.recovery.collect",
        completion_predicate="client_over_refund_recovery_matching_established",
    )


def _staff_overpayment_recovery_matching_action(
    subject_identity: str,
    subject_version: int,
) -> RecoveryActionLink:
    return RecoveryActionLink(
        action_key="match_staff_overpayment_recovery",
        label="配對月嫂超額付款追償入款",
        owning_domain="staff_payables",
        preview_operation="PreviewStaffOverpaymentRecoveryMatching",
        apply_operation="ApplyStaffOverpaymentRecoveryMatching",
        requires_preview=True,
        form_schema_key="staff_payables.overpayment_recovery.matching.v1",
        source_binding_keys=("finance_import_row_identity", "source_version"),
        source_bindings={
            "finance_import_row_identity": subject_identity,
            "source_version": subject_version,
        },
        required_operator_inputs=("evidence", "reason", "recovery_identity"),
        required_capability="staff_payables.recovery.collect",
        completion_predicate="staff_overpayment_recovery_matching_established",
    )


def _client_refund_overage_action(subject_identity: str, subject_version: int) -> RecoveryActionLink:
    return RecoveryActionLink(
        action_key="apply_client_refund_overage", label="處理客戶退款多匯",
        owning_domain="client_finance", preview_operation="PreviewClientRefundOverage",
        apply_operation="ApplyClientRefundOverage", requires_preview=True,
        form_schema_key="client_finance.refund_overage.v1",
        source_binding_keys=("finance_import_row_identity", "source_version"),
        source_bindings={"finance_import_row_identity": subject_identity, "source_version": subject_version},
        required_operator_inputs=("case_no", "evidence", "obligation_identities", "reason"),
        required_capability="client_finance.refund.apply", completion_predicate="client_refund_overage_recovery_established",
    )


def _client_receipt_overage_action(subject_identity: str, subject_version: int) -> RecoveryActionLink:
    return RecoveryActionLink(
        action_key="apply_client_receipt_overage", label="處理客戶收款超額",
        owning_domain="client_finance", preview_operation="PreviewClientReceiptOverage",
        apply_operation="ApplyClientReceiptOverage", requires_preview=True,
        form_schema_key="client_finance.receipt_overage.v1",
        source_binding_keys=("finance_import_row_identity", "source_version"),
        source_bindings={"finance_import_row_identity": subject_identity, "source_version": subject_version},
        required_operator_inputs=("case_no", "evidence", "obligation_identities", "payment_stage", "reason"),
        required_capability="client_finance.receipt.apply", completion_predicate="client_receipt_overage_refund_established",
    )


def _government_return_reconciliation_action(
    subject_identity: str,
    subject_version: int,
) -> RecoveryActionLink:
    return RecoveryActionLink(
        action_key="reconcile_government_overpayment_return",
        label="核對政府退款單出款列",
        owning_domain="government_subsidy",
        preview_operation="PreviewGovernmentOverpaymentReturnReconciliation",
        apply_operation="ApplyGovernmentOverpaymentReturnReconciliation",
        requires_preview=True,
        form_schema_key="government_subsidy.overpayment.return_reconciliation.v1",
        source_binding_keys=("finance_import_row_identity", "source_version"),
        source_bindings={
            "finance_import_row_identity": subject_identity,
            "source_version": subject_version,
        },
        required_operator_inputs=("evidence", "overpayment_identity", "reason"),
        required_capability="government_subsidy.overpayment.disposition",
        completion_predicate="government_overpayment_return_reconciled",
    )


def _staff_payout_difference_action(
    subject_identity: str,
    subject_version: int,
) -> RecoveryActionLink:
    return RecoveryActionLink(
        action_key="apply_staff_payout_difference",
        label="處理月嫂少匯／多匯",
        owning_domain="staff_payables",
        preview_operation="PreviewStaffPayoutDifference",
        apply_operation="ApplyStaffPayoutDifference",
        requires_preview=True,
        form_schema_key="staff_payables.payout_difference.v1",
        source_binding_keys=("finance_import_row_identity", "source_version"),
        source_bindings={
            "finance_import_row_identity": subject_identity,
            "source_version": subject_version,
        },
        required_operator_inputs=("evidence", "mode", "obligation_identities", "reason"),
        required_capability="staff_payables.payout.apply",
        completion_predicate="staff_payout_difference_recorded",
    )


def _refund_return_review_action(subject_identity, subject_version):
    return RecoveryActionLink(
        action_key="classify_client_refund_return",
        label="處理客戶退款退匯",
        owning_domain="finance_import",
        preview_operation="PreviewCorrectAndPostClientRefundReturn",
        apply_operation="CorrectAndPostClientRefundReturn",
        requires_preview=True,
        form_schema_key="finance_import.correction.v1",
        source_binding_keys=("finance_import_row_identity", "source_version"),
        source_bindings={
            "finance_import_row_identity": subject_identity,
            "source_version": subject_version,
        },
        required_operator_inputs=(
            "evidence",
            "reason",
            "refund_ledger_entry_identity",
            "target_obligation_identities",
        ),
        required_capability="finance_import.correct_and_post",
        completion_predicate="client_refund_return_cleared",
    )


def _recovery_actions(root_fact):
    if root_fact.definition_code == "CLIENTREFUND-001":
        return (
            _refund_return_review_action(
                root_fact.source_identity,
                root_fact.source_version,
            ),
        )
    if root_fact.definition_code == "GOVSUB-006":
        return (_government_overpayment_action(root_fact),)
    if root_fact.definition_code == "client_over_refund_recovery_open":
        return (_client_over_refund_recovery_action(root_fact),)
    if root_fact.definition_code == "staff_overpayment_recovery_open":
        return (_staff_overpayment_recovery_action(root_fact),)
    if root_fact.definition_code in {"client_refund_underpayment", "staff_payout_underpayment", "staff_payout_overpayment"}:
        return ()
    return finance_manual_review_recovery_actions(
        root_fact.source_identity,
        root_fact.source_version,
    )


def _definition_fingerprint_values(root_fact):
    if root_fact.definition_code == "CLIENTREFUND-001":
        return {
            "original_refund_ledger_entry_id": str(
                root_fact.original_refund_ledger_entry_id
            ),
        }
    if root_fact.definition_code == "GOVSUB-006":
        return {"overpayment_identity": str(dict(root_fact.recovery_bindings)["overpayment_identity"])}
    if root_fact.definition_code == "client_over_refund_recovery_open":
        return {"recovery_identity": str(dict(root_fact.recovery_bindings)["recovery_identity"])}
    if root_fact.definition_code == "staff_overpayment_recovery_open":
        return {"recovery_identity": str(dict(root_fact.recovery_bindings)["recovery_identity"])}
    if root_fact.definition_code == "client_refund_underpayment":
        return {"underpayment_identity": str(dict(root_fact.recovery_bindings)["underpayment_identity"])}
    if root_fact.definition_code in {"staff_payout_underpayment", "staff_payout_overpayment"}:
        return {"payout_difference_identity": str(dict(root_fact.recovery_bindings)["payout_difference_identity"])}
    return {}


def _desired_fingerprint_values(root_fact):
    if root_fact.definition_code in {
        "GOVSUB-006",
        "client_over_refund_recovery_open",
        "staff_overpayment_recovery_open",
        "client_refund_underpayment",
        "staff_payout_underpayment",
        "staff_payout_overpayment",
        "staff_payout_underpayment",
        "staff_payout_overpayment",
    }:
        return _definition_fingerprint_values(root_fact)
    if root_fact.definition_code == "finance_import_manual_review":
        return {"finance_import_row_id": str(root_fact.finance_import_row_id)}
    return {
        "finance_import_row_id": str(root_fact.finance_import_row_id),
        **_definition_fingerprint_values(root_fact),
    }


def _government_overpayment_action(root_fact):
    bindings = dict(root_fact.recovery_bindings)
    return RecoveryActionLink(
        action_key="dispose_government_subsidy_overpayment",
        label="處置政府補助溢撥",
        owning_domain="government_subsidy",
        preview_operation="PreviewGovernmentSubsidyOverpaymentDisposition",
        apply_operation="ApplyGovernmentSubsidyOverpaymentDisposition",
        requires_preview=True,
        form_schema_key="government_subsidy.overpayment.disposition.v1",
        source_binding_keys=tuple(sorted(bindings)),
        source_bindings=bindings,
        required_operator_inputs=("disposition", "evidence_reference", "reason"),
        required_capability="government_subsidy.overpayment.disposition",
        completion_predicate="government_subsidy_overpayment_disposed",
    )


def _client_over_refund_recovery_action(root_fact):
    bindings = dict(root_fact.recovery_bindings)
    return RecoveryActionLink(
        action_key="collect_client_over_refund_recovery",
        label="收回客戶退款超額追償",
        owning_domain="client_finance",
        preview_operation="PreviewCollectMatchedClientOverRefundRecovery",
        apply_operation="ApplyCollectMatchedClientOverRefundRecovery",
        requires_preview=True,
        form_schema_key="client_finance.over_refund_recovery.collection.v1",
        source_binding_keys=tuple(sorted(bindings)),
        source_bindings=bindings,
        required_operator_inputs=("evidence", "reason"),
        required_capability="client_finance.recovery.collect",
        completion_predicate="client_over_refund_recovery_remaining_updated",
    )


def _staff_overpayment_recovery_action(root_fact):
    bindings = dict(root_fact.recovery_bindings)
    return RecoveryActionLink(
        action_key="collect_staff_overpayment_recovery", label="收回月嫂超額付款追償",
        owning_domain="staff_payables", preview_operation="PreviewCollectMatchedStaffOverpaymentRecovery",
        apply_operation="ApplyCollectMatchedStaffOverpaymentRecovery", requires_preview=True,
        form_schema_key="staff_payables.overpayment_recovery.collection.v1",
        source_binding_keys=tuple(sorted(bindings)), source_bindings=bindings,
        required_operator_inputs=("evidence", "reason"), required_capability="staff_payables.recovery.collect",
        completion_predicate="staff_overpayment_recovery_remaining_updated",
    )




def _validate_root_fact_identity(root_fact) -> None:
    require_canonical_text(
        root_fact.source_event_identity,
        "source event identity",
        _IDENTITY_MAXIMUM_LENGTH,
    )
    if (
        root_fact.occurred_at.tzinfo is None
        or root_fact.occurred_at.utcoffset() is None
    ):
        raise ValueError("anomaly_source_fact_invalid")
    if root_fact.definition_code not in {
        "finance_import_manual_review",
        "CLIENTREFUND-001",
        "GOVSUB-006",
        "client_over_refund_recovery_open",
        "staff_overpayment_recovery_open",
        "client_refund_underpayment",
        "staff_payout_underpayment",
        "staff_payout_overpayment",
    }:
        raise ValueError("anomaly_source_fact_invalid")
    if root_fact.source_identity_override is not None:
        require_canonical_text(
            root_fact.source_identity_override,
            "source identity override",
            _IDENTITY_MAXIMUM_LENGTH,
        )


def _validate_root_fact_values(root_fact) -> None:
    require_nonnegative_integer(root_fact.source_version, "source version")
    if not isinstance(root_fact.active, bool):
        raise TypeError("root fact active flag must be bool")
    if not isinstance(root_fact.integrity_blocker_active, bool):
        raise TypeError("integrity blocker flag must be bool")
    if root_fact.active and root_fact.integrity_blocker_active:
        raise ValueError("anomaly_source_fact_invalid")
    if isinstance(root_fact.amount_delta_ntd, bool):
        raise TypeError("amount delta must be integer NTD")
    if not isinstance(root_fact.amount_delta_ntd, int):
        raise TypeError("amount delta must be integer NTD")
    require_positive_integer(root_fact.finance_import_row_id, "finance import row id")
    require_positive_integer(
        root_fact.finance_import_batch_id,
        "finance import batch id",
    )
    if root_fact.definition_code == "CLIENTREFUND-001":
        require_positive_integer(
            root_fact.original_refund_ledger_entry_id,
            "original refund ledger entry id",
        )
        if root_fact.source_identity_override is None:
            raise ValueError("anomaly_source_fact_invalid")
    if root_fact.definition_code == "GOVSUB-006":
        bindings = dict(root_fact.recovery_bindings)
        required = {"overpayment_identity", "overpayment_version"}
        if set(bindings) != required or not isinstance(bindings["overpayment_identity"], str):
            raise ValueError("anomaly_source_fact_invalid")
        require_nonnegative_integer(bindings["overpayment_version"], "overpayment version")


def _validate_root_fact_collections(root_fact) -> None:
    collections = (
        root_fact.affected_order_identities,
        root_fact.affected_obligation_identities,
        root_fact.domain_blockers,
        root_fact.reason_codes,
    )
    for values in collections:
        _validate_bounded_identities(values)
    if root_fact.recovery_bindings != tuple(sorted(root_fact.recovery_bindings)):
        raise ValueError("anomaly_source_fact_invalid")
    for key, value in root_fact.recovery_bindings:
        _validate_root_fact_binding(key, value)


def _validate_root_fact_binding(key, value) -> None:
    require_canonical_text(key, "recovery binding key", _IDENTITY_MAXIMUM_LENGTH)
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("anomaly_source_fact_invalid")


def _validate_bounded_identities(values: tuple[str, ...]) -> None:
    if not isinstance(values, tuple):
        raise TypeError("root fact identity collection must be a tuple")
    if len(values) > _BOUNDED_COLLECTION_MAXIMUM_LENGTH:
        raise ValueError("anomaly_source_fact_invalid")
    if values != tuple(sorted(set(values))):
        raise ValueError("anomaly_source_fact_invalid")
    for value in values:
        require_canonical_text(value, "root fact identity", _IDENTITY_MAXIMUM_LENGTH)


__all__ = [
    "FinanceAnomalyOccurrence",
    "FinanceManualReviewRootFact",
    "RecoveryActionLink",
    "RecoveryContext",
    "RootFactEventOrigin",
    "RootFactProjectionCandidate",
    "build_finance_manual_review_candidate",
    "finance_manual_review_recovery_actions",
    "recovery_completed",
]
