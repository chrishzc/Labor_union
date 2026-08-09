"""MySQL persistence for contract security receipts, inbox, mapping, and evidence."""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timedelta, timezone

from pymysql.err import IntegrityError

from domains.contract_integration.contract_event import (
    ContractProjectionStatus,
    VerifiedContractEvent,
    validate_projection_transition,
)
from infrastructure.mysql.line_repository_support import aware_utc, database_utc, mysql_error_code
from subsystems.contract_integration.contracts import ContractEvidenceView


class MySqlContractIntegrationRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def record_security_receipt(self, provider, payload_hash, verified, received_at, correlation_id):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO contract_webhook_security_receipts "
                "(provider,canonical_payload_hash,signature_verified,correlation_id,received_at_utc) "
                "VALUES (%s,%s,%s,%s,%s)",
                (provider, payload_hash, verified, correlation_id, database_utc(received_at)),
            )
            return int(cursor.lastrowid)

    def add_inbox(self, event, minimal_payload_json, received_at):
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(_INSERT_INBOX, _event_values(event, minimal_payload_json, received_at))
                return int(cursor.lastrowid), True
        except IntegrityError as error:
            if mysql_error_code(error) != 1062:
                raise
            return self._existing_event(event), False

    def claim_next(self, worker_id: str):
        now = datetime.now(timezone.utc)
        with self._connection.cursor() as cursor:
            cursor.execute(_CLAIM_NEXT, (database_utc(now), database_utc(now)))
            row = cursor.fetchone()
            if row is None:
                return None
            cursor.execute(
                "UPDATE contract_webhook_inbox SET processing_status='verified',"
                "processing_attempts=processing_attempts+1,lease_owner=%s,lease_expires_at_utc=%s "
                "WHERE id=%s AND processing_status IN ('received','retry_pending')",
                (worker_id, database_utc(now + timedelta(seconds=60)), row["id"]),
            )
        return _evidence(row)

    # Status validation, event, outbox, and inbox completion are one atomic evidence commit.
    def apply_verified_evidence(self, evidence):
        if evidence.internal_contract_identity is None:
            self.reject(evidence.inbox_id, "contract_mapping_not_found", status="normalized")
            return
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT contract_status FROM external_contract_events "
                "WHERE provider=%s AND provider_contract_id=%s "
                "ORDER BY occurred_at_utc DESC,id DESC LIMIT 1",
                (evidence.event.provider, evidence.event.provider_contract_id),
            )
            previous = cursor.fetchone()
            current = ContractProjectionStatus(previous["contract_status"]) if previous else None
            validate_projection_transition(current, evidence.event.contract_status)
            cursor.execute(_INSERT_EXTERNAL_EVENT, _external_values(evidence))
            event_id = int(cursor.lastrowid)
            cursor.execute(
                "INSERT INTO contract_evidence_outbox "
                "(external_event_id,aggregate_identity,payload_snapshot,idempotency_key) "
                "VALUES (%s,%s,%s,%s)",
                (event_id, evidence.internal_contract_identity, _evidence_payload(evidence),
                 f"contract-evidence:{evidence.event.provider}:{evidence.event.provider_event_id}"),
            )
            cursor.execute(
                "UPDATE contract_webhook_inbox SET processing_status='applied',"
                "lease_owner=NULL,lease_expires_at_utc=NULL,last_error_code=NULL,"
                "applied_at_utc=CURRENT_TIMESTAMP(6) WHERE id=%s",
                (evidence.inbox_id,),
            )

    def reject(self, inbox_id: int, error_code: str, status: str = "rejected"):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE contract_webhook_inbox SET processing_status=%s,last_error_code=%s,"
                "lease_owner=NULL,lease_expires_at_utc=NULL WHERE id=%s",
                (status, error_code, inbox_id),
            )

    def list_evidence(
        self,
        limit: int,
        provider_contract_id: str | None = None,
        processing_status: str | None = None,
        before_inbox_id: int | None = None,
    ):
        with self._connection.cursor() as cursor:
            cursor.execute(
                _LIST_EVIDENCE,
                (
                    provider_contract_id,
                    provider_contract_id,
                    processing_status,
                    processing_status,
                    before_inbox_id,
                    before_inbox_id,
                    limit,
                ),
            )
            rows = cursor.fetchall() or ()
        return tuple(_evidence(row) for row in rows)

    # CAS mapping, immutable audit, and unblocking inbox rows share one locked transaction.
    def map_contract(self, command):
        fingerprint = _mapping_fingerprint(command)
        with self._connection.cursor() as cursor:
            existing = _existing_mapping_event(cursor, command.idempotency_key.value)
            if existing is not None:
                if existing["payload_fingerprint"] != fingerprint:
                    raise RuntimeError("contract_mapping_idempotency_conflict")
                return int(existing["resulting_version"])
            cursor.execute(
                "SELECT id,version,internal_contract_identity FROM contract_provider_mappings "
                "WHERE provider=%s AND provider_contract_id=%s FOR UPDATE",
                (command.provider, command.provider_contract_id),
            )
            row = cursor.fetchone()
            if row is None:
                if command.expected_version != 0:
                    raise RuntimeError("contract_mapping_version_conflict")
                cursor.execute(_INSERT_MAPPING, _mapping_values(command))
                mapping_id = int(cursor.lastrowid)
                resulting_version = 0
                _insert_mapping_event(cursor, mapping_id, resulting_version, command, fingerprint)
                return resulting_version
            if int(row["version"]) != command.expected_version:
                raise RuntimeError("contract_mapping_version_conflict")
            cursor.execute(_UPDATE_MAPPING, (
                command.internal_contract_identity,
                command.actor.actor_id,
                command.provider,
                command.provider_contract_id,
                command.expected_version,
            ))
            resulting_version = command.expected_version + 1
            _insert_mapping_event(cursor, int(row["id"]), resulting_version, command, fingerprint)
            cursor.execute(
                "UPDATE contract_webhook_inbox SET processing_status='received',"
                "available_at_utc=CURRENT_TIMESTAMP(6),last_error_code=NULL "
                "WHERE provider=%s AND provider_contract_id=%s "
                "AND processing_status='normalized'",
                (command.provider, command.provider_contract_id),
            )
            return resulting_version

    def next_due_at(self):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT MIN(available_at_utc) AS due_at FROM contract_webhook_inbox "
                "WHERE processing_status IN ('received','retry_pending')"
            )
            row = cursor.fetchone()
        return None if not row or row["due_at"] is None else aware_utc(row["due_at"])

    def _existing_event(self, event):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id,canonical_payload_hash FROM contract_webhook_inbox "
                "WHERE provider=%s AND provider_event_id=%s",
                (event.provider, event.provider_event_id),
            )
            row = cursor.fetchone()
        if row is None or row["canonical_payload_hash"] != event.canonical_payload_hash:
            raise RuntimeError("external_event_payload_conflict")
        return int(row["id"])


def _event_values(event, minimal_payload_json, received_at):
    return (
        event.provider, event.provider_event_id, event.provider_contract_id,
        event.event_type, event.contract_status.value, database_utc(event.occurred_at),
        event.canonical_payload_hash, minimal_payload_json, database_utc(received_at),
    )


def _evidence(row):
    event = VerifiedContractEvent(
        str(row["provider"]), str(row["provider_contract_id"]),
        str(row["provider_event_id"]), str(row["provider_event_type"]),
        ContractProjectionStatus(str(row["provider_contract_status"])),
        aware_utc(row["provider_occurred_at_utc"]), str(row["canonical_payload_hash"]),
    )
    return ContractEvidenceView(
        int(row["id"]), event, row.get("internal_contract_identity"),
        str(row["processing_status"]), int(row["processing_attempts"]),
        row.get("last_error_code"), int(row.get("mapping_version") or 0),
    )


def _external_values(evidence):
    event = evidence.event
    return (
        evidence.inbox_id, event.provider, event.provider_event_id,
        event.provider_contract_id, evidence.internal_contract_identity,
        event.event_type, event.contract_status.value, event.canonical_payload_hash,
        database_utc(event.occurred_at),
    )


def _evidence_payload(evidence):
    event = evidence.event
    return json.dumps({
        "internal_contract_identity": evidence.internal_contract_identity,
        "provider": event.provider,
        "provider_contract_id": event.provider_contract_id,
        "provider_event_id": event.provider_event_id,
        "status": event.contract_status.value,
    }, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _mapping_values(command):
    return (
        command.provider, command.provider_contract_id,
        command.internal_contract_identity, command.actor.actor_id,
    )


def _mapping_fingerprint(command):
    payload = json.dumps({
        "provider": command.provider,
        "provider_contract_id": command.provider_contract_id,
        "internal_contract_identity": command.internal_contract_identity,
        "expected_version": command.expected_version,
        "reason": command.reason,
    }, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _existing_mapping_event(cursor, idempotency_key):
    cursor.execute(
        "SELECT resulting_version,payload_fingerprint FROM contract_mapping_events "
        "WHERE idempotency_key=%s",
        (idempotency_key,),
    )
    return cursor.fetchone()


def _insert_mapping_event(cursor, mapping_id, resulting_version, command, fingerprint):
    cursor.execute(
        "INSERT INTO contract_mapping_events "
        "(mapping_id,provider,provider_contract_id,internal_contract_identity,resulting_version,"
        "actor_id,reason,idempotency_key,payload_fingerprint) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (mapping_id, command.provider, command.provider_contract_id,
         command.internal_contract_identity, resulting_version, command.actor.actor_id,
         command.reason, command.idempotency_key.value, fingerprint),
    )


_INSERT_INBOX = """INSERT INTO contract_webhook_inbox
(provider,provider_event_id,provider_contract_id,provider_event_type,
provider_contract_status,provider_occurred_at_utc,canonical_payload_hash,
minimal_payload_json,received_at_utc) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
_CLAIM_NEXT = """SELECT i.*,m.internal_contract_identity,m.version AS mapping_version FROM contract_webhook_inbox i
LEFT JOIN contract_provider_mappings m ON m.provider=i.provider
AND m.provider_contract_id=i.provider_contract_id AND m.mapping_status='active'
WHERE i.processing_status IN ('received','retry_pending') AND i.available_at_utc<=%s
AND (i.lease_expires_at_utc IS NULL OR i.lease_expires_at_utc<=%s)
ORDER BY i.available_at_utc,i.id LIMIT 1 FOR UPDATE SKIP LOCKED"""
_LIST_EVIDENCE = """SELECT i.*,m.internal_contract_identity,m.version AS mapping_version FROM contract_webhook_inbox i
LEFT JOIN contract_provider_mappings m ON m.provider=i.provider
AND m.provider_contract_id=i.provider_contract_id AND m.mapping_status='active'
WHERE (%s IS NULL OR i.provider_contract_id=%s)
AND (%s IS NULL OR i.processing_status=%s)
AND (%s IS NULL OR i.id<%s)
ORDER BY i.received_at_utc DESC,i.id DESC LIMIT %s"""
_INSERT_EXTERNAL_EVENT = """INSERT INTO external_contract_events
(inbox_id,provider,provider_event_id,provider_contract_id,internal_contract_identity,
event_type,contract_status,canonical_payload_hash,occurred_at_utc)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
_INSERT_MAPPING = """INSERT INTO contract_provider_mappings
(provider,provider_contract_id,internal_contract_identity,mapped_by_actor_id)
VALUES (%s,%s,%s,%s)"""
_UPDATE_MAPPING = """UPDATE contract_provider_mappings SET internal_contract_identity=%s,
mapped_by_actor_id=%s,mapped_at_utc=CURRENT_TIMESTAMP(6),version=version+1
WHERE provider=%s AND provider_contract_id=%s AND version=%s"""


__all__ = ["MySqlContractIntegrationRepository"]
