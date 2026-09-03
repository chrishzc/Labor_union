"""
File: historical_order_workbook_import_repository.py
Description: 保存訂單歷史 workbook 的 command claim 與 terminal receipt，避免整檔重複採納。
"""

from __future__ import annotations

from hashlib import sha256
import json

from domains.orders.lifecycle import OrderLifecycleStatus
from subsystems.orders.historical_order_workbook_import import (
    HistoricalOrderAbsenceCancellation,
)
from subsystems.orders.order_lifecycle_command_envelope import (
    lock_order_lifecycle_command_envelope,
)
from subsystems.orders.order_lifecycle_control_commands import (
    CancellationControlCommand,
    apply_order_lifecycle_control_command,
)


class HistoricalOrderWorkbookImportRepository:
    """Orders adapter over global durable command primitives."""

    _FAMILY = "historical_order_workbook_ingest"

    def __init__(self, connection) -> None:
        self._connection = connection

    def acquire_lock(self, key: str) -> bool:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, 5) AS acquired", (self._lock_name(key),))
            return bool((row := cursor.fetchone()) and row["acquired"] == 1)

    def release_lock(self, key: str) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT RELEASE_LOCK(%s)", (self._lock_name(key),))

    def load_receipt(self, key: str):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT request_fingerprint,result_snapshot FROM admin_command_receipts "
                "WHERE command_family=%s AND idempotency_key=%s",
                (self._FAMILY, key),
            )
            return cursor.fetchone()

    def claim(self, key: str, digest: str, correlation_id: str) -> str:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT IGNORE INTO application_command_claims "
                "(idempotency_key,command_family,aggregate_identity,command_fingerprint,correlation_id) "
                "VALUES (%s,%s,%s,%s,%s)",
                (key, self._FAMILY, digest, digest, correlation_id),
            )
            created = cursor.rowcount == 1
            if not created:
                cursor.execute(
                    "SELECT command_family,command_fingerprint FROM application_command_claims "
                    "WHERE idempotency_key=%s FOR UPDATE",
                    (key,),
                )
                claim = cursor.fetchone()
                if not claim or claim["command_family"] != self._FAMILY or claim["command_fingerprint"] != digest:
                    return "conflict"
        return "created" if created else "resume"

    def save_receipt(self, key: str, digest: str, preview_fingerprint: str, actor: str, result: dict) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO admin_command_receipts "
                "(command_family,idempotency_key,request_fingerprint,preview_fingerprint,actor,reason,result_snapshot) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (self._FAMILY, key, digest, preview_fingerprint, actor, "訂單歷史資料匯入", _json(result)),
            )

    def find_open_review_identities(
        self, source_event_identities: tuple[str, ...]
    ) -> tuple[str, ...]:
        if not source_event_identities:
            return ()
        placeholders = ",".join("%s" for _ in source_event_identities)
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT review.review_identity FROM historical_order_adoption_reviews review "
                "WHERE review.source_event_identity IN (" + placeholders + ") "
                "AND NOT EXISTS (SELECT 1 FROM historical_order_review_remediation_events remediation "
                "WHERE remediation.prior_review_identity=review.review_identity) "
                "ORDER BY review.id",
                source_event_identities,
            )
            rows = cursor.fetchall()
        return tuple(str(row["review_identity"]) for row in rows)

    def find_absent_orders(
        self,
        source_case_nos: tuple[str, ...],
        *,
        for_update: bool,
    ) -> tuple[HistoricalOrderAbsenceCancellation, ...]:
        if not isinstance(source_case_nos, tuple):
            raise TypeError("source_case_nos must be a tuple")
        if any(
            not isinstance(case_no, str)
            or not case_no
            or case_no.strip() != case_no
            for case_no in source_case_nos
        ):
            raise ValueError("source_case_nos contain an invalid case number")
        if type(for_update) is not bool:
            raise TypeError("for_update must be a bool")

        source_case_set = frozenset(source_case_nos)
        lock_suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT case_no,status,lifecycle_version FROM orders "
                "WHERE status<>%s ORDER BY case_no" + lock_suffix,
                (OrderLifecycleStatus.CANCELLED.value,),
            )
            rows = tuple(cursor.fetchall() or ())
        return tuple(
            HistoricalOrderAbsenceCancellation(
                str(row["case_no"]),
                OrderLifecycleStatus(str(row["status"])),
                int(row["lifecycle_version"]),
            )
            for row in rows
            if str(row["case_no"]) not in source_case_set
        )

    def cancel_absent_orders(
        self,
        candidates: tuple[HistoricalOrderAbsenceCancellation, ...],
        *,
        workbook_key: str,
        source_content_digest: str,
        actor: str,
        correlation_id: str,
    ) -> int:
        if not isinstance(candidates, tuple):
            raise TypeError("historical absence candidates must be a tuple")
        if any(not isinstance(item, HistoricalOrderAbsenceCancellation) for item in candidates):
            raise TypeError("historical absence candidate is invalid")
        if not candidates:
            return 0

        cancelled = 0
        with self._connection.cursor() as cursor:
            for candidate in candidates:
                idempotency_key = _absence_idempotency_key(
                    workbook_key, candidate.case_no
                )
                envelope = lock_order_lifecycle_command_envelope(
                    cursor,
                    candidate.case_no,
                    candidate.expected_version,
                    idempotency_key,
                    allow_incomplete_order=True,
                )
                if envelope.current_status != candidate.before_status.value:
                    raise RuntimeError("historical_order_absence_candidate_stale")
                if (
                    envelope.existing_control_event is not None
                    or envelope.existing_lifecycle_event is not None
                ):
                    raise RuntimeError("historical_order_absence_replay_without_workbook_receipt")

                control = apply_order_lifecycle_control_command(
                    cursor,
                    envelope,
                    CancellationControlCommand(
                        "activate",
                        actor,
                        "historical_order_adoption:authoritative_workbook_absence",
                        candidate.expected_version,
                        idempotency_key,
                    ),
                )
                cursor.execute(
                    "UPDATE orders SET status=%s,lifecycle_version=%s "
                    "WHERE case_no=%s AND status=%s AND lifecycle_version=%s",
                    (
                        OrderLifecycleStatus.CANCELLED.value,
                        candidate.expected_version + 1,
                        candidate.case_no,
                        candidate.before_status.value,
                        candidate.expected_version,
                    ),
                )
                if int(cursor.rowcount) != 1:
                    raise RuntimeError("historical_order_absence_candidate_stale")

                cursor.execute(
                    "INSERT INTO order_lifecycle_state_events "
                    "(case_no,trigger_event,before_status,after_status,actor,business_date,"
                    "expected_version,idempotency_key,facts_snapshot) "
                    "VALUES (%s,'historical_order_adoption',%s,%s,%s,CURRENT_DATE,%s,%s,%s)",
                    (
                        candidate.case_no,
                        candidate.before_status.value,
                        OrderLifecycleStatus.CANCELLED.value,
                        actor,
                        candidate.expected_version,
                        idempotency_key,
                        _json({
                            "lifecycle_origin": "historical_order_authoritative_workbook_absence",
                            "source_content_digest": source_content_digest,
                            "correlation_id": correlation_id,
                            "cancellation_control_event_id": control.event_id,
                            "side_effects_suppressed": True,
                        }),
                    ),
                )
                if int(cursor.rowcount) != 1:
                    raise RuntimeError("historical_order_absence_lifecycle_event_not_written")
                cancelled += 1
        return cancelled

    @staticmethod
    def _lock_name(key: str) -> str:
        del key
        return "order-history:authoritative-workbook"


def _absence_idempotency_key(workbook_key: str, case_no: str) -> str:
    if not isinstance(workbook_key, str) or not workbook_key:
        raise ValueError("historical workbook key is invalid")
    identity = sha256(f"{workbook_key}:{case_no}".encode("utf-8")).hexdigest()
    return f"historical-order-absence:{identity}"


def _json(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
