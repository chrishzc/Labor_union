"""Append Contract Signing command receipts and committed outbox intents."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def append_command_receipt(
    connection: Any, *, idempotency_key: str, command_kind: str, case_no: str,
    document_version_id: int, signing_event_id: int, correlation_id: str,
    result_snapshot: dict[str, object],
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO contract_signing_command_receipts "
            "(idempotency_key,command_fingerprint,command_kind,case_no,document_version_id,signing_event_id,correlation_id,result_snapshot) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (idempotency_key, _fingerprint(command_kind, case_no, result_snapshot), command_kind,
             case_no, document_version_id, signing_event_id, correlation_id,
             _canonical_json(result_snapshot)),
        )


def append_outbox_intent(
    connection: Any, *, case_no: str, signing_event_id: int, intent_key: str,
    intent_type: str, payload_snapshot: dict[str, object],
) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO contract_signing_outbox "
            "(case_no,signing_event_id,intent_key,intent_type,payload_snapshot) VALUES (%s,%s,%s,%s,%s)",
            (case_no, signing_event_id, intent_key, intent_type, _canonical_json(payload_snapshot)),
        )


def _fingerprint(command_kind: str, case_no: str, snapshot: dict[str, object]) -> str:
    return hashlib.sha256(_canonical_json({"kind": command_kind, "case_no": case_no, "result": snapshot}).encode()).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
