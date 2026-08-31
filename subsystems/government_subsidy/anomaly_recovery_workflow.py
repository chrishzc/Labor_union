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
    GovernmentSubsidyReturnReconciliationWithExcessCandidate,
    build_return_reconciliation_with_excess_candidate,
    build_recovery_reconciliation_candidate,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.ports import UnitOfWork
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)
from subsystems.government_subsidy.anomaly_owner_readback import (
    GovernmentSubsidyAnomalyOwnerReadback,
)
from subsystems.government_subsidy.current_anomaly_facts import (
    GovernmentSubsidyAnomalyRecheckRequest,
    GovernmentSubsidyCurrentIssueCode,
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


@dataclass(frozen=True, slots=True)
class PreviewGovernmentSubsidyReturnReconciliationWithExcess:
    candidate: GovernmentSubsidyReturnReconciliationWithExcessCandidate


@dataclass(frozen=True, slots=True)
class ConfirmGovernmentSubsidyReturnReconciliationWithExcess:
    preview_fingerprint: PreviewFingerprint
    confirmed: bool

    def __post_init__(self) -> None:
        if type(self.confirmed) is not bool:
            raise TypeError("government subsidy return excess confirmation must be bool")


@dataclass(frozen=True, slots=True)
class ApplyGovernmentSubsidyReturnReconciliationWithExcess:
    overpayment_identity: str
    payable_identity: str
    finance_import_row_id: int
    expected_overpayment_version: ExpectedVersion
    expected_payable_version: ExpectedVersion
    confirmation: ConfirmGovernmentSubsidyReturnReconciliationWithExcess
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    evidence_reference: str
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.overpayment_identity, "overpayment identity", 191)
        require_canonical_text(self.payable_identity, "return obligation identity", 191)
        require_positive_integer(self.finance_import_row_id, "finance import row id")
        require_canonical_text(self.reason, "reason", 500)
        require_canonical_text(self.evidence_reference, "evidence reference", 191)
        if not isinstance(
            self.confirmation,
            ConfirmGovernmentSubsidyReturnReconciliationWithExcess,
        ) or not self.confirmation.confirmed:
            raise ValueError("government_subsidy_return_excess_confirmation_required")


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyReturnReconciliationWithExcessReceipt:
    receipt_reference: str
    recovery_identity: str
    overpayment_identity: str
    payable_identity: str
    bank_fact_identity: str
    lawful_amount_ntd: int
    actual_amount_ntd: int
    excess_amount_ntd: int
    resulting_overpayment_version: int
    resulting_payable_version: int

    def __post_init__(self) -> None:
        for value, label in (
            (self.receipt_reference, "receipt reference"),
            (self.recovery_identity, "recovery identity"),
            (self.overpayment_identity, "overpayment identity"),
            (self.payable_identity, "return obligation identity"),
            (self.bank_fact_identity, "outgoing bank fact identity"),
        ):
            require_canonical_text(value, label, 191)
        require_positive_integer(self.lawful_amount_ntd, "lawful return amount")
        require_positive_integer(self.actual_amount_ntd, "actual outgoing amount")
        require_positive_integer(self.excess_amount_ntd, "excess recovery amount")
        require_nonnegative_integer(
            self.resulting_overpayment_version,
            "resulting overpayment version",
        )
        require_nonnegative_integer(
            self.resulting_payable_version,
            "resulting return obligation version",
        )
        if (
            self.actual_amount_ntd <= self.lawful_amount_ntd
            or self.excess_amount_ntd
            != self.actual_amount_ntd - self.lawful_amount_ntd
        ):
            raise ValueError("government subsidy return excess receipt is invalid")


@dataclass(frozen=True, slots=True)
class GovernmentSubsidyReturnReconciliationWithExcessResult:
    receipt: GovernmentSubsidyReturnReconciliationWithExcessReceipt
    readback: GovernmentSubsidyRecoveryRoot


class GovernmentSubsidyReturnExcessRecheckPort(Protocol):
    def append_government_subsidy_recheck(
        self,
        request: GovernmentSubsidyAnomalyRecheckRequest,
    ) -> None: ...


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
    def load_return_reconciliation_with_excess_context(
        self,
        payable_identity: str,
        finance_import_row_id: int,
        *,
        for_update: bool,
    ): ...
    def apply_return_reconciliation_with_excess(
        self,
        request: ApplyGovernmentSubsidyReturnReconciliationWithExcess,
        candidate: GovernmentSubsidyReturnReconciliationWithExcessCandidate,
        command_fingerprint: PreviewFingerprint,
    ) -> GovernmentSubsidyReturnReconciliationWithExcessReceipt: ...
    def find_return_reconciliation_with_excess_receipt(
        self,
        idempotency_key: IdempotencyKey,
        command_fingerprint: PreviewFingerprint,
    ) -> GovernmentSubsidyReturnReconciliationWithExcessReceipt | None: ...
    def find_receipt(
        self,
        idempotency_key: IdempotencyKey,
        command_fingerprint: PreviewFingerprint,
    ) -> str | None: ...


class GovernmentSubsidyAnomalyRecoveryApplication:
    def __init__(
        self,
        repository: GovernmentSubsidyAnomalyRecoveryRepository,
        unit_of_work_factory: Callable[[], UnitOfWork],
        anomaly_rechecks: GovernmentSubsidyReturnExcessRecheckPort | None = None,
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory
        self._anomaly_rechecks = anomaly_rechecks

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

    def preview_return_reconciliation_with_excess(
        self,
        payable_identity: str,
        finance_import_row_id: int,
    ) -> PreviewGovernmentSubsidyReturnReconciliationWithExcess:
        obligation, outgoing = self._repository.load_return_reconciliation_with_excess_context(
            payable_identity,
            finance_import_row_id,
            for_update=False,
        )
        return PreviewGovernmentSubsidyReturnReconciliationWithExcess(
            build_return_reconciliation_with_excess_candidate(obligation, outgoing)
        )

    def apply_return_reconciliation_with_excess(
        self,
        request: ApplyGovernmentSubsidyReturnReconciliationWithExcess,
    ) -> GovernmentSubsidyReturnReconciliationWithExcessResult:
        command_fingerprint = return_reconciliation_with_excess_command_fingerprint(
            request
        )
        with self._unit_of_work_factory() as uow:
            receipt = self._repository.find_return_reconciliation_with_excess_receipt(
                request.idempotency_key,
                command_fingerprint,
            )
            if receipt is None:
                obligation, outgoing = self._repository.load_return_reconciliation_with_excess_context(
                    request.payable_identity,
                    request.finance_import_row_id,
                    for_update=True,
                )
                candidate = build_return_reconciliation_with_excess_candidate(
                    obligation,
                    outgoing,
                )
                if (
                    request.overpayment_identity != candidate.overpayment_identity
                    or request.expected_overpayment_version.value
                    != candidate.expected_overpayment_version
                    or request.expected_payable_version.value
                    != candidate.expected_payable_version
                    or request.confirmation.preview_fingerprint != candidate.fingerprint
                ):
                    raise ValueError("government_subsidy_return_excess_stale")
                receipt = self._repository.apply_return_reconciliation_with_excess(
                    request,
                    candidate,
                    command_fingerprint,
                )
                if self._anomaly_rechecks is not None:
                    self._anomaly_rechecks.append_government_subsidy_recheck(
                        GovernmentSubsidyAnomalyRecheckRequest(
                            GovernmentSubsidyCurrentIssueCode.RETURN_OUTGOING_OVERAGE,
                            (candidate.payable_identity,),
                            tuple(
                                sorted(
                                    (
                                        "bank:" + candidate.bank_fact_identity,
                                        "payable:" + candidate.payable_identity,
                                        "recovery:" + candidate.recovery_identity,
                                    )
                                )
                            ),
                            receipt.resulting_overpayment_version,
                            candidate.fingerprint.value,
                            "government-subsidy-return-excess:"
                            + request.idempotency_key.value
                            + ":GOVSUB-007",
                        )
                    )
                uow.commit()
        readback = self._repository.load_recovery(
            receipt.recovery_identity,
            for_update=False,
        )
        return GovernmentSubsidyReturnReconciliationWithExcessResult(
            receipt,
            readback,
        )


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


def return_reconciliation_with_excess_command_fingerprint(
    request: ApplyGovernmentSubsidyReturnReconciliationWithExcess,
) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "operation": "government_subsidy_return_reconciliation_with_excess",
            "overpayment_identity": request.overpayment_identity,
            "payable_identity": request.payable_identity,
            "finance_import_row_id": request.finance_import_row_id,
            "expected_overpayment_version": request.expected_overpayment_version.value,
            "expected_payable_version": request.expected_payable_version.value,
            "preview_fingerprint": request.confirmation.preview_fingerprint.value,
            "confirmed": request.confirmation.confirmed,
            "actor": request.actor.actor_id,
            "reason": request.reason,
            "evidence_reference": request.evidence_reference,
            "correlation_id": request.correlation_id.value,
        }
    )


__all__ = [
    "ApplyGovernmentSubsidyReturnReconciliationWithExcess",
    "ClaimDriftCorrectionApplyRequest", "ClaimDriftCorrectionPreview",
    "ConfirmGovernmentSubsidyReturnReconciliationWithExcess",
    "GovernmentSubsidyAnomalyRecoveryApplication", "GovernmentSubsidyAnomalyRecoveryRepository",
    "GovernmentSubsidyReturnReconciliationWithExcessReceipt",
    "GovernmentSubsidyReturnReconciliationWithExcessResult",
    "IntegrityRepairApplyRequest", "IntegrityRepairPreview", "RecoveryCreateApplyRequest",
    "PreviewGovernmentSubsidyReturnReconciliationWithExcess",
    "RecoveryReconcileApplyRequest", "RecoveryReconcilePreview",
    "claim_correction_command_fingerprint",
    "integrity_repair_command_fingerprint",
    "recovery_create_command_fingerprint",
    "recovery_reconcile_command_fingerprint",
    "return_reconciliation_with_excess_command_fingerprint",
]
