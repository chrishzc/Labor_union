"""Focused state/replay/reconcile tests for HPROJ persistence v2."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import json

import pytest
from pymysql.err import OperationalError

import infrastructure.mysql.historical_baseline_projector_repository as projector_repository
from domains.orders.historical_operational_baseline import (
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    HistoricalBaselineOwnerObservation,
    HistoricalOrderIdentity,
    HistoricalOrderProvenanceIdentity,
)
from infrastructure.mysql.historical_baseline_projector_checkpoint import (
    HistoricalBaselineSourceCheckpoint,
    validate_checkpoint_progress,
)
from infrastructure.mysql.historical_baseline_projector_delivery import (
    HistoricalBaselineDeliveryError,
    HistoricalBaselineDeliveryStatus,
    HistoricalBaselineProjectorDelivery,
    HistoricalBaselineProjectorTrigger,
)
from infrastructure.mysql.historical_baseline_projector_worker import (
    HistoricalBaselineExactReadback,
    HistoricalBaselineProjectorWorker,
)
from infrastructure.mysql.historical_baseline_projector_repository import (
    MySqlHistoricalBaselineProjectorRepository,
)
from infrastructure.mysql.historical_baseline_projector_read_model import (
    HistoricalBaselineAlertDisplayView,
    HistoricalBaselineCurrentAlertView,
    HistoricalBaselineDeliveryView,
    HistoricalBaselineMembershipView,
    HistoricalBaselinePostCommitReadbackView,
    HistoricalBaselineProjectorReadModel,
    HistoricalBaselineReceiptView,
    HistoricalBaselineRepairReferralView,
)
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.anomalies.historical_baseline_projection import (
    FreshHistoricalBaselineOwnerVectorReadback,
    HistoricalBaselineProjectionSourceIntent,
    historical_baseline_catalog_identity,
    project_historical_baseline,
)
from subsystems.orders.historical_baseline_owner_vector import (
    HistoricalBaselineOwnerObservationReadback,
    HistoricalBaselineOwnerVectorV2Query,
    HistoricalBaselineOwnerVectorV2QueryRequest,
)


_IDENTITY = HistoricalOrderIdentity("order:CASE-HPROJ-V2", "CASE-HPROJ-V2")
_PROVENANCE = HistoricalOrderProvenanceIdentity("import:CASE-HPROJ-V2", 4)


@dataclass
class _Port:
    observations: dict[str, tuple[HistoricalBaselineOwnerObservation, ...]]
    owner_domain: str

    def read_owner_observations(self, identity, descriptor, *, for_update=False):
        return HistoricalBaselineOwnerObservationReadback(
            identity, self.observations[descriptor.contract_id]
        )


def _projection(repaired_count: int, *, regression: bool = False):
    invalid = HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2[:3]
    observations = {}
    for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2:
        if descriptor in invalid:
            index = invalid.index(descriptor)
            terminal = index < repaired_count
            version = 2 if terminal else 1
            if regression and index == 0:
                terminal = False
                version = 3
        else:
            terminal = True
            version = 1
        observations[descriptor.contract_id] = (
            HistoricalBaselineOwnerObservation(
                descriptor=descriptor,
                root_identity=f"{descriptor.root_identity_kind}:{_IDENTITY.case_no}",
                source_event_identity=f"{descriptor.owner_domain}:{descriptor.contract_id}:v{version}",
                source_version=version,
                terminal_result=terminal,
                case_no=_IDENTITY.case_no,
            ),
        )
    ports = {
        owner: _Port(
            {
                descriptor.contract_id: observations[descriptor.contract_id]
                for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
                if descriptor.owner_domain == owner
            },
            owner,
        )
        for owner in {
            descriptor.owner_domain
            for descriptor in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
        }
    }
    return HistoricalBaselineOwnerVectorV2Query.from_ports(ports).query(
        HistoricalBaselineOwnerVectorV2QueryRequest(_IDENTITY, _PROVENANCE)
    )


def _trigger(version: int, projection, *, payload_marker: str = "same"):
    identity = f"hproj.case-hproj-v2.owner-repair-{version}"
    intent = HistoricalBaselineProjectionSourceIntent(
        source_intent_key=identity,
        idempotency_key=f"hproj.case-hproj-v2.project-{version}",
        baseline_event_identity="baseline-event:CASE-HPROJ-V2:1",
        baseline_receipt_identity="baseline-receipt:CASE-HPROJ-V2:1",
        baseline_outbox_identity="baseline-outbox:CASE-HPROJ-V2:1",
        identity=_IDENTITY,
        selected_step=11,
        catalog_identity=historical_baseline_catalog_identity(),
        catalog_version=2,
        expected_owner_binding_fingerprint=projection.owner_binding_fingerprint,
        source_trigger_version=version,
    )
    return HistoricalBaselineProjectorTrigger.build(
        trigger_identity=identity,
        source_kind="owner_repair",
        source_domain="orders",
        source_stream="historical-baseline-owner-repair-v1",
        source_event_identity=f"orders:repair:{version}",
        source_version=version,
        stream_start_version=1,
        partition_key=_IDENTITY.case_no,
        source_intent=intent,
        payload={"marker": payload_marker, "source_version": version},
    )


def _pure_result(repaired_count: int, *, version: int = 1, prior=()):
    projection = _projection(repaired_count)
    trigger = _trigger(version, projection)
    source_intent = replace(trigger.source_intent, projection_sequence=version)
    return trigger, project_historical_baseline(
        source_intent,
        FreshHistoricalBaselineOwnerVectorReadback(projection),
        prior_active_occurrences=prior,
    )


class _State:
    def __init__(self):
        self.deliveries = {}
        self.checkpoints = {}
        self.active = ()
        self.results = {}
        self.readbacks = []
        self.force_mismatch = False
        self.commit_count = 0


class _Repository:
    def __init__(self, state):
        self.state = state

    def query_by_delivery_identity(self, delivery_identity):
        delivery = next(
            (
                item
                for item in self.state.deliveries.values()
                if item.delivery_identity == delivery_identity
            ),
            None,
        )
        return None if delivery is None else _read_model(self.state, delivery)

    def query_latest_by_case(self, case_no):
        candidates = tuple(
            item
            for item in self.state.deliveries.values()
            if item.trigger.source_intent.identity.case_no == case_no
        )
        if not candidates:
            return None
        delivery = candidates[-1]
        return _read_model(self.state, delivery)

    def register_delivery(self, trigger, *, max_attempts):
        existing = self.state.deliveries.get(trigger.trigger_identity)
        if existing is not None:
            return existing.assert_same_trigger(trigger)
        delivery = HistoricalBaselineProjectorDelivery.pending(
            trigger, max_attempts=max_attempts
        )
        self.state.deliveries[trigger.trigger_identity] = delivery
        return delivery

    def load_delivery(self, trigger, *, for_update):
        return self.state.deliveries[trigger.trigger_identity].assert_same_trigger(trigger)

    def save_delivery(self, previous, resulting):
        assert self.state.deliveries[previous.trigger.trigger_identity] == previous
        self.state.deliveries[previous.trigger.trigger_identity] = resulting

    def lock_projection_case(self, trigger):
        return None

    def load_checkpoint(self, trigger, *, for_update):
        return self.state.checkpoints.get(
            (trigger.source_domain, trigger.source_stream, trigger.partition_key)
        )

    def load_active_occurrences(self, trigger, *, for_update):
        return self.state.active

    def next_projection_sequence(self, trigger, *, for_update):
        return len(self.state.results) + 1

    def persist_projection(self, delivery, result, checkpoint):
        self.state.active = result.occurrences
        self.state.results[result.receipt.projector_receipt_identity] = result
        self.state.checkpoints[
            (
                checkpoint.source_domain,
                checkpoint.source_stream,
                checkpoint.partition_key,
            )
        ] = checkpoint

    def read_exact_projection(self, delivery, result):
        receipt = result.receipt
        return HistoricalBaselineExactReadback(
            actual_readback_digest=(
                None if self.state.force_mismatch else receipt.expected_readback_digest
            ),
            emitted_occurrence_set_digest=receipt.emitted_occurrence_set_digest,
            emitted_occurrence_set_count=receipt.emitted_occurrence_set_count,
            active_membership_set_digest=receipt.active_membership_set_digest,
            active_membership_set_count=receipt.active_membership_set_count,
            state_event_set_digest=receipt.expected_readback_digest,
            successor_set_digest=receipt.expected_readback_digest,
            workflow_event_set_digest=receipt.expected_readback_digest,
            current_alert_fingerprint=receipt.expected_readback_digest,
            error_code=(
                "projector_post_commit_readback_mismatch"
                if self.state.force_mismatch
                else None
            ),
        )

    def append_post_commit_readback(self, delivery, result, readback, *, exact):
        self.state.readbacks.append((delivery.delivery_identity, exact))


class _UnitOfWork:
    def __init__(self, state):
        self.repository = _Repository(state)
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def commit(self):
        self.committed = True
        self.repository.state.commit_count += 1


def _worker(state, projections):
    return HistoricalBaselineProjectorWorker(
        unit_of_work_factory=lambda: _UnitOfWork(state),
        owner_vector_reader=lambda unit_of_work, trigger: FreshHistoricalBaselineOwnerVectorReadback(
            projections[trigger.source_version]
        ),
    )


def _read_model(state, delivery):
    trigger = delivery.trigger
    delivery_view = HistoricalBaselineDeliveryView(
        delivery_identity=delivery.delivery_identity,
        source_trigger_identity=trigger.trigger_identity,
        payload_digest=trigger.payload_digest,
        source_kind=trigger.source_kind,
        source_domain=trigger.source_domain,
        source_event_identity=trigger.source_event_identity,
        source_version=trigger.source_version,
        partition_key=trigger.partition_key,
        projection_sequence=delivery.projection_sequence,
        projector_receipt_identity=delivery.projector_receipt_identity,
        status=delivery.status,
        attempt_count=delivery.attempt_count,
        max_attempts=delivery.max_attempts,
        next_attempt_at=delivery.next_attempt_at,
        lease_owner=delivery.lease_owner,
        lease_expires_at=delivery.lease_expires_at,
        last_error_code=delivery.last_error_code,
    )
    if delivery.projector_receipt_identity is None:
        return HistoricalBaselineProjectorReadModel(
            delivery=delivery_view,
            receipt=None,
            active_memberships=(),
            post_commit_readback=None,
            current_alert=None,
        )
    result = state.results[delivery.projector_receipt_identity]
    persisted = result.receipt
    receipt = HistoricalBaselineReceiptView(
        projector_receipt_identity=persisted.projector_receipt_identity,
        source_trigger_identity=persisted.source_intent_key,
        source_trigger_version=trigger.source_version,
        payload_digest=trigger.payload_digest,
        idempotency_key=persisted.idempotency_key,
        case_no=persisted.case_no,
        order_identity=persisted.order_identity,
        catalog_identity=PreviewFingerprint(persisted.catalog_identity),
        catalog_version=persisted.catalog_version,
        whole_vector_fingerprint=persisted.whole_vector_fingerprint,
        whole_vector_count=persisted.whole_vector_count,
        emitted_occurrence_set_digest=persisted.emitted_occurrence_set_digest,
        emitted_occurrence_set_count=persisted.emitted_occurrence_set_count,
        emitted_occurrence_identities=tuple(
            PreviewFingerprint(item.occurrence_identity)
            for item in (*result.occurrences, *result.successor_occurrences)
        ),
        active_membership_set_digest=persisted.active_membership_set_digest,
        active_membership_set_count=persisted.active_membership_set_count,
        umbrella_identity=PreviewFingerprint(persisted.umbrella_identity),
        projection_sequence=persisted.projection_sequence,
        current_alert_fingerprint=persisted.expected_readback_digest,
        expected_readback_digest=persisted.expected_readback_digest,
        result_state=persisted.result_state,
    )
    memberships = tuple(
        HistoricalBaselineMembershipView(
            membership_identity=PreviewFingerprint(item.membership_identity),
            set_ordinal=item.set_ordinal,
            occurrence_identity=PreviewFingerprint(item.occurrence_identity),
        )
        for item in result.umbrella.memberships
    )
    referrals = tuple(
        HistoricalBaselineRepairReferralView(
            step=item.descriptor.step,
            contract_id=item.descriptor.contract_id,
            owner_domain=item.descriptor.owner_domain,
            repair_target=item.descriptor.repair_target,
            repair_capability=item.descriptor.repair_capability,
        )
        for item in result.occurrences
    )
    alert = HistoricalBaselineCurrentAlertView(
        fingerprint=persisted.expected_readback_digest,
        definition_code="HISTORICAL-BASELINE-ROOTS-001",
        definition_version=1,
        source_domain="historical_baseline",
        source_identity=PreviewFingerprint(persisted.umbrella_identity),
        source_version=persisted.projection_sequence,
        predicate_active=result.umbrella.active,
        workflow_status="open" if result.umbrella.active else "resolved",
        workflow_version=persisted.projection_sequence,
        projection_version=persisted.projection_sequence,
        display=HistoricalBaselineAlertDisplayView(
            case_no=persisted.case_no,
            earliest_blocked_step=(
                None if result.terminal_conjunction else result.current_step
            ),
            active_count=persisted.active_membership_set_count,
            repair_referrals=referrals,
            projection_fingerprint=persisted.expected_readback_digest,
        ),
    )
    readback = None
    matching = tuple(
        exact
        for identity, exact in state.readbacks
        if identity == delivery.delivery_identity
    )
    if matching:
        exact = matching[-1]
        readback = HistoricalBaselinePostCommitReadbackView(
            readback_identity=PreviewFingerprint("b" * 64),
            readback_attempt=len(matching),
            expected_readback_digest=persisted.expected_readback_digest,
            actual_readback_digest=(
                persisted.expected_readback_digest if exact else None
            ),
            emitted_occurrence_set_digest=persisted.emitted_occurrence_set_digest,
            emitted_occurrence_set_count=persisted.emitted_occurrence_set_count,
            active_membership_set_digest=persisted.active_membership_set_digest,
            active_membership_set_count=persisted.active_membership_set_count,
            state_event_set_digest=persisted.expected_readback_digest,
            successor_set_digest=persisted.expected_readback_digest,
            workflow_event_set_digest=persisted.expected_readback_digest,
            current_alert_fingerprint=persisted.expected_readback_digest,
            result="exact" if exact else "mismatch",
            error_code=None if exact else "projector_post_commit_readback_mismatch",
        )
    return HistoricalBaselineProjectorReadModel(
        delivery=delivery_view,
        receipt=receipt,
        active_memberships=memberships,
        post_commit_readback=readback,
        current_alert=alert,
    )


def test_trigger_replay_is_exact_and_different_payload_is_integrity_conflict():
    projection = _projection(0)
    trigger = _trigger(1, projection)
    delivery = HistoricalBaselineProjectorDelivery.pending(trigger, max_attempts=5)

    assert delivery.assert_same_trigger(trigger) is delivery
    changed = replace(trigger, payload_digest=PreviewFingerprint("f" * 64))
    with pytest.raises(HistoricalBaselineDeliveryError) as error:
        delivery.assert_same_trigger(changed)
    assert error.value.code == "projector_trigger_integrity_conflict"


def test_source_specific_checkpoint_rejects_gap_stale_and_same_version_conflict():
    projection = _projection(0)
    first = _trigger(1, projection)
    checkpoint = HistoricalBaselineSourceCheckpoint.advance(first, projection_sequence=4)

    validate_checkpoint_progress(checkpoint, _trigger(2, projection))
    with pytest.raises(HistoricalBaselineDeliveryError, match="projector_source_version_gap"):
        validate_checkpoint_progress(checkpoint, _trigger(3, projection))
    with pytest.raises(HistoricalBaselineDeliveryError, match="projector_source_version_stale"):
        validate_checkpoint_progress(checkpoint, _trigger(0, projection))
    conflicting = replace(
        _trigger(1, projection), source_event_identity="orders:repair:other"
    )
    with pytest.raises(
        HistoricalBaselineDeliveryError,
        match="projector_source_version_integrity_conflict",
    ):
        validate_checkpoint_progress(checkpoint, conflicting)


def test_delivery_uses_only_the_six_durable_states_and_exhausts_to_dead_letter():
    projection = _projection(0)
    trigger = _trigger(1, projection)
    now = datetime(2026, 8, 28, tzinfo=timezone.utc)
    pending = HistoricalBaselineProjectorDelivery.pending(trigger, max_attempts=2)
    first = pending.claim(
        now=now, lease_owner="worker:first", lease_duration=timedelta(seconds=60)
    )
    retryable = first.fail(
        error_code="projector_owner_read_transient",
        retryable=True,
        next_attempt_at=now + timedelta(seconds=15),
    )
    second = retryable.claim(
        now=now + timedelta(seconds=15),
        lease_owner="worker:second",
        lease_duration=timedelta(seconds=60),
    )
    dead = second.fail(
        error_code="projector_owner_read_transient",
        retryable=True,
        next_attempt_at=now + timedelta(seconds=30),
    )

    committed = first.committed(
        projection_sequence=1, projector_receipt_identity="a" * 64
    )
    assert committed.processed().status is HistoricalBaselineDeliveryStatus.PROCESSED
    assert retryable.status is HistoricalBaselineDeliveryStatus.RETRYABLE_FAILED
    assert dead.status is HistoricalBaselineDeliveryStatus.DEAD_LETTER
    assert {item.value for item in HistoricalBaselineDeliveryStatus} == {
        "pending",
        "processing",
        "retryable_failed",
        "committed_unverified",
        "processed",
        "dead_letter",
    }


def test_historical_baseline_current_alert_is_registered_without_generic_action():
    from domains.anomalies.registry import (
        AnomalySeverity,
        default_anomaly_registry,
    )

    registry = default_anomaly_registry()
    definition = registry.require("HISTORICAL-BASELINE-ROOTS-001")

    assert definition.source_domain == "historical_baseline"
    assert definition.fingerprint_fields == ("umbrella_identity",)
    assert definition.severity is AnomalySeverity.BLOCKING
    assert definition.available_actions == ()
    assert registry.auto_resolution_contract(definition.code) is not None


def test_worker_records_transient_owner_read_as_retryable_delivery():
    projection = _projection(0)
    trigger = _trigger(1, projection)
    state = _State()
    now = datetime(2026, 8, 28, tzinfo=timezone.utc)
    worker = HistoricalBaselineProjectorWorker(
        unit_of_work_factory=lambda: _UnitOfWork(state),
        owner_vector_reader=lambda _unit_of_work, _trigger: (_ for _ in ()).throw(
            OperationalError(1213, "deadlock")
        ),
    )

    with pytest.raises(OperationalError):
        worker.run(trigger, now=now, lease_owner="worker:transient")

    delivery = state.deliveries[trigger.trigger_identity]
    assert delivery.status is HistoricalBaselineDeliveryStatus.RETRYABLE_FAILED
    assert delivery.last_error_code == "projector_storage_transient"
    assert delivery.next_attempt_at == now + timedelta(seconds=15)
    assert delivery.lease_owner is None


def test_worker_records_non_transient_projection_failure_as_dead_letter():
    projection = _projection(0)
    trigger = _trigger(1, projection)
    state = _State()
    now = datetime(2026, 8, 28, tzinfo=timezone.utc)
    worker = HistoricalBaselineProjectorWorker(
        unit_of_work_factory=lambda: _UnitOfWork(state),
        owner_vector_reader=lambda _unit_of_work, _trigger: (_ for _ in ()).throw(
            HistoricalBaselineDeliveryError("projector_owner_vector_invalid")
        ),
    )

    with pytest.raises(HistoricalBaselineDeliveryError):
        worker.run(trigger, now=now, lease_owner="worker:terminal")

    delivery = state.deliveries[trigger.trigger_identity]
    assert delivery.status is HistoricalBaselineDeliveryStatus.DEAD_LETTER
    assert delivery.last_error_code == "projector_owner_vector_invalid"
    assert delivery.next_attempt_at is None


def test_worker_persists_exact_membership_three_two_one_zero_and_regression_reopens():
    projections = {index + 1: _projection(index) for index in range(4)}
    projections[5] = _projection(3, regression=True)
    state = _State()
    worker = _worker(state, projections)
    counts = []
    states = []

    for version in range(1, 6):
        result = worker.run(
            _trigger(version, projections[version]),
            now=datetime(2026, 8, 28, tzinfo=timezone.utc),
            lease_owner="worker:test",
        )
        receipt = state.results[result.projector_receipt_identity].receipt
        counts.append(receipt.active_membership_set_count)
        states.append(receipt.result_state)
        assert result.status is HistoricalBaselineDeliveryStatus.PROCESSED

    assert counts == [3, 2, 1, 0, 1]
    assert states == ["held_active", "held_active", "held_active", "projected", "held_active"]
    assert len(state.active) == 1


def test_post_commit_mismatch_stays_committed_until_second_exact_reconcile_uow():
    projection = _projection(0)
    state = _State()
    state.force_mismatch = True
    worker = _worker(state, {1: projection})
    trigger = _trigger(1, projection)

    delivery = worker.run(
        trigger,
        now=datetime(2026, 8, 28, tzinfo=timezone.utc),
        lease_owner="worker:test",
    )
    assert delivery.status is HistoricalBaselineDeliveryStatus.COMMITTED_UNVERIFIED
    result = state.results[delivery.projector_receipt_identity]
    assert state.readbacks[-1][1] is False

    state.force_mismatch = False
    reconciled = worker.reconcile(trigger, result)
    assert reconciled.status is HistoricalBaselineDeliveryStatus.PROCESSED
    assert state.readbacks[-1][1] is True


def test_worker_gap_fails_before_claim_and_leaves_projection_state_unchanged():
    first_projection = _projection(0)
    gap_projection = _projection(1)
    state = _State()
    worker = _worker(state, {1: first_projection, 3: gap_projection})
    worker.run(
        _trigger(1, first_projection),
        now=datetime(2026, 8, 28, tzinfo=timezone.utc),
        lease_owner="worker:test",
    )
    active_before = state.active
    results_before = dict(state.results)
    gap = _trigger(3, gap_projection)

    with pytest.raises(HistoricalBaselineDeliveryError, match="projector_source_version_gap"):
        worker.run(
            gap,
            now=datetime(2026, 8, 28, tzinfo=timezone.utc),
            lease_owner="worker:test",
        )

    assert state.active == active_before
    assert state.results == results_before
    assert state.deliveries[gap.trigger_identity].status is HistoricalBaselineDeliveryStatus.PENDING


def test_typed_query_is_read_only_and_identity_reconcile_fails_closed_without_emitted_snapshot():
    projection = _projection(0)
    state = _State()
    state.force_mismatch = True
    worker = _worker(state, {1: projection})
    trigger = _trigger(1, projection)
    committed = worker.run(
        trigger,
        now=datetime(2026, 8, 28, tzinfo=timezone.utc),
        lease_owner="worker:test",
    )
    commits_before_query = state.commit_count

    by_identity = worker.query_by_delivery_identity(committed.delivery_identity)
    by_case = worker.query_latest_by_case(_IDENTITY.case_no)
    outcome = worker.reconcile_by_delivery_identity(committed.delivery_identity)

    assert by_identity == by_case
    assert isinstance(by_identity, HistoricalBaselineProjectorReadModel)
    assert by_identity.receipt is not None
    assert by_identity.receipt.active_membership_set_count == 3
    assert len(by_identity.active_memberships) == 3
    assert by_identity.post_commit_readback is not None
    assert by_identity.post_commit_readback.result == "mismatch"
    assert by_identity.current_alert is not None
    assert by_identity.current_alert.display.active_count == 3
    assert all(
        isinstance(item, HistoricalBaselineRepairReferralView)
        for item in by_identity.current_alert.display.repair_referrals
    )
    assert outcome.status == "outcome_unknown"
    assert outcome.reason_code == "projector_emitted_occurrence_snapshot_not_persisted"
    assert outcome.referral == "retry_original_trigger_reconcile"
    assert state.commit_count == commits_before_query


def test_identity_reconcile_reports_processed_or_not_ready_without_mutation():
    projection = _projection(0)
    state = _State()
    worker = _worker(state, {1: projection, 2: projection})
    processed = worker.run(
        _trigger(1, projection),
        now=datetime(2026, 8, 28, tzinfo=timezone.utc),
        lease_owner="worker:test",
    )
    pending = worker.accept(_trigger(2, projection))
    commits_before_query = state.commit_count

    processed_outcome = worker.reconcile_by_delivery_identity(
        processed.delivery_identity
    )
    pending_outcome = worker.reconcile_by_delivery_identity(pending.delivery_identity)
    latest = worker.query_latest_by_case(_IDENTITY.case_no)

    assert processed_outcome.status == "processed"
    assert processed_outcome.referral == "none"
    assert pending_outcome.status == "not_ready"
    assert pending_outcome.referral == "wait_for_projector_commit"
    assert latest is not None
    assert latest.delivery.delivery_identity == pending.delivery_identity
    assert latest.receipt is None
    assert state.commit_count == commits_before_query


def test_mysql_typed_read_model_query_reads_zero_membership_without_commit():
    projection = _projection(3)
    state = _State()
    worker = _worker(state, {1: projection})
    trigger = _trigger(1, projection)
    delivery = worker.run(
        trigger,
        now=datetime(2026, 8, 28, tzinfo=timezone.utc),
        lease_owner="worker:test",
    )
    result = state.results[delivery.projector_receipt_identity]
    receipt = result.receipt
    alert_fingerprint = "c" * 64
    main_row = {
        "delivery_identity": delivery.delivery_identity,
        "delivery_source_trigger_identity": trigger.trigger_identity,
        "delivery_payload_digest": trigger.payload_digest.value,
        "delivery_source_kind": trigger.source_kind,
        "delivery_source_domain": trigger.source_domain,
        "delivery_source_event_identity": trigger.source_event_identity,
        "delivery_source_version": trigger.source_version,
        "delivery_partition_key": trigger.partition_key,
        "delivery_projection_sequence": delivery.projection_sequence,
        "delivery_status": delivery.status.value,
        "delivery_attempt_count": delivery.attempt_count,
        "delivery_max_attempts": delivery.max_attempts,
        "delivery_next_attempt_at": None,
        "delivery_lease_owner": None,
        "delivery_lease_expires_at": None,
        "delivery_last_error_code": None,
        "projector_receipt_identity": receipt.projector_receipt_identity,
        "receipt_source_trigger_identity": trigger.trigger_identity,
        "receipt_source_trigger_version": trigger.source_version,
        "receipt_payload_digest": trigger.payload_digest.value,
        "receipt_idempotency_key": receipt.idempotency_key,
        "receipt_case_no": receipt.case_no,
        "receipt_order_identity": receipt.order_identity,
        "receipt_catalog_identity": receipt.catalog_identity,
        "receipt_catalog_version": receipt.catalog_version,
        "receipt_whole_vector_fingerprint": receipt.whole_vector_fingerprint.value,
        "receipt_whole_vector_count": receipt.whole_vector_count,
        "receipt_emitted_occurrence_set_digest": receipt.emitted_occurrence_set_digest.value,
        "receipt_emitted_occurrence_set_count": receipt.emitted_occurrence_set_count,
        "receipt_emitted_occurrence_identities": json.dumps(
            [item.occurrence_identity for item in result.occurrences]
        ),
        "receipt_active_membership_set_digest": receipt.active_membership_set_digest.value,
        "receipt_active_membership_set_count": 0,
        "receipt_umbrella_identity": receipt.umbrella_identity,
        "receipt_projection_sequence": receipt.projection_sequence,
        "receipt_current_alert_fingerprint": alert_fingerprint,
        "receipt_expected_readback_digest": receipt.expected_readback_digest.value,
        "receipt_result_state": receipt.result_state,
    }
    readback_row = {
        "readback_identity": "d" * 64,
        "readback_attempt": 1,
        "expected_readback_digest": receipt.expected_readback_digest.value,
        "actual_readback_digest": receipt.expected_readback_digest.value,
        "actual_emitted_occurrence_set_digest": receipt.emitted_occurrence_set_digest.value,
        "actual_emitted_occurrence_set_count": receipt.emitted_occurrence_set_count,
        "actual_active_membership_set_digest": receipt.active_membership_set_digest.value,
        "actual_active_membership_set_count": 0,
        "actual_state_event_set_digest": "e" * 64,
        "actual_successor_set_digest": "f" * 64,
        "actual_workflow_event_set_digest": "1" * 64,
        "actual_current_alert_fingerprint": alert_fingerprint,
        "readback_result": "exact",
        "error_code": None,
    }
    alert_row = {
        "fingerprint": alert_fingerprint,
        "definition_code": "HISTORICAL-BASELINE-ROOTS-001",
        "definition_version": 1,
        "source_domain": "historical_baseline",
        "source_identity": receipt.umbrella_identity,
        "source_version": receipt.projection_sequence,
        "predicate_active": 0,
        "workflow_status": "resolved",
        "workflow_version": 1,
        "projection_version": 1,
        "display_snapshot": json.dumps(
            {
                "case_no": receipt.case_no,
                "earliest_blocked_step": None,
                "active_count": 0,
                "repair_referrals": [],
                "projection_fingerprint": receipt.expected_readback_digest.value,
            }
        ),
    }
    connection = _ReadConnection(
        [([main_row], "one"), ([], "all"), ([readback_row], "one"), ([alert_row], "one")]
    )

    model = MySqlHistoricalBaselineProjectorRepository(
        connection
    ).query_by_delivery_identity(delivery.delivery_identity)

    assert isinstance(model, HistoricalBaselineProjectorReadModel)
    assert model.receipt is not None
    assert model.receipt.active_membership_set_count == 0
    assert model.active_memberships == ()
    assert model.post_commit_readback is not None
    assert model.post_commit_readback.result == "exact"
    assert model.current_alert is not None
    assert model.current_alert.display.repair_referrals == ()
    assert connection.commit_calls == 0


def test_mysql_case_query_includes_latest_no_receipt_delivery_without_commit():
    projection = _projection(0)
    trigger = _trigger(1, projection)
    delivery = HistoricalBaselineProjectorDelivery.pending(trigger, max_attempts=5)
    row = {
        "delivery_identity": delivery.delivery_identity,
        "delivery_source_trigger_identity": trigger.trigger_identity,
        "delivery_payload_digest": trigger.payload_digest.value,
        "delivery_source_kind": trigger.source_kind,
        "delivery_source_domain": trigger.source_domain,
        "delivery_source_event_identity": trigger.source_event_identity,
        "delivery_source_version": trigger.source_version,
        "delivery_partition_key": trigger.partition_key,
        "delivery_projection_sequence": None,
        "delivery_status": delivery.status.value,
        "delivery_attempt_count": 0,
        "delivery_max_attempts": 5,
        "delivery_next_attempt_at": None,
        "delivery_lease_owner": None,
        "delivery_lease_expires_at": None,
        "delivery_last_error_code": None,
        "projector_receipt_identity": None,
    }
    connection = _ReadConnection([([row], "one")])

    model = MySqlHistoricalBaselineProjectorRepository(
        connection
    ).query_latest_by_case(_IDENTITY.case_no)

    assert model is not None
    assert model.delivery.status is HistoricalBaselineDeliveryStatus.PENDING
    assert model.receipt is None
    sql, parameters = connection.executed[0]
    assert "receipt.id IS NULL AND delivery.partition_key=%s" in sql
    assert parameters == (_IDENTITY.case_no, _IDENTITY.case_no)
    assert connection.commit_calls == 0


def test_existing_occurrence_replay_requires_the_full_immutable_tuple():
    _trigger_value, result = _pure_result(0)
    occurrence = result.occurrences[0]
    descriptor = occurrence.descriptor
    observation = occurrence.observation
    row = {
        "id": 19,
        "case_no": occurrence.case_no,
        "order_identity": occurrence.order_identity,
        "baseline_event_id": 7,
        "baseline_receipt_id": 8,
        "catalog_identity": occurrence.catalog_identity,
        "catalog_version": occurrence.catalog_version,
        "descriptor_identity": occurrence.descriptor_identity,
        "contract_id": descriptor.contract_id,
        "contract_version": descriptor.contract_version,
        "step_number": descriptor.step,
        "owner_domain": descriptor.owner_domain,
        "root_identity_kind": descriptor.root_identity_kind,
        "root_identity_path": descriptor.root_identity_path,
        "terminal_predicate_id": descriptor.terminal_predicate_id,
        "terminal_predicate_version": descriptor.terminal_predicate_version,
        "repair_target": descriptor.repair_target,
        "repair_capability": descriptor.repair_capability,
        "observation_variant": "available" if observation.available else "unavailable",
        "observation_identity": occurrence.observation_identity,
        "observed_root_identity": observation.root_identity,
        "owner_source_event_identity": observation.source_event_identity,
        "owner_source_version": observation.source_version,
        "terminal_result": observation.terminal_result,
        "unavailable_code": observation.unavailable_code,
        "owner_binding_fingerprint": occurrence.owner_binding_fingerprint.value,
    }
    connection = _ReadConnection([([dict(row, owner_domain="wrong-owner")], "one")])
    cursor = connection.cursor()

    with pytest.raises(
        HistoricalBaselineDeliveryError,
        match="projector_occurrence_integrity_conflict",
    ):
        projector_repository._ensure_occurrence(cursor, occurrence, (7, 8, 9))


def test_successor_replay_and_predecessor_state_require_exact_canonical_vectors():
    _first_trigger, first = _pure_result(0)
    second_trigger, second = _pure_result(
        1, version=2, prior=first.occurrences
    )
    successor = second.successors[0]

    def state_row_for(
        occurrence,
        *,
        state,
        version,
        owner_event_identity,
        owner_source_version,
        owner_binding_fingerprint,
        prior_id=None,
    ):
        descriptor = occurrence.descriptor
        return {
            "occurrence_identity": occurrence.occurrence_identity,
            "state_event_identity": projector_repository._state_identity(
                occurrence.occurrence_identity, state, version
            ),
            "prior_state_event_id": prior_id,
            "state": state,
            "owner_event_identity": owner_event_identity,
            "owner_source_version": owner_source_version,
            "expected_state_version": version - 1,
            "resulting_state_version": version,
            "case_no": occurrence.case_no,
            "order_identity": occurrence.order_identity,
            "baseline_event_id": 7,
            "baseline_event_identity": occurrence.baseline_event_identity,
            "catalog_identity": occurrence.catalog_identity,
            "catalog_version": occurrence.catalog_version,
            "descriptor_identity": occurrence.descriptor_identity,
            "contract_id": descriptor.contract_id,
            "contract_version": descriptor.contract_version,
            "terminal_predicate_id": descriptor.terminal_predicate_id,
            "terminal_predicate_version": descriptor.terminal_predicate_version,
            "owner_binding_fingerprint": owner_binding_fingerprint,
            "fresh_readback_fingerprint": owner_binding_fingerprint,
            "prior_id": prior_id,
            "prior_resulting_state_version": None if prior_id is None else version - 1,
            "occurrence_case_no": occurrence.case_no,
            "occurrence_order_identity": occurrence.order_identity,
            "occurrence_baseline_event_id": 7,
            "occurrence_catalog_identity": occurrence.catalog_identity,
            "occurrence_catalog_version": occurrence.catalog_version,
            "occurrence_descriptor_identity": occurrence.descriptor_identity,
            "occurrence_contract_id": descriptor.contract_id,
            "occurrence_contract_version": descriptor.contract_version,
            "occurrence_terminal_predicate_id": descriptor.terminal_predicate_id,
            "occurrence_terminal_predicate_version": descriptor.terminal_predicate_version,
            "occurrence_owner_binding_fingerprint": owner_binding_fingerprint,
        }

    row = {
        "successor_relation_identity": successor.successor_relation_identity,
        "predecessor_occurrence_identity": successor.predecessor_occurrence_identity,
        "successor_occurrence_identity": successor.successor_occurrence_identity,
        "case_no": successor.case_no,
        "order_identity": successor.order_identity,
        "baseline_event_identity": successor.baseline_event_identity,
        "catalog_identity": successor.catalog_identity,
        "catalog_version": successor.catalog_version,
        "descriptor_identity": successor.descriptor_identity,
        "contract_id": successor.contract_id,
        "contract_version": successor.contract_version,
        "owner_event_identity": successor.owner_event_identity,
        "prior_owner_source_version": successor.prior_owner_source_version,
        "new_owner_source_version": successor.new_owner_source_version,
        "terminal_predicate_id": successor.terminal_predicate_id,
        "terminal_predicate_version": successor.terminal_predicate_version,
        "fresh_readback_fingerprint": successor.fresh_readback_fingerprint.value,
    }
    assert projector_repository._successor_vector_matches((row,), second)
    assert not projector_repository._successor_vector_matches(
        (dict(row, new_owner_source_version=999),), second
    )

    predecessor = next(
        item
        for item in first.occurrences
        if item.occurrence_identity == successor.predecessor_occurrence_identity
    )
    state_row = state_row_for(
        predecessor,
        state="superseded",
        version=2,
        owner_event_identity=second_trigger.source_event_identity,
        owner_source_version=second_trigger.source_version,
        owner_binding_fingerprint=second_trigger.source_intent.expected_owner_binding_fingerprint.value,
        prior_id=101,
    )
    remaining = tuple(
        state_row_for(
            item,
            state="opened",
            version=1,
            owner_event_identity=item.observation.source_event_identity,
            owner_source_version=item.observation.source_version,
            owner_binding_fingerprint=item.owner_binding_fingerprint.value,
        )
        for item in second.occurrences
    )
    successor_occurrence = next(
        item
        for item in second.successor_occurrences
        if item.occurrence_identity == successor.successor_occurrence_identity
    )
    successor_state = state_row_for(
        successor_occurrence,
        state="resolved",
        version=1,
        owner_event_identity=successor.owner_event_identity,
        owner_source_version=successor.new_owner_source_version,
        owner_binding_fingerprint=successor.fresh_readback_fingerprint.value,
    )
    rows = tuple(
        sorted(
            (*remaining, successor_state, state_row),
            key=lambda item: item["occurrence_identity"],
        )
    )
    assert projector_repository._state_vector_matches(
        rows, second, second_trigger
    )
    resolved_predecessor = tuple(
        dict(item, state="resolved")
        if item["occurrence_identity"] == successor.predecessor_occurrence_identity
        else item
        for item in rows
    )
    assert not projector_repository._state_vector_matches(
        resolved_predecessor, second, second_trigger
    )


def test_receipt_and_membership_exactness_reject_extra_or_changed_rows():
    trigger, result = _pure_result(0)
    delivery = HistoricalBaselineProjectorDelivery.pending(trigger, max_attempts=5)
    receipt = result.receipt
    emitted = tuple(
        sorted(
            item.occurrence_identity
            for item in (*result.occurrences, *result.successor_occurrences)
        )
    )
    row = {
        "source_trigger_identity": trigger.trigger_identity,
        "source_trigger_version": trigger.source_version,
        "payload_digest": trigger.payload_digest.value,
        "idempotency_key": receipt.idempotency_key,
        "baseline_event_identity": receipt.baseline_event_identity,
        "baseline_receipt_identity": receipt.baseline_receipt_identity,
        "baseline_outbox_identity": receipt.baseline_outbox_identity,
        "case_no": receipt.case_no,
        "order_identity": receipt.order_identity,
        "catalog_identity": receipt.catalog_identity,
        "catalog_version": receipt.catalog_version,
        "whole_vector_fingerprint": receipt.whole_vector_fingerprint.value,
        "whole_vector_count": receipt.whole_vector_count,
        "emitted_occurrence_set_digest": receipt.emitted_occurrence_set_digest.value,
        "emitted_occurrence_set_count": receipt.emitted_occurrence_set_count,
        "emitted_occurrence_identities": json.dumps(emitted),
        "active_membership_set_digest": receipt.active_membership_set_digest.value,
        "active_membership_set_count": receipt.active_membership_set_count,
        "umbrella_identity": receipt.umbrella_identity,
        "projection_sequence": receipt.projection_sequence,
        "current_alert_fingerprint": projector_repository._alert_fingerprint(
            receipt.umbrella_identity
        ).value,
        "expected_readback_digest": receipt.expected_readback_digest.value,
        "result_state": receipt.result_state,
    }
    assert projector_repository._stored_receipt_matches(row, delivery, result)
    assert not projector_repository._stored_receipt_matches(
        dict(row, whole_vector_count=receipt.whole_vector_count + 1),
        delivery,
        result,
    )
    assert not projector_repository._stored_receipt_matches(
        dict(row, emitted_occurrence_identities=json.dumps((*emitted, "f" * 64))),
        delivery,
        result,
    )

    memberships = tuple(
        {
            "membership_identity": item.membership_identity,
            "set_ordinal": item.set_ordinal,
            "occurrence_identity": item.occurrence_identity,
        }
        for item in result.umbrella.memberships
    )
    assert projector_repository._membership_vector_matches(memberships, result)
    assert not projector_repository._membership_vector_matches(
        (*memberships, dict(memberships[0], set_ordinal=99)), result
    )


def test_typed_read_model_fails_closed_when_committed_receipt_or_alert_is_missing():
    projection = _projection(0)
    state = _State()
    worker = _worker(state, {1: projection})
    delivery = worker.run(
        _trigger(1, projection),
        now=datetime(2026, 8, 28, tzinfo=timezone.utc),
        lease_owner="worker:test",
    )
    model = _read_model(state, delivery)
    with pytest.raises(
        projector_repository.HistoricalBaselineProjectorQueryError,
        match="projector_read_model_current_alert_missing",
    ):
        projector_repository._validate_typed_read_model(
            replace(model, current_alert=None)
        )

    receipt_missing = HistoricalBaselineProjectorReadModel(
        delivery=replace(
            model.delivery,
            status=HistoricalBaselineDeliveryStatus.PROCESSED,
        ),
        receipt=None,
        active_memberships=(),
        post_commit_readback=None,
        current_alert=None,
    )
    with pytest.raises(
        projector_repository.HistoricalBaselineProjectorQueryError,
        match="projector_read_model_receipt_missing",
    ):
        projector_repository._validate_typed_read_model(receipt_missing)


def test_initial_zero_active_projection_fails_closed_without_fabricating_resolved_alert():
    _trigger_value, result = _pure_result(3)
    connection = _ReadConnection([([], "one")])
    cursor = connection.cursor()

    with pytest.raises(
        HistoricalBaselineDeliveryError,
        match="projector_inactive_initial_projection_has_no_current_alert",
    ):
        projector_repository._upsert_current_alert(cursor, result)

    assert len(connection.executed) == 1
    assert connection.executed[0][0].startswith("SELECT fingerprint")


class _ReadCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []
        self.mode = "one"

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def execute(self, sql, parameters):
        self.connection.executed.append((sql, parameters))
        self.rows, self.mode = self.connection.responses.pop(0)

    def fetchone(self):
        return None if not self.rows else self.rows[0]

    def fetchall(self):
        return tuple(self.rows)


class _ReadConnection:
    def __init__(self, responses):
        self.responses = list(responses)
        self.executed = []
        self.commit_calls = 0

    def cursor(self):
        return _ReadCursor(self)

    def commit(self):
        self.commit_calls += 1
