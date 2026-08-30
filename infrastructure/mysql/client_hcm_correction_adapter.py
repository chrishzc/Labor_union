"""Borrowed-transaction adapter for the Client HCM correction command."""

from __future__ import annotations

import hashlib
import json
from typing import Mapping

from domains.clients.hcm_correction import (
    ClientHcmCorrectionCommand,
    ClientHcmCorrectionReceipt,
)
from shared_kernel.fingerprints import fingerprint_payload


class MySqlClientHcmCorrectionAdapter:
    """Persist one Client correction without owning a transaction."""

    def __init__(self, connection) -> None:
        self._connection = connection

    def apply_in_current_uow(
        self, command: ClientHcmCorrectionCommand
    ) -> ClientHcmCorrectionReceipt:
        existing = self.find_receipt(command.idempotency_key)
        command_fingerprint = _command_fingerprint(command)
        if existing is not None:
            stored_fingerprint, receipt = existing
            if stored_fingerprint != command_fingerprint:
                raise ValueError("client_hcm_correction_idempotency_conflict")
            return ClientHcmCorrectionReceipt(
                receipt.event_identity, receipt.client_id, receipt.case_no,
                receipt.resulting_client_version, receipt.field_path,
                receipt.values, True,
            )

        columns = tuple(sorted(str(key) for key in command.values))
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT case_no,client_hcm_correction_version," + ",".join(
                    f"`{column}`" for column in columns
                ) + " FROM clients WHERE id=%s FOR UPDATE",
                (command.client_id,),
            )
            row = cursor.fetchone()
            if row is None or str(row["case_no"]) != command.case_no:
                raise ValueError("client_hcm_correction_root_not_found")
            current_version = int(row["client_hcm_correction_version"])
            if current_version != command.expected_client_version:
                raise ValueError("client_hcm_correction_stale")
            before = {column: row[column] for column in columns}
            assignments = ",".join(
                f"`{column}`=%s" for column in columns
            )
            values = tuple(command.values[column] for column in columns)
            cursor.execute(
                "UPDATE clients SET " + assignments +
                ",client_hcm_correction_version=client_hcm_correction_version+1 "
                "WHERE id=%s AND case_no=%s AND client_hcm_correction_version=%s",
                (*values, command.client_id, command.case_no, command.expected_client_version),
            )
            if int(cursor.rowcount) != 1:
                raise ValueError("client_hcm_correction_stale")
            resulting_version = command.expected_client_version + 1
            after = dict(command.values)
            event_identity = _identity(
                "client-hcm-correction-event",
                f"{command.review_identity}:{command.source_event_identity}:{command.idempotency_key}",
            )
            cursor.execute(
                "INSERT INTO client_hcm_correction_events "
                "(event_identity,client_id,case_no,review_identity,source_event_identity,"
                "field_path,source_fingerprint,expected_client_version,resulting_client_version,"
                "before_values,after_values,actor,reason,correlation_id) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    event_identity, command.client_id, command.case_no,
                    command.review_identity, command.source_event_identity,
                    command.field_path, command.source_fingerprint or _sha(command.source_event_identity),
                    command.expected_client_version, resulting_version,
                    _json(before), _json(after), command.actor, command.reason,
                    command.correlation_id,
                ),
            )
            event_id = int(cursor.lastrowid or 0)
            if event_id <= 0:
                raise RuntimeError("client_hcm_correction_event_insert_failed")
            receipt = ClientHcmCorrectionReceipt(
                event_identity, command.client_id, command.case_no,
                resulting_version, command.field_path, after,
            )
            cursor.execute(
                "INSERT INTO client_hcm_correction_receipts "
                "(idempotency_key,command_fingerprint,correction_event_id,result_snapshot) "
                "VALUES (%s,%s,%s,%s)",
                (command.idempotency_key, command_fingerprint, event_id, _json({
                    "event_identity": receipt.event_identity,
                    "client_id": receipt.client_id,
                    "case_no": receipt.case_no,
                    "resulting_client_version": receipt.resulting_client_version,
                    "field_path": receipt.field_path,
                    "values": receipt.values,
                })),
            )
            return receipt

    def find_receipt(self, idempotency_key: str):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT command_fingerprint,result_snapshot "
                "FROM client_hcm_correction_receipts WHERE idempotency_key=%s",
                (idempotency_key,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        payload = _json_object(row["result_snapshot"])
        return str(row["command_fingerprint"]), ClientHcmCorrectionReceipt(
            str(payload["event_identity"]), int(payload["client_id"]),
            str(payload["case_no"]), int(payload["resulting_client_version"]),
            str(payload["field_path"]), dict(payload["values"]), False,
        )

    def readback(self, client_id: int) -> Mapping[str, object]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id,case_no,client_hcm_correction_version,service_type "
                "FROM clients WHERE id=%s", (client_id,),
            )
            row = cursor.fetchone()
        if row is None:
            raise ValueError("client_hcm_correction_root_not_found")
        return dict(row)


def _command_fingerprint(command: ClientHcmCorrectionCommand) -> str:
    return fingerprint_payload({
        "client_id": command.client_id,
        "case_no": command.case_no,
        "expected_client_version": command.expected_client_version,
        "review_identity": command.review_identity,
        "source_event_identity": command.source_event_identity,
        "field_path": command.field_path,
        "values": dict(sorted(command.values.items())),
        "actor": command.actor,
        "reason": command.reason,
        "correlation_id": command.correlation_id,
        "source_fingerprint": command.source_fingerprint,
    }).value


def _identity(namespace: str, value: str) -> str:
    return f"{namespace}:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _json_object(value: object) -> dict[str, object]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("client_hcm_correction_receipt_invalid")
    return parsed


__all__ = ["MySqlClientHcmCorrectionAdapter"]
