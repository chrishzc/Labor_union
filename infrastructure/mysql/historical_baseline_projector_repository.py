"""MySQL persistence adapter for historical-baseline projector v2."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
from typing import Iterator, Mapping

from domains.orders.historical_operational_baseline import (
    HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2,
    HistoricalBaselineOwnerObservation,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from subsystems.anomalies.historical_baseline_projection import (
    HistoricalBaselineOccurrenceProjection,
    HistoricalBaselineProjectionResult,
)

from infrastructure.mysql.historical_baseline_projector_checkpoint import (
    HistoricalBaselineSourceCheckpoint,
)
from infrastructure.mysql.historical_baseline_projector_delivery import (
    HistoricalBaselineDeliveryError,
    HistoricalBaselineDeliveryStatus,
    HistoricalBaselineProjectorDelivery,
)
from infrastructure.mysql.historical_baseline_projector_worker import (
    HistoricalBaselineExactReadback,
)
from infrastructure.mysql.historical_baseline_projector_read_model import (
    HistoricalBaselineAlertDisplayView,
    HistoricalBaselineCurrentAlertView,
    HistoricalBaselineDeliveryView,
    HistoricalBaselineMembershipView,
    HistoricalBaselinePostCommitReadbackView,
    HistoricalBaselineProjectorQueryError,
    HistoricalBaselineProjectorReadModel,
    HistoricalBaselineReceiptView,
    HistoricalBaselineRepairReferralView,
)


_DEFINITION_CODE = "HISTORICAL-BASELINE-ROOTS-001"
_SOURCE_DOMAIN = "historical_baseline"


class MySqlHistoricalBaselineProjectorUnitOfWork(MySqlUnitOfWork):
    def __init__(self, connection) -> None:
        super().__init__(connection)
        self.connection = connection
        self.repository = MySqlHistoricalBaselineProjectorRepository(connection)


class MySqlHistoricalBaselineProjectorRepository:
    """Issue SQL only; the surrounding unit of work owns commit and rollback."""

    def __init__(self, connection) -> None:
        self._connection = connection

    def query_by_delivery_identity(
        self, delivery_identity: str
    ) -> HistoricalBaselineProjectorReadModel | None:
        return self._query_read_model(
            "delivery.delivery_identity=%s", (delivery_identity,)
        )

    def query_latest_by_case(
        self, case_no: str
    ) -> HistoricalBaselineProjectorReadModel | None:
        return self._query_read_model(
            "(receipt.case_no=%s OR (receipt.id IS NULL AND delivery.partition_key=%s))",
            (case_no, case_no),
            order_by="delivery.id DESC",
        )

    def _query_read_model(self, predicate, parameters, *, order_by="delivery.id DESC"):
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _PROJECTOR_READ_MODEL_SELECT_SQL.format(
                    predicate=predicate, order_by=order_by
                ),
                parameters,
            )
            row = cursor.fetchone()
            if row is None:
                return None
            delivery = _delivery_view(row)
            receipt = _receipt_view(row)
            if receipt is None:
                model = HistoricalBaselineProjectorReadModel(
                    delivery=delivery,
                    receipt=None,
                    active_memberships=(),
                    post_commit_readback=None,
                    current_alert=None,
                )
                _validate_typed_read_model(model)
                return model
            cursor.execute(
                _READ_MODEL_MEMBERSHIP_SELECT_SQL,
                (receipt.projector_receipt_identity,),
            )
            memberships = tuple(_membership_view(item) for item in cursor.fetchall())
            cursor.execute(
                _READ_MODEL_READBACK_SELECT_SQL,
                (receipt.projector_receipt_identity,),
            )
            readback_row = cursor.fetchone()
            cursor.execute(
                _READ_MODEL_ALERT_SELECT_SQL,
                (receipt.current_alert_fingerprint.value,),
            )
            alert_row = cursor.fetchone()
        model = HistoricalBaselineProjectorReadModel(
            delivery=delivery,
            receipt=receipt,
            active_memberships=memberships,
            post_commit_readback=(
                None
                if readback_row is None
                else _post_commit_readback_view(readback_row)
            ),
            current_alert=(
                None if alert_row is None else _current_alert_view(alert_row)
            ),
        )
        _validate_typed_read_model(model)
        return model

    def register_delivery(self, trigger, *, max_attempts):
        if trigger.partition_key != trigger.source_intent.identity.case_no:
            raise HistoricalBaselineDeliveryError(
                "projector_delivery_case_partition_mismatch"
            )
        existing = self._select_delivery(trigger, for_update=True)
        if existing is not None:
            return existing.assert_same_trigger(trigger)
        delivery = HistoricalBaselineProjectorDelivery.pending(
            trigger, max_attempts=max_attempts
        )
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _DELIVERY_INSERT_SQL,
                (
                    delivery.delivery_identity,
                    trigger.trigger_identity,
                    trigger.payload_digest.value,
                    trigger.source_kind,
                    trigger.source_domain,
                    trigger.source_event_identity,
                    trigger.source_version,
                    trigger.partition_key,
                    delivery.status.value,
                    delivery.attempt_count,
                    delivery.max_attempts,
                ),
            )
        return delivery

    def load_delivery(self, trigger, *, for_update):
        delivery = self._select_delivery(trigger, for_update=for_update)
        if delivery is None:
            raise HistoricalBaselineDeliveryError("projector_delivery_not_found")
        return delivery.assert_same_trigger(trigger)

    def _select_delivery(self, trigger, *, for_update):
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(_DELIVERY_SELECT_SQL + suffix, (trigger.trigger_identity,))
            row = cursor.fetchone()
        if row is None:
            return None
        if str(row["payload_digest"]) != trigger.payload_digest.value:
            raise HistoricalBaselineDeliveryError(
                "projector_trigger_integrity_conflict"
            )
        stored_trigger = (
            str(row["source_kind"]),
            str(row["source_domain"]),
            str(row["source_event_identity"]),
            int(row["source_version"]),
            str(row["partition_key"]),
        )
        supplied_trigger = (
            trigger.source_kind,
            trigger.source_domain,
            trigger.source_event_identity,
            trigger.source_version,
            trigger.partition_key,
        )
        if stored_trigger != supplied_trigger:
            raise HistoricalBaselineDeliveryError(
                "projector_trigger_integrity_conflict"
            )
        return HistoricalBaselineProjectorDelivery(
            delivery_identity=str(row["delivery_identity"]),
            trigger=trigger,
            status=HistoricalBaselineDeliveryStatus(str(row["delivery_status"])),
            attempt_count=int(row["attempt_count"]),
            max_attempts=int(row["max_attempts"]),
            projection_sequence=_optional_int(row["projection_sequence"]),
            projector_receipt_identity=(
                None
                if row["projector_receipt_identity"] is None
                else str(row["projector_receipt_identity"])
            ),
            next_attempt_at=row["next_attempt_at"],
            lease_owner=(None if row["lease_owner"] is None else str(row["lease_owner"])),
            lease_expires_at=row["lease_expires_at"],
            last_error_code=(
                None if row["last_error_code"] is None else str(row["last_error_code"])
            ),
        )

    def save_delivery(self, previous, resulting):
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _DELIVERY_UPDATE_SQL,
                (
                    resulting.projection_sequence,
                    _receipt_database_id(cursor, resulting.projector_receipt_identity),
                    resulting.status.value,
                    resulting.attempt_count,
                    resulting.next_attempt_at,
                    resulting.lease_owner,
                    resulting.lease_expires_at,
                    resulting.last_error_code,
                    previous.delivery_identity,
                    previous.status.value,
                    previous.attempt_count,
                ),
            )
            if int(cursor.rowcount) != 1:
                raise HistoricalBaselineDeliveryError("projector_delivery_cas_conflict")

    def lock_projection_case(self, trigger):
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT case_no FROM orders WHERE case_no=%s FOR UPDATE",
                (trigger.source_intent.identity.case_no,),
            )
            if cursor.fetchone() is None:
                raise HistoricalBaselineDeliveryError("projector_case_not_found")

    def load_checkpoint(self, trigger, *, for_update):
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _CHECKPOINT_SELECT_SQL + suffix,
                (trigger.source_domain, trigger.source_stream, trigger.partition_key),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return HistoricalBaselineSourceCheckpoint(
            checkpoint_identity=str(row["checkpoint_identity"]),
            source_domain=str(row["source_domain"]),
            source_stream=str(row["source_stream"]),
            partition_key=str(row["partition_key"]),
            last_source_event_identity=str(row["last_source_event_identity"]),
            last_source_version=int(row["last_source_version"]),
            last_projection_sequence=int(row["last_projection_sequence"]),
            checkpoint_fingerprint=PreviewFingerprint(
                str(row["checkpoint_fingerprint"])
            ),
        )

    def load_active_occurrences(self, trigger, *, for_update):
        suffix = " FOR UPDATE" if for_update else ""
        source = trigger.source_intent
        with _cursor(self._connection) as cursor:
            cursor.execute(
                _ACTIVE_OCCURRENCES_SELECT_SQL + suffix,
                (
                    source.identity.case_no,
                    source.baseline_event_identity,
                    source.catalog_identity.value,
                    source.catalog_version,
                ),
            )
            rows = cursor.fetchall()
        return tuple(_occurrence_from_row(row) for row in rows)

    def next_projection_sequence(self, trigger, *, for_update):
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT source_version FROM anomaly_current_alerts "
                "WHERE definition_code=%s AND source_identity IN ("
                "SELECT umbrella_identity FROM historical_baseline_v2_projector_receipts "
                "WHERE case_no=%s) ORDER BY source_version DESC LIMIT 1" + suffix,
                (_DEFINITION_CODE, trigger.source_intent.identity.case_no),
            )
            row = cursor.fetchone()
        return 1 if row is None else int(row["source_version"]) + 1

    def persist_projection(self, delivery, result, checkpoint):
        trigger = delivery.trigger
        with _cursor(self._connection) as cursor:
            baseline_ids = _baseline_ids(cursor, trigger)
            occurrence_ids: dict[str, int] = {}
            for occurrence in (*result.occurrences, *result.successor_occurrences):
                occurrence_id, inserted = _ensure_occurrence(
                    cursor, occurrence, baseline_ids
                )
                occurrence_ids[occurrence.occurrence_identity] = occurrence_id
                if inserted:
                    _append_initial_state(cursor, occurrence_id, occurrence, trigger)
            superseded_predecessors = {
                item.predecessor_occurrence_identity for item in result.successors
            }
            for prior_identity in result.inactive_predecessor_identities:
                prior_id = _occurrence_database_id(cursor, prior_identity)
                _append_inactive_state(
                    cursor,
                    prior_id,
                    prior_identity,
                    trigger,
                    state=(
                        "superseded"
                        if prior_identity in superseded_predecessors
                        else "resolved"
                    ),
                )
            for successor in result.successors:
                _ensure_successor(cursor, successor, occurrence_ids)

            alert = _upsert_current_alert(cursor, result)
            receipt_id = _insert_receipt(
                cursor, trigger, result, baseline_ids, alert["fingerprint"]
            )
            for membership in result.umbrella.memberships:
                cursor.execute(
                    _MEMBERSHIP_INSERT_SQL,
                    (
                        membership.membership_identity,
                        receipt_id,
                        result.umbrella.umbrella_identity,
                        membership.set_ordinal,
                        occurrence_ids[membership.occurrence_identity],
                        result.receipt.case_no,
                        result.receipt.order_identity,
                        baseline_ids[0],
                        result.receipt.catalog_identity,
                        result.receipt.catalog_version,
                        result.receipt.projection_sequence,
                    ),
                )
            _save_checkpoint(cursor, checkpoint)

    def read_exact_projection(self, delivery, result):
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT receipt.source_trigger_identity,receipt.source_trigger_version,"
                "receipt.payload_digest,receipt.idempotency_key,event.baseline_event_identity,"
                "baseline_receipt.receipt_identity AS baseline_receipt_identity,"
                "outbox.intent_key AS baseline_outbox_identity,receipt.case_no,receipt.order_identity,"
                "receipt.catalog_identity,receipt.catalog_version,receipt.whole_vector_fingerprint,"
                "receipt.whole_vector_count,receipt.emitted_occurrence_set_digest,"
                "receipt.emitted_occurrence_set_count,receipt.emitted_occurrence_identities,"
                "receipt.active_membership_set_digest,receipt.active_membership_set_count,"
                "receipt.umbrella_identity,receipt.projection_sequence,"
                "receipt.current_alert_fingerprint,receipt.expected_readback_digest,receipt.result_state "
                "FROM historical_baseline_v2_projector_receipts AS receipt "
                "INNER JOIN historical_order_operational_baseline_events AS event "
                "ON event.id=receipt.baseline_event_id "
                "INNER JOIN historical_order_operational_baseline_receipts AS baseline_receipt "
                "ON baseline_receipt.id=receipt.baseline_receipt_id "
                "INNER JOIN historical_order_operational_baseline_outbox AS outbox "
                "ON outbox.id=receipt.baseline_outbox_id "
                "WHERE receipt.projector_receipt_identity=%s",
                (result.receipt.projector_receipt_identity,),
            )
            stored_receipt = cursor.fetchone()
            stored_emitted = (
                ()
                if stored_receipt is None
                else _json_array(stored_receipt["emitted_occurrence_identities"])
            )
            emitted = _existing_identities(
                cursor,
                "historical_baseline_occurrences",
                "occurrence_identity",
                stored_emitted,
            )
            cursor.execute(
                "SELECT member.membership_identity,member.set_ordinal,"
                "occurrence.occurrence_identity "
                "FROM historical_baseline_v2_active_membership_snapshots AS member "
                "INNER JOIN historical_baseline_v2_projector_receipts AS receipt "
                "ON receipt.id=member.projector_receipt_id "
                "INNER JOIN historical_baseline_occurrences AS occurrence "
                "ON occurrence.id=member.occurrence_id "
                "WHERE receipt.projector_receipt_identity=%s "
                "ORDER BY member.set_ordinal",
                (result.receipt.projector_receipt_identity,),
            )
            membership_rows = tuple(cursor.fetchall())
            active = tuple(
                str(row["occurrence_identity"]) for row in membership_rows
            )
            state_rows = _latest_state_rows(cursor, result)
            successor_rows = _successor_rows(cursor, result)
            alert_fingerprint = _alert_fingerprint(result.umbrella.umbrella_identity)
            cursor.execute(
                "SELECT fingerprint,definition_code,definition_version,source_domain,"
                "source_identity,source_version,predicate_active,workflow_status,workflow_version,"
                "projection_version,claimed_by,claimed_at,resolved_by,resolved_at,display_snapshot "
                "FROM anomaly_current_alerts WHERE fingerprint=%s",
                (alert_fingerprint.value,),
            )
            alert = cursor.fetchone()
            workflow_rows = _workflow_rows(cursor, alert_fingerprint)

        emitted_digest = _identity_set_digest(emitted)
        active_digest = _identity_set_digest(active)
        state_ids = tuple(str(row["state_event_identity"]) for row in state_rows)
        successor_ids = tuple(
            str(row["successor_relation_identity"]) for row in successor_rows
        )
        workflow_ids = tuple(str(row["idempotency_key"]) for row in workflow_rows)
        objects_exact = (
            len(emitted) == result.receipt.emitted_occurrence_set_count
            and emitted == stored_emitted
            and emitted_digest == result.receipt.emitted_occurrence_set_digest
            and len(active) == result.receipt.active_membership_set_count
            and active_digest == result.receipt.active_membership_set_digest
            and _membership_vector_matches(membership_rows, result)
            and _state_vector_matches(state_rows, result, delivery.trigger)
            and _successor_vector_matches(successor_rows, result)
            and _workflow_vector_matches(workflow_rows, alert)
            and _stored_receipt_matches(stored_receipt, delivery, result)
            and _current_alert_matches(
                alert,
                result,
                alert_fingerprint,
                workflow_rows=workflow_rows,
            )
        )
        return HistoricalBaselineExactReadback(
            actual_readback_digest=(
                result.receipt.expected_readback_digest if objects_exact else None
            ),
            emitted_occurrence_set_digest=emitted_digest,
            emitted_occurrence_set_count=len(emitted),
            active_membership_set_digest=active_digest,
            active_membership_set_count=len(active),
            state_event_set_digest=_identity_set_digest(state_ids),
            successor_set_digest=_identity_set_digest(successor_ids),
            workflow_event_set_digest=_identity_set_digest(workflow_ids),
            current_alert_fingerprint=(
                alert_fingerprint if alert is not None else None
            ),
            error_code=None if objects_exact else "projector_post_commit_readback_mismatch",
        )

    def append_post_commit_readback(self, delivery, result, readback, *, exact):
        with _cursor(self._connection) as cursor:
            receipt_id = _receipt_database_id(
                cursor, result.receipt.projector_receipt_identity
            )
            cursor.execute(
                "SELECT COALESCE(MAX(readback_attempt),0)+1 AS next_attempt "
                "FROM historical_baseline_v2_post_commit_readbacks "
                "WHERE projector_receipt_id=%s FOR UPDATE",
                (receipt_id,),
            )
            attempt = int(cursor.fetchone()["next_attempt"])
            identity = hashlib.sha256(
                f"hbp-v2-readback:{result.receipt.projector_receipt_identity}:{attempt}".encode(
                    "utf-8"
                )
            ).hexdigest()
            cursor.execute(
                _READBACK_INSERT_SQL,
                (
                    identity,
                    receipt_id,
                    _delivery_database_id(cursor, delivery.delivery_identity),
                    result.receipt.case_no,
                    result.receipt.order_identity,
                    _baseline_event_database_id(cursor, result.receipt.baseline_event_identity),
                    result.receipt.catalog_identity,
                    result.receipt.catalog_version,
                    result.receipt.umbrella_identity,
                    result.receipt.projection_sequence,
                    attempt,
                    result.receipt.expected_readback_digest.value,
                    _value(readback.actual_readback_digest),
                    _value(readback.emitted_occurrence_set_digest),
                    readback.emitted_occurrence_set_count,
                    _value(readback.active_membership_set_digest),
                    readback.active_membership_set_count,
                    _value(readback.state_event_set_digest),
                    _value(readback.successor_set_digest),
                    _value(readback.workflow_event_set_digest),
                    _value(readback.current_alert_fingerprint),
                    "exact" if exact else "mismatch",
                    None if exact else (readback.error_code or "projector_post_commit_readback_mismatch"),
                ),
            )


def _delivery_view(row):
    source_kind = str(row["delivery_source_kind"])
    if source_kind not in {"baseline_confirmed", "owner_repair"}:
        raise HistoricalBaselineProjectorQueryError("projector_delivery_source_kind_invalid")
    return HistoricalBaselineDeliveryView(
        delivery_identity=str(row["delivery_identity"]),
        source_trigger_identity=str(row["delivery_source_trigger_identity"]),
        payload_digest=PreviewFingerprint(str(row["delivery_payload_digest"])),
        source_kind=source_kind,
        source_domain=str(row["delivery_source_domain"]),
        source_event_identity=str(row["delivery_source_event_identity"]),
        source_version=int(row["delivery_source_version"]),
        partition_key=str(row["delivery_partition_key"]),
        projection_sequence=_optional_int(row["delivery_projection_sequence"]),
        projector_receipt_identity=(
            None
            if row["projector_receipt_identity"] is None
            else str(row["projector_receipt_identity"])
        ),
        status=HistoricalBaselineDeliveryStatus(str(row["delivery_status"])),
        attempt_count=int(row["delivery_attempt_count"]),
        max_attempts=int(row["delivery_max_attempts"]),
        next_attempt_at=row["delivery_next_attempt_at"],
        lease_owner=(
            None if row["delivery_lease_owner"] is None else str(row["delivery_lease_owner"])
        ),
        lease_expires_at=row["delivery_lease_expires_at"],
        last_error_code=(
            None
            if row["delivery_last_error_code"] is None
            else str(row["delivery_last_error_code"])
        ),
    )


def _receipt_view(row):
    if row["projector_receipt_identity"] is None:
        return None
    result_state = str(row["receipt_result_state"])
    if result_state not in {"projected", "held_active"}:
        raise HistoricalBaselineProjectorQueryError("projector_receipt_result_state_invalid")
    return HistoricalBaselineReceiptView(
        projector_receipt_identity=str(row["projector_receipt_identity"]),
        source_trigger_identity=str(row["receipt_source_trigger_identity"]),
        source_trigger_version=int(row["receipt_source_trigger_version"]),
        payload_digest=PreviewFingerprint(str(row["receipt_payload_digest"])),
        idempotency_key=str(row["receipt_idempotency_key"]),
        case_no=str(row["receipt_case_no"]),
        order_identity=str(row["receipt_order_identity"]),
        catalog_identity=PreviewFingerprint(str(row["receipt_catalog_identity"])),
        catalog_version=int(row["receipt_catalog_version"]),
        whole_vector_fingerprint=PreviewFingerprint(
            str(row["receipt_whole_vector_fingerprint"])
        ),
        whole_vector_count=int(row["receipt_whole_vector_count"]),
        emitted_occurrence_set_digest=PreviewFingerprint(
            str(row["receipt_emitted_occurrence_set_digest"])
        ),
        emitted_occurrence_set_count=int(row["receipt_emitted_occurrence_set_count"]),
        emitted_occurrence_identities=tuple(
            PreviewFingerprint(str(identity))
            for identity in _json_array(row["receipt_emitted_occurrence_identities"])
        ),
        active_membership_set_digest=PreviewFingerprint(
            str(row["receipt_active_membership_set_digest"])
        ),
        active_membership_set_count=int(row["receipt_active_membership_set_count"]),
        umbrella_identity=PreviewFingerprint(str(row["receipt_umbrella_identity"])),
        projection_sequence=int(row["receipt_projection_sequence"]),
        current_alert_fingerprint=PreviewFingerprint(
            str(row["receipt_current_alert_fingerprint"])
        ),
        expected_readback_digest=PreviewFingerprint(
            str(row["receipt_expected_readback_digest"])
        ),
        result_state=result_state,
    )


def _membership_view(row):
    return HistoricalBaselineMembershipView(
        membership_identity=PreviewFingerprint(str(row["membership_identity"])),
        set_ordinal=int(row["set_ordinal"]),
        occurrence_identity=PreviewFingerprint(str(row["occurrence_identity"])),
    )


def _post_commit_readback_view(row):
    result = str(row["readback_result"])
    if result not in {"exact", "mismatch", "unknown"}:
        raise HistoricalBaselineProjectorQueryError("projector_readback_result_invalid")
    return HistoricalBaselinePostCommitReadbackView(
        readback_identity=PreviewFingerprint(str(row["readback_identity"])),
        readback_attempt=int(row["readback_attempt"]),
        expected_readback_digest=PreviewFingerprint(
            str(row["expected_readback_digest"])
        ),
        actual_readback_digest=_optional_fingerprint(row["actual_readback_digest"]),
        emitted_occurrence_set_digest=_optional_fingerprint(
            row["actual_emitted_occurrence_set_digest"]
        ),
        emitted_occurrence_set_count=_optional_int(
            row["actual_emitted_occurrence_set_count"]
        ),
        active_membership_set_digest=_optional_fingerprint(
            row["actual_active_membership_set_digest"]
        ),
        active_membership_set_count=_optional_int(
            row["actual_active_membership_set_count"]
        ),
        state_event_set_digest=_optional_fingerprint(
            row["actual_state_event_set_digest"]
        ),
        successor_set_digest=_optional_fingerprint(
            row["actual_successor_set_digest"]
        ),
        workflow_event_set_digest=_optional_fingerprint(
            row["actual_workflow_event_set_digest"]
        ),
        current_alert_fingerprint=_optional_fingerprint(
            row["actual_current_alert_fingerprint"]
        ),
        result=result,
        error_code=(None if row["error_code"] is None else str(row["error_code"])),
    )


def _current_alert_view(row):
    display = _json_object(row["display_snapshot"])
    referrals_value = display.get("repair_referrals")
    if not isinstance(referrals_value, list):
        raise HistoricalBaselineProjectorQueryError(
            "projector_alert_repair_referrals_invalid"
        )
    referrals = tuple(_repair_referral_view(item) for item in referrals_value)
    workflow_status = str(row["workflow_status"])
    if workflow_status not in {"open", "claimed", "resolved"}:
        raise HistoricalBaselineProjectorQueryError(
            "projector_alert_workflow_status_invalid"
        )
    earliest = display.get("earliest_blocked_step")
    if earliest is not None and (isinstance(earliest, bool) or not isinstance(earliest, int)):
        raise HistoricalBaselineProjectorQueryError(
            "projector_alert_earliest_step_invalid"
        )
    active_count = display.get("active_count")
    if isinstance(active_count, bool) or not isinstance(active_count, int):
        raise HistoricalBaselineProjectorQueryError("projector_alert_active_count_invalid")
    display_case = display.get("case_no")
    projection_fingerprint = display.get("projection_fingerprint")
    if not isinstance(display_case, str) or not isinstance(projection_fingerprint, str):
        raise HistoricalBaselineProjectorQueryError("projector_alert_display_invalid")
    return HistoricalBaselineCurrentAlertView(
        fingerprint=PreviewFingerprint(str(row["fingerprint"])),
        definition_code=str(row["definition_code"]),
        definition_version=int(row["definition_version"]),
        source_domain=str(row["source_domain"]),
        source_identity=PreviewFingerprint(str(row["source_identity"])),
        source_version=int(row["source_version"]),
        predicate_active=bool(row["predicate_active"]),
        workflow_status=workflow_status,
        workflow_version=int(row["workflow_version"]),
        projection_version=int(row["projection_version"]),
        display=HistoricalBaselineAlertDisplayView(
            case_no=display_case,
            earliest_blocked_step=earliest,
            active_count=active_count,
            repair_referrals=referrals,
            projection_fingerprint=PreviewFingerprint(projection_fingerprint),
        ),
    )


def _repair_referral_view(value):
    if not isinstance(value, Mapping):
        raise HistoricalBaselineProjectorQueryError(
            "projector_alert_repair_referral_invalid"
        )
    required = {
        "step",
        "contract_id",
        "owner_domain",
        "repair_target",
        "repair_capability",
    }
    if set(value) != required:
        raise HistoricalBaselineProjectorQueryError(
            "projector_alert_repair_referral_invalid"
        )
    step = value["step"]
    strings = tuple(value[key] for key in sorted(required - {"step"}))
    if (
        isinstance(step, bool)
        or not isinstance(step, int)
        or any(not isinstance(item, str) for item in strings)
    ):
        raise HistoricalBaselineProjectorQueryError(
            "projector_alert_repair_referral_invalid"
        )
    return HistoricalBaselineRepairReferralView(
        step=step,
        contract_id=str(value["contract_id"]),
        owner_domain=str(value["owner_domain"]),
        repair_target=str(value["repair_target"]),
        repair_capability=str(value["repair_capability"]),
    )


def _validate_typed_read_model(model):
    receipt = model.receipt
    alert = model.current_alert
    delivery = model.delivery
    if receipt is None:
        if (
            delivery.status
            in {
                HistoricalBaselineDeliveryStatus.COMMITTED_UNVERIFIED,
                HistoricalBaselineDeliveryStatus.PROCESSED,
            }
            or delivery.projector_receipt_identity is not None
            or delivery.projection_sequence is not None
            or alert is not None
            or model.active_memberships
            or model.post_commit_readback is not None
        ):
            raise HistoricalBaselineProjectorQueryError(
                "projector_read_model_receipt_missing"
            )
        return
    if alert is None:
        raise HistoricalBaselineProjectorQueryError(
            "projector_read_model_current_alert_missing"
        )
    if (
        delivery.projector_receipt_identity != receipt.projector_receipt_identity
        or delivery.source_trigger_identity != receipt.source_trigger_identity
        or delivery.payload_digest != receipt.payload_digest
        or delivery.source_version != receipt.source_trigger_version
        or delivery.projection_sequence != receipt.projection_sequence
    ):
        raise HistoricalBaselineProjectorQueryError(
            "projector_read_model_delivery_receipt_binding_mismatch"
        )
    ordinals = tuple(item.set_ordinal for item in model.active_memberships)
    if ordinals != tuple(range(1, len(ordinals) + 1)):
        raise HistoricalBaselineProjectorQueryError(
            "projector_read_model_membership_ordinal_mismatch"
        )
    membership_digest = _identity_set_digest(
        tuple(item.occurrence_identity.value for item in model.active_memberships)
    )
    if membership_digest != receipt.active_membership_set_digest:
        raise HistoricalBaselineProjectorQueryError(
            "projector_read_model_membership_digest_mismatch"
        )
    emitted_identities = tuple(
        item.value for item in receipt.emitted_occurrence_identities
    )
    if (
        len(emitted_identities) != receipt.emitted_occurrence_set_count
        or emitted_identities != tuple(sorted(set(emitted_identities)))
        or _identity_set_digest(emitted_identities)
        != receipt.emitted_occurrence_set_digest
    ):
        raise HistoricalBaselineProjectorQueryError(
            "projector_read_model_emitted_snapshot_mismatch"
        )
    if (
        alert.fingerprint != receipt.current_alert_fingerprint
        or alert.definition_code != _DEFINITION_CODE
        or alert.definition_version != 1
        or alert.source_domain != _SOURCE_DOMAIN
        or alert.source_identity != receipt.umbrella_identity
        or alert.source_version != receipt.projection_sequence
        or alert.projection_version != receipt.projection_sequence
        or alert.display.case_no != receipt.case_no
        or alert.display.active_count != receipt.active_membership_set_count
        or alert.display.projection_fingerprint != receipt.expected_readback_digest
        or alert.predicate_active != (receipt.active_membership_set_count > 0)
        or alert.workflow_status
        != ("open" if receipt.active_membership_set_count > 0 else "resolved")
        or receipt.result_state
        != ("held_active" if receipt.active_membership_set_count > 0 else "projected")
    ):
        raise HistoricalBaselineProjectorQueryError(
            "projector_read_model_alert_binding_mismatch"
        )
    readback = model.post_commit_readback
    if readback is not None and (
        readback.expected_readback_digest != receipt.expected_readback_digest
        or (
            readback.result == "exact"
            and (
                readback.emitted_occurrence_set_digest
                != receipt.emitted_occurrence_set_digest
                or readback.emitted_occurrence_set_count
                != receipt.emitted_occurrence_set_count
                or readback.active_membership_set_digest
                != receipt.active_membership_set_digest
                or readback.active_membership_set_count
                != receipt.active_membership_set_count
            )
        )
        or (
            readback.current_alert_fingerprint is not None
            and readback.current_alert_fingerprint != receipt.current_alert_fingerprint
        )
    ):
        raise HistoricalBaselineProjectorQueryError(
            "projector_read_model_readback_binding_mismatch"
        )
    if delivery.status is HistoricalBaselineDeliveryStatus.PROCESSED and (
        readback is None
        or readback.result != "exact"
        or readback.actual_readback_digest != receipt.expected_readback_digest
    ):
        raise HistoricalBaselineProjectorQueryError(
            "projector_read_model_processed_without_exact_readback"
        )
    if (
        delivery.status is HistoricalBaselineDeliveryStatus.COMMITTED_UNVERIFIED
        and readback is not None
        and readback.result == "exact"
    ):
        raise HistoricalBaselineProjectorQueryError(
            "projector_read_model_delivery_readback_state_mismatch"
        )


def _occurrence_from_row(row) -> HistoricalBaselineOccurrenceProjection:
    descriptor = next(
        item
        for item in HISTORICAL_BASELINE_OWNER_ROOT_CATALOG_V2
        if item.contract_id == str(row["contract_id"])
    )
    if str(row["observation_variant"]) == "available":
        observation = HistoricalBaselineOwnerObservation(
            descriptor=descriptor,
            root_identity=str(row["observed_root_identity"]),
            source_event_identity=str(row["owner_source_event_identity"]),
            source_version=int(row["owner_source_version"]),
            terminal_result=bool(row["terminal_result"]),
            case_no=str(row["case_no"]),
        )
    else:
        observation = HistoricalBaselineOwnerObservation.unavailable(
            descriptor,
            code=str(row["unavailable_code"]),
            case_no=str(row["case_no"]),
        )
    return HistoricalBaselineOccurrenceProjection(
        occurrence_identity=str(row["occurrence_identity"]),
        case_no=str(row["case_no"]),
        order_identity=str(row["order_identity"]),
        baseline_event_identity=str(row["baseline_event_identity"]),
        catalog_identity=str(row["catalog_identity"]),
        catalog_version=int(row["catalog_version"]),
        descriptor_identity=str(row["descriptor_identity"]),
        observation_identity=str(row["observation_identity"]),
        descriptor=descriptor,
        observation=observation,
        owner_binding_fingerprint=PreviewFingerprint(
            str(row["owner_binding_fingerprint"])
        ),
        terminal=False,
        active=True,
    )


def _ensure_occurrence(cursor, occurrence, baseline_ids):
    cursor.execute(
        "SELECT id,case_no,order_identity,baseline_event_id,baseline_receipt_id,"
        "catalog_identity,catalog_version,descriptor_identity,contract_id,contract_version,"
        "step_number,owner_domain,root_identity_kind,root_identity_path,terminal_predicate_id,"
        "terminal_predicate_version,repair_target,repair_capability,observation_variant,"
        "observation_identity,observed_root_identity,owner_source_event_identity,"
        "owner_source_version,terminal_result,unavailable_code,owner_binding_fingerprint "
        "FROM historical_baseline_occurrences WHERE occurrence_identity=%s",
        (occurrence.occurrence_identity,),
    )
    row = cursor.fetchone()
    if row is not None:
        if not _stored_occurrence_matches(row, occurrence, baseline_ids):
            raise HistoricalBaselineDeliveryError(
                "projector_occurrence_integrity_conflict"
            )
        return int(row["id"]), False
    descriptor = occurrence.descriptor
    observation = occurrence.observation
    cursor.execute(
        _OCCURRENCE_INSERT_SQL,
        (
            occurrence.occurrence_identity,
            occurrence.case_no,
            occurrence.order_identity,
            baseline_ids[0],
            baseline_ids[1],
            occurrence.catalog_identity,
            occurrence.catalog_version,
            occurrence.descriptor_identity,
            descriptor.contract_id,
            descriptor.contract_version,
            descriptor.step,
            descriptor.owner_domain,
            descriptor.root_identity_kind,
            descriptor.root_identity_path,
            descriptor.terminal_predicate_id,
            descriptor.terminal_predicate_version,
            descriptor.repair_target,
            descriptor.repair_capability,
            "available" if observation.available else "unavailable",
            occurrence.observation_identity,
            observation.root_identity,
            observation.source_event_identity,
            observation.source_version,
            observation.terminal_result,
            observation.unavailable_code,
            occurrence.owner_binding_fingerprint.value,
        ),
    )
    return int(cursor.lastrowid), True


def _stored_occurrence_matches(row, occurrence, baseline_ids):
    descriptor = occurrence.descriptor
    observation = occurrence.observation
    return (
        str(row["case_no"]) == occurrence.case_no
        and str(row["order_identity"]) == occurrence.order_identity
        and int(row["baseline_event_id"]) == baseline_ids[0]
        and int(row["baseline_receipt_id"]) == baseline_ids[1]
        and str(row["catalog_identity"]) == occurrence.catalog_identity
        and int(row["catalog_version"]) == occurrence.catalog_version
        and str(row["descriptor_identity"]) == occurrence.descriptor_identity
        and str(row["contract_id"]) == descriptor.contract_id
        and int(row["contract_version"]) == descriptor.contract_version
        and int(row["step_number"]) == descriptor.step
        and str(row["owner_domain"]) == descriptor.owner_domain
        and str(row["root_identity_kind"]) == descriptor.root_identity_kind
        and str(row["root_identity_path"]) == descriptor.root_identity_path
        and str(row["terminal_predicate_id"])
        == descriptor.terminal_predicate_id
        and int(row["terminal_predicate_version"])
        == descriptor.terminal_predicate_version
        and str(row["repair_target"]) == descriptor.repair_target
        and str(row["repair_capability"]) == descriptor.repair_capability
        and str(row["observation_variant"])
        == ("available" if observation.available else "unavailable")
        and str(row["observation_identity"]) == occurrence.observation_identity
        and _optional_string(row["observed_root_identity"])
        == observation.root_identity
        and _optional_string(row["owner_source_event_identity"])
        == observation.source_event_identity
        and _optional_int(row["owner_source_version"])
        == observation.source_version
        and _optional_bool(row["terminal_result"])
        is observation.terminal_result
        and _optional_string(row["unavailable_code"])
        == observation.unavailable_code
        and str(row["owner_binding_fingerprint"])
        == occurrence.owner_binding_fingerprint.value
    )


def _append_initial_state(cursor, occurrence_id, occurrence, trigger):
    state = "opened" if occurrence.active else "resolved"
    event_identity = _state_identity(occurrence.occurrence_identity, state, 1)
    owner_event_identity = occurrence.observation.source_event_identity or trigger.source_event_identity
    owner_version = (
        trigger.source_version
        if occurrence.observation.source_version is None
        else occurrence.observation.source_version
    )
    cursor.execute(
        _STATE_INSERT_SQL,
        (
            event_identity,
            occurrence_id,
            None,
            occurrence.case_no,
            occurrence.order_identity,
            _baseline_event_database_id(cursor, occurrence.baseline_event_identity),
            occurrence.catalog_identity,
            occurrence.catalog_version,
            occurrence.descriptor_identity,
            occurrence.descriptor.contract_id,
            occurrence.descriptor.contract_version,
            occurrence.descriptor.terminal_predicate_id,
            occurrence.descriptor.terminal_predicate_version,
            owner_event_identity,
            owner_version,
            0,
            1,
            state,
            occurrence.owner_binding_fingerprint.value,
            occurrence.owner_binding_fingerprint.value,
            (
                "Historical baseline predicate is active."
                if occurrence.active
                else "Strictly newer owner readback satisfied the terminal predicate."
            ),
        ),
    )


def _append_inactive_state(
    cursor, occurrence_id, occurrence_identity, trigger, *, state
):
    if state not in {"resolved", "superseded"}:
        raise HistoricalBaselineDeliveryError("projector_occurrence_state_invalid")
    cursor.execute(
        "SELECT current.id,current.state_event_identity,current.prior_state_event_id,"
        "current.state,current.owner_event_identity,current.owner_source_version,"
        "current.expected_state_version,current.resulting_state_version,current.case_no,"
        "current.order_identity,current.baseline_event_id,event.baseline_event_identity,"
        "current.catalog_identity,current.catalog_version,current.descriptor_identity,"
        "current.contract_id,current.contract_version,current.terminal_predicate_id,"
        "current.terminal_predicate_version,current.owner_binding_fingerprint,"
        "current.fresh_readback_fingerprint,prior.id AS prior_id,"
        "prior.resulting_state_version AS prior_resulting_state_version,"
        "occurrence.case_no AS occurrence_case_no,occurrence.order_identity AS occurrence_order_identity,"
        "occurrence.baseline_event_id AS occurrence_baseline_event_id,"
        "occurrence.catalog_identity AS occurrence_catalog_identity,"
        "occurrence.catalog_version AS occurrence_catalog_version,"
        "occurrence.descriptor_identity AS occurrence_descriptor_identity,"
        "occurrence.contract_id AS occurrence_contract_id,"
        "occurrence.contract_version AS occurrence_contract_version,"
        "occurrence.terminal_predicate_id AS occurrence_terminal_predicate_id,"
        "occurrence.terminal_predicate_version AS occurrence_terminal_predicate_version,"
        "occurrence.owner_binding_fingerprint AS occurrence_owner_binding_fingerprint "
        "FROM historical_baseline_v2_occurrence_state_events AS current "
        "INNER JOIN historical_baseline_occurrences AS occurrence "
        "ON occurrence.id=current.occurrence_id "
        "INNER JOIN historical_order_operational_baseline_events AS event "
        "ON event.id=current.baseline_event_id "
        "LEFT JOIN historical_baseline_v2_occurrence_state_events AS prior "
        "ON prior.id=current.prior_state_event_id "
        "WHERE current.occurrence_id=%s "
        "ORDER BY current.resulting_state_version DESC LIMIT 1 FOR UPDATE",
        (occurrence_id,),
    )
    prior = cursor.fetchone()
    if prior is None or str(prior["state"]) in {"resolved", "superseded"}:
        if prior is None:
            raise HistoricalBaselineDeliveryError("projector_occurrence_state_missing")
        if not _stored_inactive_state_matches(
            prior, occurrence_identity, trigger, state=state
        ):
            raise HistoricalBaselineDeliveryError(
                "projector_occurrence_state_integrity_conflict"
            )
        return
    version = int(prior["resulting_state_version"]) + 1
    cursor.execute(
        _STATE_INSERT_SQL,
        (
            _state_identity(occurrence_identity, state, version),
            occurrence_id,
            int(prior["id"]),
            str(prior["case_no"]),
            str(prior["order_identity"]),
            int(prior["baseline_event_id"]),
            str(prior["catalog_identity"]),
            int(prior["catalog_version"]),
            str(prior["descriptor_identity"]),
            str(prior["contract_id"]),
            int(prior["contract_version"]),
            str(prior["terminal_predicate_id"]),
            int(prior["terminal_predicate_version"]),
            trigger.source_event_identity,
            trigger.source_version,
            version - 1,
            version,
            state,
            str(prior["owner_binding_fingerprint"]),
            trigger.source_intent.expected_owner_binding_fingerprint.value,
            (
                "Strictly newer owner readback superseded the predecessor occurrence."
                if state == "superseded"
                else "Strictly newer owner readback satisfied the terminal predicate."
            ),
        ),
    )


def _stored_inactive_state_matches(row, occurrence_identity, trigger, *, state):
    version = int(row["resulting_state_version"])
    expected_version = version - 1
    prior_id = row["prior_state_event_id"]
    return (
        str(row["state_event_identity"])
        == _state_identity(occurrence_identity, state, version)
        and str(row["state"]) == state
        and str(row["owner_event_identity"]) == trigger.source_event_identity
        and int(row["owner_source_version"]) == trigger.source_version
        and int(row["expected_state_version"]) == expected_version
        and expected_version >= 1
        and prior_id is not None
        and int(prior_id) == int(row["prior_id"])
        and int(row["prior_resulting_state_version"]) == expected_version
        and str(row["case_no"]) == trigger.source_intent.identity.case_no
        and str(row["order_identity"])
        == trigger.source_intent.identity.order_identity
        and str(row["baseline_event_identity"])
        == trigger.source_intent.baseline_event_identity
        and str(row["catalog_identity"])
        == trigger.source_intent.catalog_identity.value
        and int(row["catalog_version"]) == trigger.source_intent.catalog_version
        and str(row["fresh_readback_fingerprint"])
        == trigger.source_intent.expected_owner_binding_fingerprint.value
        and str(row["case_no"]) == str(row["occurrence_case_no"])
        and str(row["order_identity"]) == str(row["occurrence_order_identity"])
        and int(row["baseline_event_id"])
        == int(row["occurrence_baseline_event_id"])
        and str(row["catalog_identity"])
        == str(row["occurrence_catalog_identity"])
        and int(row["catalog_version"])
        == int(row["occurrence_catalog_version"])
        and str(row["descriptor_identity"])
        == str(row["occurrence_descriptor_identity"])
        and str(row["contract_id"]) == str(row["occurrence_contract_id"])
        and int(row["contract_version"])
        == int(row["occurrence_contract_version"])
        and str(row["terminal_predicate_id"])
        == str(row["occurrence_terminal_predicate_id"])
        and int(row["terminal_predicate_version"])
        == int(row["occurrence_terminal_predicate_version"])
        and str(row["owner_binding_fingerprint"])
        == str(row["occurrence_owner_binding_fingerprint"])
    )


def _ensure_successor(cursor, successor, occurrence_ids):
    cursor.execute(
        "SELECT id,predecessor_occurrence_id,successor_occurrence_id,case_no,order_identity,"
        "baseline_event_id,catalog_identity,catalog_version,descriptor_identity,contract_id,"
        "contract_version,owner_event_identity,prior_owner_source_version,new_owner_source_version,"
        "terminal_predicate_id,terminal_predicate_version,fresh_readback_fingerprint "
        "FROM historical_baseline_successors WHERE successor_relation_identity=%s",
        (successor.successor_relation_identity,),
    )
    row = cursor.fetchone()
    predecessor_id = _occurrence_database_id(
        cursor, successor.predecessor_occurrence_identity
    )
    successor_id = occurrence_ids[successor.successor_occurrence_identity]
    baseline_event_id = _baseline_event_database_id(
        cursor, successor.baseline_event_identity
    )
    if row is not None:
        if not _stored_successor_matches(
            row,
            successor,
            predecessor_id=predecessor_id,
            successor_id=successor_id,
            baseline_event_id=baseline_event_id,
        ):
            raise HistoricalBaselineDeliveryError(
                "projector_successor_integrity_conflict"
            )
        return
    cursor.execute(
        _SUCCESSOR_INSERT_SQL,
        (
            successor.successor_relation_identity,
            predecessor_id,
            successor_id,
            successor.case_no,
            successor.order_identity,
            baseline_event_id,
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
        ),
    )


def _stored_successor_matches(
    row, successor, *, predecessor_id, successor_id, baseline_event_id
):
    return (
        int(row["predecessor_occurrence_id"]) == predecessor_id
        and int(row["successor_occurrence_id"]) == successor_id
        and str(row["case_no"]) == successor.case_no
        and str(row["order_identity"]) == successor.order_identity
        and int(row["baseline_event_id"]) == baseline_event_id
        and str(row["catalog_identity"]) == successor.catalog_identity
        and int(row["catalog_version"]) == successor.catalog_version
        and str(row["descriptor_identity"]) == successor.descriptor_identity
        and str(row["contract_id"]) == successor.contract_id
        and int(row["contract_version"]) == successor.contract_version
        and str(row["owner_event_identity"]) == successor.owner_event_identity
        and int(row["prior_owner_source_version"])
        == successor.prior_owner_source_version
        and int(row["new_owner_source_version"])
        == successor.new_owner_source_version
        and str(row["terminal_predicate_id"])
        == successor.terminal_predicate_id
        and int(row["terminal_predicate_version"])
        == successor.terminal_predicate_version
        and str(row["fresh_readback_fingerprint"])
        == successor.fresh_readback_fingerprint.value
    )


def _upsert_current_alert(cursor, result):
    fingerprint = _alert_fingerprint(result.umbrella.umbrella_identity)
    cursor.execute(
        "SELECT fingerprint,definition_code,definition_version,source_domain,source_identity,"
        "source_version,predicate_active,workflow_status,workflow_version,projection_version,"
        "claimed_by,claimed_at,resolved_by,resolved_at "
        "FROM anomaly_current_alerts WHERE fingerprint=%s FOR UPDATE",
        (fingerprint.value,),
    )
    previous = cursor.fetchone()
    active = result.umbrella.active
    if previous is None and not active:
        raise HistoricalBaselineDeliveryError(
            "projector_inactive_initial_projection_has_no_current_alert"
        )
    if previous is not None and not _current_alert_identity_matches(
        previous, result, fingerprint
    ):
        raise HistoricalBaselineDeliveryError(
            "projector_current_alert_integrity_conflict"
        )
    status = "open" if active else "resolved"
    workflow_version = 0 if previous is None else int(previous["workflow_version"])
    action = None
    if previous is not None:
        previous_status = str(previous["workflow_status"])
        if active and previous_status == "resolved":
            action = "reopen"
        elif not active and previous_status != "resolved":
            action = "auto_resolve"
        if active and previous_status == "claimed":
            status = "claimed"
        if (
            int(previous["source_version"]) != result.receipt.projection_sequence
            or bool(previous["predicate_active"]) is not active
            or previous_status != status
        ):
            workflow_version += 1
        if action is None and status != "claimed":
            status = previous_status if previous_status == status else status
    display = _display_snapshot(result)
    actor_fields = _projected_alert_actor_fields(previous, status)
    if previous is None:
        cursor.execute(
            _ALERT_INSERT_SQL,
            (
                fingerprint.value,
                _DEFINITION_CODE,
                _SOURCE_DOMAIN,
                result.umbrella.umbrella_identity,
                result.receipt.projection_sequence,
                active,
                status,
                workflow_version,
                *actor_fields,
                _json_dump(display),
            ),
        )
    else:
        cursor.execute(
            _ALERT_UPDATE_SQL,
            (
                result.receipt.projection_sequence,
                active,
                status,
                workflow_version,
                *actor_fields,
                _json_dump(display),
                fingerprint.value,
                int(previous["workflow_version"]),
            ),
        )
        if int(cursor.rowcount) != 1:
            raise HistoricalBaselineDeliveryError("projector_current_alert_cas_conflict")
    if action is not None:
        cursor.execute(
            _WORKFLOW_INSERT_SQL,
            (
                fingerprint.value,
                action,
                workflow_version - 1,
                workflow_version,
                "historical-baseline-projector",
                "Historical baseline active membership changed.",
                result.receipt.projector_receipt_identity,
                f"hbp-v2:{result.receipt.projector_receipt_identity}:{action}",
            ),
        )
    return {"fingerprint": fingerprint.value}


def _current_alert_identity_matches(row, result, fingerprint):
    return (
        str(row["fingerprint"]) == fingerprint.value
        and str(row["definition_code"]) == _DEFINITION_CODE
        and int(row["definition_version"]) == 1
        and str(row["source_domain"]) == _SOURCE_DOMAIN
        and str(row["source_identity"]) == result.umbrella.umbrella_identity
        and int(row["source_version"]) < result.receipt.projection_sequence
        and int(row["projection_version"]) < result.receipt.projection_sequence
    )


def _projected_alert_actor_fields(previous, status):
    if status == "open":
        return None, None, None, None
    if status == "claimed":
        if (
            previous is None
            or previous["claimed_by"] is None
            or previous["claimed_at"] is None
        ):
            raise HistoricalBaselineDeliveryError(
                "projector_claimed_alert_actor_missing"
            )
        return str(previous["claimed_by"]), previous["claimed_at"], None, None
    if previous is not None and str(previous["workflow_status"]) == "resolved":
        if previous["resolved_by"] is None or previous["resolved_at"] is None:
            raise HistoricalBaselineDeliveryError(
                "projector_resolved_alert_actor_missing"
            )
        return None, None, str(previous["resolved_by"]), previous["resolved_at"]
    return None, None, "historical-baseline-projector", datetime.utcnow()


def _insert_receipt(cursor, trigger, result, baseline_ids, alert_fingerprint):
    receipt = result.receipt
    cursor.execute(
        _RECEIPT_INSERT_SQL,
        (
            receipt.projector_receipt_identity,
            trigger.trigger_identity,
            trigger.source_version,
            trigger.payload_digest.value,
            receipt.idempotency_key,
            baseline_ids[0],
            baseline_ids[1],
            baseline_ids[2],
            receipt.case_no,
            receipt.order_identity,
            receipt.catalog_identity,
            receipt.catalog_version,
            receipt.whole_vector_fingerprint.value,
            receipt.whole_vector_count,
            receipt.emitted_occurrence_set_digest.value,
            receipt.emitted_occurrence_set_count,
            _json_dump(
                tuple(
                    sorted(
                        item.occurrence_identity
                        for item in (*result.occurrences, *result.successor_occurrences)
                    )
                )
            ),
            receipt.active_membership_set_digest.value,
            receipt.active_membership_set_count,
            receipt.umbrella_identity,
            receipt.projection_sequence,
            alert_fingerprint,
            receipt.expected_readback_digest.value,
            receipt.result_state,
        ),
    )
    return int(cursor.lastrowid)


def _save_checkpoint(cursor, checkpoint):
    cursor.execute(
        _CHECKPOINT_UPSERT_SQL,
        (
            checkpoint.checkpoint_identity,
            checkpoint.source_domain,
            checkpoint.source_stream,
            checkpoint.partition_key,
            checkpoint.last_source_event_identity,
            checkpoint.last_source_version,
            checkpoint.last_projection_sequence,
            checkpoint.checkpoint_fingerprint.value,
        ),
    )


def _baseline_ids(cursor, trigger):
    source = trigger.source_intent
    cursor.execute(
        "SELECT event.id AS event_id,receipt.id AS receipt_id,outbox.id AS outbox_id "
        "FROM historical_order_operational_baseline_events AS event "
        "INNER JOIN historical_order_operational_baseline_receipts AS receipt "
        "ON receipt.event_id=event.id "
        "INNER JOIN historical_order_operational_baseline_outbox AS outbox "
        "ON outbox.event_id=event.id AND outbox.receipt_id=receipt.id "
        "WHERE event.baseline_event_identity=%s AND receipt.receipt_identity=%s "
        "AND outbox.intent_key=%s FOR UPDATE",
        (
            source.baseline_event_identity,
            source.baseline_receipt_identity,
            source.baseline_outbox_identity,
        ),
    )
    row = cursor.fetchone()
    if row is None:
        raise HistoricalBaselineDeliveryError("projector_baseline_lineage_not_found")
    return int(row["event_id"]), int(row["receipt_id"]), int(row["outbox_id"])


def _existing_identities(cursor, table, column, identities):
    if not identities:
        return ()
    placeholders = ",".join(("%s",) * len(identities))
    cursor.execute(
        f"SELECT {column} FROM {table} WHERE {column} IN ({placeholders}) ORDER BY {column}",
        identities,
    )
    return tuple(str(row[column]) for row in cursor.fetchall())


def _latest_state_rows(cursor, result):
    occurrence_ids = tuple(
        sorted(
            {
                *(item.occurrence_identity for item in result.occurrences),
                *(item.occurrence_identity for item in result.successor_occurrences),
                *result.inactive_predecessor_identities,
            }
        )
    )
    if not occurrence_ids:
        return ()
    placeholders = ",".join(("%s",) * len(occurrence_ids))
    cursor.execute(
        "SELECT occurrence.occurrence_identity,state.state_event_identity,"
        "state.prior_state_event_id,state.state,"
        "state.owner_event_identity,state.owner_source_version,state.expected_state_version,"
        "state.resulting_state_version,state.case_no,state.order_identity,state.baseline_event_id,"
        "event.baseline_event_identity,state.catalog_identity,state.catalog_version,"
        "state.descriptor_identity,state.contract_id,state.contract_version,"
        "state.terminal_predicate_id,state.terminal_predicate_version,"
        "state.owner_binding_fingerprint,state.fresh_readback_fingerprint,"
        "prior.id AS prior_id,prior.resulting_state_version AS prior_resulting_state_version,"
        "occurrence.case_no AS occurrence_case_no,"
        "occurrence.order_identity AS occurrence_order_identity,"
        "occurrence.baseline_event_id AS occurrence_baseline_event_id,"
        "occurrence.catalog_identity AS occurrence_catalog_identity,"
        "occurrence.catalog_version AS occurrence_catalog_version,"
        "occurrence.descriptor_identity AS occurrence_descriptor_identity,"
        "occurrence.contract_id AS occurrence_contract_id,"
        "occurrence.contract_version AS occurrence_contract_version,"
        "occurrence.terminal_predicate_id AS occurrence_terminal_predicate_id,"
        "occurrence.terminal_predicate_version AS occurrence_terminal_predicate_version,"
        "occurrence.owner_binding_fingerprint AS occurrence_owner_binding_fingerprint "
        "FROM historical_baseline_v2_occurrence_state_events AS state "
        "INNER JOIN historical_baseline_occurrences AS occurrence ON occurrence.id=state.occurrence_id "
        "INNER JOIN historical_order_operational_baseline_events AS event "
        "ON event.id=state.baseline_event_id "
        "LEFT JOIN historical_baseline_v2_occurrence_state_events AS prior "
        "ON prior.id=state.prior_state_event_id "
        "LEFT JOIN historical_baseline_v2_occurrence_state_events AS newer "
        "ON newer.occurrence_id=state.occurrence_id "
        "AND newer.resulting_state_version>state.resulting_state_version "
        f"WHERE occurrence.occurrence_identity IN ({placeholders}) AND newer.id IS NULL "
        "ORDER BY occurrence.occurrence_identity",
        occurrence_ids,
    )
    return tuple(cursor.fetchall())


def _successor_rows(cursor, result):
    predecessor_ids = tuple(sorted(result.inactive_predecessor_identities))
    if not predecessor_ids:
        return ()
    placeholders = ",".join(("%s",) * len(predecessor_ids))
    cursor.execute(
        "SELECT relation.successor_relation_identity,predecessor.occurrence_identity "
        "AS predecessor_occurrence_identity,successor.occurrence_identity "
        "AS successor_occurrence_identity,relation.case_no,relation.order_identity,"
        "event.baseline_event_identity,relation.catalog_identity,relation.catalog_version,"
        "relation.descriptor_identity,relation.contract_id,relation.contract_version,"
        "relation.owner_event_identity,relation.prior_owner_source_version,"
        "relation.new_owner_source_version,relation.terminal_predicate_id,"
        "relation.terminal_predicate_version,relation.fresh_readback_fingerprint "
        "FROM historical_baseline_successors AS relation "
        "INNER JOIN historical_baseline_occurrences AS predecessor "
        "ON predecessor.id=relation.predecessor_occurrence_id "
        "INNER JOIN historical_baseline_occurrences AS successor "
        "ON successor.id=relation.successor_occurrence_id "
        "INNER JOIN historical_order_operational_baseline_events AS event "
        "ON event.id=relation.baseline_event_id "
        f"WHERE predecessor.occurrence_identity IN ({placeholders}) "
        "ORDER BY relation.successor_relation_identity",
        predecessor_ids,
    )
    return tuple(cursor.fetchall())


def _workflow_rows(cursor, fingerprint):
    cursor.execute(
        "SELECT action,expected_workflow_version,resulting_workflow_version,actor,reason,"
        "correlation_id,idempotency_key FROM anomaly_workflow_events "
        "WHERE alert_fingerprint=%s ORDER BY resulting_workflow_version,idempotency_key",
        (fingerprint.value,),
    )
    return tuple(cursor.fetchall())


def _display_snapshot(result):
    active = tuple(
        {
            "step": item.descriptor.step,
            "contract_id": item.descriptor.contract_id,
            "owner_domain": item.descriptor.owner_domain,
            "repair_target": item.descriptor.repair_target,
            "repair_capability": item.descriptor.repair_capability,
        }
        for item in result.occurrences
    )
    return {
        "case_no": result.receipt.case_no,
        "earliest_blocked_step": None if result.terminal_conjunction else result.current_step,
        "active_count": result.umbrella.membership_count,
        "repair_referrals": active,
        "projection_fingerprint": result.receipt.expected_readback_digest.value,
    }


def _membership_vector_matches(rows, result):
    actual = tuple(
        (
            str(row["membership_identity"]),
            int(row["set_ordinal"]),
            str(row["occurrence_identity"]),
        )
        for row in rows
    )
    expected = tuple(
        (
            item.membership_identity,
            item.set_ordinal,
            item.occurrence_identity,
        )
        for item in result.umbrella.memberships
    )
    return actual == expected


def _state_vector_matches(rows, result, trigger):
    expected_states = {
        item.occurrence_identity: "opened" for item in result.occurrences
    }
    expected_states.update(
        {
            item.occurrence_identity: "resolved"
            for item in result.successor_occurrences
        }
    )
    superseded = {
        item.predecessor_occurrence_identity for item in result.successors
    }
    expected_states.update(
        {
            identity: ("superseded" if identity in superseded else "resolved")
            for identity in result.inactive_predecessor_identities
        }
    )
    if len(rows) != len(expected_states):
        return False
    for row in rows:
        occurrence_identity = str(row["occurrence_identity"])
        state = expected_states.get(occurrence_identity)
        if state is None or str(row["state"]) != state:
            return False
        version = int(row["resulting_state_version"])
        if (
            int(row["expected_state_version"]) != version - 1
            or str(row["state_event_identity"])
            != _state_identity(occurrence_identity, state, version)
            or not _state_lineage_matches(row, result, version=version)
        ):
            return False
        projected = next(
            (
                item
                for item in (*result.occurrences, *result.successor_occurrences)
                if item.occurrence_identity == occurrence_identity
            ),
            None,
        )
        if projected is not None:
            expected_owner_event = (
                projected.observation.source_event_identity
                or trigger.source_event_identity
            )
            expected_owner_version = (
                trigger.source_version
                if projected.observation.source_version is None
                else projected.observation.source_version
            )
            expected_binding = projected.owner_binding_fingerprint.value
            if (
                version != 1
                or row["prior_state_event_id"] is not None
                or row["prior_id"] is not None
            ):
                return False
        else:
            expected_owner_event = trigger.source_event_identity
            expected_owner_version = trigger.source_version
            expected_binding = (
                trigger.source_intent.expected_owner_binding_fingerprint.value
            )
            if (
                version < 2
                or row["prior_state_event_id"] is None
                or int(row["prior_state_event_id"]) != int(row["prior_id"])
                or int(row["prior_resulting_state_version"]) != version - 1
            ):
                return False
        if (
            str(row["owner_event_identity"]) != expected_owner_event
            or int(row["owner_source_version"]) != expected_owner_version
            or str(row["fresh_readback_fingerprint"]) != expected_binding
        ):
            return False
    return True


def _state_lineage_matches(row, result, *, version):
    receipt = result.receipt
    return (
        str(row["case_no"]) == receipt.case_no
        and str(row["order_identity"]) == receipt.order_identity
        and str(row["baseline_event_identity"]) == receipt.baseline_event_identity
        and str(row["catalog_identity"]) == receipt.catalog_identity
        and int(row["catalog_version"]) == receipt.catalog_version
        and str(row["case_no"]) == str(row["occurrence_case_no"])
        and str(row["order_identity"]) == str(row["occurrence_order_identity"])
        and int(row["baseline_event_id"])
        == int(row["occurrence_baseline_event_id"])
        and str(row["catalog_identity"])
        == str(row["occurrence_catalog_identity"])
        and int(row["catalog_version"])
        == int(row["occurrence_catalog_version"])
        and str(row["descriptor_identity"])
        == str(row["occurrence_descriptor_identity"])
        and str(row["contract_id"]) == str(row["occurrence_contract_id"])
        and int(row["contract_version"])
        == int(row["occurrence_contract_version"])
        and str(row["terminal_predicate_id"])
        == str(row["occurrence_terminal_predicate_id"])
        and int(row["terminal_predicate_version"])
        == int(row["occurrence_terminal_predicate_version"])
        and str(row["owner_binding_fingerprint"])
        == str(row["occurrence_owner_binding_fingerprint"])
        and int(row["expected_state_version"]) == version - 1
    )


def _successor_vector_matches(rows, result):
    expected = {
        item.successor_relation_identity: item for item in result.successors
    }
    if len(rows) != len(expected):
        return False
    for row in rows:
        item = expected.get(str(row["successor_relation_identity"]))
        if item is None or (
            str(row["predecessor_occurrence_identity"])
            != item.predecessor_occurrence_identity
            or str(row["successor_occurrence_identity"])
            != item.successor_occurrence_identity
            or str(row["case_no"]) != item.case_no
            or str(row["order_identity"]) != item.order_identity
            or str(row["baseline_event_identity"]) != item.baseline_event_identity
            or str(row["catalog_identity"]) != item.catalog_identity
            or int(row["catalog_version"]) != item.catalog_version
            or str(row["descriptor_identity"]) != item.descriptor_identity
            or str(row["contract_id"]) != item.contract_id
            or int(row["contract_version"]) != item.contract_version
            or str(row["owner_event_identity"]) != item.owner_event_identity
            or int(row["prior_owner_source_version"])
            != item.prior_owner_source_version
            or int(row["new_owner_source_version"])
            != item.new_owner_source_version
            or str(row["terminal_predicate_id"])
            != item.terminal_predicate_id
            or int(row["terminal_predicate_version"])
            != item.terminal_predicate_version
            or str(row["fresh_readback_fingerprint"])
            != item.fresh_readback_fingerprint.value
        ):
            return False
    return True


def _workflow_vector_matches(rows, alert):
    prior_resulting_version = -1
    for row in rows:
        action = str(row["action"])
        expected_version = int(row["expected_workflow_version"])
        resulting_version = int(row["resulting_workflow_version"])
        if (
            action not in {"claim", "resolve", "auto_resolve", "reopen"}
            or expected_version < prior_resulting_version
            or resulting_version != expected_version + 1
            or not str(row["actor"])
            or not str(row["reason"])
            or not str(row["correlation_id"])
            or not str(row["idempotency_key"])
        ):
            return False
        if action in {"auto_resolve", "reopen"} and (
            str(row["actor"]) != "historical-baseline-projector"
            or str(row["reason"])
            != "Historical baseline active membership changed."
            or str(row["idempotency_key"])
            != f"hbp-v2:{row['correlation_id']}:{action}"
        ):
            return False
        prior_resulting_version = resulting_version
    if alert is None:
        return not rows
    return int(alert["workflow_version"]) >= max(prior_resulting_version, 0)


def _stored_receipt_matches(row, delivery, result):
    if row is None:
        return False
    receipt = result.receipt
    emitted_identities = tuple(
        sorted(
            item.occurrence_identity
            for item in (*result.occurrences, *result.successor_occurrences)
        )
    )
    return (
        str(row["source_trigger_identity"]) == delivery.trigger.trigger_identity
        and int(row["source_trigger_version"]) == delivery.trigger.source_version
        and str(row["payload_digest"]) == delivery.trigger.payload_digest.value
        and str(row["idempotency_key"]) == receipt.idempotency_key
        and str(row["baseline_event_identity"]) == receipt.baseline_event_identity
        and str(row["baseline_receipt_identity"])
        == receipt.baseline_receipt_identity
        and str(row["baseline_outbox_identity"]) == receipt.baseline_outbox_identity
        and str(row["case_no"]) == receipt.case_no
        and str(row["order_identity"]) == receipt.order_identity
        and str(row["catalog_identity"]) == receipt.catalog_identity
        and int(row["catalog_version"]) == receipt.catalog_version
        and str(row["whole_vector_fingerprint"])
        == receipt.whole_vector_fingerprint.value
        and int(row["whole_vector_count"]) == receipt.whole_vector_count
        and str(row["emitted_occurrence_set_digest"])
        == receipt.emitted_occurrence_set_digest.value
        and int(row["emitted_occurrence_set_count"])
        == receipt.emitted_occurrence_set_count
        and _json_array(row["emitted_occurrence_identities"])
        == emitted_identities
        and str(row["active_membership_set_digest"])
        == receipt.active_membership_set_digest.value
        and int(row["active_membership_set_count"])
        == receipt.active_membership_set_count
        and str(row["umbrella_identity"]) == receipt.umbrella_identity
        and int(row["projection_sequence"]) == receipt.projection_sequence
        and str(row["current_alert_fingerprint"])
        == _alert_fingerprint(receipt.umbrella_identity).value
        and str(row["expected_readback_digest"])
        == receipt.expected_readback_digest.value
        and str(row["result_state"]) == receipt.result_state
    )


def _current_alert_matches(row, result, fingerprint, *, workflow_rows):
    if row is None:
        return False
    display = row["display_snapshot"]
    if isinstance(display, str):
        display = json.loads(display)
    workflow_status = str(row["workflow_status"])
    expected_status = (
        {"open", "claimed"} if result.umbrella.active else {"resolved"}
    )
    return (
        str(row["fingerprint"]) == fingerprint.value
        and str(row["definition_code"]) == _DEFINITION_CODE
        and int(row["definition_version"]) == 1
        and str(row["source_domain"]) == _SOURCE_DOMAIN
        and str(row["source_identity"]) == result.umbrella.umbrella_identity
        and int(row["source_version"]) == result.receipt.projection_sequence
        and bool(row["predicate_active"]) is result.umbrella.active
        and workflow_status in expected_status
        and (
            workflow_status != "claimed"
            or (row["claimed_by"] is not None and row["claimed_at"] is not None)
        )
        and _workflow_vector_matches(workflow_rows, row)
        and int(row["projection_version"]) == result.receipt.projection_sequence
        and display == _display_snapshot(result)
    )


def _alert_fingerprint(umbrella_identity):
    return fingerprint_payload(
        {
            "definition_code": _DEFINITION_CODE,
            "source_identity": umbrella_identity,
            "fingerprint_values": {"umbrella_identity": umbrella_identity},
        }
    )


def _identity_set_digest(identities):
    return fingerprint_payload(
        {
            "kind": "historical_baseline_occurrence_set_v1",
            "identities": tuple(sorted(identities)),
        }
    )


def _state_identity(occurrence_identity, state, version):
    return hashlib.sha256(
        f"hbp-v2-state:{occurrence_identity}:{state}:{version}".encode("utf-8")
    ).hexdigest()


def _receipt_database_id(cursor, identity):
    if identity is None:
        return None
    cursor.execute(
        "SELECT id FROM historical_baseline_v2_projector_receipts "
        "WHERE projector_receipt_identity=%s",
        (identity,),
    )
    row = cursor.fetchone()
    return None if row is None else int(row["id"])


def _delivery_database_id(cursor, identity):
    cursor.execute(
        "SELECT id FROM historical_baseline_v2_projector_deliveries WHERE delivery_identity=%s",
        (identity,),
    )
    row = cursor.fetchone()
    if row is None:
        raise HistoricalBaselineDeliveryError("projector_delivery_not_found")
    return int(row["id"])


def _occurrence_database_id(cursor, identity):
    cursor.execute(
        "SELECT id FROM historical_baseline_occurrences WHERE occurrence_identity=%s",
        (identity,),
    )
    row = cursor.fetchone()
    if row is None:
        raise HistoricalBaselineDeliveryError("projector_occurrence_not_found")
    return int(row["id"])


def _baseline_event_database_id(cursor, identity):
    cursor.execute(
        "SELECT id FROM historical_order_operational_baseline_events "
        "WHERE baseline_event_identity=%s",
        (identity,),
    )
    row = cursor.fetchone()
    if row is None:
        raise HistoricalBaselineDeliveryError("projector_baseline_event_not_found")
    return int(row["id"])


def _optional_int(value):
    return None if value is None else int(value)


def _optional_bool(value):
    return None if value is None else bool(value)


def _optional_string(value):
    return None if value is None else str(value)


def _optional_fingerprint(value):
    return None if value is None else PreviewFingerprint(str(value))


def _value(value):
    return None if value is None else value.value


def _json_dump(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def _json_object(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, Mapping):
        raise HistoricalBaselineProjectorQueryError(
            "projector_read_model_json_invalid"
        )
    return parsed


def _json_array(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        raise HistoricalBaselineProjectorQueryError(
            "projector_read_model_json_array_invalid"
        )
    return tuple(parsed)


@contextmanager
def _cursor(connection) -> Iterator[object]:
    with connection.cursor() as cursor:
        yield cursor


_DELIVERY_SELECT_SQL = (
    "SELECT delivery.delivery_identity,delivery.delivery_status,delivery.attempt_count,"
    "delivery.max_attempts,delivery.projection_sequence,receipt.projector_receipt_identity,"
    "delivery.next_attempt_at,delivery.lease_owner,delivery.lease_expires_at,"
    "delivery.last_error_code,delivery.payload_digest,delivery.source_kind,"
    "delivery.source_domain,delivery.source_event_identity,delivery.source_version,"
    "delivery.partition_key "
    "FROM historical_baseline_v2_projector_deliveries AS delivery "
    "LEFT JOIN historical_baseline_v2_projector_receipts AS receipt "
    "ON receipt.id=delivery.projector_receipt_id WHERE delivery.source_trigger_identity=%s"
)
_PROJECTOR_READ_MODEL_SELECT_SQL = (
    "SELECT delivery.delivery_identity,"
    "delivery.source_trigger_identity AS delivery_source_trigger_identity,"
    "delivery.payload_digest AS delivery_payload_digest,"
    "delivery.source_kind AS delivery_source_kind,"
    "delivery.source_domain AS delivery_source_domain,"
    "delivery.source_event_identity AS delivery_source_event_identity,"
    "delivery.source_version AS delivery_source_version,"
    "delivery.partition_key AS delivery_partition_key,"
    "delivery.projection_sequence AS delivery_projection_sequence,"
    "delivery.delivery_status,delivery.attempt_count AS delivery_attempt_count,"
    "delivery.max_attempts AS delivery_max_attempts,"
    "delivery.next_attempt_at AS delivery_next_attempt_at,"
    "delivery.lease_owner AS delivery_lease_owner,"
    "delivery.lease_expires_at AS delivery_lease_expires_at,"
    "delivery.last_error_code AS delivery_last_error_code,"
    "receipt.projector_receipt_identity,"
    "receipt.source_trigger_identity AS receipt_source_trigger_identity,"
    "receipt.source_trigger_version AS receipt_source_trigger_version,"
    "receipt.payload_digest AS receipt_payload_digest,"
    "receipt.idempotency_key AS receipt_idempotency_key,"
    "receipt.case_no AS receipt_case_no,receipt.order_identity AS receipt_order_identity,"
    "receipt.catalog_identity AS receipt_catalog_identity,"
    "receipt.catalog_version AS receipt_catalog_version,"
    "receipt.whole_vector_fingerprint AS receipt_whole_vector_fingerprint,"
    "receipt.whole_vector_count AS receipt_whole_vector_count,"
    "receipt.emitted_occurrence_set_digest AS receipt_emitted_occurrence_set_digest,"
    "receipt.emitted_occurrence_set_count AS receipt_emitted_occurrence_set_count,"
    "receipt.emitted_occurrence_identities AS receipt_emitted_occurrence_identities,"
    "receipt.active_membership_set_digest AS receipt_active_membership_set_digest,"
    "receipt.active_membership_set_count AS receipt_active_membership_set_count,"
    "receipt.umbrella_identity AS receipt_umbrella_identity,"
    "receipt.projection_sequence AS receipt_projection_sequence,"
    "receipt.current_alert_fingerprint AS receipt_current_alert_fingerprint,"
    "receipt.expected_readback_digest AS receipt_expected_readback_digest,"
    "receipt.result_state AS receipt_result_state "
    "FROM historical_baseline_v2_projector_deliveries AS delivery "
    "LEFT JOIN historical_baseline_v2_projector_receipts AS receipt "
    "ON receipt.id=delivery.projector_receipt_id "
    "WHERE {predicate} ORDER BY {order_by} LIMIT 1"
)
_READ_MODEL_MEMBERSHIP_SELECT_SQL = (
    "SELECT member.membership_identity,member.set_ordinal,occurrence.occurrence_identity "
    "FROM historical_baseline_v2_active_membership_snapshots AS member "
    "INNER JOIN historical_baseline_v2_projector_receipts AS receipt "
    "ON receipt.id=member.projector_receipt_id "
    "INNER JOIN historical_baseline_occurrences AS occurrence "
    "ON occurrence.id=member.occurrence_id "
    "WHERE receipt.projector_receipt_identity=%s ORDER BY member.set_ordinal"
)
_READ_MODEL_READBACK_SELECT_SQL = (
    "SELECT readback.readback_identity,readback.readback_attempt,"
    "readback.expected_readback_digest,readback.actual_readback_digest,"
    "readback.actual_emitted_occurrence_set_digest,"
    "readback.actual_emitted_occurrence_set_count,"
    "readback.actual_active_membership_set_digest,"
    "readback.actual_active_membership_set_count,"
    "readback.actual_state_event_set_digest,readback.actual_successor_set_digest,"
    "readback.actual_workflow_event_set_digest,"
    "readback.actual_current_alert_fingerprint,readback.readback_result,readback.error_code "
    "FROM historical_baseline_v2_post_commit_readbacks AS readback "
    "INNER JOIN historical_baseline_v2_projector_receipts AS receipt "
    "ON receipt.id=readback.projector_receipt_id "
    "WHERE receipt.projector_receipt_identity=%s "
    "ORDER BY readback.readback_attempt DESC LIMIT 1"
)
_READ_MODEL_ALERT_SELECT_SQL = (
    "SELECT fingerprint,definition_code,definition_version,source_domain,source_identity,"
    "source_version,predicate_active,workflow_status,workflow_version,projection_version,"
    "display_snapshot FROM anomaly_current_alerts WHERE fingerprint=%s"
)
_DELIVERY_INSERT_SQL = (
    "INSERT INTO historical_baseline_v2_projector_deliveries "
    "(delivery_identity,source_trigger_identity,payload_digest,source_kind,source_domain,"
    "source_event_identity,source_version,partition_key,delivery_status,attempt_count,max_attempts) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_DELIVERY_UPDATE_SQL = (
    "UPDATE historical_baseline_v2_projector_deliveries SET projection_sequence=%s,"
    "projector_receipt_id=%s,delivery_status=%s,attempt_count=%s,next_attempt_at=%s,"
    "lease_owner=%s,lease_expires_at=%s,last_error_code=%s "
    "WHERE delivery_identity=%s AND delivery_status=%s AND attempt_count=%s"
)
_CHECKPOINT_SELECT_SQL = (
    "SELECT checkpoint_identity,source_domain,source_stream,partition_key,"
    "last_source_event_identity,last_source_version,last_projection_sequence,"
    "checkpoint_fingerprint FROM historical_baseline_v2_source_checkpoints "
    "WHERE source_domain=%s AND source_stream=%s AND partition_key=%s"
)
_ACTIVE_OCCURRENCES_SELECT_SQL = (
    "SELECT occurrence.*,event.baseline_event_identity FROM historical_baseline_occurrences AS occurrence "
    "INNER JOIN historical_order_operational_baseline_events AS event ON event.id=occurrence.baseline_event_id "
    "INNER JOIN historical_baseline_v2_occurrence_state_events AS state ON state.occurrence_id=occurrence.id "
    "LEFT JOIN historical_baseline_v2_occurrence_state_events AS newer "
    "ON newer.occurrence_id=state.occurrence_id AND newer.resulting_state_version>state.resulting_state_version "
    "WHERE occurrence.case_no=%s AND event.baseline_event_identity=%s "
    "AND occurrence.catalog_identity=%s AND occurrence.catalog_version=%s "
    "AND newer.id IS NULL AND state.state='opened' ORDER BY occurrence.occurrence_identity"
)
_OCCURRENCE_INSERT_SQL = (
    "INSERT INTO historical_baseline_occurrences "
    "(occurrence_identity,case_no,order_identity,baseline_event_id,baseline_receipt_id,"
    "catalog_identity,catalog_version,descriptor_identity,contract_id,contract_version,"
    "step_number,owner_domain,root_identity_kind,root_identity_path,terminal_predicate_id,"
    "terminal_predicate_version,repair_target,repair_capability,observation_variant,"
    "observation_identity,observed_root_identity,owner_source_event_identity,owner_source_version,"
    "terminal_result,unavailable_code,owner_binding_fingerprint) "
    "VALUES (" + ",".join(("%s",) * 26) + ")"
)
_STATE_INSERT_SQL = (
    "INSERT INTO historical_baseline_v2_occurrence_state_events "
    "(state_event_identity,occurrence_id,prior_state_event_id,case_no,order_identity,baseline_event_id,"
    "catalog_identity,catalog_version,descriptor_identity,contract_id,contract_version,"
    "terminal_predicate_id,terminal_predicate_version,owner_event_identity,owner_source_version,"
    "expected_state_version,resulting_state_version,state,owner_binding_fingerprint,"
    "fresh_readback_fingerprint,reason) VALUES (" + ",".join(("%s",) * 21) + ")"
)
_SUCCESSOR_INSERT_SQL = (
    "INSERT INTO historical_baseline_successors "
    "(successor_relation_identity,predecessor_occurrence_id,successor_occurrence_id,case_no,"
    "order_identity,baseline_event_id,catalog_identity,catalog_version,descriptor_identity,"
    "contract_id,contract_version,owner_event_identity,prior_owner_source_version,new_owner_source_version,"
    "terminal_predicate_id,terminal_predicate_version,fresh_readback_fingerprint) "
    "VALUES (" + ",".join(("%s",) * 17) + ")"
)
_ALERT_INSERT_SQL = (
    "INSERT INTO anomaly_current_alerts (fingerprint,definition_code,definition_version,source_domain,"
    "source_identity,source_version,predicate_active,workflow_status,workflow_version,projection_version,"
    "claimed_by,claimed_at,resolved_by,resolved_at,display_snapshot) "
    "VALUES (%s,%s,1,%s,%s,%s,%s,%s,%s,1,%s,%s,%s,%s,%s)"
)
_ALERT_UPDATE_SQL = (
    "UPDATE anomaly_current_alerts SET source_version=%s,predicate_active=%s,workflow_status=%s,"
    "workflow_version=%s,projection_version=projection_version+1,claimed_by=%s,claimed_at=%s,"
    "resolved_by=%s,resolved_at=%s,display_snapshot=%s WHERE fingerprint=%s AND workflow_version=%s"
)
_WORKFLOW_INSERT_SQL = (
    "INSERT INTO anomaly_workflow_events (alert_fingerprint,action,expected_workflow_version,"
    "resulting_workflow_version,actor,reason,correlation_id,idempotency_key) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
)
_RECEIPT_INSERT_SQL = (
    "INSERT INTO historical_baseline_v2_projector_receipts "
    "(projector_receipt_identity,source_trigger_identity,source_trigger_version,payload_digest,idempotency_key,"
    "baseline_event_id,baseline_receipt_id,baseline_outbox_id,case_no,order_identity,catalog_identity,"
    "catalog_version,whole_vector_fingerprint,whole_vector_count,emitted_occurrence_set_digest,"
    "emitted_occurrence_set_count,emitted_occurrence_identities,active_membership_set_digest,active_membership_set_count,umbrella_identity,"
    "projection_sequence,current_alert_fingerprint,expected_readback_digest,result_state) "
    "VALUES (" + ",".join(("%s",) * 24) + ")"
)
_MEMBERSHIP_INSERT_SQL = (
    "INSERT INTO historical_baseline_v2_active_membership_snapshots "
    "(membership_identity,projector_receipt_id,umbrella_identity,set_ordinal,occurrence_id,case_no,"
    "order_identity,baseline_event_id,catalog_identity,catalog_version,projection_sequence) "
    "VALUES (" + ",".join(("%s",) * 11) + ")"
)
_CHECKPOINT_UPSERT_SQL = (
    "INSERT INTO historical_baseline_v2_source_checkpoints "
    "(checkpoint_identity,source_domain,source_stream,partition_key,last_source_event_identity,"
    "last_source_version,last_projection_sequence,checkpoint_fingerprint) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
    "ON DUPLICATE KEY UPDATE last_source_event_identity=VALUES(last_source_event_identity),"
    "last_source_version=VALUES(last_source_version),last_projection_sequence=VALUES(last_projection_sequence),"
    "checkpoint_fingerprint=VALUES(checkpoint_fingerprint)"
)
_READBACK_INSERT_SQL = (
    "INSERT INTO historical_baseline_v2_post_commit_readbacks "
    "(readback_identity,projector_receipt_id,delivery_id,case_no,order_identity,baseline_event_id,"
    "catalog_identity,catalog_version,umbrella_identity,projection_sequence,readback_attempt,"
    "expected_readback_digest,actual_readback_digest,actual_emitted_occurrence_set_digest,"
    "actual_emitted_occurrence_set_count,actual_active_membership_set_digest,"
    "actual_active_membership_set_count,actual_state_event_set_digest,actual_successor_set_digest,"
    "actual_workflow_event_set_digest,actual_current_alert_fingerprint,readback_result,error_code) "
    "VALUES (" + ",".join(("%s",) * 23) + ")"
)


__all__ = [
    "MySqlHistoricalBaselineProjectorRepository",
    "MySqlHistoricalBaselineProjectorUnitOfWork",
]
