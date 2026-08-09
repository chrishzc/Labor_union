"""Root-fact contracts for canonical Anomalies projection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domains.anomalies.registry import (
    AnomalyDefinitionRegistry,
    CurrentAlertProjection,
    DesiredAlertState,
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


@dataclass(frozen=True, slots=True)
class RecoveryActionLink:
    action_code: str
    owning_domain: str
    command_name: str
    preview_endpoint: str
    subject_identity: str
    subject_version: int
    required_inputs: tuple[str, ...]
    requires_preview: bool = True


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
    return (_finance_correction_action(subject_identity, subject_version),)


def _desired_alert(root_fact: FinanceManualReviewRootFact) -> DesiredAlertState:
    return DesiredAlertState(
        definition_code=root_fact.definition_code,
        source_identity=root_fact.source_identity,
        source_version=root_fact.source_version,
        active=root_fact.active,
        fingerprint_values={
            "finance_import_row_id": str(root_fact.finance_import_row_id),
            **_refund_return_fingerprint_values(root_fact),
        },
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
        action_code="correct_and_post",
        owning_domain="finance_import",
        command_name="PreviewCorrectAndPostFinanceImportRow",
        preview_endpoint="/api/v1/finance-import/corrections/preview",
        subject_identity=subject_identity,
        subject_version=subject_version,
        required_inputs=(
            "classification_type",
            "evidence",
            "reason",
            "target_obligation_identities",
        ),
    )


def _refund_return_review_action(subject_identity, subject_version):
    return RecoveryActionLink(
        action_code="correct_refund_return",
        owning_domain="finance_import",
        command_name="PreviewCorrectAndPostClientRefundReturn",
        preview_endpoint="/api/v1/finance-import/corrections/preview",
        subject_identity=subject_identity,
        subject_version=subject_version,
        required_inputs=(
            "evidence",
            "reason",
            "refund_ledger_entry_identity",
            "target_obligation_identities",
        ),
    )


def _recovery_actions(root_fact):
    if root_fact.definition_code == "CLIENTREFUND-001":
        return (
            _refund_return_review_action(
                root_fact.source_identity,
                root_fact.source_version,
            ),
        )
    return finance_manual_review_recovery_actions(
        root_fact.source_identity,
        root_fact.source_version,
    )


def _refund_return_fingerprint_values(root_fact):
    if root_fact.definition_code != "CLIENTREFUND-001":
        return {}
    return {
        "original_refund_ledger_entry_id": str(
            root_fact.original_refund_ledger_entry_id
        ),
    }


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


def _validate_root_fact_collections(root_fact) -> None:
    collections = (
        root_fact.affected_order_identities,
        root_fact.affected_obligation_identities,
        root_fact.domain_blockers,
        root_fact.reason_codes,
    )
    for values in collections:
        _validate_bounded_identities(values)


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
