"""
File: historical_operational_baseline_repository.py
Description: 鎖定歷史 Orders 根事實並原子追加 baseline event、receipt 與專屬 outbox。
"""

from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import json

from domains.orders.historical_operational_baseline import (
    HistoricalBaselineLineage,
    HistoricalOperationalBaselineCandidate,
    HistoricalOperationalBaselineFacts,
    HistoricalOrderIdentity,
    HistoricalOrderProvenanceIdentity,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import IdempotencyKey
from shared_kernel.ports import OutboxIntent
from subsystems.orders.historical_operational_baseline_workflow import (
    ApplyHistoricalOperationalBaseline,
    HistoricalOperationalBaselinePersisted,
    HistoricalOperationalBaselineReceipt,
    StoredHistoricalOperationalBaselineReceipt,
)


class HistoricalOperationalBaselineMySqlUnitOfWork(MySqlUnitOfWork):
    """Names the workflow that owns the shared MySQL transaction."""


class MySqlHistoricalOperationalBaselineRepository:
    """B1 append-only persistence adapter; it never commits or rolls back."""

    def __init__(self, connection) -> None:
        self._connection = connection

    def load_facts(
        self,
        identity: HistoricalOrderIdentity,
        *,
        for_update: bool,
    ) -> HistoricalOperationalBaselineFacts | None:
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT o.case_no,o.lifecycle_version,adoption.source_event_identity,"
                "adoption.id AS source_version "
                "FROM orders o JOIN historical_order_adoption_receipts adoption "
                "ON adoption.case_no=o.case_no "
                "WHERE o.case_no=%s AND adoption.outcome='adopted' "
                "ORDER BY adoption.id DESC LIMIT 1" + suffix,
                (identity.case_no,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            order_identity = _order_identity(str(row["case_no"]))
            if identity.order_identity != order_identity:
                return None
            cursor.execute(
                "SELECT baseline_event_identity,order_identity,case_no,selected_step,"
                "resulting_orders_version,owner_binding_fingerprint "
                "FROM historical_order_operational_baseline_events "
                "WHERE case_no=%s ORDER BY id DESC LIMIT 1" + suffix,
                (identity.case_no,),
            )
            baseline_row = cursor.fetchone()

        provenance = HistoricalOrderProvenanceIdentity(
            str(row["source_event_identity"]),
            int(row["source_version"]),
        )
        orders_version = int(row["lifecycle_version"])
        owner_binding_fingerprint = _owner_binding_fingerprint(
            identity,
            provenance,
            orders_version,
        )
        lineage = (
            None
            if baseline_row is None
            else HistoricalBaselineLineage(
                str(baseline_row["baseline_event_identity"]),
                HistoricalOrderIdentity(
                    str(baseline_row["order_identity"]),
                    str(baseline_row["case_no"]),
                ),
                int(baseline_row["selected_step"]),
                int(baseline_row["resulting_orders_version"]),
                PreviewFingerprint(str(baseline_row["owner_binding_fingerprint"])),
            )
        )
        return HistoricalOperationalBaselineFacts(
            identity,
            provenance,
            orders_version,
            owner_binding_fingerprint,
            lineage,
        )

    def find_receipt(
        self,
        key: IdempotencyKey,
        *,
        for_update: bool,
    ) -> StoredHistoricalOperationalBaselineReceipt | None:
        suffix = " FOR UPDATE" if for_update else ""
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT receipt.command_fingerprint,receipt.receipt_identity,"
                "receipt.preview_fingerprint,receipt.resulting_orders_version,"
                "event.baseline_event_identity,event.order_identity,event.case_no,"
                "event.selected_step "
                "FROM historical_order_operational_baseline_receipts receipt "
                "JOIN historical_order_operational_baseline_events event "
                "ON event.id=receipt.event_id "
                "WHERE receipt.idempotency_key=%s" + suffix,
                (key.value,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        command_fingerprint = PreviewFingerprint(str(row["command_fingerprint"]))
        receipt = HistoricalOperationalBaselineReceipt(
            HistoricalOrderIdentity(
                str(row["order_identity"]),
                str(row["case_no"]),
            ),
            str(row["baseline_event_identity"]),
            str(row["receipt_identity"]),
            int(row["selected_step"]),
            int(row["resulting_orders_version"]),
            PreviewFingerprint(str(row["preview_fingerprint"])),
            command_fingerprint,
        )
        return StoredHistoricalOperationalBaselineReceipt(
            command_fingerprint,
            receipt,
        )

    def append_baseline(
        self,
        command: ApplyHistoricalOperationalBaseline,
        candidate: HistoricalOperationalBaselineCandidate,
        command_fingerprint: PreviewFingerprint,
    ) -> HistoricalOperationalBaselinePersisted:
        prior_event_id = self._prior_event_id(candidate)
        baseline_event_identity = _identity(
            "historical-operational-baseline-event",
            command.idempotency_key.value,
        )
        receipt_identity = _identity(
            "historical-operational-baseline-receipt",
            command.idempotency_key.value,
        )
        step_projection = [
            {"step": item.step, "state": item.state.value}
            for item in candidate.step_projection
        ]
        candidate_snapshot = {
            **candidate.canonical_payload,
            "candidate_fingerprint": candidate.fingerprint.value,
        }
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO historical_order_operational_baseline_events "
                "(baseline_event_identity,prior_baseline_event_id,order_identity,case_no,"
                "source_event_identity,source_version,selected_step,expected_orders_version,"
                "resulting_orders_version,owner_binding_fingerprint,evidence_mode,reason,"
                "evidence_reference,document_kind,affected_steps,candidate_snapshot,"
                "step_projection,preview_fingerprint,command_fingerprint,actor,correlation_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    baseline_event_identity,
                    prior_event_id,
                    candidate.identity.order_identity,
                    candidate.identity.case_no,
                    candidate.historical_provenance.source_event_identity,
                    candidate.historical_provenance.source_version,
                    candidate.selected_step,
                    candidate.expected_orders_version,
                    candidate.current_orders_version,
                    candidate.current_owner_binding_fingerprint.value,
                    candidate.evidence_mode.value,
                    candidate.reason,
                    candidate.evidence_reference,
                    candidate.document_kind,
                    None
                    if candidate.affected_steps is None
                    else _json(candidate.affected_steps),
                    _json(candidate_snapshot),
                    _json(step_projection),
                    command.preview_fingerprint.value,
                    command_fingerprint.value,
                    command.actor.actor_id,
                    command.correlation_id.value,
                ),
            )
        return HistoricalOperationalBaselinePersisted(
            baseline_event_identity,
            receipt_identity,
            candidate.current_orders_version,
        )

    def save_receipt(
        self,
        key: IdempotencyKey,
        stored: StoredHistoricalOperationalBaselineReceipt,
    ) -> None:
        receipt = stored.receipt
        result_snapshot = {
            "order_identity": receipt.identity.order_identity,
            "case_no": receipt.identity.case_no,
            "baseline_event_identity": receipt.baseline_event_identity,
            "receipt_identity": receipt.receipt_identity,
            "selected_step": receipt.selected_step,
            "resulting_orders_version": receipt.resulting_orders_version,
            "preview_fingerprint": receipt.preview_fingerprint.value,
            "command_fingerprint": receipt.command_fingerprint.value,
        }
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO historical_order_operational_baseline_receipts "
                "(receipt_identity,event_id,idempotency_key,command_fingerprint,"
                "preview_fingerprint,resulting_orders_version,result_snapshot,actor,"
                "correlation_id) "
                "SELECT %s,event.id,%s,%s,%s,%s,%s,event.actor,event.correlation_id "
                "FROM historical_order_operational_baseline_events event "
                "WHERE event.baseline_event_identity=%s",
                (
                    receipt.receipt_identity,
                    key.value,
                    stored.command_fingerprint.value,
                    receipt.preview_fingerprint.value,
                    receipt.resulting_orders_version,
                    _json(result_snapshot),
                    receipt.baseline_event_identity,
                ),
            )
            if int(cursor.rowcount) != 1:
                raise RuntimeError(
                    "historical_operational_baseline_receipt_event_missing"
                )

    def _prior_event_id(
        self,
        candidate: HistoricalOperationalBaselineCandidate,
    ) -> int | None:
        prior = candidate.prior_baseline_lineage
        if prior is None:
            return None
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "SELECT id,order_identity,case_no FROM "
                "historical_order_operational_baseline_events "
                "WHERE baseline_event_identity=%s FOR UPDATE",
                (prior.event_identity,),
            )
            row = cursor.fetchone()
        if row is None:
            raise ValueError("historical_baseline_prior_lineage_missing")
        if (
            str(row["order_identity"]) != candidate.identity.order_identity
            or str(row["case_no"]) != candidate.identity.case_no
        ):
            raise ValueError("historical_baseline_prior_identity_mismatch")
        return int(row["id"])


class MySqlHistoricalOperationalBaselineOutbox:
    """Writes the B1 baseline-owned outbox inside the caller's transaction."""

    def __init__(self, connection) -> None:
        self._connection = connection

    def append(self, intent: OutboxIntent) -> int:
        snapshot = json.loads(intent.payload_json)
        if not isinstance(snapshot, dict):
            raise ValueError("historical_operational_baseline_outbox_payload_invalid")
        event_identity = str(snapshot.get("baseline_event_identity", ""))
        receipt_identity = str(snapshot.get("receipt_identity", ""))
        with _cursor(self._connection) as cursor:
            cursor.execute(
                "INSERT INTO historical_order_operational_baseline_outbox "
                "(event_id,receipt_id,intent_key,intent_type,bounded_snapshot) "
                "SELECT event.id,receipt.id,%s,%s,%s "
                "FROM historical_order_operational_baseline_events event "
                "JOIN historical_order_operational_baseline_receipts receipt "
                "ON receipt.event_id=event.id "
                "WHERE event.baseline_event_identity=%s "
                "AND receipt.receipt_identity=%s",
                (
                    intent.idempotency_identity,
                    intent.intent_type,
                    intent.payload_json,
                    event_identity,
                    receipt_identity,
                ),
            )
            if int(cursor.rowcount) != 1:
                raise RuntimeError(
                    "historical_operational_baseline_outbox_binding_missing"
                )
            return int(cursor.lastrowid)


def canonical_historical_order_identity(case_no: str) -> HistoricalOrderIdentity:
    """Build the one public identity accepted by this Orders adapter."""

    return HistoricalOrderIdentity(_order_identity(case_no), case_no)


def _order_identity(case_no: str) -> str:
    return f"order:{case_no}"


def _owner_binding_fingerprint(
    identity: HistoricalOrderIdentity,
    provenance: HistoricalOrderProvenanceIdentity,
    orders_version: int,
) -> PreviewFingerprint:
    return fingerprint_payload(
        {
            "order_identity": identity.order_identity,
            "case_no": identity.case_no,
            "orders_version": orders_version,
            "historical_source_event_identity": provenance.source_event_identity,
            "historical_source_version": provenance.source_version,
        }
    )


def _identity(namespace: str, value: str) -> str:
    return f"{namespace}:{sha256(value.encode('utf-8')).hexdigest()}"


def _json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


@contextmanager
def _cursor(connection):
    cursor = connection.cursor()
    try:
        yield cursor
    finally:
        cursor.close()


__all__ = [
    "HistoricalOperationalBaselineMySqlUnitOfWork",
    "MySqlHistoricalOperationalBaselineOutbox",
    "MySqlHistoricalOperationalBaselineRepository",
    "canonical_historical_order_identity",
]
