"""
File: historical_operational_baseline.py
Description: 驗證歷史訂單作業基準候選與不可偽造的步驟投影。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Mapping

from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)

_CASE_NUMBER_MAXIMUM_LENGTH = 50
_ORDER_IDENTITY_MAXIMUM_LENGTH = 191
_REASON_MAXIMUM_LENGTH = 500
_EVIDENCE_REFERENCE_MAXIMUM_LENGTH = 191
_FIRST_STEP = 1
_LAST_STEP = 11
HISTORICAL_BASELINE_CATALOG_VERSION = 1


def _catalog_source_event_identity(owner_domain: str) -> str:
    """Name the owner read-port field required by a catalog descriptor."""

    return f"{owner_domain}.source_event_identity"


class HistoricalOperationalBaselineError(ValueError):
    """A candidate cannot satisfy the historical baseline contract."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _validate_step(selected_step: int) -> None:
    if isinstance(selected_step, bool) or not isinstance(selected_step, int):
        raise HistoricalOperationalBaselineError("historical_baseline_step_invalid")
    if not _FIRST_STEP <= selected_step <= _LAST_STEP:
        raise HistoricalOperationalBaselineError("historical_baseline_step_out_of_range")


def _validate_catalog_version(catalog_version: int) -> None:
    if isinstance(catalog_version, bool) or not isinstance(catalog_version, int):
        raise HistoricalOperationalBaselineError(
            "historical_baseline_catalog_version_invalid"
        )
    if catalog_version != HISTORICAL_BASELINE_CATALOG_VERSION:
        raise HistoricalOperationalBaselineError(
            "historical_baseline_catalog_version_unsupported"
        )


class HistoricalBaselineEvidenceMode(StrEnum):
    RETAINED = "retained"
    UNAVAILABLE_ACCEPTED = "historical_evidence_unavailable_accepted"


# Keep the longer name available at the domain boundary for callers that use
# the event's terminology.
HistoricalOperationalBaselineEvidenceMode = HistoricalBaselineEvidenceMode


class HistoricalBaselineStepState(StrEnum):
    HISTORICAL_BASELINE_COMPLETED = "historical_baseline_completed"
    IN_PROGRESS = "in_progress"


@dataclass(frozen=True, slots=True)
class HistoricalBaselineOwnerRootContract:
    """Immutable descriptor supplied by the owning Domain for one SOP step."""

    contract_id: str
    contract_version: int
    step: int
    owner_domain: str
    root_identity_kind: str
    root_identity_path: str
    terminal_predicate_id: str
    terminal_predicate_version: int
    repair_target: str
    repair_capability: str
    # These are descriptor-level requirements.  The fresh per-case values are
    # carried by HistoricalBaselineOwnerRoot below.
    source_event_identity: str | None = None
    source_version: int | None = None

    def __post_init__(self) -> None:
        for value, name, maximum in (
            (self.contract_id, "owner root contract id", _ORDER_IDENTITY_MAXIMUM_LENGTH),
            (self.owner_domain, "owner root domain", 100),
            (self.root_identity_kind, "owner root identity kind", 100),
            (self.root_identity_path, "owner root identity path", 255),
            (self.terminal_predicate_id, "owner root terminal predicate id", 191),
            (self.repair_target, "owner root repair target", 191),
            (self.repair_capability, "owner root repair capability", 191),
        ):
            require_canonical_text(value, name, maximum)
        if self.source_event_identity is None:
            raise HistoricalOperationalBaselineError(
                "historical_baseline_catalog_source_event_identity_required"
            )
        require_canonical_text(
            self.source_event_identity,
            "owner root source event identity field",
            191,
        )
        if self.source_version is None:
            raise HistoricalOperationalBaselineError(
                "historical_baseline_catalog_source_version_required"
            )
        require_positive_integer(self.source_version, "owner root source version field")
        _validate_step(self.step)
        require_positive_integer(self.contract_version, "owner root contract version")
        require_positive_integer(
            self.terminal_predicate_version,
            "owner root terminal predicate version",
        )

    @property
    def canonical_tuple(self) -> tuple[object, ...]:
        return (
            self.contract_id,
            self.contract_version,
            self.step,
            self.owner_domain,
            self.root_identity_kind,
            self.root_identity_path,
            self.terminal_predicate_id,
            self.terminal_predicate_version,
            self.repair_target,
            self.repair_capability,
            self.source_event_identity,
            self.source_version,
        )


@dataclass(frozen=True, slots=True)
class HistoricalBaselineOwnerRoot:
    """One fresh typed owner-root readback bound to its catalog descriptor."""

    contract_id: str
    contract_version: int
    step: int
    owner_domain: str
    root_identity_kind: str
    root_identity_path: str
    terminal_predicate_id: str
    terminal_predicate_version: int
    repair_target: str
    repair_capability: str
    root_identity: str | None
    source_event_identity: str | None
    source_version: int | None
    terminal_result: bool | None
    unavailable_reason: str | None = None
    case_no: str | None = None

    def __post_init__(self) -> None:
        contract = self.contract
        if self.root_identity is not None:
            require_canonical_text(self.root_identity, "owner root identity", _ORDER_IDENTITY_MAXIMUM_LENGTH)
        if self.source_event_identity is not None:
            require_canonical_text(
                self.source_event_identity,
                "owner root source event identity",
                _ORDER_IDENTITY_MAXIMUM_LENGTH,
            )
        if self.source_version is not None:
            require_nonnegative_integer(self.source_version, "owner root source version")
        if not isinstance(self.terminal_result, (bool, type(None))):
            raise TypeError("owner root terminal result is invalid")
        if self.unavailable_reason is not None:
            require_canonical_text(self.unavailable_reason, "owner root unavailable reason", _REASON_MAXIMUM_LENGTH)
        if self.case_no is not None:
            require_canonical_text(self.case_no, "owner root case number", _CASE_NUMBER_MAXIMUM_LENGTH)
        if self.unavailable_reason is not None:
            if self.terminal_result is not None or any(
                value is not None
                for value in (
                    self.root_identity,
                    self.source_event_identity,
                    self.source_version,
                )
            ):
                raise HistoricalOperationalBaselineError(
                    "historical_baseline_owner_root_availability_inconsistent"
                )
            return
        if self.terminal_result is None:
            raise HistoricalOperationalBaselineError(
                "historical_baseline_owner_root_readback_unavailable"
            )
        if (
            self.root_identity is None
            or self.source_event_identity is None
            or self.source_version is None
        ):
            raise HistoricalOperationalBaselineError(
                "historical_baseline_owner_root_fact_missing"
            )
        if self.source_version < 1:
            raise HistoricalOperationalBaselineError(
                "historical_baseline_owner_root_source_version_invalid"
            )

    @property
    def contract(self) -> HistoricalBaselineOwnerRootContract:
        return HistoricalBaselineOwnerRootContract(
            self.contract_id,
            self.contract_version,
            self.step,
            self.owner_domain,
            self.root_identity_kind,
            self.root_identity_path,
            self.terminal_predicate_id,
            self.terminal_predicate_version,
            self.repair_target,
            self.repair_capability,
            _catalog_source_event_identity(self.owner_domain),
            1,
        )

    @property
    def available(self) -> bool:
        return self.unavailable_reason is None

    @property
    def canonical_tuple(self) -> tuple[object, ...]:
        return (
            *self.contract.canonical_tuple,
            self.root_identity,
            self.source_event_identity,
            self.source_version,
            self.terminal_result,
            self.unavailable_reason,
            self.case_no,
        )


@dataclass(frozen=True, slots=True)
class HistoricalBaselineInvalidationEvent:
    """Typed owner event that reopens an exact set of baseline roots (H-06)."""

    identity: HistoricalOrderIdentity
    catalog_version: int
    source_event_identity: str
    source_version: int
    invalidated_steps: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.identity, HistoricalOrderIdentity):
            raise TypeError("historical baseline invalidation identity is invalid")
        _validate_catalog_version(self.catalog_version)
        require_canonical_text(
            self.source_event_identity,
            "historical baseline invalidation source event identity",
            _ORDER_IDENTITY_MAXIMUM_LENGTH,
        )
        require_positive_integer(
            self.source_version,
            "historical baseline invalidation source version",
        )
        if not isinstance(self.invalidated_steps, tuple) or not self.invalidated_steps:
            raise HistoricalOperationalBaselineError(
                "historical_baseline_invalidation_set_required"
            )
        if any(isinstance(step, bool) or not isinstance(step, int) for step in self.invalidated_steps):
            raise HistoricalOperationalBaselineError(
                "historical_baseline_invalidation_set_invalid"
            )
        if self.invalidated_steps != tuple(sorted(set(self.invalidated_steps))) or any(
            step < _FIRST_STEP or step > _LAST_STEP for step in self.invalidated_steps
        ):
            raise HistoricalOperationalBaselineError(
                "historical_baseline_invalidation_set_invalid"
            )

    @property
    def canonical_tuple(self) -> tuple[object, ...]:
        return (
            self.identity.order_identity,
            self.identity.case_no,
            self.catalog_version,
            self.source_event_identity,
            self.source_version,
            self.invalidated_steps,
        )


# Descriptive alias for adapters that name this a reversal/reopen event.
HistoricalBaselineRootInvalidationEvent = HistoricalBaselineInvalidationEvent


# The catalog is an immutable composition point. Predicate semantics remain
# owned by each Domain; Orders only validates and orders their descriptors.
HISTORICAL_BASELINE_OWNER_ROOT_CATALOG: tuple[HistoricalBaselineOwnerRootContract, ...] = tuple(
    HistoricalBaselineOwnerRootContract(
        f"historical-baseline.step-{step}",
        1,
        step,
        owner,
        kind,
        path,
        f"historical-baseline.step-{step}.terminal",
        1,
        target,
        capability,
        _catalog_source_event_identity(owner),
        1,
    )
    for step, owner, kind, path, target, capability in (
        (1, "orders", "order", "orders.order_identity", "orders", "orders.historical_review.remediate"),
        (2, "matching", "caregiver", "matching.caregiver_identity", "matching", "orders.historical_review.remediate"),
        (3, "line", "candidate_contact", "line.candidate_contact_identity", "line", "orders.historical_review.remediate"),
        (4, "matching", "matching_binding", "matching.binding_identity", "matching", "orders.historical_review.remediate"),
        (5, "orders", "customer_decision", "orders.customer_decision_identity", "orders", "orders.historical_review.remediate"),
        (6, "contract_signing", "contract", "contract_signing.contract_identity", "contract_signing", "orders.historical_review.remediate"),
        (7, "client_finance", "deposit", "client_finance.deposit_obligation_identity", "client_finance", "orders.historical_review.remediate"),
        (8, "contract_signing", "commitment", "contract_signing.commitment_identity", "contract_signing", "orders.historical_review.remediate"),
        (9, "orders", "confirmed_dates", "orders.confirmed_service_dates_identity", "orders", "orders.historical_review.remediate"),
        (10, "scheduling", "assignment", "scheduling.assignment_identity", "scheduling", "orders.historical_review.remediate"),
        (11, "orders", "completion", "orders.completion_identity", "orders", "orders.historical_review.remediate"),
    )
)
# Descriptive aliases keep the domain vocabulary discoverable to adapters.
HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V1 = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG
HistoricalBaselineOwnerRootContractEntry = HistoricalBaselineOwnerRootContract
HistoricalBaselineOwnerRootFact = HistoricalBaselineOwnerRoot
HistoricalBaselineOwnerRootVectorEntry = HistoricalBaselineOwnerRoot


@dataclass(frozen=True, slots=True)
class HistoricalOrderIdentity:
    """The canonical order/case identity; provenance is carried separately."""

    order_identity: str
    case_no: str

    def __post_init__(self) -> None:
        require_canonical_text(
            self.order_identity,
            "order identity",
            _ORDER_IDENTITY_MAXIMUM_LENGTH,
        )
        require_canonical_text(self.case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)


@dataclass(frozen=True, slots=True)
class HistoricalOrderProvenanceIdentity:
    """Server-owned historical provenance bound to an adopted Order root."""

    source_event_identity: str
    source_version: int

    def __post_init__(self) -> None:
        require_canonical_text(
            self.source_event_identity,
            "historical provenance event identity",
            _ORDER_IDENTITY_MAXIMUM_LENGTH,
        )
        require_nonnegative_integer(self.source_version, "historical provenance version")


def validate_historical_baseline_owner_catalog(
    catalog: Iterable[HistoricalBaselineOwnerRootContract] = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG,
    *,
    catalog_version: int = HISTORICAL_BASELINE_CATALOG_VERSION,
) -> tuple[HistoricalBaselineOwnerRootContract, ...]:
    """Validate an immutable catalog and return it in server-defined step order."""

    _validate_catalog_version(catalog_version)
    entries = tuple(catalog)
    if len(entries) != _LAST_STEP or any(
        not isinstance(entry, HistoricalBaselineOwnerRootContract) for entry in entries
    ):
        raise HistoricalOperationalBaselineError("historical_baseline_catalog_invalid")
    steps = tuple(entry.step for entry in entries)
    if set(steps) != set(range(_FIRST_STEP, _LAST_STEP + 1)) or len(set(steps)) != len(steps):
        raise HistoricalOperationalBaselineError("historical_baseline_catalog_step_invalid")
    contract_keys = tuple((entry.contract_id, entry.contract_version) for entry in entries)
    if len(set(contract_keys)) != len(contract_keys):
        raise HistoricalOperationalBaselineError("historical_baseline_catalog_duplicate")
    if any(entry.repair_target != entry.owner_domain for entry in entries):
        raise HistoricalOperationalBaselineError(
            "historical_baseline_owner_root_repair_boundary_unsupported"
        )
    return tuple(sorted(entries, key=lambda entry: entry.step))


def build_historical_baseline_owner_root_vector(
    roots: Iterable[HistoricalBaselineOwnerRoot],
    *,
    identity: HistoricalOrderIdentity | None = None,
    catalog: Iterable[HistoricalBaselineOwnerRootContract] = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG,
    catalog_version: int = HISTORICAL_BASELINE_CATALOG_VERSION,
) -> tuple[HistoricalBaselineOwnerRoot, ...]:
    """Bind fresh owner roots to every catalog entry, rejecting unsafe drift."""

    catalog_entries = validate_historical_baseline_owner_catalog(
        catalog, catalog_version=catalog_version
    )
    by_step = {entry.step: entry for entry in catalog_entries}
    vector = tuple(roots)
    if len(vector) != len(catalog_entries) or any(
        not isinstance(root, HistoricalBaselineOwnerRoot) for root in vector
    ):
        raise HistoricalOperationalBaselineError("historical_baseline_owner_root_vector_incomplete")
    if len({root.step for root in vector}) != len(vector):
        raise HistoricalOperationalBaselineError("historical_baseline_owner_root_duplicate")
    if identity is not None and not isinstance(identity, HistoricalOrderIdentity):
        raise TypeError("historical baseline identity is invalid")
    ordered: list[HistoricalBaselineOwnerRoot] = []
    for root in sorted(vector, key=lambda item: item.step):
        expected = by_step.get(root.step)
        if expected is None or root.contract.canonical_tuple != expected.canonical_tuple:
            raise HistoricalOperationalBaselineError("historical_baseline_owner_root_contract_unsupported")
        if identity is not None:
            if root.case_no is None or root.case_no != identity.case_no:
                raise HistoricalOperationalBaselineError("historical_baseline_owner_root_cross_case")
        ordered.append(root)
    return tuple(ordered)


def historical_baseline_owner_binding_fingerprint(
    identity: HistoricalOrderIdentity,
    historical_provenance: HistoricalOrderProvenanceIdentity,
    owner_root_vector: Iterable[HistoricalBaselineOwnerRoot],
    *,
    catalog: Iterable[HistoricalBaselineOwnerRootContract] = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG,
    catalog_version: int = HISTORICAL_BASELINE_CATALOG_VERSION,
) -> PreviewFingerprint:
    """Fingerprint identity, provenance and the complete canonical root vector."""

    vector = build_historical_baseline_owner_root_vector(
        owner_root_vector,
        identity=identity,
        catalog=catalog,
        catalog_version=catalog_version,
    )
    catalog_entries = validate_historical_baseline_owner_catalog(
        catalog, catalog_version=catalog_version
    )
    payload: Mapping[str, object] = {
        "catalog_version": catalog_version,
        "identity": (identity.order_identity, identity.case_no),
        "provenance": (historical_provenance.source_event_identity, historical_provenance.source_version),
        "owner_roots": tuple(root.canonical_tuple for root in vector),
    }
    return fingerprint_payload(payload)


# Explicit name used by adapters that treat this digest as a whole-vector value.
build_historical_baseline_owner_binding_fingerprint = historical_baseline_owner_binding_fingerprint


def project_earliest_invalidated_root(
    owner_root_vector: Iterable[HistoricalBaselineOwnerRoot],
    *,
    invalidated_steps: Iterable[int] = (),
    invalidation_event: HistoricalBaselineInvalidationEvent | None = None,
    identity: HistoricalOrderIdentity | None = None,
) -> int | None:
    """Return the server-computed earliest non-terminal or invalidated step."""

    vector = build_historical_baseline_owner_root_vector(owner_root_vector)
    if invalidation_event is not None and not isinstance(
        invalidation_event, HistoricalBaselineInvalidationEvent
    ):
        raise TypeError("historical baseline invalidation event is invalid")
    invalidated = tuple(invalidated_steps)
    if invalidation_event is not None:
        if invalidated:
            raise HistoricalOperationalBaselineError(
                "historical_baseline_invalidation_set_conflict"
            )
        if identity is None or invalidation_event.identity != identity:
            raise HistoricalOperationalBaselineError(
                "historical_baseline_invalidation_identity_mismatch"
            )
        case_numbers = {root.case_no for root in vector}
        if None in case_numbers or identity.case_no not in case_numbers:
            raise HistoricalOperationalBaselineError(
                "historical_baseline_invalidation_identity_mismatch"
            )
        invalidated = invalidation_event.invalidated_steps
        affected_versions = [
            root.source_version
            for root in vector
            if root.step in invalidated and root.source_version is not None
        ]
        if affected_versions and invalidation_event.source_version <= max(affected_versions):
            raise HistoricalOperationalBaselineError(
                "historical_baseline_invalidation_source_version_stale"
            )
    if any(isinstance(step, bool) or not isinstance(step, int) for step in invalidated):
        raise HistoricalOperationalBaselineError("historical_baseline_invalidated_step_invalid")
    if any(step < _FIRST_STEP or step > _LAST_STEP for step in invalidated):
        raise HistoricalOperationalBaselineError("historical_baseline_invalidated_step_invalid")
    candidates = [
        root.step for root in vector
        if root.step in invalidated or not root.available or root.terminal_result is False
    ]
    return min(candidates) if candidates else None


project_historical_baseline_earliest_invalidated_root = project_earliest_invalidated_root


@dataclass(frozen=True, slots=True)
class HistoricalBaselineLineage:
    """Immutable prior baseline lineage used to reject regressions."""

    event_identity: str
    identity: HistoricalOrderIdentity
    selected_step: int
    resulting_orders_version: int
    resulting_owner_binding_fingerprint: PreviewFingerprint

    def __post_init__(self) -> None:
        require_canonical_text(self.event_identity, "prior baseline event identity", _ORDER_IDENTITY_MAXIMUM_LENGTH)
        if not isinstance(self.identity, HistoricalOrderIdentity):
            raise TypeError("prior baseline identity is invalid")
        _validate_step(self.selected_step)
        require_nonnegative_integer(self.resulting_orders_version, "prior baseline Orders version")
        if not isinstance(self.resulting_owner_binding_fingerprint, PreviewFingerprint):
            raise TypeError("prior baseline owner binding fingerprint is invalid")


@dataclass(frozen=True, slots=True)
class HistoricalOperationalBaselineFacts:
    """The fresh, owner-owned facts used to build a candidate."""

    identity: HistoricalOrderIdentity
    historical_provenance: HistoricalOrderProvenanceIdentity
    current_orders_version: int
    current_owner_binding_fingerprint: PreviewFingerprint
    prior_baseline_lineage: HistoricalBaselineLineage | None = None
    owner_root_vector: tuple[HistoricalBaselineOwnerRoot, ...] | None = None
    catalog_version: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, HistoricalOrderIdentity):
            raise TypeError("historical baseline identity is invalid")
        if not isinstance(self.historical_provenance, HistoricalOrderProvenanceIdentity):
            raise TypeError("historical provenance identity is required")
        require_nonnegative_integer(
            self.current_orders_version,
            "current Orders version",
        )
        if not isinstance(
            self.current_owner_binding_fingerprint,
            PreviewFingerprint,
        ):
            raise TypeError("current owner binding fingerprint is invalid")
        if self.prior_baseline_lineage is not None and not isinstance(self.prior_baseline_lineage, HistoricalBaselineLineage):
            raise TypeError("prior baseline lineage is invalid")
        if self.owner_root_vector is not None:
            if self.catalog_version is None:
                object.__setattr__(self, "catalog_version", HISTORICAL_BASELINE_CATALOG_VERSION)
            _validate_catalog_version(self.catalog_version)
            object.__setattr__(
                self,
                "owner_root_vector",
                build_historical_baseline_owner_root_vector(
                    self.owner_root_vector,
                    identity=self.identity,
                    catalog_version=self.catalog_version,
                ),
            )
            expected_binding = historical_baseline_owner_binding_fingerprint(
                self.identity,
                self.historical_provenance,
                self.owner_root_vector,
                catalog_version=self.catalog_version,
            )
            if expected_binding != self.current_owner_binding_fingerprint:
                raise HistoricalOperationalBaselineError(
                    "historical_baseline_owner_vector_fingerprint_mismatch"
                )
        if self.owner_root_vector is None and self.catalog_version is not None:
            raise HistoricalOperationalBaselineError(
                "historical_baseline_owner_root_vector_required"
            )


@dataclass(frozen=True, slots=True)
class HistoricalOperationalBaselineRequest:
    """Actor-independent business payload supplied to Query/Preview/Apply."""

    identity: HistoricalOrderIdentity
    selected_step: int
    expected_orders_version: int
    expected_owner_binding_fingerprint: PreviewFingerprint
    evidence_mode: HistoricalBaselineEvidenceMode
    reason: str
    evidence_reference: str
    document_kind: str | None = None
    affected_steps: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, HistoricalOrderIdentity):
            raise TypeError("historical baseline identity is invalid")
        _validate_step(self.selected_step)
        require_nonnegative_integer(
            self.expected_orders_version,
            "expected Orders version",
        )
        if not isinstance(
            self.expected_owner_binding_fingerprint,
            PreviewFingerprint,
        ):
            raise TypeError("expected owner binding fingerprint is invalid")
        object.__setattr__(self, "evidence_mode", _evidence_mode(self.evidence_mode))
        require_canonical_text(self.reason, "baseline reason", _REASON_MAXIMUM_LENGTH)
        require_canonical_text(
            self.evidence_reference,
            "baseline evidence reference",
            _EVIDENCE_REFERENCE_MAXIMUM_LENGTH,
        )
        _validate_evidence_details(self.evidence_mode, self.document_kind, self.affected_steps)


@dataclass(frozen=True, slots=True)
class HistoricalBaselineStepProjection:
    step: int
    state: HistoricalBaselineStepState

    def __post_init__(self) -> None:
        _validate_step(self.step)
        if not isinstance(self.state, HistoricalBaselineStepState):
            raise TypeError("historical baseline step state is invalid")


@dataclass(frozen=True, slots=True)
class HistoricalOperationalBaselineCandidate:
    """Append-only baseline payload; it contains no actor or fabricated owner fact."""

    identity: HistoricalOrderIdentity
    historical_provenance: HistoricalOrderProvenanceIdentity
    selected_step: int
    expected_orders_version: int
    current_orders_version: int
    current_owner_binding_fingerprint: PreviewFingerprint
    evidence_mode: HistoricalBaselineEvidenceMode
    reason: str
    evidence_reference: str
    document_kind: str | None
    affected_steps: tuple[int, ...] | None
    prior_baseline_lineage: HistoricalBaselineLineage | None
    step_projection: tuple[HistoricalBaselineStepProjection, ...]
    fingerprint: PreviewFingerprint
    owner_root_vector: tuple[HistoricalBaselineOwnerRoot, ...] | None = None
    catalog_version: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, HistoricalOrderIdentity):
            raise TypeError("historical baseline identity is invalid")
        if not isinstance(self.historical_provenance, HistoricalOrderProvenanceIdentity):
            raise TypeError("historical provenance identity is required")
        _validate_step(self.selected_step)
        require_nonnegative_integer(
            self.expected_orders_version,
            "expected Orders version",
        )
        require_nonnegative_integer(
            self.current_orders_version,
            "current Orders version",
        )
        if self.expected_orders_version != self.current_orders_version:
            raise HistoricalOperationalBaselineError(
                "historical_baseline_version_mismatch"
            )
        if not isinstance(self.current_owner_binding_fingerprint, PreviewFingerprint):
            raise TypeError("current owner binding fingerprint is invalid")
        object.__setattr__(self, "evidence_mode", _evidence_mode(self.evidence_mode))
        require_canonical_text(self.reason, "baseline reason", _REASON_MAXIMUM_LENGTH)
        require_canonical_text(
            self.evidence_reference,
            "baseline evidence reference",
            _EVIDENCE_REFERENCE_MAXIMUM_LENGTH,
        )
        _validate_evidence_details(self.evidence_mode, self.document_kind, self.affected_steps)
        if self.prior_baseline_lineage is not None and not isinstance(self.prior_baseline_lineage, HistoricalBaselineLineage):
            raise TypeError("prior baseline lineage is invalid")
        if self.prior_baseline_lineage is not None:
            prior = self.prior_baseline_lineage
            if prior.identity != self.identity:
                raise HistoricalOperationalBaselineError(
                    "historical_baseline_prior_identity_mismatch"
                )
            if self.current_orders_version < prior.resulting_orders_version:
                raise HistoricalOperationalBaselineError(
                    "historical_baseline_version_rollback"
                )
            if (
                self.current_orders_version == prior.resulting_orders_version
                and self.current_owner_binding_fingerprint
                != prior.resulting_owner_binding_fingerprint
            ):
                raise HistoricalOperationalBaselineError(
                    "historical_baseline_prior_binding_conflict"
                )
            if self.selected_step < prior.selected_step:
                raise HistoricalOperationalBaselineError(
                    "historical_baseline_step_regression"
                )
        expected_projection = project_historical_baseline_steps(self.selected_step)
        if self.step_projection != expected_projection:
            raise HistoricalOperationalBaselineError(
                "historical_baseline_projection_invalid"
            )
        if not isinstance(self.fingerprint, PreviewFingerprint):
            raise TypeError("baseline fingerprint is invalid")
        if self.fingerprint != fingerprint_payload(self.canonical_payload):
            raise HistoricalOperationalBaselineError(
                "historical_baseline_fingerprint_mismatch"
            )
        if self.owner_root_vector is not None:
            object.__setattr__(
                self,
                "owner_root_vector",
                build_historical_baseline_owner_root_vector(
                    self.owner_root_vector,
                    identity=self.identity,
                    catalog_version=self.catalog_version or HISTORICAL_BASELINE_CATALOG_VERSION,
                ),
            )
            expected_binding = historical_baseline_owner_binding_fingerprint(
                self.identity,
                self.historical_provenance,
                self.owner_root_vector,
                catalog_version=self.catalog_version or HISTORICAL_BASELINE_CATALOG_VERSION,
            )
            if expected_binding != self.current_owner_binding_fingerprint:
                raise HistoricalOperationalBaselineError(
                    "historical_baseline_owner_vector_fingerprint_mismatch"
                )
        if self.owner_root_vector is None and self.catalog_version is not None:
            raise HistoricalOperationalBaselineError(
                "historical_baseline_owner_root_vector_required"
            )
        if self.catalog_version is not None:
            _validate_catalog_version(self.catalog_version)

    @property
    def canonical_payload(self) -> dict[str, object]:
        return _canonical_payload(
            self.identity,
            self.historical_provenance,
            self.selected_step,
            self.expected_orders_version,
            self.current_orders_version,
            self.current_owner_binding_fingerprint,
            self.evidence_mode,
            self.reason,
            self.evidence_reference,
            self.document_kind,
            self.affected_steps,
            self.prior_baseline_lineage,
            self.owner_root_vector,
            self.catalog_version,
        )

    @property
    def current_step(self) -> int:
        """Current server projection, possibly reset by owner invalidation."""

        if self.owner_root_vector is None:
            return self.selected_step
        return project_earliest_invalidated_root(self.owner_root_vector) or self.selected_step

    @property
    def earliest_invalidated_root(self) -> int | None:
        if self.owner_root_vector is None:
            return None
        return project_earliest_invalidated_root(self.owner_root_vector)


def build_historical_operational_baseline_candidate(
    current: HistoricalOperationalBaselineFacts,
    request: HistoricalOperationalBaselineRequest,
) -> HistoricalOperationalBaselineCandidate:
    """Build a deterministic candidate from one fresh owner snapshot."""

    if request.identity != current.identity:
        raise HistoricalOperationalBaselineError(
            "historical_baseline_identity_mismatch"
        )
    if request.expected_orders_version < current.current_orders_version:
        raise HistoricalOperationalBaselineError("historical_baseline_stale")
    if request.expected_orders_version > current.current_orders_version:
        raise HistoricalOperationalBaselineError("historical_baseline_version_rollback")
    if (
        request.expected_owner_binding_fingerprint
        != current.current_owner_binding_fingerprint
    ):
        raise HistoricalOperationalBaselineError("historical_baseline_binding_drift")
    prior = current.prior_baseline_lineage
    if prior is not None:
        if prior.identity != current.identity:
            raise HistoricalOperationalBaselineError(
                "historical_baseline_prior_identity_mismatch"
            )
        if current.current_orders_version < prior.resulting_orders_version:
            raise HistoricalOperationalBaselineError(
                "historical_baseline_version_rollback"
            )
        if (
            current.current_orders_version == prior.resulting_orders_version
            and current.current_owner_binding_fingerprint
            != prior.resulting_owner_binding_fingerprint
        ):
            raise HistoricalOperationalBaselineError(
                "historical_baseline_prior_binding_conflict"
            )
        if request.selected_step < prior.selected_step:
            raise HistoricalOperationalBaselineError(
                "historical_baseline_step_regression"
            )

    owner_root_vector = current.owner_root_vector
    if owner_root_vector is not None:
        owner_root_vector = build_historical_baseline_owner_root_vector(
            owner_root_vector, identity=current.identity
        )

    projection = project_historical_baseline_steps(request.selected_step)
    payload = _canonical_payload(
        current.identity,
        current.historical_provenance,
        request.selected_step,
        request.expected_orders_version,
        current.current_orders_version,
        current.current_owner_binding_fingerprint,
        request.evidence_mode,
        request.reason,
        request.evidence_reference,
        request.document_kind,
        request.affected_steps,
        prior,
        owner_root_vector,
        current.catalog_version,
    )
    return HistoricalOperationalBaselineCandidate(
        identity=current.identity,
        historical_provenance=current.historical_provenance,
        selected_step=request.selected_step,
        expected_orders_version=request.expected_orders_version,
        current_orders_version=current.current_orders_version,
        current_owner_binding_fingerprint=current.current_owner_binding_fingerprint,
        evidence_mode=request.evidence_mode,
        reason=request.reason,
        evidence_reference=request.evidence_reference,
        document_kind=request.document_kind,
        affected_steps=request.affected_steps,
        prior_baseline_lineage=prior,
        step_projection=projection,
        fingerprint=fingerprint_payload(payload),
        owner_root_vector=owner_root_vector,
        catalog_version=current.catalog_version,
    )


def project_historical_baseline_steps(
    selected_step: int,
) -> tuple[HistoricalBaselineStepProjection, ...]:
    """Annotate only prior steps and the selected current step."""

    _validate_step(selected_step)
    return tuple(
        HistoricalBaselineStepProjection(
            step,
            (
                HistoricalBaselineStepState.IN_PROGRESS
                if step == selected_step
                else HistoricalBaselineStepState.HISTORICAL_BASELINE_COMPLETED
            ),
        )
        for step in range(_FIRST_STEP, selected_step + 1)
    )


def baseline_payload_equivalent(
    left: HistoricalOperationalBaselineCandidate,
    right: HistoricalOperationalBaselineCandidate,
) -> bool:
    """Compare replay payloads without introducing actor identity.

    The application layer owns idempotency-key binding and receipt replay;
    this pure Domain helper only compares the actor-independent payload.
    """

    if not isinstance(left, HistoricalOperationalBaselineCandidate):
        raise TypeError("left baseline candidate is invalid")
    if not isinstance(right, HistoricalOperationalBaselineCandidate):
        raise TypeError("right baseline candidate is invalid")
    return left.canonical_payload == right.canonical_payload


def _validate_evidence_details(
    mode: HistoricalBaselineEvidenceMode,
    document_kind: str | None,
    affected_steps: tuple[int, ...] | None,
) -> None:
    if mode is HistoricalBaselineEvidenceMode.RETAINED:
        if document_kind is not None or affected_steps not in (None, ()):
            raise HistoricalOperationalBaselineError(
                "historical_baseline_unavailable_evidence_fields_invalid"
            )
        return
    if document_kind is None:
        raise HistoricalOperationalBaselineError(
            "historical_baseline_document_kind_required"
        )
    require_canonical_text(document_kind, "historical evidence document kind", _EVIDENCE_REFERENCE_MAXIMUM_LENGTH)
    if not isinstance(affected_steps, tuple) or not affected_steps:
        raise HistoricalOperationalBaselineError(
            "historical_baseline_affected_steps_required"
        )
    if any(isinstance(step, bool) or not isinstance(step, int) for step in affected_steps):
        raise HistoricalOperationalBaselineError(
            "historical_baseline_affected_steps_invalid"
        )
    if affected_steps != tuple(sorted(set(affected_steps))) or any(
        step < _FIRST_STEP or step > _LAST_STEP for step in affected_steps
    ):
        raise HistoricalOperationalBaselineError(
            "historical_baseline_affected_steps_invalid"
        )


def _evidence_mode(
    value: HistoricalBaselineEvidenceMode,
) -> HistoricalBaselineEvidenceMode:
    try:
        return (
            value
            if isinstance(value, HistoricalBaselineEvidenceMode)
            else HistoricalBaselineEvidenceMode(value)
        )
    except (TypeError, ValueError) as error:
        raise HistoricalOperationalBaselineError(
            "historical_baseline_evidence_mode_invalid"
        ) from error


def _canonical_payload(
    identity: HistoricalOrderIdentity,
    historical_provenance: HistoricalOrderProvenanceIdentity,
    selected_step: int,
    expected_orders_version: int,
    current_orders_version: int,
    owner_binding_fingerprint: PreviewFingerprint,
    evidence_mode: HistoricalBaselineEvidenceMode,
    reason: str,
    evidence_reference: str,
    document_kind: str | None,
    affected_steps: tuple[int, ...] | None,
    prior_baseline_lineage: HistoricalBaselineLineage | None,
    owner_root_vector: tuple[HistoricalBaselineOwnerRoot, ...] | None = None,
    catalog_version: int | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "order_identity": identity.order_identity,
        "case_no": identity.case_no,
        "historical_provenance_event_identity": historical_provenance.source_event_identity,
        "historical_provenance_source_version": historical_provenance.source_version,
        "selected_step": selected_step,
        "expected_orders_version": expected_orders_version,
        "current_orders_version": current_orders_version,
        "current_owner_binding_fingerprint": owner_binding_fingerprint.value,
        "evidence_mode": evidence_mode.value,
        "reason": reason,
        "evidence_reference": evidence_reference,
        "document_kind": document_kind,
        "affected_steps": affected_steps,
        "prior_baseline_lineage": None if prior_baseline_lineage is None else {
            "event_identity": prior_baseline_lineage.event_identity,
            "order_identity": prior_baseline_lineage.identity.order_identity,
            "case_no": prior_baseline_lineage.identity.case_no,
            "selected_step": prior_baseline_lineage.selected_step,
            "resulting_orders_version": prior_baseline_lineage.resulting_orders_version,
            "resulting_owner_binding_fingerprint": prior_baseline_lineage.resulting_owner_binding_fingerprint.value,
        },
        "catalog_version": catalog_version,
        "owner_root_vector": None if owner_root_vector is None else tuple(
            root.canonical_tuple for root in owner_root_vector
        ),
    }
    return payload


# catalog-v2 is deliberately additive.  The v1 classes and builder above are
# persisted-history compatibility and retain their one-root-per-step contract.
HISTORICAL_BASELINE_CATALOG_VERSION_V2 = 2
# Alternate vocabulary used by callers that put the revision before the
# catalog noun; both names denote the same immutable adopted revision.
HISTORICAL_BASELINE_CATALOG_V2_VERSION = HISTORICAL_BASELINE_CATALOG_VERSION_V2


@dataclass(frozen=True, slots=True)
class HistoricalBaselineOwnerRootCollectionContract:
    """Owner-declared cardinality and all-required policy for one descriptor."""

    collection_predicate_id: str
    collection_predicate_version: int
    minimum_cardinality: int
    maximum_cardinality: int | None
    all_required: bool = True
    required_root_identity_kinds: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_canonical_text(
            self.collection_predicate_id,
            "owner root collection predicate id",
            191,
        )
        require_positive_integer(
            self.collection_predicate_version,
            "owner root collection predicate version",
        )
        require_nonnegative_integer(
            self.minimum_cardinality,
            "owner root collection minimum cardinality",
        )
        if self.maximum_cardinality is not None:
            require_positive_integer(
                self.maximum_cardinality,
                "owner root collection maximum cardinality",
            )
            if self.maximum_cardinality < self.minimum_cardinality:
                raise HistoricalOperationalBaselineError(
                    "historical_baseline_v2_collection_cardinality_invalid"
                )
        if not isinstance(self.all_required, bool):
            raise TypeError("owner root collection all-required flag is invalid")
        if self.all_required is not True:
            raise HistoricalOperationalBaselineError(
                "historical_baseline_v2_collection_all_required"
            )
        if not isinstance(self.required_root_identity_kinds, tuple):
            raise TypeError("owner root collection required kinds are invalid")
        if not self.required_root_identity_kinds:
            raise HistoricalOperationalBaselineError(
                "historical_baseline_v2_collection_required_kind_missing"
            )
        for kind in self.required_root_identity_kinds:
            require_canonical_text(kind, "owner root required identity kind", 100)

    @property
    def canonical_tuple(self) -> tuple[object, ...]:
        return (
            self.collection_predicate_id,
            self.collection_predicate_version,
            self.minimum_cardinality,
            self.maximum_cardinality,
            self.all_required,
            self.required_root_identity_kinds,
        )

    @property
    def minimum_observations(self) -> int:
        return self.minimum_cardinality

    @property
    def maximum_observations(self) -> int | None:
        return self.maximum_cardinality


@dataclass(frozen=True, slots=True)
class HistoricalBaselineOwnerRootDescriptor:
    """Versioned owner descriptor; one descriptor may return many observations."""

    contract_id: str
    contract_version: int
    step: int
    owner_domain: str
    root_identity_kind: str
    root_identity_path: str
    terminal_predicate_id: str
    terminal_predicate_version: int
    repair_target: str
    repair_capability: str
    source_event_identity: str
    source_version: int = 1
    collection: HistoricalBaselineOwnerRootCollectionContract | None = None

    def __post_init__(self) -> None:
        for value, name, maximum in (
            (self.contract_id, "owner root descriptor id", _ORDER_IDENTITY_MAXIMUM_LENGTH),
            (self.owner_domain, "owner root descriptor domain", 100),
            (self.root_identity_kind, "owner root descriptor identity kind", 100),
            (self.root_identity_path, "owner root descriptor identity path", 255),
            (self.terminal_predicate_id, "owner root descriptor predicate id", 191),
            (self.repair_target, "owner root descriptor repair target", 191),
            (self.repair_capability, "owner root descriptor repair capability", 191),
            (self.source_event_identity, "owner root descriptor event field", 191),
        ):
            require_canonical_text(value, name, maximum)
        _validate_step(self.step)
        require_positive_integer(self.contract_version, "owner root descriptor contract version")
        require_positive_integer(
            self.terminal_predicate_version,
            "owner root descriptor terminal predicate version",
        )
        require_positive_integer(self.source_version, "owner root descriptor source version")
        if self.collection is not None and not isinstance(
            self.collection, HistoricalBaselineOwnerRootCollectionContract
        ):
            raise TypeError("owner root descriptor collection contract is invalid")

    @property
    def canonical_tuple(self) -> tuple[object, ...]:
        return (
            self.contract_id,
            self.contract_version,
            self.step,
            self.owner_domain,
            self.root_identity_kind,
            self.root_identity_path,
            self.terminal_predicate_id,
            self.terminal_predicate_version,
            self.repair_target,
            self.repair_capability,
            self.source_event_identity,
            self.source_version,
            None if self.collection is None else self.collection.canonical_tuple,
        )

    @property
    def collection_contract(self) -> HistoricalBaselineOwnerRootCollectionContract:
        if self.collection is None:
            raise HistoricalOperationalBaselineError(
                "historical_baseline_v2_collection_contract_required"
            )
        return self.collection

    @property
    def collection_predicate(self) -> HistoricalBaselineOwnerRootCollectionContract:
        """Explicit vocabulary for the descriptor's collection-level rule."""

        return self.collection_contract

    @property
    def collection_predicate_id(self) -> str:
        return self.collection_contract.collection_predicate_id

    @property
    def collection_predicate_version(self) -> int:
        return self.collection_contract.collection_predicate_version

    @property
    def minimum_cardinality(self) -> int:
        return self.collection_contract.minimum_cardinality

    @property
    def maximum_cardinality(self) -> int | None:
        return self.collection_contract.maximum_cardinality


@dataclass(frozen=True, slots=True)
class HistoricalBaselineOwnerObservation:
    """One typed available or unavailable fresh readback for a v2 descriptor."""

    descriptor: HistoricalBaselineOwnerRootDescriptor
    root_identity: str | None
    source_event_identity: str | None
    source_version: int | None
    terminal_result: bool | None
    unavailable_code: str | None = None
    case_no: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.descriptor, HistoricalBaselineOwnerRootDescriptor):
            raise TypeError("historical baseline v2 descriptor is invalid")
        if self.case_no is None:
            raise HistoricalOperationalBaselineError("historical_baseline_v2_case_required")
        require_canonical_text(self.case_no, "historical baseline v2 case number", _CASE_NUMBER_MAXIMUM_LENGTH)
        if self.unavailable_code is not None:
            require_canonical_text(
                self.unavailable_code,
                "historical baseline v2 unavailable code",
                _REASON_MAXIMUM_LENGTH,
            )
            if self.terminal_result is not None or any(
                value is not None
                for value in (self.root_identity, self.source_event_identity, self.source_version)
            ):
                raise HistoricalOperationalBaselineError(
                    "historical_baseline_v2_availability_inconsistent"
                )
            return
        if self.terminal_result is None:
            raise HistoricalOperationalBaselineError(
                "historical_baseline_v2_readback_unavailable"
            )
        if not isinstance(self.terminal_result, bool):
            raise TypeError("historical baseline v2 terminal result is invalid")
        if self.root_identity is None or self.source_event_identity is None or self.source_version is None:
            raise HistoricalOperationalBaselineError(
                "historical_baseline_v2_observation_fact_missing"
            )
        require_canonical_text(self.root_identity, "historical baseline v2 root identity", _ORDER_IDENTITY_MAXIMUM_LENGTH)
        require_canonical_text(
            self.source_event_identity,
            "historical baseline v2 source event identity",
            _ORDER_IDENTITY_MAXIMUM_LENGTH,
        )
        # Owner versions are valid from their initial zero-based snapshot;
        # descriptor contract versions remain strictly positive above.
        require_nonnegative_integer(
            self.source_version, "historical baseline v2 source version"
        )

    @classmethod
    def unavailable(
        cls,
        descriptor: HistoricalBaselineOwnerRootDescriptor,
        *,
        code: str,
        case_no: str,
    ) -> "HistoricalBaselineOwnerObservation":
        return cls(descriptor, None, None, None, None, code, case_no)

    @property
    def available(self) -> bool:
        return self.unavailable_code is None

    @property
    def unavailable_reason(self) -> str | None:
        """Compatibility vocabulary; codes remain typed and non-display data."""

        return self.unavailable_code

    @property
    def observation_variant(self) -> str:
        return "available" if self.available else "unavailable"

    @property
    def observation_identity(self) -> tuple[object, ...]:
        return self.canonical_order_key

    @property
    def canonical_order_key(self) -> tuple[object, ...]:
        return (
            self.descriptor.step,
            self.descriptor.contract_id,
            self.root_identity or "",
            self.source_event_identity or "",
            -1 if self.source_version is None else self.source_version,
        )

    @property
    def canonical_tuple(self) -> tuple[object, ...]:
        return (
            self.descriptor.step,
            self.descriptor.contract_id,
            self.root_identity,
            self.source_event_identity,
            self.source_version,
            self.descriptor.contract_version,
            self.descriptor.owner_domain,
            self.descriptor.root_identity_kind,
            self.descriptor.root_identity_path,
            self.descriptor.terminal_predicate_id,
            self.descriptor.terminal_predicate_version,
            self.descriptor.repair_target,
            self.descriptor.repair_capability,
            self.terminal_result,
            self.unavailable_code,
            self.case_no,
        )


@dataclass(frozen=True, slots=True)
class HistoricalBaselineOwnerRootCollection:
    """Typed descriptor collection used to validate cardinality before projection."""

    descriptor: HistoricalBaselineOwnerRootDescriptor
    observations: tuple[HistoricalBaselineOwnerObservation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.descriptor, HistoricalBaselineOwnerRootDescriptor):
            raise TypeError("historical baseline v2 collection descriptor is invalid")
        if not isinstance(self.observations, tuple):
            raise TypeError("historical baseline v2 collection observations are invalid")
        _validate_v2_collection(self.descriptor, self.observations)

    @property
    def terminal(self) -> bool:
        return bool(self.observations) and all(
            observation.available and observation.terminal_result is True
            for observation in self.observations
        )

    @property
    def values(self) -> tuple[HistoricalBaselineOwnerObservation, ...]:
        return self.observations


HistoricalBaselineOwnerRootContractV2 = HistoricalBaselineOwnerRootDescriptor
HistoricalBaselineOwnerRootObservation = HistoricalBaselineOwnerObservation
HistoricalBaselineOwnerObservationV2 = HistoricalBaselineOwnerObservation
HistoricalBaselineOwnerDescriptor = HistoricalBaselineOwnerRootDescriptor
HistoricalBaselineOwnerRootCollectionDescriptor = HistoricalBaselineOwnerRootCollectionContract


def _v2_descriptor(
    step: int,
    owner: str,
    kind: str,
    path: str,
    *,
    minimum: int = 1,
    maximum: int | None = 1,
    predicate: str | None = None,
) -> HistoricalBaselineOwnerRootDescriptor:
    contract_id = f"historical-baseline.v2.step-{step}.{owner}.{kind}"
    return HistoricalBaselineOwnerRootDescriptor(
        contract_id,
        2,
        step,
        owner,
        kind,
        path,
        f"{contract_id}.terminal",
        1,
        owner,
        f"{owner}.historical_baseline.repair.{kind}",
        f"{owner}.source_event_identity",
        1,
        HistoricalBaselineOwnerRootCollectionContract(
            predicate or f"{contract_id}.collection",
            1,
            minimum,
            maximum,
            True,
            (kind,),
        ),
    )


HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2: tuple[HistoricalBaselineOwnerRootDescriptor, ...] = (
    _v2_descriptor(1, "orders", "order", "orders.order_identity"),
    _v2_descriptor(2, "matching", "candidate_pool", "matching.candidate_pool_identity", minimum=1, maximum=100),
    _v2_descriptor(3, "matching", "candidate_contact", "matching.candidate_contact_identity", minimum=1, maximum=100),
    _v2_descriptor(4, "matching", "willingness_binding", "matching.willingness_binding_identity"),
    _v2_descriptor(5, "matching", "selected_staff", "matching.selected_staff_identity"),
    _v2_descriptor(5, "matching", "customer_decision", "matching.customer_decision_identity"),
    _v2_descriptor(6, "contract_signing", "signed_staff_segment", "contract_signing.staff_segment_identity", minimum=1, maximum=100),
    _v2_descriptor(7, "client_finance", "deposit_obligation", "client_finance.deposit_obligation_identity"),
    _v2_descriptor(7, "client_finance", "ledger_allocation", "client_finance.ledger_allocation_identity"),
    _v2_descriptor(7, "client_finance", "settlement", "client_finance.settlement_identity"),
    _v2_descriptor(8, "matching", "caregiver_binding", "matching.caregiver_binding_identity"),
    _v2_descriptor(8, "contract_signing", "commitment", "contract_signing.commitment_identity"),
    _v2_descriptor(8, "contract_signing", "client_signed_evidence", "contract_signing.client_signed_evidence_identity"),
    _v2_descriptor(9, "scheduling", "confirmed_service_date", "scheduling.confirmed_service_date_identity", minimum=1, maximum=None),
    _v2_descriptor(10, "orders", "actual_start", "orders.actual_start_identity"),
    _v2_descriptor(10, "scheduling", "effective_generation", "scheduling.effective_generation_identity"),
    _v2_descriptor(10, "scheduling", "assignment_official_date", "scheduling.assignment_official_date_identity", minimum=1, maximum=None),
    _v2_descriptor(11, "orders", "completion", "orders.completion_identity"),
    _v2_descriptor(11, "scheduling", "official_service", "scheduling.official_service_identity"),
    _v2_descriptor(11, "client_finance", "client_settlement", "client_finance.client_settlement_identity"),
    _v2_descriptor(11, "staff_payables", "staff_payout", "staff_payables.staff_payout_identity", minimum=1, maximum=None),
)


def validate_historical_baseline_owner_catalog_v2(
    catalog: Iterable[HistoricalBaselineOwnerRootDescriptor] = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    *,
    catalog_version: int = HISTORICAL_BASELINE_CATALOG_VERSION_V2,
) -> tuple[HistoricalBaselineOwnerRootDescriptor, ...]:
    if catalog_version != HISTORICAL_BASELINE_CATALOG_VERSION_V2:
        raise HistoricalOperationalBaselineError(
            "historical_baseline_v2_catalog_version_unsupported"
        )
    entries = tuple(catalog)
    if not entries or any(
        not isinstance(entry, HistoricalBaselineOwnerRootDescriptor) for entry in entries
    ):
        raise HistoricalOperationalBaselineError("historical_baseline_v2_catalog_invalid")
    keys = [(entry.contract_id, entry.contract_version) for entry in entries]
    if len(keys) != len(set(keys)):
        raise HistoricalOperationalBaselineError("historical_baseline_v2_catalog_duplicate")
    allowed_owners = {
        descriptor.owner_domain for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    }
    unknown_owners = {
        entry.owner_domain for entry in entries
    } - allowed_owners
    if unknown_owners:
        raise HistoricalOperationalBaselineError(
            "historical_baseline_v2_catalog_owner_unsupported"
        )
    if any(entry.repair_target != entry.owner_domain for entry in entries):
        raise HistoricalOperationalBaselineError(
            "historical_baseline_v2_repair_boundary_invalid"
        )
    if any(entry.contract_version != HISTORICAL_BASELINE_CATALOG_VERSION_V2 for entry in entries):
        raise HistoricalOperationalBaselineError(
            "historical_baseline_v2_contract_version_unsupported"
        )
    expected_by_id = {
        entry.contract_id: entry
        for entry in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
    }
    actual_by_id = {entry.contract_id: entry for entry in entries}
    if set(actual_by_id) != set(expected_by_id):
        raise HistoricalOperationalBaselineError(
            "historical_baseline_v2_catalog_descriptor_set_invalid"
        )
    if any(
        actual_by_id[contract_id].canonical_tuple
        != expected_descriptor.canonical_tuple
        for contract_id, expected_descriptor in expected_by_id.items()
    ):
        raise HistoricalOperationalBaselineError(
            "historical_baseline_v2_catalog_descriptor_contract_drift"
        )
    return tuple(sorted(entries, key=lambda item: (item.step, item.contract_id)))


def _validate_v2_collection(
    descriptor: HistoricalBaselineOwnerRootDescriptor,
    observations: tuple[HistoricalBaselineOwnerObservation, ...],
) -> None:
    if not isinstance(
        descriptor.collection,
        HistoricalBaselineOwnerRootCollectionContract,
    ):
        raise HistoricalOperationalBaselineError(
            "historical_baseline_v2_collection_contract_required"
        )
    contract = descriptor.collection
    if contract.all_required is not True:
        raise HistoricalOperationalBaselineError(
            "historical_baseline_v2_collection_all_required"
        )
    if not contract.required_root_identity_kinds:
        raise HistoricalOperationalBaselineError(
            "historical_baseline_v2_collection_required_kind_missing"
        )
    if not observations or len(observations) < contract.minimum_cardinality:
        raise HistoricalOperationalBaselineError(
            "historical_baseline_v2_collection_cardinality_invalid"
        )
    if contract.maximum_cardinality is not None and len(observations) > contract.maximum_cardinality:
        raise HistoricalOperationalBaselineError(
            "historical_baseline_v2_collection_cardinality_invalid"
        )
    if any(item.descriptor != descriptor for item in observations):
        raise HistoricalOperationalBaselineError(
            "historical_baseline_v2_observation_descriptor_mismatch"
        )
    observed_kinds = {item.descriptor.root_identity_kind for item in observations}
    required_kinds = set(contract.required_root_identity_kinds)
    if not required_kinds.issubset(observed_kinds) or not observed_kinds.issubset(
        required_kinds
    ):
        raise HistoricalOperationalBaselineError(
            "historical_baseline_v2_collection_required_fact_missing"
        )


def build_historical_baseline_owner_root_vector_v2(
    observations: Iterable[HistoricalBaselineOwnerObservation],
    *,
    identity: HistoricalOrderIdentity | None = None,
    catalog: Iterable[HistoricalBaselineOwnerRootDescriptor] = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    catalog_version: int = HISTORICAL_BASELINE_CATALOG_VERSION_V2,
) -> tuple[HistoricalBaselineOwnerObservation, ...]:
    if not isinstance(identity, HistoricalOrderIdentity):
        raise TypeError("historical baseline v2 identity is required")
    descriptors = validate_historical_baseline_owner_catalog_v2(
        catalog, catalog_version=catalog_version
    )
    values = tuple(observations)
    if any(not isinstance(item, HistoricalBaselineOwnerObservation) for item in values):
        raise HistoricalOperationalBaselineError("historical_baseline_v2_observation_invalid")
    by_contract = {descriptor.contract_id: descriptor for descriptor in descriptors}
    grouped: dict[str, list[HistoricalBaselineOwnerObservation]] = {
        descriptor.contract_id: [] for descriptor in descriptors
    }
    seen_identity: set[tuple[object, ...]] = set()
    root_versions: dict[tuple[str, str], tuple[str, int]] = {}
    event_versions: dict[tuple[str, str], int] = {}
    for item in values:
        descriptor = by_contract.get(item.descriptor.contract_id)
        if descriptor is None or item.descriptor != descriptor:
            raise HistoricalOperationalBaselineError(
                "historical_baseline_v2_observation_descriptor_unsupported"
            )
        if item.case_no != identity.case_no:
            raise HistoricalOperationalBaselineError("historical_baseline_v2_cross_case")
        key = item.canonical_order_key
        if key in seen_identity:
            raise HistoricalOperationalBaselineError("historical_baseline_v2_observation_duplicate")
        seen_identity.add(key)
        if item.available:
            root_key = (item.descriptor.contract_id, item.root_identity or "")
            prior = root_versions.get(root_key)
            current = (item.source_event_identity or "", item.source_version or 0)
            if prior is not None and prior != current:
                raise HistoricalOperationalBaselineError(
                    "historical_baseline_v2_source_version_drift"
                )
            root_versions[root_key] = current
            event_key = (item.descriptor.contract_id, item.source_event_identity or "")
            prior_event_version = event_versions.get(event_key)
            if prior_event_version is not None and prior_event_version != current[1]:
                raise HistoricalOperationalBaselineError(
                    "historical_baseline_v2_source_version_drift"
                )
            event_versions[event_key] = current[1]
        grouped[item.descriptor.contract_id].append(item)
    for descriptor in descriptors:
        group = tuple(grouped[descriptor.contract_id])
        _validate_v2_collection(descriptor, group)
    return tuple(sorted(values, key=lambda item: item.canonical_order_key))


def historical_baseline_owner_binding_fingerprint_v2(
    identity: HistoricalOrderIdentity,
    historical_provenance: HistoricalOrderProvenanceIdentity,
    observations: Iterable[HistoricalBaselineOwnerObservation],
    *,
    catalog: Iterable[HistoricalBaselineOwnerRootDescriptor] = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    catalog_version: int = HISTORICAL_BASELINE_CATALOG_VERSION_V2,
) -> PreviewFingerprint:
    if not isinstance(identity, HistoricalOrderIdentity):
        raise TypeError("historical baseline v2 identity is invalid")
    if not isinstance(historical_provenance, HistoricalOrderProvenanceIdentity):
        raise TypeError("historical baseline v2 provenance is invalid")
    vector = build_historical_baseline_owner_root_vector_v2(
        observations,
        identity=identity,
        catalog=catalog,
        catalog_version=catalog_version,
    )
    return fingerprint_payload(
        {
            "catalog_version": catalog_version,
            "identity": (identity.order_identity, identity.case_no),
            "provenance": (
                historical_provenance.source_event_identity,
                historical_provenance.source_version,
            ),
            "owner_observations": tuple(item.canonical_tuple for item in vector),
        }
    )


build_historical_baseline_owner_binding_fingerprint_v2 = historical_baseline_owner_binding_fingerprint_v2


def project_earliest_invalidated_root_v2(
    observations: Iterable[HistoricalBaselineOwnerObservation],
    *,
    identity: HistoricalOrderIdentity | None = None,
    catalog: Iterable[HistoricalBaselineOwnerRootDescriptor] = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    catalog_version: int = HISTORICAL_BASELINE_CATALOG_VERSION_V2,
) -> int | None:
    vector = build_historical_baseline_owner_root_vector_v2(
        observations,
        identity=identity,
        catalog=catalog,
        catalog_version=catalog_version,
    )
    candidates = [
        item.descriptor.step
        for item in vector
        if not item.available or item.terminal_result is False
    ]
    return min(candidates) if candidates else None


@dataclass(frozen=True, slots=True)
class HistoricalBaselineOwnerRepairReferralV2:
    """Owner-specific typed referral returned by the v2 descriptor."""

    step: int
    contract_id: str
    owner_domain: str
    root_identity_path: str
    repair_target: str
    repair_capability: str


def historical_baseline_owner_repair_referrals_v2(
    catalog: Iterable[HistoricalBaselineOwnerRootDescriptor] = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
) -> tuple[HistoricalBaselineOwnerRepairReferralV2, ...]:
    return tuple(
        HistoricalBaselineOwnerRepairReferralV2(
            descriptor.step,
            descriptor.contract_id,
            descriptor.owner_domain,
            descriptor.root_identity_path,
            descriptor.repair_target,
            descriptor.repair_capability,
        )
        for descriptor in validate_historical_baseline_owner_catalog_v2(catalog)
    )


__all__ = [
    "HistoricalBaselineEvidenceMode",
    "HistoricalBaselineInvalidationEvent",
    "HistoricalBaselineOwnerRoot",
    "HistoricalBaselineOwnerRootContract",
    "HistoricalBaselineOwnerRootContractEntry",
    "HistoricalBaselineOwnerRootFact",
    "HistoricalBaselineOwnerRootVectorEntry",
    "HistoricalBaselineStepProjection",
    "HistoricalBaselineStepState",
    "HistoricalOperationalBaselineCandidate",
    "HistoricalBaselineLineage",
    "HistoricalOperationalBaselineError",
    "HistoricalOperationalBaselineEvidenceMode",
    "HistoricalOperationalBaselineFacts",
    "HistoricalOrderProvenanceIdentity",
    "HistoricalOperationalBaselineRequest",
    "HistoricalOrderIdentity",
    "HistoricalBaselineRootInvalidationEvent",
    "HISTORICAL_BASELINE_CATALOG_VERSION",
    "HISTORICAL_BASELINE_OWNER_ROOT_CATALOG",
    "HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V1",
    "baseline_payload_equivalent",
    "build_historical_baseline_owner_binding_fingerprint",
    "build_historical_baseline_owner_root_vector",
    "build_historical_operational_baseline_candidate",
    "historical_baseline_owner_binding_fingerprint",
    "project_earliest_invalidated_root",
    "project_historical_baseline_earliest_invalidated_root",
    "project_historical_baseline_steps",
    "validate_historical_baseline_owner_catalog",
    "HISTORICAL_BASELINE_CATALOG_VERSION_V2",
    "HISTORICAL_BASELINE_CATALOG_V2_VERSION",
    "HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2",
    "HistoricalBaselineOwnerRootCollectionContract",
    "HistoricalBaselineOwnerRootDescriptor",
    "HistoricalBaselineOwnerRootContractV2",
    "HistoricalBaselineOwnerDescriptor",
    "HistoricalBaselineOwnerObservation",
    "HistoricalBaselineOwnerObservationV2",
    "HistoricalBaselineOwnerRootObservation",
    "HistoricalBaselineOwnerRootCollection",
    "HistoricalBaselineOwnerRootCollectionDescriptor",
    "HistoricalBaselineOwnerRepairReferralV2",
    "build_historical_baseline_owner_root_vector_v2",
    "historical_baseline_owner_binding_fingerprint_v2",
    "build_historical_baseline_owner_binding_fingerprint_v2",
    "project_earliest_invalidated_root_v2",
    "historical_baseline_owner_repair_referrals_v2",
    "validate_historical_baseline_owner_catalog_v2",
]
