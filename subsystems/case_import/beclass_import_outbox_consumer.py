"""Consume committed BeClass review outbox events owned by Case Import.

The review row is the canonical source of evidence.  Delivery only validates
that the bounded outbox snapshot still refers to that immutable row, then
acknowledges (or retries) the Case Import owner outbox.  It deliberately does
not materialize a second issue projection or recovery task.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Protocol

from pymysql.err import OperationalError

from domains.case_import.beclass_import_review import (
    BeClassImportSourceKind,
    InvalidBeClassImportRow,
    build_review_identity,
    fingerprint_source_row,
)
from shared_kernel.fingerprints import PreviewFingerprint


MAX_BECLASS_REVIEW_OUTBOX_ATTEMPTS = 3
BECLASS_REVIEW_OUTBOX_RETRY_DELAY_SECONDS = 1
BECLASS_REVIEW_OUTBOX_RETRY_READY_SQL = (
    "(last_error IS NULL OR JSON_VALID(last_error)=0 OR "
    "COALESCE(CAST(JSON_UNQUOTE(JSON_EXTRACT(last_error,'$.retry_after_epoch')) "
    "AS DECIMAL(20,6)),0)<=UNIX_TIMESTAMP(UTC_TIMESTAMP(6)))"
)


class BeClassImportOutboxRuntime(Protocol):
    """The only runtime capability needed for retry bookkeeping."""

    def failure_unit_of_work(self, connection: Any) -> Any: ...


@dataclass(frozen=True, slots=True)
class BeClassImportOutboxResult:
    delivered_count: int
    failed_count: int


def consume_beclass_import_review_events(
    connection,
    *,
    maximum_events: int = 50,
    runtime: BeClassImportOutboxRuntime | None = None,
) -> BeClassImportOutboxResult:
    if not isinstance(maximum_events, int) or not 1 <= maximum_events <= 100:
        raise ValueError("maximum_events must be between 1 and 100")
    if runtime is None:
        raise RuntimeError("beclass_import_outbox_runtime_not_composed")

    delivered = failed = 0
    for _ in range(maximum_events):
        outcome = _consume_next(connection, runtime)
        if outcome is None:
            break
        delivered += int(outcome)
        failed += int(not outcome)
    return BeClassImportOutboxResult(delivered, failed)


def _consume_next(connection, runtime: BeClassImportOutboxRuntime):
    event = None
    try:
        event = _claim_next(connection)
        if event is None:
            connection.rollback()
            return None
        snapshot = _json_object(event["bounded_snapshot"])
        _load_canonical_review_evidence(connection, event, snapshot)
        _mark_delivered(connection, int(event["id"]))
        connection.commit()
        return True
    except OperationalError as error:
        connection.rollback()
        if event is None:
            raise
        _record_failure(connection, event, error, runtime)
        return False
    except Exception as error:
        connection.rollback()
        _record_failure(connection, event, error, runtime)
        return False


def _claim_next(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id,review_row_id,review_event_id,intent_type,bounded_snapshot,created_at "
            "FROM beclass_import_review_outbox WHERE published_at IS NULL "
            f"AND attempts<{MAX_BECLASS_REVIEW_OUTBOX_ATTEMPTS} "
            f"AND {BECLASS_REVIEW_OUTBOX_RETRY_READY_SQL} "
            "ORDER BY id LIMIT 1 FOR UPDATE SKIP LOCKED"
        )
        return cursor.fetchone()


def _load_canonical_review_evidence(connection, event, snapshot) -> Mapping[str, object]:
    """Read and validate the immutable Case Import review root for delivery.

    The outbox snapshot is only a bounded delivery envelope.  It cannot make
    an owner decision or replace the review root.  Any missing, mismatched,
    or malformed canonical fact fails closed and is retried.
    """

    review_row_id = _positive_integer(event.get("review_row_id"), "review row id")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT review_identity,source_kind,source_event_identity,source_sheet,"
            "source_row,masked_identifier,source_fingerprint,source_payload,issue_codes "
            "FROM beclass_import_review_rows WHERE id=%s FOR UPDATE",
            (review_row_id,),
        )
        review = cursor.fetchone()
    if not isinstance(review, Mapping):
        raise RuntimeError("beclass_import_review_root_missing")

    source_kind = BeClassImportSourceKind(str(review["source_kind"]))
    source_event_identity = _canonical_text(review.get("source_event_identity"), "source event identity")
    source_sheet = _canonical_text(review.get("source_sheet"), "source sheet")
    source_row = _positive_integer(review.get("source_row"), "source row")
    masked_identifier = _canonical_text(review.get("masked_identifier"), "masked identifier")
    source_payload = _json_object(review["source_payload"])
    issue_codes = _text_tuple(review["issue_codes"])
    source_fingerprint = _canonical_text(review.get("source_fingerprint"), "source fingerprint")
    review_identity = _canonical_text(review.get("review_identity"), "review identity")

    if review_identity != build_review_identity(source_kind, source_event_identity):
        raise RuntimeError("beclass_import_review_identity_mismatch")
    if source_fingerprint != fingerprint_source_row(
        source_kind,
        source_event_identity,
        source_sheet,
        source_row,
        masked_identifier,
        source_payload,
        issue_codes,
    ).value:
        raise RuntimeError("beclass_import_review_fingerprint_mismatch")
    InvalidBeClassImportRow(
        review_identity,
        source_kind,
        source_event_identity,
        source_sheet,
        source_row,
        masked_identifier,
        source_payload,
        issue_codes,
        PreviewFingerprint(source_fingerprint),
    )

    _validate_snapshot(
        snapshot,
        review_identity,
        source_kind,
        source_sheet,
        source_row,
        masked_identifier,
        issue_codes,
        str(event.get("intent_type")),
    )
    _validate_event_shape(connection, event, review_row_id, review_identity, snapshot)
    return review


def _validate_snapshot(
    snapshot,
    review_identity: str,
    source_kind: BeClassImportSourceKind,
    source_sheet: str,
    source_row: int,
    masked_identifier: str,
    issue_codes: tuple[str, ...],
    intent_type: str,
) -> None:
    required = {
        "review_identity",
        "source_kind",
        "source_sheet",
        "source_row",
        "issue_codes",
        "version",
        "masked_identifier",
        "active",
    }
    if set(snapshot) != required:
        raise ValueError("beclass_import_review_outbox_snapshot_invalid")
    if snapshot["review_identity"] != review_identity:
        raise ValueError("beclass_import_review_outbox_review_identity_mismatch")
    if snapshot["source_kind"] != source_kind.value:
        raise ValueError("beclass_import_review_outbox_source_kind_mismatch")
    if snapshot["source_sheet"] != source_sheet or snapshot["source_row"] != source_row:
        raise ValueError("beclass_import_review_outbox_source_location_mismatch")
    if snapshot["masked_identifier"] != masked_identifier:
        raise ValueError("beclass_import_review_outbox_masked_identifier_mismatch")
    if _text_tuple(snapshot["issue_codes"]) != issue_codes:
        raise ValueError("beclass_import_review_outbox_issue_codes_mismatch")
    expected_snapshot = (
        (0, True) if intent_type == "review_opened" else (1, False)
    )
    if (snapshot["version"], snapshot["active"]) != expected_snapshot:
        raise ValueError("beclass_import_review_outbox_snapshot_state_invalid")


def _validate_event_shape(connection, event, review_row_id: int, review_identity: str, snapshot) -> None:
    intent_type = event.get("intent_type")
    review_event_id = event.get("review_event_id")
    if intent_type == "review_opened":
        if review_event_id is not None:
            raise ValueError("beclass_import_review_opened_event_link_invalid")
        return
    if intent_type != "review_resolved" or not isinstance(review_event_id, int) or review_event_id <= 0:
        raise ValueError("beclass_import_review_outbox_intent_invalid")

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT review_row_id,event_type,expected_version,resulting_version,"
            "corrected_payload,resolved_issue_codes FROM beclass_import_review_events "
            "WHERE id=%s FOR UPDATE",
            (review_event_id,),
        )
        review_event = cursor.fetchone()
    if not isinstance(review_event, Mapping):
        raise RuntimeError("beclass_import_review_event_missing")
    if (
        int(review_event["review_row_id"]) != review_row_id
        or review_event["event_type"] != "resolved"
        or int(review_event["expected_version"]) != 0
        or int(review_event["resulting_version"]) != 1
    ):
        raise ValueError("beclass_import_review_resolution_event_invalid")
    if not isinstance(_json_object(review_event["corrected_payload"]), dict):
        raise ValueError("beclass_import_review_corrected_payload_invalid")
    if _text_tuple(review_event["resolved_issue_codes"]) != _text_tuple(snapshot["issue_codes"]):
        raise ValueError("beclass_import_review_resolution_issue_codes_mismatch")
    if snapshot["review_identity"] != review_identity:
        raise ValueError("beclass_import_review_resolution_identity_mismatch")


def _mark_delivered(connection, event_id: int) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE beclass_import_review_outbox SET published_at=CURRENT_TIMESTAMP,last_error=NULL "
            "WHERE id=%s AND published_at IS NULL",
            (event_id,),
        )
        if int(cursor.rowcount) != 1:
            raise RuntimeError("beclass_import_review_outbox_delivery_conflict")


def _mark_failed(connection, event, error) -> None:
    if not isinstance(event, Mapping) or "id" not in event:
        return None
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE beclass_import_review_outbox SET attempts=attempts+1,"
            "last_error=JSON_OBJECT('error_code',%s,'retry_after_epoch',"
            f"UNIX_TIMESTAMP(DATE_ADD(UTC_TIMESTAMP(6),INTERVAL {BECLASS_REVIEW_OUTBOX_RETRY_DELAY_SECONDS} SECOND)),"
            f"'terminal',attempts+1>={MAX_BECLASS_REVIEW_OUTBOX_ATTEMPTS}) WHERE id=%s",
            (_delivery_error_code(error), int(event["id"])),
        )


def _record_failure(connection, event, error, runtime: BeClassImportOutboxRuntime) -> None:
    if not isinstance(event, Mapping) or "id" not in event:
        return None
    with runtime.failure_unit_of_work(connection) as unit_of_work:
        _mark_failed(connection, event, error)
        unit_of_work.commit()


def _json_object(value: object) -> dict[str, object]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, dict):
        raise ValueError("BeClass review outbox payload must be an object")
    return parsed


def _text_tuple(value: object) -> tuple[str, ...]:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, list) or not parsed or any(not isinstance(item, str) for item in parsed):
        raise ValueError("BeClass review issue codes must be a non-empty array")
    result = tuple(parsed)
    if result != tuple(sorted(set(result))):
        raise ValueError("BeClass review issue codes must be sorted and unique")
    return result


def _canonical_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 191:
        raise ValueError(f"BeClass review {field} is not canonical")
    return value


def _positive_integer(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"BeClass review {field} is not a positive integer")
    return value


def _delivery_error_code(error: Exception) -> str:
    digest = hashlib.sha256(
        f"{type(error).__name__}:{str(error).strip()}".encode("utf-8")
    ).hexdigest()[:16]
    return f"beclass_review_outbox_delivery_failed:{digest}"


__all__ = [
    "BECLASS_REVIEW_OUTBOX_RETRY_DELAY_SECONDS",
    "BECLASS_REVIEW_OUTBOX_RETRY_READY_SQL",
    "BeClassImportOutboxResult",
    "BeClassImportOutboxRuntime",
    "MAX_BECLASS_REVIEW_OUTBOX_ATTEMPTS",
    "consume_beclass_import_review_events",
]
