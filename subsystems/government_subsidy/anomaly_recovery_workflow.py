"""Bounded Government Subsidy owner remediation application.

The operations are deliberately separate types.  There is no generic repair
command: each operation checks the fresh owner fact and delegates persistence to
the Government Subsidy repository inside one caller-owned unit of work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from domains.government_subsidy.anomaly_remediation import (
    GovernmentSubsidyClaimDriftOwnerFact,
    GovernmentSubsidyClaimDriftRepairPath,
    GovernmentSubsidyIntegrityOwnerFact,
    GovernmentSubsidyIntegrityRepairPath,
    GovernmentSubsidyIncomingRecoveryFact,
    GovernmentSubsidyRecoveryReconciliationCandidate,
    GovernmentSubsidyRecoveryRoot,
    GovernmentSubsidyRecoveryStatus,
    build_recovery_reconciliation_candidate,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import require_canonical_text, require_positive_integer
from subsystems.government_subsidy.anomaly_owner_readback import (
    GovernmentSubsidyAnomalyOwnerReadback,
)


@dataclass(frozen=True, slots=True)
class IntegrityRepairPreview:
    batch_id: int
    expected_version: int
    repair_path: GovernmentSubsidyIntegrityRepairPath
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class IntegrityRepairApplyRequest:
    batch_id: int
    expected_version: ExpectedVersion
    repair_path: GovernmentSubsidyIntegrityRepairPath
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_positive_integer(self.batch_id, "claim batch id")
        require_canonical_text(self.reason, "reason", 500)
        if self.repair_path is not GovernmentSubsidyIntegrityRepairPath.DERIVED_REBUILD:
            raise ValueError("government_subsidy_integrity_generic_repair_forbidden")


@dataclass(frozen=True, slots=True)
class ClaimDriftCorrectionPreview:
    claim_item_id: int
    expected_version: int
    repair_path: GovernmentSubsidyClaimDriftRepairPath
    scheduling_snapshot_identity: str
    scheduling_snapshot_token: str
    scheduling_snapshot_version: int
    fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class ClaimDriftCorrectionApplyRequest:
    claim_item_id: int
    expected_version: ExpectedVersion
    repair_path: GovernmentSubsidyClaimDriftRepairPath
    scheduling_snapshot_identity: str
    scheduling_snapshot_token: str
    scheduling_snapshot_version: int
    successor_revision_identity: str
    financial_consequence_reference: str
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_positive_integer(self.claim_item_id, "claim item id")
        require_canonical_text(
            self.scheduling_snapshot_identity,
            "scheduling snapshot identity",
            191,
        )
        require_canonical_text(
            self.scheduling_snapshot_token,
            "scheduling snapshot token",
            191,
        )
        if self.scheduling_snapshot_version < 0:
            raise ValueError("scheduling snapshot version must be nonnegative")
        require_canonical_text(
            self.successor_revision_identity,
            "successor revision identity",
            191,
        )
        require_canonical_text(
            self.financial_consequence_reference,
            "financial consequence reference",
            191,
        )
        require_canonical_text(self.reason, "reason", 500)
        if self.repair_path is GovernmentSubsidyClaimDriftRepairPath.STRUCTURAL_AMBIGUITY:
            raise ValueError("government_subsidy_claim_drift_generic_repair_forbidden")


@dataclass(frozen=True, slots=True)
class RecoveryCreateApplyRequest:
    root: GovernmentSubsidyRecoveryRoot
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        if (
            self.root.version != 0
            or self.root.status is not GovernmentSubsidyRecoveryStatus.OPEN
            or self.root.remaining_excess_ntd != self.root.excess_amount_ntd
        ):
            raise ValueError("government_subsidy_recovery_create_state_invalid")


@dataclass(frozen=True, slots=True)
class RecoveryReconcilePreview:
    recovery_identity: str
    expected_version: int
    candidate: GovernmentSubsidyRecoveryReconciliationCandidate


@dataclass(frozen=True, slots=True)
class RecoveryReconcileApplyRequest:
    recovery_identity: str
    incoming: GovernmentSubsidyIncomingRecoveryFact
    expected_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.recovery_identity, "recovery identity", 191)
        require_canonical_text(self.reason, "reason", 500)


class GovernmentSubsidyAnomalyRecoveryRepository(Protocol):
    def read_integrity(self, batch_id: int) -> GovernmentSubsidyIntegrityOwnerFact: ...
    def read_claim_drift(self, claim_item_id: int) -> GovernmentSubsidyClaimDriftOwnerFact: ...
    def read_return_overage(self, payable_identity: str) -> GovernmentSubsidyRecoveryRoot | None: ...
    def load_integrity(self, batch_id: int, *, for_update: bool) -> GovernmentSubsidyIntegrityOwnerFact: ...
    def persist_integrity_repair(self, request: IntegrityRepairApplyRequest, fact: GovernmentSubsidyIntegrityOwnerFact) -> str: ...
    def load_claim_drift(self, claim_item_id: int, *, for_update: bool) -> GovernmentSubsidyClaimDriftOwnerFact: ...
    def persist_claim_drift_correction(self, request: ClaimDriftCorrectionApplyRequest, fact: GovernmentSubsidyClaimDriftOwnerFact) -> str: ...
    def create_recovery_root(self, request: RecoveryCreateApplyRequest) -> str: ...
    def load_recovery(self, recovery_identity: str, *, for_update: bool) -> GovernmentSubsidyRecoveryRoot: ...
    def persist_recovery_reconciliation(self, request: RecoveryReconcileApplyRequest, candidate: GovernmentSubsidyRecoveryReconciliationCandidate) -> str: ...
    def find_receipt(
        self,
        idempotency_key: IdempotencyKey,
        command_fingerprint: PreviewFingerprint,
    ) -> str | None: ...


class GovernmentSubsidyAnomalyRecoveryApplication:
    def __init__(self, repository: GovernmentSubsidyAnomalyRecoveryRepository, unit_of_work_factory: Callable[[], UnitOfWork]) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def query(self, definition_code: str, subject_identity: str):
        return GovernmentSubsidyAnomalyOwnerReadback(self._repository).read(definition_code, subject_identity)

    def preview_integrity(self, batch_id: int) -> IntegrityRepairPreview:
        fact = self._repository.load_integrity(batch_id, for_update=False)
        if (
            not fact.authoritative_complete
            or not fact.immutable_roots_valid
            or fact.projection_consistent
            or fact.repair_path is not GovernmentSubsidyIntegrityRepairPath.DERIVED_REBUILD
        ):
            raise ValueError("government_subsidy_integrity_repair_not_eligible")
        return IntegrityRepairPreview(batch_id, fact.owner_version, fact.repair_path, _fingerprint("integrity", fact.batch_id, fact.owner_version, fact.repair_path.value, fact.owner_snapshot_token))

    def apply_integrity(self, request: IntegrityRepairApplyRequest) -> str:
        with self._unit_of_work_factory() as uow:
            replay = _check_replay(
                self._repository,
                request.idempotency_key,
                integrity_repair_command_fingerprint(request),
            )
            if replay is not None:
                return replay
            fact = self._repository.load_integrity(request.batch_id, for_update=True)
            _verify_integrity(request, fact)
            receipt = self._repository.persist_integrity_repair(request, fact)
            uow.commit()
            return receipt

    def preview_claim_drift(self, claim_item_id: int) -> ClaimDriftCorrectionPreview:
        fact = self._repository.load_claim_drift(claim_item_id, for_update=False)
        if (
            not fact.authoritative_complete
            or not fact.frozen_claim_immutable
            or not fact.drift_detected
            or fact.revision_resolved
            or fact.repair_path
            is GovernmentSubsidyClaimDriftRepairPath.STRUCTURAL_AMBIGUITY
        ):
            raise ValueError("government_subsidy_claim_drift_repair_not_eligible")
        return ClaimDriftCorrectionPreview(
            claim_item_id,
            fact.owner_version,
            fact.repair_path,
            fact.scheduling_snapshot_identity,
            fact.scheduling_snapshot_token,
            fact.scheduling_snapshot_version,
            _claim_drift_fingerprint(fact),
        )

    def apply_claim_drift(self, request: ClaimDriftCorrectionApplyRequest) -> str:
        with self._unit_of_work_factory() as uow:
            replay = _check_replay(
                self._repository,
                request.idempotency_key,
                claim_correction_command_fingerprint(request),
            )
            if replay is not None:
                return replay
            fact = self._repository.load_claim_drift(request.claim_item_id, for_update=True)
            if fact.owner_version != request.expected_version.value or fact.repair_path is not request.repair_path:
                raise ValueError("government_subsidy_claim_drift_stale")
            expected = _claim_drift_fingerprint(fact)
            if (
                expected != request.preview_fingerprint
                or request.scheduling_snapshot_identity
                != fact.scheduling_snapshot_identity
                or request.scheduling_snapshot_token != fact.scheduling_snapshot_token
                or request.scheduling_snapshot_version
                != fact.scheduling_snapshot_version
            ):
                raise ValueError("government_subsidy_claim_drift_stale")
            receipt = self._repository.persist_claim_drift_correction(request, fact)
            uow.commit()
            return receipt

    def create_recovery(self, request: RecoveryCreateApplyRequest) -> str:
        with self._unit_of_work_factory() as uow:
            replay = _check_replay(
                self._repository,
                request.root.idempotency_key,
                recovery_create_command_fingerprint(request),
            )
            if replay is not None:
                return replay
            receipt = self._repository.create_recovery_root(request)
            uow.commit()
            return receipt

    def preview_recovery_reconciliation(self, recovery_identity: str, incoming: GovernmentSubsidyIncomingRecoveryFact) -> RecoveryReconcilePreview:
        root = self._repository.load_recovery(recovery_identity, for_update=False)
        candidate = build_recovery_reconciliation_candidate(root, incoming)
        return RecoveryReconcilePreview(recovery_identity, root.version, candidate)

    def apply_recovery_reconciliation(self, request: RecoveryReconcileApplyRequest) -> str:
        with self._unit_of_work_factory() as uow:
            replay = _check_replay(
                self._repository,
                request.idempotency_key,
                recovery_reconcile_command_fingerprint(request),
            )
            if replay is not None:
                return replay
            root = self._repository.load_recovery(request.recovery_identity, for_update=True)
            if root.version != request.expected_version.value:
                raise ValueError("government_subsidy_recovery_stale")
            candidate = build_recovery_reconciliation_candidate(root, request.incoming)
            if candidate.fingerprint != request.preview_fingerprint:
                raise ValueError("government_subsidy_recovery_stale")
            receipt = self._repository.persist_recovery_reconciliation(request, candidate)
            uow.commit()
            return receipt


def _verify_integrity(request, fact):
    if (
        request.repair_path is not GovernmentSubsidyIntegrityRepairPath.DERIVED_REBUILD
        or fact.owner_version != request.expected_version.value
        or fact.repair_path is not request.repair_path
    ):
        raise ValueError("government_subsidy_integrity_stale")
    expected = _fingerprint("integrity", fact.batch_id, fact.owner_version, fact.repair_path.value, fact.owner_snapshot_token)
    if expected != request.preview_fingerprint:
        raise ValueError("government_subsidy_integrity_stale")


def _check_replay(repository, key, command_fingerprint):
    receipt = repository.find_receipt(key, command_fingerprint)
    if receipt is not None:
        return receipt
    return None


def _fingerprint(*values) -> PreviewFingerprint:
    return fingerprint_payload({"operation": values[0], "identity": values[1], "version": values[2], "path": values[3], "snapshot": values[4]})


def _claim_drift_fingerprint(
    fact: GovernmentSubsidyClaimDriftOwnerFact,
) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "operation": "claim-drift",
            "identity": fact.claim_item_id,
            "version": fact.owner_version,
            "path": fact.repair_path.value,
            "snapshot": fact.owner_snapshot_token,
            "scheduling_snapshot_identity": fact.scheduling_snapshot_identity,
            "scheduling_snapshot_token": fact.scheduling_snapshot_token,
            "scheduling_snapshot_version": fact.scheduling_snapshot_version,
        }
    )


def integrity_repair_command_fingerprint(
    request: IntegrityRepairApplyRequest,
) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "operation": "integrity_rebuild",
            "batch_id": request.batch_id,
            "expected_version": request.expected_version.value,
            "repair_path": request.repair_path.value,
            "preview_fingerprint": request.preview_fingerprint.value,
            "actor": request.actor.actor_id,
            "reason": request.reason,
            "correlation_id": request.correlation_id.value,
        }
    )


def claim_correction_command_fingerprint(
    request: ClaimDriftCorrectionApplyRequest,
) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "operation": "claim_correction",
            "claim_item_id": request.claim_item_id,
            "expected_version": request.expected_version.value,
            "repair_path": request.repair_path.value,
            "scheduling_snapshot_identity": request.scheduling_snapshot_identity,
            "scheduling_snapshot_token": request.scheduling_snapshot_token,
            "scheduling_snapshot_version": request.scheduling_snapshot_version,
            "successor_revision_identity": request.successor_revision_identity,
            "financial_consequence_reference": request.financial_consequence_reference,
            "preview_fingerprint": request.preview_fingerprint.value,
            "actor": request.actor.actor_id,
            "reason": request.reason,
            "correlation_id": request.correlation_id.value,
        }
    )


def recovery_create_command_fingerprint(
    request: RecoveryCreateApplyRequest,
) -> PreviewFingerprint:
    root = request.root
    return fingerprint_payload(
        {
            "operation": "recovery_create",
            "recovery_identity": root.recovery_identity,
            "source_outgoing_bank_fact_identity": root.source_outgoing_bank_fact_identity,
            "original_return_obligation_identity": root.original_return_obligation_identity,
            "lawful_amount_ntd": root.lawful_amount_ntd.amount,
            "actual_amount_ntd": root.actual_amount_ntd.amount,
            "government_payer_identity": root.government_payer_identity,
            "actor": root.actor,
            "reason": root.reason,
            "evidence_reference": root.evidence_reference,
            "correlation_id": request.correlation_id.value,
        }
    )


def recovery_reconcile_command_fingerprint(
    request: RecoveryReconcileApplyRequest,
) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "operation": "recovery_reconcile",
            "recovery_identity": request.recovery_identity,
            "incoming_bank_fact_identity": request.incoming.bank_fact_identity,
            "incoming_amount_ntd": request.incoming.amount_ntd.amount,
            "government_payer_identity": request.incoming.government_payer_identity,
            "expected_version": request.expected_version.value,
            "preview_fingerprint": request.preview_fingerprint.value,
            "actor": request.actor.actor_id,
            "reason": request.reason,
            "correlation_id": request.correlation_id.value,
        }
    )


__all__ = [
    "ClaimDriftCorrectionApplyRequest", "ClaimDriftCorrectionPreview",
    "GovernmentSubsidyAnomalyRecoveryApplication", "GovernmentSubsidyAnomalyRecoveryRepository",
    "IntegrityRepairApplyRequest", "IntegrityRepairPreview", "RecoveryCreateApplyRequest",
    "RecoveryReconcileApplyRequest", "RecoveryReconcilePreview",
    "claim_correction_command_fingerprint",
    "integrity_repair_command_fingerprint",
    "recovery_create_command_fingerprint",
    "recovery_reconcile_command_fingerprint",
]
