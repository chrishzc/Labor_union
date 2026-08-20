"""
File: import_warning_auto_resolution.py
Description: 以已提交 owner event 將既有匯入警示冪等投影為系統自動解除。
"""

from __future__ import annotations

import hashlib
import json


def auto_resolve_import_warning_occurrence(
    connection,
    *,
    occurrence_identity: str,
    owning_lane: str,
    owner_event_identity: str,
    projector_identity: str,
) -> int:
    """Resolve one existing occurrence; an absent occurrence is a valid no-op."""
    rows = _load_tasks(
        connection,
        "o.occurrence_identity=%s AND o.owning_lane=%s",
        (occurrence_identity, owning_lane),
    )
    return _resolve_rows(
        connection,
        rows,
        owner_event_identity=owner_event_identity,
        projector_identity=projector_identity,
    )


def _load_tasks(connection, predicate: str, parameters: tuple[str, str]):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT o.id,o.occurrence_identity,t.tracking_status,t.tracking_version "
            "FROM import_warning_occurrences o JOIN import_warning_current_tasks t "
            "ON t.occurrence_id=o.id WHERE " + predicate + " FOR UPDATE",
            parameters,
        )
        return tuple(cursor.fetchall())


def _resolve_rows(
    connection,
    rows,
    *,
    owner_event_identity: str,
    projector_identity: str,
) -> int:
    resolved_count = 0
    for row in rows:
        if str(row["tracking_status"]) == "auto_resolved":
            continue
        _append_auto_resolved_event(
            connection,
            row,
            owner_event_identity=owner_event_identity,
            projector_identity=projector_identity,
        )
        resolved_count += 1
    return resolved_count


def _append_auto_resolved_event(
    connection,
    row,
    *,
    owner_event_identity: str,
    projector_identity: str,
) -> None:
    occurrence_identity = str(row["occurrence_identity"])
    occurrence_id = int(row["id"])
    expected_version = int(row["tracking_version"])
    resulting_version = expected_version + 1
    idempotency_key = _identity(
        "import-warning-auto-resolve",
        f"{owner_event_identity}:{occurrence_identity}",
    )
    fingerprint = _identity(
        "import-warning-auto-resolve-fingerprint",
        f"{owner_event_identity}:{occurrence_identity}:{expected_version}",
    )
    correlation_id = _identity(
        "import-warning-auto-resolve-correlation", owner_event_identity
    )
    snapshot = {
        "occurrence_identity": occurrence_identity,
        "expected_version": expected_version,
        "resulting_status": "auto_resolved",
        "resulting_version": resulting_version,
    }
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO import_warning_tracking_events "
            "(event_identity,occurrence_id,action,before_status,after_status,"
            "expected_version,resulting_version,actor_kind,actor_identity,reason_code,"
            "command_fingerprint,idempotency_key,correlation_id) "
            "VALUES (%s,%s,'auto_resolved',%s,'auto_resolved',%s,%s,'system',%s,"
            "'root_predicate_cleared',%s,%s,%s)",
            (
                idempotency_key,
                occurrence_id,
                str(row["tracking_status"]),
                expected_version,
                resulting_version,
                projector_identity,
                fingerprint,
                idempotency_key,
                correlation_id,
            ),
        )
        tracking_event_id = int(cursor.lastrowid or 0)
        if tracking_event_id <= 0:
            raise RuntimeError("import_warning_auto_resolve_event_missing")
        cursor.execute(
            "UPDATE import_warning_current_tasks SET tracking_status='auto_resolved',"
            "tracking_version=%s,last_event_id=%s,last_event_at=CURRENT_TIMESTAMP "
            "WHERE occurrence_id=%s AND tracking_version=%s",
            (resulting_version, tracking_event_id, occurrence_id, expected_version),
        )
        if int(cursor.rowcount) != 1:
            raise RuntimeError("import_warning_auto_resolve_version_conflict")
        cursor.execute(
            "INSERT INTO import_warning_tracking_receipts "
            "(idempotency_key,command_fingerprint,occurrence_id,tracking_event_id,"
            "expected_version,resulting_version,result_snapshot) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (
                idempotency_key,
                fingerprint,
                occurrence_id,
                tracking_event_id,
                expected_version,
                resulting_version,
                _json(snapshot),
            ),
        )
        cursor.execute(
            "INSERT INTO import_warning_tracking_outbox "
            "(tracking_event_id,intent_key,bounded_snapshot) VALUES (%s,%s,%s)",
            (
                tracking_event_id,
                _identity("import-warning-auto-resolve-outbox", idempotency_key),
                _json(
                    {
                        "occurrence_identity": occurrence_identity,
                        "tracking_status": "auto_resolved",
                        "tracking_version": resulting_version,
                    }
                ),
            ),
        )


def _identity(namespace: str, value: str) -> str:
    return hashlib.sha256(f"{namespace}:{value}".encode("utf-8")).hexdigest()


def _json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


__all__ = [
    "auto_resolve_import_warning_occurrence",
]
