"""
File: historical_baseline_projection.py
Description: 以 fresh HCAT v2 根事實純投影 occurrence、umbrella、successor 與持久化意圖。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from domains.orders.historical_operational_baseline import (
    HISTORICAL_BASELINE_CATALOG_VERSION_V2,
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    HistoricalBaselineOwnerObservation,
    HistoricalBaselineOwnerRootCollection,
    HistoricalBaselineOwnerRootDescriptor,
    HistoricalOperationalBaselineError,
    HistoricalOrderIdentity,
    HistoricalOrderProvenanceIdentity,
    build_historical_baseline_owner_root_vector_v2,
    historical_baseline_owner_binding_fingerprint_v2,
    historical_baseline_owner_repair_referrals_v2,
    project_earliest_invalidated_root_v2,
    validate_historical_baseline_owner_catalog_v2,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.validation import require_canonical_text
from subsystems.orders.historical_baseline_owner_vector import (
    HistoricalBaselineOwnerVectorV2Projection,
)


_INTENT_KEY = re.compile(r"^[a-z0-9][a-z0-9._:-]{0,190}$")


class HistoricalBaselineProjectionError(ValueError):
    """The supplied source or readback cannot safely drive the projector."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def historical_baseline_catalog_identity() -> PreviewFingerprint:
    """Return the canonical identity of the only supported v2 catalog."""

    catalog = validate_historical_baseline_owner_catalog_v2(
        HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
        catalog_version=HISTORICAL_BASELINE_CATALOG_VERSION_V2,
    )
    return _digest(
        {
            "kind": "historical_baseline_catalog_v2",
            "catalog_version": HISTORICAL_BASELINE_CATALOG_VERSION_V2,
            "descriptors": tuple(item.canonical_tuple for item in catalog),
        }
    )


@dataclass(frozen=True, slots=True)
class HistoricalBaselineProjectionSourceIntent:
    """Committed B1 intent identities plus the vector fingerprint it requested."""

    source_intent_key: str
    idempotency_key: str
    baseline_event_identity: str
    baseline_receipt_identity: str
    baseline_outbox_identity: str
    identity: HistoricalOrderIdentity
    selected_step: int
    catalog_identity: PreviewFingerprint
    catalog_version: int
    expected_owner_binding_fingerprint: PreviewFingerprint
    source_trigger_version: int = 1
    projection_sequence: int = 1

    def __post_init__(self) -> None:
        for value, label in (
            (self.source_intent_key, "baseline projector source intent key"),
            (self.idempotency_key, "baseline projector idempotency key"),
        ):
            require_canonical_text(value, label, 191)
            if _INTENT_KEY.fullmatch(value) is None:
                raise HistoricalBaselineProjectionError("projector_intent_key_invalid")
        for value, label in (
            (self.baseline_event_identity, "baseline projector event identity"),
            (self.baseline_receipt_identity, "baseline projector receipt identity"),
            (self.baseline_outbox_identity, "baseline projector outbox identity"),
        ):
            require_canonical_text(value, label, 191)
        if not isinstance(self.identity, HistoricalOrderIdentity):
            raise TypeError("baseline projector order identity is invalid")
        if isinstance(self.selected_step, bool) or not isinstance(self.selected_step, int):
            raise HistoricalBaselineProjectionError("projector_selected_step_invalid")
        if not 1 <= self.selected_step <= 11:
            raise HistoricalBaselineProjectionError("projector_selected_step_invalid")
        if not isinstance(self.catalog_identity, PreviewFingerprint):
            raise TypeError("baseline projector catalog identity is invalid")
        if (
            isinstance(self.catalog_version, bool)
            or not isinstance(self.catalog_version, int)
            or self.catalog_version != HISTORICAL_BASELINE_CATALOG_VERSION_V2
        ):
            raise HistoricalBaselineProjectionError("projector_catalog_version_invalid")
        if not isinstance(self.expected_owner_binding_fingerprint, PreviewFingerprint):
            raise TypeError("baseline projector expected vector fingerprint is invalid")
        if (
            isinstance(self.source_trigger_version, bool)
            or not isinstance(self.source_trigger_version, int)
            or self.source_trigger_version < 0
        ):
            raise HistoricalBaselineProjectionError(
                "projector_source_trigger_version_invalid"
            )
        if (
            isinstance(self.projection_sequence, bool)
            or not isinstance(self.projection_sequence, int)
            or self.projection_sequence < 1
        ):
            raise HistoricalBaselineProjectionError(
                "projector_projection_sequence_invalid"
            )


@dataclass(frozen=True, slots=True)
class FreshHistoricalBaselineOwnerVectorReadback:
    projection: HistoricalBaselineOwnerVectorV2Projection
    complete: bool = True
    fresh: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.projection, HistoricalBaselineOwnerVectorV2Projection):
            raise TypeError("baseline projector owner vector projection is invalid")
        if type(self.complete) is not bool or type(self.fresh) is not bool:
            raise TypeError("baseline projector readback flags must be bool")


@dataclass(frozen=True, slots=True)
class HistoricalBaselineOccurrenceProjection:
    occurrence_identity: str
    case_no: str
    order_identity: str
    baseline_event_identity: str
    catalog_identity: str
    catalog_version: int
    descriptor_identity: str
    observation_identity: str
    descriptor: HistoricalBaselineOwnerRootDescriptor
    observation: HistoricalBaselineOwnerObservation
    owner_binding_fingerprint: PreviewFingerprint
    terminal: bool
    active: bool


@dataclass(frozen=True, slots=True)
class HistoricalBaselineSuccessorProjection:
    successor_relation_identity: str
    predecessor_occurrence_identity: str
    successor_occurrence_identity: str
    case_no: str
    order_identity: str
    baseline_event_identity: str
    catalog_identity: str
    catalog_version: int
    descriptor_identity: str
    contract_id: str
    contract_version: int
    owner_event_identity: str
    prior_owner_source_version: int
    new_owner_source_version: int
    terminal_predicate_id: str
    terminal_predicate_version: int
    fresh_readback_fingerprint: PreviewFingerprint


@dataclass(frozen=True, slots=True)
class HistoricalBaselineUmbrellaMembershipProjection:
    membership_identity: str
    umbrella_identity: str
    set_ordinal: int
    occurrence_identity: str


@dataclass(frozen=True, slots=True)
class HistoricalBaselineUmbrellaProjection:
    umbrella_identity: str
    memberships: tuple[HistoricalBaselineUmbrellaMembershipProjection, ...]
    membership_set_digest: PreviewFingerprint
    membership_count: int
    active: bool

    @property
    def membership_occurrence_identities(self) -> tuple[str, ...]:
        return tuple(item.occurrence_identity for item in self.memberships)


@dataclass(frozen=True, slots=True)
class HistoricalBaselineProjectorReceiptProjection:
    projector_receipt_identity: str
    source_intent_key: str
    payload_digest: PreviewFingerprint
    idempotency_key: str
    baseline_event_identity: str
    baseline_receipt_identity: str
    baseline_outbox_identity: str
    case_no: str
    order_identity: str
    catalog_identity: str
    catalog_version: int
    whole_vector_fingerprint: PreviewFingerprint
    whole_vector_count: int
    emitted_occurrence_set_digest: PreviewFingerprint
    emitted_occurrence_set_count: int
    active_membership_set_digest: PreviewFingerprint
    active_membership_set_count: int
    umbrella_identity: str
    projection_sequence: int
    result_state: Literal["projected", "held_active"]
    expected_readback_digest: PreviewFingerprint

    @property
    def occurrence_set_digest(self) -> PreviewFingerprint:
        """Compatibility name for the v1 emitted-occurrence field."""

        return self.emitted_occurrence_set_digest

    @property
    def occurrence_set_count(self) -> int:
        """Compatibility name for the v1 emitted-occurrence field."""

        return self.emitted_occurrence_set_count

    @property
    def post_commit_readback_digest(self) -> PreviewFingerprint:
        """Compatibility name retained for existing pure-projector callers."""

        return self.expected_readback_digest


@dataclass(frozen=True, slots=True)
class HistoricalBaselineProjectorOutboxIntent:
    intent_type: Literal["historical_baseline_projection_readback_requested"]
    target_owner: Literal["orders_anomalies_projection"]
    intent_key: str
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class HistoricalBaselineProjectionResult:
    occurrences: tuple[HistoricalBaselineOccurrenceProjection, ...]
    successor_occurrences: tuple[HistoricalBaselineOccurrenceProjection, ...]
    inactive_predecessor_identities: tuple[str, ...]
    successors: tuple[HistoricalBaselineSuccessorProjection, ...]
    umbrella: HistoricalBaselineUmbrellaProjection
    baseline_selected_step: int
    current_step: int
    terminal_conjunction: bool
    receipt: HistoricalBaselineProjectorReceiptProjection
    outbox: HistoricalBaselineProjectorOutboxIntent


def project_historical_baseline(
    source_intent: HistoricalBaselineProjectionSourceIntent,
    readback: FreshHistoricalBaselineOwnerVectorReadback,
    *,
    prior_active_occurrences: tuple[HistoricalBaselineOccurrenceProjection, ...] = (),
) -> HistoricalBaselineProjectionResult:
    """Purely derive one exact projector candidate from a fresh complete vector."""

    if not isinstance(source_intent, HistoricalBaselineProjectionSourceIntent):
        raise TypeError("baseline projector source intent is invalid")
    if not isinstance(readback, FreshHistoricalBaselineOwnerVectorReadback):
        raise TypeError("baseline projector readback is invalid")
    if not isinstance(prior_active_occurrences, tuple) or any(
        not isinstance(item, HistoricalBaselineOccurrenceProjection)
        for item in prior_active_occurrences
    ):
        raise TypeError("baseline projector prior occurrences are invalid")
    if not readback.complete or not readback.fresh:
        raise HistoricalBaselineProjectionError("projector_readback_unavailable")

    projection = readback.projection
    vector, catalog_identity = _validated_vector(projection)
    if projection.identity != source_intent.identity:
        raise HistoricalBaselineProjectionError("projector_cross_case_or_order")
    if projection.catalog_version != source_intent.catalog_version:
        raise HistoricalBaselineProjectionError("projector_catalog_version_mismatch")
    if catalog_identity != source_intent.catalog_identity:
        raise HistoricalBaselineProjectionError("projector_catalog_identity_mismatch")
    if projection.owner_binding_fingerprint != source_intent.expected_owner_binding_fingerprint:
        raise HistoricalBaselineProjectionError("projector_owner_binding_stale")

    occurrences = tuple(
        _occurrence(source_intent, observation, projection.owner_binding_fingerprint)
        for observation in vector
        if not observation.available or observation.terminal_result is not True
    )
    occurrences = tuple(sorted(occurrences, key=lambda item: item.occurrence_identity))
    current_by_identity = {item.occurrence_identity: item for item in occurrences}
    current_by_contract: dict[str, tuple[HistoricalBaselineOwnerObservation, ...]] = {}
    for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2:
        current_by_contract[descriptor.contract_id] = tuple(
            item for item in vector if item.descriptor.contract_id == descriptor.contract_id
        )

    inactive: list[str] = []
    successors: list[HistoricalBaselineSuccessorProjection] = []
    successor_occurrences: list[HistoricalBaselineOccurrenceProjection] = []
    seen_prior: set[str] = set()
    for prior in prior_active_occurrences:
        _validate_prior(source_intent, prior)
        if prior.occurrence_identity in seen_prior:
            raise HistoricalBaselineProjectionError("projector_prior_occurrence_duplicate")
        seen_prior.add(prior.occurrence_identity)
        if prior.occurrence_identity in current_by_identity:
            continue
        current_group = current_by_contract.get(prior.descriptor.contract_id)
        if not current_group:
            raise HistoricalBaselineProjectionError("projector_successor_readback_partial")
        if prior.observation.available:
            matching = tuple(
                item
                for item in current_group
                if item.available and item.root_identity == prior.observation.root_identity
            )
            if len(matching) != 1:
                raise HistoricalBaselineProjectionError("projector_successor_identity_drift")
            successor_observation = matching[0]
            if successor_observation.terminal_result is not True:
                raise HistoricalBaselineProjectionError("projector_successor_not_terminal")
            relation, successor_occurrence = _successor(
                    source_intent,
                    prior,
                    successor_observation,
                    projection.owner_binding_fingerprint,
                )
            successors.append(relation)
            successor_occurrences.append(successor_occurrence)
        elif not all(
            item.available and item.terminal_result is True for item in current_group
        ):
            raise HistoricalBaselineProjectionError("projector_unavailable_occurrence_not_terminal")
        inactive.append(prior.occurrence_identity)

    active_ids = tuple(item.occurrence_identity for item in occurrences)
    umbrella_identity = _digest(
        {
            "kind": "historical_baseline_umbrella_v1",
            "case_no": source_intent.identity.case_no,
            "baseline_event_identity": source_intent.baseline_event_identity,
            "catalog_identity": catalog_identity.value,
            "catalog_version": source_intent.catalog_version,
        }
    ).value
    emitted_ids = tuple(
        sorted(
            (*active_ids, *(item.occurrence_identity for item in successor_occurrences))
        )
    )
    occurrence_set_digest = _identity_set_digest(emitted_ids)
    membership_set_digest = _identity_set_digest(active_ids)
    memberships = tuple(
        HistoricalBaselineUmbrellaMembershipProjection(
            membership_identity=_digest(
                {
                    "kind": "historical_baseline_umbrella_membership_v2",
                    "source_trigger_identity": source_intent.source_intent_key,
                    "projection_sequence": source_intent.projection_sequence,
                    "umbrella_identity": umbrella_identity,
                    "occurrence_identity": occurrence_identity,
                }
            ).value,
            umbrella_identity=umbrella_identity,
            set_ordinal=ordinal,
            occurrence_identity=occurrence_identity,
        )
        for ordinal, occurrence_identity in enumerate(active_ids, start=1)
    )
    umbrella = HistoricalBaselineUmbrellaProjection(
        umbrella_identity=umbrella_identity,
        memberships=memberships,
        membership_set_digest=membership_set_digest,
        membership_count=len(active_ids),
        active=bool(active_ids),
    )
    earliest = project_earliest_invalidated_root_v2(
        vector,
        identity=projection.identity,
        catalog_version=projection.catalog_version,
    )
    terminal = earliest is None
    current_step = 11 if earliest is None else earliest
    payload_digest = _digest(
        {
            "kind": "historical_baseline_projector_payload_v2",
            "source": _source_payload(source_intent),
            "source_trigger_version": source_intent.source_trigger_version,
            "projection_sequence": source_intent.projection_sequence,
            "whole_vector_fingerprint": projection.owner_binding_fingerprint.value,
            "prior_active_occurrences": tuple(sorted(seen_prior)),
        }
    )
    post_commit_readback_digest = _digest(
        {
            "kind": "historical_baseline_projector_readback_v2",
            "active_occurrences": active_ids,
            "successor_occurrences": tuple(
                item.occurrence_identity
                for item in sorted(
                    successor_occurrences, key=lambda value: value.occurrence_identity
                )
            ),
            "inactive_predecessors": tuple(sorted(inactive)),
            "successors": tuple(
                _successor_payload(item)
                for item in sorted(successors, key=lambda value: value.successor_relation_identity)
            ),
            "umbrella_identity": umbrella_identity,
            "occurrence_set_digest": occurrence_set_digest.value,
            "occurrence_set_count": len(emitted_ids),
            "membership_set_digest": membership_set_digest.value,
            "membership_count": len(active_ids),
            "projection_sequence": source_intent.projection_sequence,
            "current_step": current_step,
            "terminal_conjunction": terminal,
        }
    )
    projector_receipt_identity = _digest(
        {
            "kind": "historical_baseline_projector_receipt_v2",
            "source_intent_key": source_intent.source_intent_key,
            "source_trigger_version": source_intent.source_trigger_version,
            "projection_sequence": source_intent.projection_sequence,
            "payload_digest": payload_digest.value,
            "post_commit_readback_digest": post_commit_readback_digest.value,
        }
    ).value
    receipt = HistoricalBaselineProjectorReceiptProjection(
        projector_receipt_identity=projector_receipt_identity,
        source_intent_key=source_intent.source_intent_key,
        payload_digest=payload_digest,
        idempotency_key=source_intent.idempotency_key,
        baseline_event_identity=source_intent.baseline_event_identity,
        baseline_receipt_identity=source_intent.baseline_receipt_identity,
        baseline_outbox_identity=source_intent.baseline_outbox_identity,
        case_no=source_intent.identity.case_no,
        order_identity=source_intent.identity.order_identity,
        catalog_identity=catalog_identity.value,
        catalog_version=source_intent.catalog_version,
        whole_vector_fingerprint=projection.owner_binding_fingerprint,
        whole_vector_count=len(vector),
        emitted_occurrence_set_digest=occurrence_set_digest,
        emitted_occurrence_set_count=len(emitted_ids),
        active_membership_set_digest=membership_set_digest,
        active_membership_set_count=len(active_ids),
        umbrella_identity=umbrella_identity,
        projection_sequence=source_intent.projection_sequence,
        result_state="held_active" if active_ids else "projected",
        expected_readback_digest=post_commit_readback_digest,
    )
    outbox_payload = {
        "projector_receipt_identity": projector_receipt_identity,
        "source_intent_key": source_intent.source_intent_key,
        "baseline_event_identity": source_intent.baseline_event_identity,
        "baseline_receipt_identity": source_intent.baseline_receipt_identity,
        "baseline_outbox_identity": source_intent.baseline_outbox_identity,
        "case_no": source_intent.identity.case_no,
        "order_identity": source_intent.identity.order_identity,
        "catalog_identity": catalog_identity.value,
        "catalog_version": source_intent.catalog_version,
        "whole_vector_fingerprint": projection.owner_binding_fingerprint.value,
        "emitted_occurrence_set_digest": occurrence_set_digest.value,
        "emitted_occurrence_set_count": len(emitted_ids),
        "occurrence_set_digest": occurrence_set_digest.value,
        "occurrence_set_count": len(emitted_ids),
        "active_membership_set_digest": membership_set_digest.value,
        "active_membership_set_count": len(active_ids),
        "membership_set_digest": membership_set_digest.value,
        "membership_count": len(active_ids),
        "umbrella_identity": umbrella_identity,
        "projection_sequence": source_intent.projection_sequence,
        "result_state": receipt.result_state,
        "current_step": current_step,
        "terminal_conjunction": terminal,
        "post_commit_readback_digest": post_commit_readback_digest.value,
    }
    return HistoricalBaselineProjectionResult(
        occurrences=occurrences,
        successor_occurrences=tuple(
            sorted(successor_occurrences, key=lambda item: item.occurrence_identity)
        ),
        inactive_predecessor_identities=tuple(sorted(inactive)),
        successors=tuple(
            sorted(successors, key=lambda item: item.successor_relation_identity)
        ),
        umbrella=umbrella,
        baseline_selected_step=source_intent.selected_step,
        current_step=current_step,
        terminal_conjunction=terminal,
        receipt=receipt,
        outbox=HistoricalBaselineProjectorOutboxIntent(
            intent_type="historical_baseline_projection_readback_requested",
            target_owner="orders_anomalies_projection",
            intent_key=f"hbp.readback:{projector_receipt_identity}",
            payload=outbox_payload,
        ),
    )


def _validated_vector(
    projection: HistoricalBaselineOwnerVectorV2Projection,
) -> tuple[tuple[HistoricalBaselineOwnerObservation, ...], PreviewFingerprint]:
    if (
        not isinstance(projection.identity, HistoricalOrderIdentity)
        or not isinstance(
            projection.historical_provenance, HistoricalOrderProvenanceIdentity
        )
        or not isinstance(projection.owner_binding_fingerprint, PreviewFingerprint)
    ):
        raise HistoricalBaselineProjectionError("projector_owner_vector_malformed")
    if projection.catalog_version != HISTORICAL_BASELINE_CATALOG_VERSION_V2:
        raise HistoricalBaselineProjectionError("projector_catalog_version_unsupported")
    if not isinstance(projection.owner_observations, tuple):
        raise HistoricalBaselineProjectionError("projector_owner_vector_malformed")
    for observation in projection.owner_observations:
        if not isinstance(observation, HistoricalBaselineOwnerObservation):
            raise HistoricalBaselineProjectionError("projector_owner_vector_malformed")
        if observation.case_no != projection.identity.case_no:
            raise HistoricalBaselineProjectionError("projector_owner_vector_cross_case")
        _validate_observation_shape(observation)
    try:
        catalog = validate_historical_baseline_owner_catalog_v2(
            HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
            catalog_version=projection.catalog_version,
        )
        vector = build_historical_baseline_owner_root_vector_v2(
            projection.owner_observations,
            identity=projection.identity,
            catalog=catalog,
            catalog_version=projection.catalog_version,
        )
        fingerprint = historical_baseline_owner_binding_fingerprint_v2(
            projection.identity,
            projection.historical_provenance,
            vector,
            catalog=catalog,
            catalog_version=projection.catalog_version,
        )
    except (HistoricalOperationalBaselineError, TypeError, ValueError) as error:
        raise HistoricalBaselineProjectionError("projector_owner_vector_malformed") from error
    if fingerprint != projection.owner_binding_fingerprint:
        raise HistoricalBaselineProjectionError("projector_owner_vector_fingerprint_mismatch")
    _validate_collections(projection.owner_collections, vector, catalog)
    expected_earliest = project_earliest_invalidated_root_v2(
        vector,
        identity=projection.identity,
        catalog=catalog,
        catalog_version=projection.catalog_version,
    )
    expected_step = 11 if expected_earliest is None else expected_earliest
    expected_unavailable = next(
        (item.descriptor.step for item in vector if not item.available), None
    )
    if (
        projection.current_step != expected_step
        or projection.earliest_unavailable_step != expected_unavailable
    ):
        raise HistoricalBaselineProjectionError("projector_current_step_readback_mismatch")
    if projection.repair_referrals != historical_baseline_owner_repair_referrals_v2(catalog):
        raise HistoricalBaselineProjectionError("projector_repair_referral_readback_mismatch")
    catalog_identity = historical_baseline_catalog_identity()
    return vector, catalog_identity


def _validate_collections(
    collections: tuple[HistoricalBaselineOwnerRootCollection, ...],
    vector: tuple[HistoricalBaselineOwnerObservation, ...],
    catalog: tuple[HistoricalBaselineOwnerRootDescriptor, ...],
) -> None:
    if not isinstance(collections, tuple) or any(
        not isinstance(item, HistoricalBaselineOwnerRootCollection) for item in collections
    ):
        raise HistoricalBaselineProjectionError("projector_owner_collections_malformed")
    if len(collections) != len(catalog):
        raise HistoricalBaselineProjectionError("projector_owner_collections_partial")
    by_contract = {item.descriptor.contract_id: item for item in collections}
    if len(by_contract) != len(catalog):
        raise HistoricalBaselineProjectionError("projector_owner_collections_duplicate")
    flattened: list[HistoricalBaselineOwnerObservation] = []
    for descriptor in catalog:
        collection = by_contract.get(descriptor.contract_id)
        if collection is None or collection.descriptor.canonical_tuple != descriptor.canonical_tuple:
            raise HistoricalBaselineProjectionError("projector_owner_collection_descriptor_mismatch")
        flattened.extend(collection.observations)
    if tuple(sorted(flattened, key=lambda item: item.canonical_order_key)) != vector:
        raise HistoricalBaselineProjectionError("projector_owner_collection_vector_mismatch")


def _occurrence(
    source: HistoricalBaselineProjectionSourceIntent,
    observation: HistoricalBaselineOwnerObservation,
    owner_binding_fingerprint: PreviewFingerprint,
    *,
    active: bool = True,
) -> HistoricalBaselineOccurrenceProjection:
    descriptor_identity = _descriptor_identity(observation.descriptor)
    observation_identity = _observation_identity(observation)
    occurrence_identity = _digest(
        {
            "kind": "historical_baseline_occurrence_v1",
            "case_no": source.identity.case_no,
            "order_identity": source.identity.order_identity,
            "baseline_event_identity": source.baseline_event_identity,
            "catalog_identity": source.catalog_identity.value,
            "catalog_version": source.catalog_version,
            "descriptor": observation.descriptor.canonical_tuple,
            "observation": observation.canonical_tuple,
        }
    ).value
    terminal = observation.available and observation.terminal_result is True
    return HistoricalBaselineOccurrenceProjection(
        occurrence_identity=occurrence_identity,
        case_no=source.identity.case_no,
        order_identity=source.identity.order_identity,
        baseline_event_identity=source.baseline_event_identity,
        catalog_identity=source.catalog_identity.value,
        catalog_version=source.catalog_version,
        descriptor_identity=descriptor_identity,
        observation_identity=observation_identity,
        descriptor=observation.descriptor,
        observation=observation,
        owner_binding_fingerprint=owner_binding_fingerprint,
        terminal=terminal,
        active=active,
    )


def _successor(
    source: HistoricalBaselineProjectionSourceIntent,
    prior: HistoricalBaselineOccurrenceProjection,
    observation: HistoricalBaselineOwnerObservation,
    fingerprint: PreviewFingerprint,
) -> tuple[
    HistoricalBaselineSuccessorProjection,
    HistoricalBaselineOccurrenceProjection,
]:
    prior_version = prior.observation.source_version
    new_version = observation.source_version
    if prior_version is None or new_version is None:
        raise HistoricalBaselineProjectionError("projector_successor_version_missing")
    if new_version <= prior_version:
        raise HistoricalBaselineProjectionError("projector_successor_source_version_not_newer")
    if observation.source_event_identity is None:
        raise HistoricalBaselineProjectionError("projector_successor_event_missing")
    successor_occurrence = _occurrence(
        source, observation, fingerprint, active=False
    )
    payload = {
        "kind": "historical_baseline_successor_v1",
        "predecessor_occurrence_identity": prior.occurrence_identity,
        "successor_occurrence_identity": successor_occurrence.occurrence_identity,
        "case_no": source.identity.case_no,
        "order_identity": source.identity.order_identity,
        "baseline_event_identity": source.baseline_event_identity,
        "catalog_identity": source.catalog_identity.value,
        "catalog_version": source.catalog_version,
        "descriptor_identity": prior.descriptor_identity,
        "contract_id": prior.descriptor.contract_id,
        "contract_version": prior.descriptor.contract_version,
        "owner_event_identity": observation.source_event_identity,
        "prior_owner_source_version": prior_version,
        "new_owner_source_version": new_version,
        "terminal_predicate_id": prior.descriptor.terminal_predicate_id,
        "terminal_predicate_version": prior.descriptor.terminal_predicate_version,
        "fresh_readback_fingerprint": fingerprint.value,
    }
    relation = HistoricalBaselineSuccessorProjection(
        successor_relation_identity=_digest(payload).value,
        predecessor_occurrence_identity=prior.occurrence_identity,
        successor_occurrence_identity=successor_occurrence.occurrence_identity,
        case_no=source.identity.case_no,
        order_identity=source.identity.order_identity,
        baseline_event_identity=source.baseline_event_identity,
        catalog_identity=source.catalog_identity.value,
        catalog_version=source.catalog_version,
        descriptor_identity=prior.descriptor_identity,
        contract_id=prior.descriptor.contract_id,
        contract_version=prior.descriptor.contract_version,
        owner_event_identity=observation.source_event_identity,
        prior_owner_source_version=prior_version,
        new_owner_source_version=new_version,
        terminal_predicate_id=prior.descriptor.terminal_predicate_id,
        terminal_predicate_version=prior.descriptor.terminal_predicate_version,
        fresh_readback_fingerprint=fingerprint,
    )
    return relation, successor_occurrence


def _validate_prior(
    source: HistoricalBaselineProjectionSourceIntent,
    prior: HistoricalBaselineOccurrenceProjection,
) -> None:
    if prior.active is not True or prior.terminal is not False:
        raise HistoricalBaselineProjectionError("projector_prior_occurrence_not_active")
    if not isinstance(prior.owner_binding_fingerprint, PreviewFingerprint):
        raise HistoricalBaselineProjectionError("projector_prior_occurrence_malformed")
    try:
        _validate_observation_shape(prior.observation)
    except HistoricalBaselineProjectionError as error:
        raise HistoricalBaselineProjectionError(
            "projector_prior_occurrence_malformed"
        ) from error
    catalog_descriptor = next(
        (
            item
            for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
            if item.contract_id == prior.descriptor.contract_id
        ),
        None,
    )
    if (
        catalog_descriptor is None
        or prior.descriptor.canonical_tuple != catalog_descriptor.canonical_tuple
        or prior.observation.descriptor.canonical_tuple
        != catalog_descriptor.canonical_tuple
    ):
        raise HistoricalBaselineProjectionError("projector_prior_occurrence_malformed")
    if (
        prior.case_no != source.identity.case_no
        or prior.order_identity != source.identity.order_identity
        or prior.observation.case_no != source.identity.case_no
    ):
        raise HistoricalBaselineProjectionError("projector_prior_occurrence_cross_case")
    if prior.baseline_event_identity != source.baseline_event_identity:
        raise HistoricalBaselineProjectionError("projector_prior_occurrence_lineage_mismatch")
    if (
        prior.catalog_identity != source.catalog_identity.value
        or prior.catalog_version != source.catalog_version
    ):
        raise HistoricalBaselineProjectionError("projector_prior_occurrence_catalog_mismatch")
    expected = _occurrence(
        source,
        prior.observation,
        prior.owner_binding_fingerprint,
        active=True,
    )
    if expected != prior:
        raise HistoricalBaselineProjectionError("projector_prior_occurrence_malformed")


def _validate_observation_shape(
    observation: HistoricalBaselineOwnerObservation,
) -> None:
    if observation.available:
        if (
            observation.root_identity is None
            or observation.source_event_identity is None
            or observation.source_version is None
            or isinstance(observation.source_version, bool)
            or not isinstance(observation.source_version, int)
            or observation.source_version < 0
            or type(observation.terminal_result) is not bool
        ):
            raise HistoricalBaselineProjectionError("projector_owner_vector_malformed")
    elif (
        observation.root_identity is not None
        or observation.source_event_identity is not None
        or observation.source_version is not None
        or observation.terminal_result is not None
        or not observation.unavailable_code
    ):
        raise HistoricalBaselineProjectionError("projector_owner_vector_malformed")


def _descriptor_identity(descriptor: HistoricalBaselineOwnerRootDescriptor) -> str:
    return _digest(
        {"kind": "historical_baseline_descriptor_v1", "descriptor": descriptor.canonical_tuple}
    ).value


def _successor_payload(
    successor: HistoricalBaselineSuccessorProjection,
) -> tuple[object, ...]:
    return (
        successor.successor_relation_identity,
        successor.predecessor_occurrence_identity,
        successor.successor_occurrence_identity,
        successor.case_no,
        successor.order_identity,
        successor.baseline_event_identity,
        successor.catalog_identity,
        successor.catalog_version,
        successor.descriptor_identity,
        successor.contract_id,
        successor.contract_version,
        successor.owner_event_identity,
        successor.prior_owner_source_version,
        successor.new_owner_source_version,
        successor.terminal_predicate_id,
        successor.terminal_predicate_version,
        successor.fresh_readback_fingerprint.value,
    )


def _observation_identity(observation: HistoricalBaselineOwnerObservation) -> str:
    return _digest(
        {"kind": "historical_baseline_observation_v1", "observation": observation.canonical_tuple}
    ).value


def _identity_set_digest(identities: tuple[str, ...]) -> PreviewFingerprint:
    return _digest(
        {"kind": "historical_baseline_occurrence_set_v1", "identities": tuple(sorted(identities))}
    )


def _source_payload(source: HistoricalBaselineProjectionSourceIntent) -> dict[str, object]:
    return {
        "source_intent_key": source.source_intent_key,
        "idempotency_key": source.idempotency_key,
        "baseline_event_identity": source.baseline_event_identity,
        "baseline_receipt_identity": source.baseline_receipt_identity,
        "baseline_outbox_identity": source.baseline_outbox_identity,
        "case_no": source.identity.case_no,
        "order_identity": source.identity.order_identity,
        "selected_step": source.selected_step,
        "catalog_identity": source.catalog_identity.value,
        "catalog_version": source.catalog_version,
        "expected_owner_binding_fingerprint": source.expected_owner_binding_fingerprint.value,
    }


def _digest(payload: dict[str, object]) -> PreviewFingerprint:
    return fingerprint_payload(payload)


__all__ = [
    "FreshHistoricalBaselineOwnerVectorReadback",
    "HistoricalBaselineOccurrenceProjection",
    "HistoricalBaselineProjectionError",
    "HistoricalBaselineProjectionResult",
    "HistoricalBaselineProjectionSourceIntent",
    "HistoricalBaselineProjectorOutboxIntent",
    "HistoricalBaselineProjectorReceiptProjection",
    "HistoricalBaselineSuccessorProjection",
    "HistoricalBaselineUmbrellaProjection",
    "HistoricalBaselineUmbrellaMembershipProjection",
    "historical_baseline_catalog_identity",
    "project_historical_baseline",
]
