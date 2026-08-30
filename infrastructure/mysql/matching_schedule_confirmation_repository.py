"""
File: matching_schedule_confirmation_repository.py
Description: 持久化 LINE 或人工日期表快照，套用前重驗日期、方案與人員 lifecycle。
"""

import json
import hashlib
import secrets
from datetime import date, datetime, timezone
from domains.orders.service_date_confirmation import group_service_dates_by_calendar_week
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineUserId
from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import CorrelationId, IdempotencyKey


class MySqlMatchingScheduleConfirmationRepository:
    def __init__(self, connection):
        self.connection = connection
        self.deliveries = MySqlLineDeliveryTaskRepository(connection)

    def query(self, case_no, plan_id):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT id,version FROM confirmed_service_date_versions WHERE case_no=%s AND is_current=1", (case_no,))
            root = cursor.fetchone()
            if not root:
                raise ValueError("confirmed_service_dates_required")
            preview = self._preview(cursor, case_no, plan_id, root["id"])
            snapshot = self._latest_snapshot(cursor, case_no, plan_id)
            status = _snapshot_status(root["id"], snapshot)
            is_current = status in {"sent", "manual_ready"}
            recipients = self._recipients(cursor, snapshot["id"]) if snapshot and is_current else []
            outdated_preview = (
                self._preview(cursor, case_no, plan_id, snapshot["confirmed_version_id"])
                if snapshot and status == "sent_outdated"
                else None
            )
        passed = bool(recipients) and all(r["confirmation_status"] in ("confirmed", "manually_confirmed") for r in recipients)
        return {"case_no": case_no, "plan_id": plan_id, "confirmed_service_date_version": root["version"], "snapshot_id": snapshot["id"] if snapshot else None, "snapshot_status": status, "schedule_preview": preview, "outdated_schedule_preview": outdated_preview, "recipients": recipients, "gate_passed": passed}

    def invalidate_current_snapshot(self, case_no: str) -> None:
        """Invalidate Scheduling's current snapshot in the caller's transaction."""
        with self.connection.cursor() as cursor:
            cursor.execute(
                "UPDATE matching_schedule_snapshots SET current_marker=NULL,status='invalidated',"
                "invalidated_at_utc=UTC_TIMESTAMP(6) WHERE case_no=%s AND current_marker=1",
                (case_no,),
            )

    def preview_manual(self, case_no, plan_id):
        with self.connection.cursor() as cursor:
            root, payloads = self._manual_source(cursor, case_no, plan_id, lock=False)
        return {
            "case_no": case_no,
            "plan_id": plan_id,
            "confirmed_service_date_version": root["version"],
            "schedule_preview": self._preview_from_payloads(payloads),
            "preview_fingerprint": _manual_preview_fingerprint(case_no, plan_id, root, payloads),
        }

    def prepare_manual(self, case_no, plan_id, actor, reason, expected_version, fingerprint, key):
        del key
        with self.connection.cursor() as cursor:
            root, payloads = self._manual_source(cursor, case_no, plan_id, lock=True)
            if root["version"] != expected_version:
                raise ValueError("manual_schedule_confirmation_preview_stale")
            expected = _manual_preview_fingerprint(case_no, plan_id, root, payloads)
            if fingerprint != expected:
                raise ValueError("manual_schedule_confirmation_preview_stale")
            cursor.execute(
                "SELECT id,status,snapshot_fingerprint FROM matching_schedule_snapshots "
                "WHERE case_no=%s AND current_marker=1 FOR UPDATE",
                (case_no,),
            )
            current = cursor.fetchone()
            if current:
                if current["status"] == "draft" and current["snapshot_fingerprint"] == expected:
                    return self.query(case_no, plan_id)
                raise ValueError("manual_schedule_confirmation_current_snapshot_conflict")
            cursor.execute(
                "INSERT INTO matching_schedule_snapshots "
                "(case_no,plan_id,confirmed_version_id,snapshot_fingerprint,status,current_marker,created_by_actor_id) "
                "VALUES (%s,%s,%s,%s,'draft',1,%s)",
                (case_no, plan_id, root["id"], expected, actor),
            )
            snapshot_id = cursor.lastrowid
            for payload in payloads:
                self._store_recipient(
                    cursor,
                    snapshot_id,
                    {**payload, "manual_preparation": {"actor": actor, "reason": reason}},
                    delivery_status="blocked",
                )
        return self.query(case_no, plan_id)

    def send(self, case_no, plan_id, actor, key):
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT id,version FROM confirmed_service_date_versions WHERE case_no=%s AND is_current=1 FOR UPDATE", (case_no,))
            version = cursor.fetchone()
            if not version:
                raise ValueError("confirmed_service_dates_required")
            cursor.execute("SELECT id FROM caregiver_matching_plans WHERE id=%s AND case_no=%s AND is_active=1", (plan_id, case_no))
            if not cursor.fetchone():
                raise ValueError("active_matching_plan_required")
            cursor.execute("SELECT id,status FROM matching_schedule_snapshots WHERE case_no=%s AND plan_id=%s AND confirmed_version_id=%s AND current_marker=1 FOR UPDATE", (case_no, plan_id, version["id"]))
            current = cursor.fetchone()
            if current and current["status"] == "sent":
                return self.query(case_no, plan_id)
            cursor.execute("UPDATE matching_schedule_snapshots SET current_marker=NULL,status='invalidated',invalidated_at_utc=UTC_TIMESTAMP(6) WHERE case_no=%s AND current_marker=1", (case_no,))
            self._require_active_lifecycle(cursor, plan_id)
            payloads = self._payloads(cursor, case_no, plan_id, version["id"])
            self._require_line_binding(payloads)
            digest = fingerprint_payload({"case_no": case_no, "plan_id": plan_id, "version": version["version"], "payloads": payloads}).value
            cursor.execute("INSERT INTO matching_schedule_snapshots (case_no,plan_id,confirmed_version_id,snapshot_fingerprint,status,current_marker,created_by_actor_id) VALUES (%s,%s,%s,%s,'sent',1,%s)", (case_no, plan_id, version["id"], digest, actor))
            snapshot_id = cursor.lastrowid
            for payload in payloads:
                recipient_id = self._store_recipient(cursor, snapshot_id, payload)
                self._enqueue(cursor, recipient_id, snapshot_id, payload, key)
        return self.query(case_no, plan_id)

    def confirm(self, recipient_id, value, actor, reason, key):
        if value not in ("confirmed", "rejected", "manually_confirmed", "manually_revoked"):
            raise ValueError("schedule_confirmation_value_invalid")
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT s.case_no,s.plan_id,s.current_marker FROM matching_schedule_recipient_snapshots r JOIN matching_schedule_snapshots s ON s.id=r.parent_snapshot_id WHERE r.id=%s FOR UPDATE", (recipient_id,))
            target = cursor.fetchone()
            if not target or target["current_marker"] != 1:
                raise ValueError("schedule_snapshot_stale")
            cursor.execute("INSERT INTO matching_schedule_confirmation_events (recipient_snapshot_id,confirmation_value,source,actor_id,reason,idempotency_key) VALUES (%s,%s,'admin',%s,%s,%s) ON DUPLICATE KEY UPDATE id=id", (recipient_id, value, actor, reason or None, key))
        return self.query(target["case_no"], target["plan_id"])

    def confirm_line_postback(self, token, decision, line_user_id, event_key):
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT r.id FROM matching_schedule_line_interactions i "
                "JOIN matching_schedule_recipient_snapshots r ON r.id=i.recipient_snapshot_id "
                "JOIN matching_schedule_snapshots s ON s.id=r.parent_snapshot_id "
                "LEFT JOIN caregiver_matching_plan_segments segment ON segment.id=r.segment_id "
                "LEFT JOIN staff_lifecycle_states lifecycle ON lifecycle.staff_id=segment.staff_id "
                "WHERE i.token_hash=%s AND i.interaction_status='active' AND s.current_marker=1 "
                "AND r.recipient_line_user_id=%s AND (r.segment_id IS NULL OR COALESCE(lifecycle.lifecycle_state,'active')='active') FOR UPDATE",
                (token_hash, line_user_id.value),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError("schedule_confirmation_interaction_invalid")
            if decision == "rejected":
                self._request_line_rejection_reason(cursor, row["id"], line_user_id, event_key)
                return
            cursor.execute(
                "INSERT INTO matching_schedule_confirmation_events (recipient_snapshot_id,confirmation_value,source,actor_id,reason,idempotency_key) VALUES (%s,'confirmed','line',%s,NULL,%s)",
                (row["id"], line_user_id.value, event_key),
            )
            cursor.execute(
                "UPDATE matching_schedule_line_interactions SET interaction_status='consumed',consumed_at_utc=UTC_TIMESTAMP(6) WHERE token_hash=%s",
                (token_hash,),
            )

    def confirm_line_rejection_reason(self, line_user_id, reason, event_key):
        normalized_reason = reason.strip()
        if not normalized_reason:
            return False
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT r.id FROM matching_schedule_line_interactions i "
                "JOIN matching_schedule_recipient_snapshots r ON r.id=i.recipient_snapshot_id "
                "JOIN matching_schedule_snapshots s ON s.id=r.parent_snapshot_id "
                "LEFT JOIN caregiver_matching_plan_segments segment ON segment.id=r.segment_id "
                "LEFT JOIN staff_lifecycle_states lifecycle ON lifecycle.staff_id=segment.staff_id "
                "WHERE i.interaction_status='awaiting_rejection_reason' "
                "AND s.current_marker=1 AND r.recipient_line_user_id=%s AND (r.segment_id IS NULL OR COALESCE(lifecycle.lifecycle_state,'active')='active') "
                "ORDER BY i.created_at_utc DESC,i.id DESC LIMIT 1 FOR UPDATE",
                (line_user_id.value,),
            )
            row = cursor.fetchone()
            if not row:
                return False
            cursor.execute(
                "INSERT INTO matching_schedule_confirmation_events "
                "(recipient_snapshot_id,confirmation_value,source,actor_id,reason,idempotency_key) "
                "VALUES (%s,'rejected','line',%s,%s,%s)",
                (row["id"], line_user_id.value, normalized_reason, event_key),
            )
            cursor.execute(
                "UPDATE matching_schedule_line_interactions SET interaction_status='consumed',"
                "consumed_at_utc=UTC_TIMESTAMP(6) WHERE recipient_snapshot_id=%s "
                "AND interaction_status='awaiting_rejection_reason'",
                (row["id"],),
            )
        return True

    def _request_line_rejection_reason(self, cursor, recipient_id, line_user_id, event_key):
        cursor.execute(
            "UPDATE matching_schedule_line_interactions "
            "SET interaction_status='awaiting_rejection_reason' "
            "WHERE recipient_snapshot_id=%s AND interaction_status='active'",
            (recipient_id,),
        )
        if cursor.rowcount != 1:
            raise ValueError("schedule_confirmation_interaction_invalid")
        self.deliveries.enqueue(
            LineDeliveryRequest(
                LineRecipient(LineRecipientType.USER, line_user_id),
                LineMessageKind.TEXT,
                canonical_line_payload_json({"type": "text", "text": "已收到您拒絕目前服務日期表的回覆。請直接回覆拒絕原因，工會人員會協助處理。"}),
                datetime.now(timezone.utc),
                IdempotencyKey(f"schedule-rejection-reason:{event_key}"),
                CorrelationId(f"matching-schedule-rejection:{recipient_id}"),
                "matching_schedule_recipient",
                str(recipient_id),
            )
        )

    @staticmethod
    def _require_active_lifecycle(cursor, plan_id):
        cursor.execute("SELECT segment.staff_id FROM caregiver_matching_plan_segments segment LEFT JOIN staff_lifecycle_states lifecycle ON lifecycle.staff_id=segment.staff_id WHERE segment.plan_id=%s AND COALESCE(lifecycle.lifecycle_state,'active')<>'active' FOR UPDATE", (plan_id,))
        if cursor.fetchone():
            raise ValueError("staff_retired_matching_ineligible")

    @staticmethod
    def _payloads(cursor, case_no, plan_id, version_id):
        cursor.execute("SELECT service_date FROM confirmed_service_date_days WHERE confirmed_version_id=%s ORDER BY ordinal", (version_id,))
        dates = [r["service_date"].isoformat() for r in cursor.fetchall()]
        cursor.execute("SELECT c.line_user_id FROM orders o JOIN clients c ON c.id=o.client_id WHERE o.case_no=%s", (case_no,))
        client = cursor.fetchone()
        result = [_schedule_payload("customer", "customer", None, client["line_user_id"], dates)]
        cursor.execute("SELECT s.id,s.assigned_start_date,s.assigned_end_date,st.line_user_id FROM caregiver_matching_plan_segments s JOIN staff st ON st.id=s.staff_id WHERE s.plan_id=%s ORDER BY s.segment_order", (plan_id,))
        for row in cursor.fetchall():
            own = [d for d in dates if row["assigned_start_date"].isoformat() <= d <= row["assigned_end_date"].isoformat()]
            result.append(_schedule_payload("caregiver", f"caregiver:{row['id']}", row["id"], row["line_user_id"], own))
        return result

    def _manual_source(self, cursor, case_no, plan_id, *, lock):
        suffix = " FOR UPDATE" if lock else ""
        cursor.execute(
            "SELECT id,version FROM confirmed_service_date_versions "
            "WHERE case_no=%s AND is_current=1" + suffix,
            (case_no,),
        )
        root = cursor.fetchone()
        if not root:
            raise ValueError("confirmed_service_dates_required")
        cursor.execute(
            "SELECT id FROM caregiver_matching_plans "
            "WHERE id=%s AND case_no=%s AND is_active=1" + suffix,
            (plan_id, case_no),
        )
        if not cursor.fetchone():
            raise ValueError("active_matching_plan_required")
        self._require_active_lifecycle(cursor, plan_id)
        return root, self._payloads(cursor, case_no, plan_id, root["id"])

    @staticmethod
    def _latest_snapshot(cursor, case_no, plan_id):
        cursor.execute(
            "SELECT id,confirmed_version_id,status,current_marker FROM matching_schedule_snapshots "
            "WHERE case_no=%s AND plan_id=%s ORDER BY id DESC LIMIT 1",
            (case_no, plan_id),
        )
        return cursor.fetchone()

    @classmethod
    def _preview(cls, cursor, case_no, plan_id, version_id):
        payloads = cls._payloads(cursor, case_no, plan_id, version_id)
        return cls._preview_from_payloads(payloads)

    @staticmethod
    def _preview_from_payloads(payloads):
        return {
            "week_grouping_policy": "calendar_week_sunday_to_saturday_v1",
            "total_service_days": payloads[0]["total_service_days"],
            "total_weeks": payloads[0]["total_weeks"],
            "weeks": payloads[0]["weeks"],
            "recipient_schedules": [
                _recipient_schedule(payload) for payload in payloads
            ],
        }

    @staticmethod
    def _store_recipient(cursor, snapshot_id, payload, delivery_status="pending"):
        cursor.execute("INSERT INTO matching_schedule_recipient_snapshots (parent_snapshot_id,audience_type,recipient_key,segment_id,recipient_line_user_id,payload_snapshot,payload_fingerprint,delivery_status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)", (snapshot_id, payload["audience"], payload["key"], payload["segment_id"], payload["line_user_id"], json.dumps(payload, ensure_ascii=False), fingerprint_payload(payload).value, delivery_status))
        return cursor.lastrowid

    @staticmethod
    def _require_line_binding(payloads):
        unbound_recipient_keys = [
            payload["key"] for payload in payloads if not payload["line_user_id"]
        ]
        if unbound_recipient_keys:
            raise ValueError(
                "matching_schedule_recipient_line_binding_required:"
                + ",".join(unbound_recipient_keys)
            )

    def _enqueue(self, cursor, recipient_id, snapshot_id, payload, key):
        if not payload["line_user_id"]: return
        token = secrets.token_urlsafe(24)
        cursor.execute("INSERT INTO matching_schedule_line_interactions (recipient_snapshot_id,token_hash) VALUES (%s,%s)", (recipient_id, hashlib.sha256(token.encode()).hexdigest()))
        body = _schedule_confirmation_card(payload, token)
        self.deliveries.enqueue(LineDeliveryRequest(LineRecipient(LineRecipientType.USER, LineUserId(str(payload["line_user_id"]))), LineMessageKind.FLEX, body, datetime.now(timezone.utc), IdempotencyKey(f"schedule:{key}:{recipient_id}"), CorrelationId(f"matching-schedule:{snapshot_id}"), "matching_schedule_recipient", str(recipient_id)))
        cursor.execute("UPDATE matching_schedule_recipient_snapshots SET delivery_status='queued' WHERE id=%s", (recipient_id,))

    @staticmethod
    def _recipients(cursor, snapshot_id):
        cursor.execute("SELECT r.id,r.audience_type,r.segment_id,r.delivery_status,delivery.processing_status,"
                       "event.confirmation_value confirmation_status,event.source confirmation_source,"
                       "event.reason confirmation_reason,event.occurred_at_utc confirmation_occurred_at_utc "
                       "FROM matching_schedule_recipient_snapshots r "
                       "LEFT JOIN line_delivery_tasks delivery ON delivery.source_aggregate_type='matching_schedule_recipient' "
                       "AND CAST(delivery.source_aggregate_identity AS UNSIGNED)=r.id "
                       "LEFT JOIN matching_schedule_confirmation_events event ON event.id=("
                       "SELECT e.id FROM matching_schedule_confirmation_events e "
                       "WHERE e.recipient_snapshot_id=r.id ORDER BY e.occurred_at_utc DESC,e.id DESC LIMIT 1) "
                       "WHERE r.parent_snapshot_id=%s ORDER BY r.id", (snapshot_id,))
        return [{"recipient_snapshot_id": r["id"], "audience_type": r["audience_type"], "segment_id": r["segment_id"], "delivery_status": _delivery_status(r), "confirmation_status": r["confirmation_status"] or "pending", "confirmation_source": r["confirmation_source"], "confirmation_reason": r["confirmation_reason"], "confirmation_occurred_at_utc": r["confirmation_occurred_at_utc"]} for r in cursor.fetchall()]


def _delivery_status(row):
    delivery_status = row.get("processing_status")
    if delivery_status == "sent":
        return "sent"
    if delivery_status in {"failed", "cancelled"}:
        return "failed"
    return row["delivery_status"]


def _snapshot_status(current_version_id, snapshot):
    if snapshot is None:
        return "not_sent"
    if snapshot["confirmed_version_id"] != current_version_id:
        return "sent_outdated"
    if snapshot["current_marker"] != 1:
        return "not_sent"
    if snapshot["status"] == "draft":
        return "manual_ready"
    return snapshot["status"]


def _manual_preview_fingerprint(case_no, plan_id, root, payloads):
    return fingerprint_payload({
        "case_no": case_no,
        "plan_id": plan_id,
        "confirmed_service_date_version_id": root["id"],
        "confirmed_service_date_version": root["version"],
        "payloads": payloads,
        "mode": "manual_schedule_confirmation_v1",
    }).value


def _schedule_payload(audience, key, segment_id, line_user_id, dates):
    weeks = _calendar_weeks(dates)
    return {
        "audience": audience,
        "key": key,
        "segment_id": segment_id,
        "line_user_id": line_user_id,
        "dates": dates,
        "week_grouping_policy": "calendar_week_sunday_to_saturday_v1",
        "total_service_days": len(dates),
        "total_weeks": len(weeks),
        "weeks": weeks,
    }


def _calendar_weeks(dates):
    return list(
        group_service_dates_by_calendar_week(tuple(date.fromisoformat(value) for value in dates))
    )


def _recipient_schedule(payload):
    return {
        "audience_type": payload["audience"],
        "segment_id": payload["segment_id"],
        "total_service_days": payload["total_service_days"],
        "total_weeks": payload["total_weeks"],
        "weeks": payload["weeks"],
    }


def _schedule_confirmation_card(payload, token):
    audience = "客戶" if payload["audience"] == "customer" else "月嫂"
    weekly_schedule = _weekly_schedule_text(payload["weeks"])
    return canonical_line_payload_json({
        "type": "flex", "altText": "服務日期表確認",
        "contents": {"type": "bubble", "body": {"type": "box", "layout": "vertical", "contents": [
            {"type": "text", "text": "服務日期表確認", "weight": "bold", "size": "xl"},
            {"type": "text", "text": f"對象：{audience}", "margin": "md"},
            {"type": "text", "text": f"共 {payload['total_service_days']} 個服務日／{payload['total_weeks']} 週", "wrap": True, "margin": "md"},
            {"type": "text", "text": weekly_schedule, "wrap": True, "margin": "md"},
            {"type": "text", "text": "請確認目前日期表；若拒絕，工會將向您索取原因。", "wrap": True, "size": "sm", "margin": "md"},
        ]}, "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": [
            {"type": "button", "style": "primary", "color": "#06C755", "action": {"type": "postback", "label": "確認日期表", "data": f"schedule:{token}:confirmed", "displayText": "我確認日期表"}},
            {"type": "button", "style": "secondary", "action": {"type": "postback", "label": "拒絕日期表", "data": f"schedule:{token}:rejected", "displayText": "我拒絕日期表，請聯絡我"}},
        ]}},
    })


def _weekly_schedule_text(weeks):
    if not weeks:
        return "此區段沒有服務日期"
    return "\n".join(
        f"第{week['week_number']}週 {week['period_start']}～{week['period_end']}"
        f"（{week['service_day_count']}日）：{'、'.join(week['service_dates'])}"
        for week in weeks
    )
