"""MySQL persistence adapter for LINE safe-review-link roots."""

from __future__ import annotations

import json
from datetime import datetime


class MySqlLineSafeReviewLinkRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def get_link(self, link_id: str, *, for_update: bool = False):
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM line_safe_review_links WHERE link_id=%s" + suffix,
                (link_id,),
            )
            return cursor.fetchone()

    def insert_link(self, **values) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO line_safe_review_links
                (link_id,token_digest,canonical_internal_target,target_version,
                 source_alert_identity,allowed_actor_ref,required_capability,status,
                 issued_at_utc,expires_at_utc,idempotency_key,correlation_id)
                VALUES (%(link_id)s,%(token_digest)s,%(canonical_internal_target)s,%(target_version)s,
                        %(source_alert_identity)s,%(allowed_actor_ref)s,%(required_capability)s,'issued',
                        %(issued_at)s,%(expires_at)s,%(idempotency_key)s,%(correlation_id)s)""",
                values,
            )
            return int(cursor.lastrowid)

    def transition(self, link_pk: int, status: str, at: datetime) -> None:
        field = "redeemed_at_utc" if status == "redeemed" else "revoked_at_utc" if status == "revoked" else None
        if status not in {"redeemed", "revoked", "expired"}:
            raise ValueError("unsupported safe review link transition")
        if field:
            sql = f"UPDATE line_safe_review_links SET status=%s, {field}=%s, root_version=root_version+1 WHERE id=%s AND status='issued'"
            params = (status, at, link_pk)
        else:
            sql = "UPDATE line_safe_review_links SET status=%s, root_version=root_version+1 WHERE id=%s AND status='issued'"
            params = (status, link_pk)
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            if cursor.rowcount != 1:
                raise RuntimeError("safe review link transition lost race")

    def insert_event(self, link_pk: int, event_type: str, actor_ref: str, resulting_status: str,
                     target_version: int, idempotency_key: str, correlation_id: str, payload: dict) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO line_safe_review_link_events
                (link_id,event_type,actor_ref,resulting_status,target_version,idempotency_key,
                 correlation_id,event_payload,occurred_at_utc)
                SELECT id,%s,%s,%s,%s,%s,%s,%s,UTC_TIMESTAMP(6)
                FROM line_safe_review_links WHERE id=%s""",
                (event_type, actor_ref, resulting_status, target_version, idempotency_key,
                 correlation_id, json.dumps(payload, ensure_ascii=False, separators=(",", ":")), link_pk),
            )

    def insert_receipt(self, idempotency_key: str, command_fingerprint: str, outcome: str,
                       result_snapshot: dict, link_pk: int) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO line_safe_review_link_receipts
                (idempotency_key,link_id,command_fingerprint,outcome,result_snapshot)
                VALUES (%s,%s,%s,%s,%s)""",
                (idempotency_key, link_pk, command_fingerprint, outcome,
                 json.dumps(result_snapshot, ensure_ascii=False, separators=(",", ":"))),
            )

    def insert_outbox(self, link_pk: int, idempotency_key: str, correlation_id: str,
                      payload: dict) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO line_safe_review_link_outbox
                (link_id,intent_type,target_owner,intent_payload,idempotency_key,correlation_id)
                VALUES (%s,'safe_review_link_issued','line_integration',%s,%s,%s)""",
                (link_pk, json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                 idempotency_key, correlation_id),
            )

    def load_receipt(self, idempotency_key: str, *, for_update: bool = False):
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM line_safe_review_link_receipts WHERE idempotency_key=%s" + suffix,
                (idempotency_key,),
            )
            return cursor.fetchone()


__all__ = ["MySqlLineSafeReviewLinkRepository"]
