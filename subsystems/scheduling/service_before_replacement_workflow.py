"""
File: service_before_replacement_workflow.py
Description: Scheduling 服務前換人 Query、Preview、Apply 與 owner readback。
"""

from __future__ import annotations

import json
import re
from hashlib import sha256
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Protocol

from domains.scheduling.service_before_replacement import (
    ReplacementOutcome,
    ReplacementResumeStep,
    ReplacementScenario,
    ServiceBeforeReplacementCandidate,
    ServiceBeforeReplacementFacts,
    ServiceBeforeReplacementQuery,
    preview_service_before_replacement,
    query_service_before_replacement,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.ports import OutboxIntent, UnitOfWork
from shared_kernel.validation import require_canonical_text, require_nonnegative_integer


_IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,190}$")


class ReplacementApplyStatus(StrEnum):
    APPLIED = "applied"
    REPLAYED = "replayed"
    BLOCKED = "blocked"
    SUBSTITUTION_REFERRAL = "substitution_referral"
    OUTCOME_UNKNOWN = "outcome_unknown"


@dataclass(frozen=True, slots=True)
class ServiceBeforeReplacementQueryRequest:
    case_no: str
    scenario: ReplacementScenario
    correlation_id: CorrelationId
    reason: str | None = None
    evidence: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "replacement case number", 50)
        if not isinstance(self.scenario, ReplacementScenario):
            object.__setattr__(self, "scenario", ReplacementScenario(self.scenario))
        if self.reason is None and self.evidence is None:
            return
        if self.reason is None or self.evidence is None:
            raise ValueError("replacement preview reason/evidence must be supplied together")
        require_canonical_text(self.reason, "replacement reason", 500)
        if not isinstance(self.evidence, tuple):
            raise TypeError("replacement evidence must be a tuple")
        for value in self.evidence:
            require_canonical_text(value, "replacement evidence", 191)
        if not self.evidence or self.evidence != tuple(sorted(set(self.evidence))):
            raise ValueError("replacement evidence must be canonical")


ServiceBeforeReplacementPreviewRequest = ServiceBeforeReplacementQueryRequest


@dataclass(frozen=True, slots=True)
class ApplyServiceBeforeReplacement:
    case_no: str
    scenario: ReplacementScenario
    expected_generation_version: ExpectedVersion
    expected_event_version: ExpectedVersion
    expected_aggregate_version: ExpectedVersion
    prior_generation_identity: str
    prior_event_identity: str
    prior_aggregate_identity: str
    preview_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    actor: ActorContext
    reason: str
    evidence: tuple[str, ...]
    correlation_id: CorrelationId

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "replacement case number", 50)
        if not isinstance(self.scenario, ReplacementScenario):
            object.__setattr__(self, "scenario", ReplacementScenario(self.scenario))
        for value, label in (
            (self.prior_generation_identity, "prior generation identity"),
            (self.prior_event_identity, "prior event identity"),
            (self.prior_aggregate_identity, "prior aggregate identity"),
            (self.reason, "replacement reason"),
        ):
            require_canonical_text(value, label, 500)
        if not isinstance(self.evidence, tuple):
            raise TypeError("replacement evidence must be a tuple")
        for value in self.evidence:
            require_canonical_text(value, "replacement evidence", 191)
        if self.evidence != tuple(sorted(set(self.evidence))):
            raise ValueError("replacement evidence must be canonical")
        if not _IDEMPOTENCY_KEY_PATTERN.fullmatch(self.idempotency_key.value):
            raise ValueError("replacement idempotency key is invalid")


ServiceBeforeReplacementApplyRequest = ApplyServiceBeforeReplacement


@dataclass(frozen=True, slots=True)
class ReplacementOwnerReadback:
    case_no: str
    generation_identity: str
    event_identity: str
    successor_round_identity: str
    generation_version: int
    event_version: int
    aggregate_version: int
    retained_root_ids: tuple[str, ...]
    superseded_root_ids: tuple[str, ...]
    created_root_ids: tuple[str, ...]
    resume_step: ReplacementResumeStep
    candidate_count: int
    zero_candidate_disposition: str | None
    complete: bool = True
    root_set_digests: tuple[str, ...] = ()
    root_set_counts: tuple[int, ...] = ()
    outbox_identity: str = ""
    matching_package_lineage_id: int | None = None
    matching_event_id: int | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "readback case number", 50)
        for value, label in (
            (self.generation_identity, "readback generation identity"),
            (self.event_identity, "readback event identity"),
            (self.successor_round_identity, "readback successor round identity"),
        ):
            require_canonical_text(value, label, 191)
        for value, label in (
            (self.generation_version, "readback generation version"),
            (self.event_version, "readback event version"),
            (self.aggregate_version, "readback aggregate version"),
        ):
            require_nonnegative_integer(value, label)
        _validate_ids(self.retained_root_ids, "readback retained root ids")
        _validate_ids(self.superseded_root_ids, "readback superseded root ids")
        _validate_ids(self.created_root_ids, "readback created root ids")
        if not isinstance(self.resume_step, ReplacementResumeStep):
            raise TypeError("readback resume step is invalid")
        require_nonnegative_integer(self.candidate_count, "readback candidate count")
        if self.zero_candidate_disposition is not None:
            require_canonical_text(
                self.zero_candidate_disposition,
                "readback zero candidate disposition",
                500,
            )
            if (
                self.zero_candidate_disposition != "blocked_no_candidate"
                or self.candidate_count != 0
                or self.resume_step is not ReplacementResumeStep.STEP_2
            ):
                raise ValueError("readback zero candidate disposition is invalid")
        if not isinstance(self.complete, bool):
            raise TypeError("readback completeness must be bool")
        if self.root_set_digests and len(self.root_set_digests) != 3:
            raise ValueError("readback root set digests must contain three values")
        if self.root_set_counts and len(self.root_set_counts) != 3:
            raise ValueError("readback root set counts must contain three values")


@dataclass(frozen=True, slots=True)
class ReplacementReceipt:
    case_no: str
    receipt_identity: str
    idempotency_key: IdempotencyKey
    command_fingerprint: PreviewFingerprint
    preview_fingerprint: PreviewFingerprint
    replacement_generation_identity: str
    replacement_event_identity: str
    successor_round_identity: str
    resulting_generation_version: int
    resulting_event_version: int
    resulting_aggregate_version: int
    outbox_identity: str
    retained_root_ids: tuple[str, ...]
    superseded_root_ids: tuple[str, ...]
    created_root_ids: tuple[str, ...]
    retained_root_set_digest: str = ""
    retained_root_count: int = 0
    superseded_root_set_digest: str = ""
    superseded_root_count: int = 0
    created_root_set_digest: str = ""
    created_root_count: int = 0
    matching_package_lineage_id: int | None = None
    matching_event_id: int | None = None

    def __post_init__(self) -> None:
        require_canonical_text(self.case_no, "receipt case number", 50)
        require_canonical_text(self.receipt_identity, "replacement receipt identity", 191)
        for value, label in (
            (self.replacement_generation_identity, "receipt generation identity"),
            (self.replacement_event_identity, "receipt event identity"),
            (self.successor_round_identity, "receipt successor round identity"),
            (self.outbox_identity, "receipt outbox identity"),
        ):
            require_canonical_text(value, label, 191)
        for value, label in (
            (self.resulting_generation_version, "receipt generation version"),
            (self.resulting_event_version, "receipt event version"),
            (self.resulting_aggregate_version, "receipt aggregate version"),
        ):
            require_nonnegative_integer(value, label)
        _validate_ids(self.retained_root_ids, "receipt retained root ids")
        _validate_ids(self.superseded_root_ids, "receipt superseded root ids")
        _validate_ids(self.created_root_ids, "receipt created root ids")
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise TypeError("receipt idempotency key is invalid")
        if not isinstance(self.command_fingerprint, PreviewFingerprint) or not isinstance(self.preview_fingerprint, PreviewFingerprint):
            raise TypeError("receipt fingerprint is invalid")


@dataclass(frozen=True, slots=True)
class StoredReplacementReceipt:
    command_fingerprint: PreviewFingerprint
    receipt: ReplacementReceipt


@dataclass(frozen=True, slots=True)
class ReplacementPersistenceBundle:
    """One repository call owns event, supersession, successor, receipt and outbox."""

    command: ApplyServiceBeforeReplacement
    candidate: ServiceBeforeReplacementCandidate
    receipt: ReplacementReceipt
    outbox: OutboxIntent


@dataclass(frozen=True, slots=True)
class ReplacementApplyResult:
    status: ReplacementApplyStatus
    case_no: str
    candidate: ServiceBeforeReplacementCandidate | None = None
    receipt: ReplacementReceipt | None = None
    readback: ReplacementOwnerReadback | None = None
    error: TypedError | None = None


class ServiceBeforeReplacementRepository(Protocol):
    """Typed Scheduling port; implementations never commit or rollback."""

    def load_facts(self, case_no: str, *, for_update: bool) -> ServiceBeforeReplacementFacts | None: ...

    def load_facts_for_request(self, request: object, *, for_update: bool) -> ServiceBeforeReplacementFacts | None: ...

    def find_receipt(
        self, key: IdempotencyKey, case_no: str, *, for_update: bool
    ) -> StoredReplacementReceipt | None: ...

    def persist_replacement(self, bundle: ReplacementPersistenceBundle) -> ReplacementReceipt | None: ...

    def load_owner_readback(
        self, case_no: str, *, for_update: bool
    ) -> ReplacementOwnerReadback | None: ...


class ServiceBeforeReplacementWorkflowError(Exception):
    def __init__(self, error: TypedError) -> None:
        super().__init__(error.code)
        self.error = error


class ServiceBeforeReplacementWorkflow:
    def __init__(
        self,
        repository: ServiceBeforeReplacementRepository,
        unit_of_work_factory: Callable[[], UnitOfWork],
    ) -> None:
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def query(self, request: ServiceBeforeReplacementQueryRequest) -> ServiceBeforeReplacementQuery:
        facts = _load_facts(self._repository, request, for_update=False)
        if facts is None:
            raise _error(ErrorCategory.NOT_FOUND, "replacement_facts_not_found", "找不到服務前換人根事實。", request.correlation_id)
        _validate_request_identity(request, facts)
        return query_service_before_replacement(facts)

    def preview(self, request: ServiceBeforeReplacementPreviewRequest) -> ServiceBeforeReplacementCandidate:
        facts = _load_facts(self._repository, request, for_update=False)
        if facts is None:
            raise _error(ErrorCategory.NOT_FOUND, "replacement_facts_not_found", "找不到服務前換人根事實。", request.correlation_id)
        _validate_request_identity(request, facts)
        _validate_preview_context(request, facts)
        return preview_service_before_replacement(facts)

    def apply(self, command: ApplyServiceBeforeReplacement) -> ReplacementApplyResult:
        command_fingerprint = replacement_command_fingerprint(command)
        committed = False
        replay_receipt = None
        candidate = None
        receipt = None
        unit_of_work = self._unit_of_work_factory()
        try:
            with unit_of_work:
                stored = self._repository.find_receipt(command.idempotency_key, command.case_no, for_update=True)
                if stored is not None:
                    if stored.command_fingerprint != command_fingerprint:
                        raise _error(ErrorCategory.IDEMPOTENCY_MISMATCH, "replacement_idempotency_conflict", "同一 idempotency key 對應不同換人命令。", command.correlation_id)
                    replay_receipt = stored.receipt
                    # Lock/read inside the transaction, then verify again after commit.
                    self._repository.load_owner_readback(command.case_no, for_update=True)
                    unit_of_work.commit()
                    committed = True
                else:
                    facts = _load_facts(self._repository, command, for_update=True)
                    if facts is None:
                        raise _error(ErrorCategory.NOT_FOUND, "replacement_facts_not_found", "找不到服務前換人根事實。", command.correlation_id)
                    _validate_command_identity(command, facts)
                    candidate = preview_service_before_replacement(facts)
                    if candidate.fingerprint != command.preview_fingerprint:
                        raise _error(ErrorCategory.CONFLICT, "replacement_preview_stale", "服務前換人 Preview 已過期，請重新查詢。", command.correlation_id, current_version=ExpectedVersion(facts.aggregate_version))
                    if candidate.outcome is not ReplacementOutcome.READY:
                        unit_of_work.rollback()
                        return ReplacementApplyResult(_status_for_outcome(candidate.outcome), command.case_no, candidate=candidate, error=_candidate_error(candidate, command.correlation_id))

                    receipt = _receipt(command, candidate, command_fingerprint)
                    outbox = _outbox(command, candidate, receipt)
                    persisted_receipt = self._repository.persist_replacement(
                        ReplacementPersistenceBundle(command, candidate, receipt, outbox)
                    )
                    if persisted_receipt is not None:
                        receipt = persisted_receipt
                    persisted_readback = self._repository.load_owner_readback(command.case_no, for_update=True)
                    if not _readback_matches(persisted_readback, candidate):
                        raise _error(ErrorCategory.UNAVAILABLE, "replacement_readback_unavailable", "換人已寫入但交易內 owner readback 無法對帳。", command.correlation_id, retryable=True)
                    unit_of_work.commit()
                    committed = True
        except ServiceBeforeReplacementWorkflowError:
            if not committed:
                _safe_rollback(unit_of_work)
            raise
        except Exception as error:
            if not committed:
                _safe_rollback(unit_of_work)
            return ReplacementApplyResult(
                ReplacementApplyStatus.OUTCOME_UNKNOWN,
                command.case_no,
                error=_typed_error(ErrorCategory.UNAVAILABLE, "replacement_transaction_unknown", "換人交易結果無法確認。", command.correlation_id, retryable=True),
            )

        # The commit boundary was crossed; only a fresh owner readback can prove success.
        try:
            readback = self._repository.load_owner_readback(command.case_no, for_update=False)
        except Exception:
            readback = None
        if replay_receipt is not None:
            if not _receipt_readback_matches(readback, replay_receipt):
                return ReplacementApplyResult(
                    ReplacementApplyStatus.OUTCOME_UNKNOWN,
                    command.case_no,
                    receipt=replay_receipt,
                    readback=readback,
                    error=_typed_error(ErrorCategory.UNAVAILABLE, "replacement_replay_readback_unknown", "換人 replay 的 fresh owner readback 無法對帳。", command.correlation_id, retryable=True),
                )
            return ReplacementApplyResult(ReplacementApplyStatus.REPLAYED, command.case_no, receipt=replay_receipt, readback=readback)
        if not _readback_matches(readback, candidate):
            return ReplacementApplyResult(
                ReplacementApplyStatus.OUTCOME_UNKNOWN,
                command.case_no,
                candidate=candidate,
                receipt=receipt,
                readback=readback,
                error=_typed_error(ErrorCategory.UNAVAILABLE, "replacement_post_commit_readback_unknown", "換人已提交但 fresh owner readback 無法對帳。", command.correlation_id, retryable=True),
            )
        return ReplacementApplyResult(ReplacementApplyStatus.APPLIED, command.case_no, candidate=candidate, receipt=receipt, readback=readback)


def replacement_command_fingerprint(command: ApplyServiceBeforeReplacement) -> PreviewFingerprint:
    return fingerprint_payload({
        "command_type": "scheduling.service_before_replacement.apply",
        "command_version": 1,
        "case_no": command.case_no,
        "scenario": command.scenario.value,
        "expected_generation_version": command.expected_generation_version.value,
        "expected_event_version": command.expected_event_version.value,
        "expected_aggregate_version": command.expected_aggregate_version.value,
        "prior_generation_identity": command.prior_generation_identity,
        "prior_event_identity": command.prior_event_identity,
        "prior_aggregate_identity": command.prior_aggregate_identity,
        "preview_fingerprint": command.preview_fingerprint.value,
        "actor": command.actor.actor_id,
        "capabilities": command.actor.permission_scope,
        "reason": command.reason,
        "evidence": command.evidence,
    })


def _receipt(command, candidate, command_fingerprint) -> ReplacementReceipt:
    retained = tuple(sorted(item.root_id for item in candidate.retained_roots))
    superseded = tuple(sorted(item.root_id for item in candidate.superseded_roots))
    created = tuple(sorted(item.root_id for item in candidate.created_roots))
    return ReplacementReceipt(
        command.case_no,
        f"replacement-receipt:{command.case_no}:{candidate.resulting_event_version}",
        command.idempotency_key,
        command_fingerprint,
        candidate.fingerprint,
        candidate.replacement_generation_identity or "",
        candidate.replacement_event_identity or "",
        candidate.successor_round_identity or "",
        candidate.resulting_generation_version or 0,
        candidate.resulting_event_version or 0,
        candidate.resulting_aggregate_version or 0,
        f"replacement-outbox:{command.case_no}:{candidate.resulting_event_version}",
        retained,
        superseded,
        created,
        _root_set_digest(retained), len(retained),
        _root_set_digest(superseded), len(superseded),
        _root_set_digest(created), len(created),
    )


def _root_set_digest(values: tuple[str, ...]) -> str:
    return sha256("\n".join(sorted(values)).encode("utf-8")).hexdigest()


def _load_facts(repository, request, *, for_update):
    loader = getattr(repository, "load_facts_for_request", None)
    if loader is not None:
        return loader(request, for_update=for_update)
    return repository.load_facts(request.case_no, for_update=for_update)


def _outbox(command, candidate, receipt) -> OutboxIntent:
    payload = json.dumps({
        "case_no": command.case_no,
        "event_identity": receipt.replacement_event_identity,
        "successor_round_identity": receipt.successor_round_identity,
        "superseded_root_ids": candidate.superseded_root_ids,
        "created_root_ids": candidate.created_root_ids,
        "receipt_identity": receipt.receipt_identity,
    }, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return OutboxIntent(
        "scheduling.service_before_replacement",
        command.case_no,
        "service_before_replacement_successor_created",
        payload,
        command.idempotency_key.value,
    )


def _validate_request_identity(request, facts) -> None:
    if facts.case_no != request.case_no:
        raise _error(ErrorCategory.CONFLICT, "replacement_case_identity_mismatch", "服務前換人 case identity 與 Scheduling 根事實不一致。", request.correlation_id)
    if facts.scenario is not request.scenario:
        raise _error(ErrorCategory.CONFLICT, "replacement_scenario_identity_mismatch", "服務前換人 scenario 與 Scheduling 根事實不一致。", request.correlation_id)


def _validate_preview_context(request, facts) -> None:
    """Bind API reason/evidence to the same facts used by Apply and fingerprinting."""
    if request.reason is None and request.evidence is None:
        return
    if (request.reason, request.evidence) != (facts.replacement_reason, facts.reason_evidence):
        raise _error(
            ErrorCategory.CONFLICT,
            "replacement_reason_evidence_drift",
            "服務前換人 Preview reason/evidence 與 Scheduling 根事實不一致。",
            request.correlation_id,
        )


def _validate_command_identity(command, facts) -> None:
    _validate_request_identity(command, facts)
    expected = (
        (command.expected_generation_version.value, facts.generation_version),
        (command.expected_event_version.value, facts.event_version),
        (command.expected_aggregate_version.value, facts.aggregate_version),
    )
    if any(left != right for left, right in expected):
        raise _error(ErrorCategory.CONFLICT, "replacement_stale_version", "服務前換人根事實已變更。", command.correlation_id, current_version=ExpectedVersion(facts.aggregate_version))
    if (command.prior_generation_identity, command.prior_event_identity, command.prior_aggregate_identity) != (facts.prior_generation_identity, facts.prior_event_identity, facts.prior_aggregate_identity):
        raise _error(ErrorCategory.CONFLICT, "replacement_identity_drift", "服務前換人 prior identity 已變更。", command.correlation_id)
    if command.reason != facts.replacement_reason or command.evidence != facts.reason_evidence:
        raise _error(ErrorCategory.CONFLICT, "replacement_reason_evidence_drift", "服務前換人 reason/evidence 已變更。", command.correlation_id)


def _readback_matches(readback, candidate) -> bool:
    if readback is None or not readback.complete:
        return False
    matches = (
        readback.case_no == candidate.case_no
        and readback.generation_identity == candidate.replacement_generation_identity
        and readback.event_identity == candidate.replacement_event_identity
        and readback.successor_round_identity == candidate.successor_round_identity
        and readback.generation_version == candidate.resulting_generation_version
        and readback.event_version == candidate.resulting_event_version
        and readback.aggregate_version == candidate.resulting_aggregate_version
        and readback.resume_step == candidate.resume_step
        and readback.candidate_count
        == (0 if candidate.candidate_pool_reuse_proof is None else 1)
        and readback.zero_candidate_disposition
        == (
            "blocked_no_candidate"
            if candidate.scenario is ReplacementScenario.R07
            else None
        )
        and set(readback.retained_root_ids) == set(candidate.retained_root_ids)
        and set(readback.superseded_root_ids) == set(candidate.superseded_root_ids)
        and set(readback.created_root_ids) == set(candidate.created_root_ids)
    )
    if not matches:
        return False
    if readback.root_set_digests:
        expected = tuple(_root_set_digest(values) for values in (
            candidate.retained_root_ids, candidate.superseded_root_ids, candidate.created_root_ids
        ))
        if readback.root_set_digests != expected:
            return False
    if readback.root_set_counts and readback.root_set_counts != tuple(
        len(values) for values in (candidate.retained_root_ids, candidate.superseded_root_ids, candidate.created_root_ids)
    ):
        return False
    if readback.outbox_identity and readback.outbox_identity != _expected_outbox_identity(candidate):
        return False
    if readback.outbox_identity and (
        readback.matching_package_lineage_id is None
        or readback.matching_event_id is None
        or readback.matching_package_lineage_id <= 0
        or readback.matching_event_id <= 0
    ):
        return False
    return True


def _receipt_readback_matches(readback, receipt) -> bool:
    matches = (
        readback is not None
        and readback.complete
        and readback.case_no == receipt.case_no
        and readback.generation_identity == receipt.replacement_generation_identity
        and readback.event_identity == receipt.replacement_event_identity
        and readback.successor_round_identity == receipt.successor_round_identity
        and readback.generation_version == receipt.resulting_generation_version
        and readback.event_version == receipt.resulting_event_version
        and readback.aggregate_version == receipt.resulting_aggregate_version
        and set(readback.retained_root_ids) == set(receipt.retained_root_ids)
        and set(readback.superseded_root_ids) == set(receipt.superseded_root_ids)
        and set(readback.created_root_ids) == set(receipt.created_root_ids)
    )
    if not matches:
        return False
    if readback.root_set_digests:
        expected = tuple(_root_set_digest(values) for values in (
            receipt.retained_root_ids, receipt.superseded_root_ids, receipt.created_root_ids
        ))
        if readback.root_set_digests != expected:
            return False
    if readback.root_set_counts and readback.root_set_counts != tuple(
        len(values) for values in (receipt.retained_root_ids, receipt.superseded_root_ids, receipt.created_root_ids)
    ):
        return False
    if readback.outbox_identity and readback.outbox_identity != receipt.outbox_identity:
        return False
    if receipt.matching_package_lineage_id is not None and readback.matching_package_lineage_id != receipt.matching_package_lineage_id:
        return False
    if receipt.matching_event_id is not None and readback.matching_event_id != receipt.matching_event_id:
        return False
    return True


def _expected_outbox_identity(candidate) -> str:
    return f"replacement-outbox:{candidate.case_no}:{candidate.resulting_event_version}"


def _status_for_outcome(outcome):
    return ReplacementApplyStatus.SUBSTITUTION_REFERRAL if outcome is ReplacementOutcome.SUBSTITUTION_REFERRAL else ReplacementApplyStatus.BLOCKED


def _candidate_error(candidate, correlation_id):
    code = candidate.blockers[0] if candidate.blockers else "replacement_blocked"
    category = ErrorCategory.DOMAIN_BLOCKED if candidate.outcome is ReplacementOutcome.BLOCKED else ErrorCategory.CONFLICT
    return _typed_error(category, code, "服務前換人目前不可執行。", correlation_id, retryable=False)


def _typed_error(category, code, message, correlation_id, *, current_version=None, retryable=False):
    return TypedError(category, code, message, correlation_id, current_version=current_version, retryable=retryable)


def _error(category, code, message, correlation_id, *, current_version=None, retryable=False):
    return ServiceBeforeReplacementWorkflowError(_typed_error(category, code, message, correlation_id, current_version=current_version, retryable=retryable))


def _safe_rollback(unit_of_work):
    try:
        unit_of_work.rollback()
    except Exception:
        pass


def _validate_ids(values, label):
    if not isinstance(values, tuple):
        raise TypeError(f"{label} must be a tuple")
    for value in values:
        require_canonical_text(value, label, 191)
    if len(set(values)) != len(values):
        raise ValueError(f"{label} must be unique")


__all__ = [
    "ApplyServiceBeforeReplacement", "ReplacementApplyResult", "ReplacementApplyStatus",
    "ReplacementOwnerReadback", "ReplacementPersistenceBundle", "ReplacementReceipt",
    "ServiceBeforeReplacementApplyRequest", "ServiceBeforeReplacementPreviewRequest",
    "ServiceBeforeReplacementQueryRequest", "ServiceBeforeReplacementRepository",
    "ServiceBeforeReplacementWorkflow", "ServiceBeforeReplacementWorkflowError",
    "StoredReplacementReceipt", "replacement_command_fingerprint",
]
