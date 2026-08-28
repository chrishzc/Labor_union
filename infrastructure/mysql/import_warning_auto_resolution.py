"""
File: import_warning_auto_resolution.py
Description: 以已提交 owner event 將既有匯入警示冪等投影為系統自動解除。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

HCM_FIELD_CORRECTION_TERMINAL_PREDICATE = "hcm_validated_field_correction_root_exact"
_TERMINAL_PREDICATE_LOGICAL_CODES = {
    HCM_FIELD_CORRECTION_TERMINAL_PREDICATE: frozenset(
        {"HCM-FIELD-001", "HCM-FIELD-002"}
    ),
}


@dataclass(frozen=True, slots=True)
class ImportWarningReviewResolutionState:
    review_identity: str
    source_row: int
    masked_case_identity: str
    unresolved_occurrence_count: int
    unresolved_issue_codes: tuple[str, ...]

    @property
    def active(self) -> bool:
        return self.unresolved_occurrence_count > 0

    @property
    def unresolved_count(self) -> int:
        return self.unresolved_occurrence_count


def auto_resolve_import_warning_occurrence(
    connection,
    *,
    occurrence_identity: str,
    owning_lane: str,
    owner_event_identity: str,
    projector_identity: str,
    terminal_predicate: str,
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
        terminal_predicate=terminal_predicate,
    )


def load_import_warning_review_resolution_state(
    connection,
    *,
    occurrence_identity: str,
    owning_lane: str,
) -> ImportWarningReviewResolutionState:
    """Read the exact review aggregate after one occurrence transition."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT o.source_receipt_identity AS review_identity,"
            "r.source_row,r.masked_case_identity "
            "FROM import_warning_occurrences o "
            "JOIN case_import_hcm_review_rows r "
            "ON r.review_identity=o.source_receipt_identity "
            "WHERE o.occurrence_identity=%s AND o.owning_lane=%s FOR UPDATE",
            (occurrence_identity, owning_lane),
        )
        review = cursor.fetchone()
        if review is None:
            raise ValueError("import_warning_review_binding_missing")
        cursor.execute(
            "SELECT o.issue_codes,t.tracking_status "
            "FROM import_warning_occurrences o "
            "LEFT JOIN import_warning_current_tasks t ON t.occurrence_id=o.id "
            "WHERE o.source_receipt_identity=%s AND o.owning_lane=%s "
            "ORDER BY o.id FOR UPDATE",
            (str(review["review_identity"]), owning_lane),
        )
        siblings = tuple(cursor.fetchall())
    if not siblings:
        raise ValueError("import_warning_review_occurrences_missing")
    return _review_resolution_state(review, siblings)


def _load_tasks(connection, predicate: str, parameters: tuple[str, str]):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT o.id,o.occurrence_identity,o.logical_code,"
            "t.tracking_status,t.tracking_version "
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
    terminal_predicate: str,
) -> int:
    _require_rulebook_terminal_contract(rows, terminal_predicate)
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


def _require_rulebook_terminal_contract(rows, terminal_predicate: str) -> None:
    allowed_codes = _TERMINAL_PREDICATE_LOGICAL_CODES.get(terminal_predicate)
    if allowed_codes is None:
        raise ValueError("import_warning_auto_resolution_rulebook_contract_missing")
    if any(str(row.get("logical_code")) not in allowed_codes for row in rows):
        raise ValueError("import_warning_auto_resolution_predicate_mismatch")


def _review_resolution_state(review, siblings) -> ImportWarningReviewResolutionState:
    unresolved: list[str] = []
    unresolved_occurrence_count = 0
    for sibling in siblings:
        # Manual tracking closure is not an owning-domain terminal predicate.
        if str(sibling["tracking_status"]) == "auto_resolved":
            continue
        unresolved_occurrence_count += 1
        issue_codes = json.loads(sibling["issue_codes"]) if isinstance(
            sibling["issue_codes"], str
        ) else sibling["issue_codes"]
        if not isinstance(issue_codes, list) or any(
            not isinstance(code, str) or not code.strip() for code in issue_codes
        ):
            raise ValueError("import_warning_review_issue_codes_invalid")
        unresolved.extend(issue_codes)
    return ImportWarningReviewResolutionState(
        review_identity=str(review["review_identity"]),
        source_row=int(review["source_row"]),
        masked_case_identity=str(review["masked_case_identity"]),
        unresolved_occurrence_count=unresolved_occurrence_count,
        unresolved_issue_codes=tuple(sorted(set(unresolved))),
    )


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
    "HCM_FIELD_CORRECTION_TERMINAL_PREDICATE",
    "ImportWarningReviewResolutionState",
    "auto_resolve_import_warning_occurrence",
    "load_import_warning_review_resolution_state",
]
