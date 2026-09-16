"""File: staff_leave_intake_repository.py
Description: 保存 Scheduling 月嫂請假待辦的 aggregate、事件與冪等 receipt。"""

from __future__ import annotations

import json
from typing import Any

from domains.scheduling.staff_leave_intake import StaffLeaveRequestStatus
from domains.scheduling.leave_substitution import (
    LeaveResolutionType,
    LeaveSubstitutionBatchIntent,
    LeaveSubstitutionItem,
)
from subsystems.scheduling.staff_leave_intake_workflow import (
    RecordStaffLeaveCustomerDecision,
    StaffLeaveCustomerDecisionReceipt,
    StaffLeaveRequestSnapshot,
)


class MySqlStaffLeaveIntakeRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def replay(self, key: str, fingerprint: str) -> StaffLeaveRequestSnapshot | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_SQL, (key,))
            row = cursor.fetchone()
        if row is None:
            return None
        if str(row["request_fingerprint"]) != fingerprint:
            raise ValueError("leave_request_idempotency_conflict")
        return _snapshot(row)

    def create(self, command, fingerprint: str) -> StaffLeaveRequestSnapshot:
        with self._connection.cursor() as cursor:
            intent = command.intent
            cursor.execute(
                _ROOT_INSERT_SQL,
                (command.staff_id, command.line_user_id, intent.leave_start_date,
                 intent.leave_end_date, intent.reason.strip(), fingerprint),
            )
            request_id = int(cursor.lastrowid)
            cursor.execute(
                _EVENT_INSERT_SQL,
                (request_id, 1, "submitted", f"line:{command.line_user_id}", intent.reason.strip()),
            )
            cursor.execute(
                _RECEIPT_INSERT_SQL,
                (command.idempotency_key, request_id, fingerprint, _result_snapshot(request_id, "pending", 1)),
            )
            cursor.execute(_ROOT_SQL, (request_id,))
            return _snapshot(cursor.fetchone())

    def load_for_update(self, request_id: int) -> StaffLeaveRequestSnapshot | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_ROOT_SQL + " FOR UPDATE", (request_id,))
            row = cursor.fetchone()
        return _snapshot(row) if row is not None else None

    def load(self, request_id: int) -> StaffLeaveRequestSnapshot | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_ROOT_SQL, (request_id,))
            row = cursor.fetchone()
        return _snapshot(row) if row is not None else None

    def load_for_staff(self, request_id: int, staff_id: int) -> StaffLeaveRequestSnapshot | None:
        """Read back only a request owned by the verified staff subject."""
        with self._connection.cursor() as cursor:
            cursor.execute(_ROOT_SQL + " AND staff_id=%s", (request_id, staff_id))
            row = cursor.fetchone()
        return _snapshot(row) if row is not None else None

    def coordination_context(self, request_id: int, expected_version: int) -> dict[str, Any]:
        """Project current impacted cases and customer recipients for an accepted leave request."""
        snapshot = self.load(request_id)
        if snapshot is None:
            raise ValueError("leave_request_not_found")
        if snapshot.version != expected_version:
            raise ValueError("leave_request_stale")
        if snapshot.status is not StaffLeaveRequestStatus.ACCEPTED_FOR_PROCESSING:
            raise ValueError("leave_request_not_accepted")
        if snapshot.leave_start_date is None or snapshot.leave_end_date is None:
            raise ValueError("leave_request_dates_missing")

        with self._connection.cursor() as cursor:
            cursor.execute(
                _COORDINATION_TARGETS_SQL,
                (snapshot.staff_id, snapshot.leave_end_date, snapshot.leave_start_date),
            )
            rows = tuple(cursor.fetchall() or ())

        targets: list[dict[str, Any]] = []
        for row in rows:
            case_no = str(row.get("case_no") or "").strip()
            if not case_no:
                continue
            line_user_id = row.get("client_line_user_id")
            if isinstance(line_user_id, str):
                line_user_id = line_user_id.strip() or None
            else:
                line_user_id = None
            targets.append({"case_no": case_no, "client_line_user_id": line_user_id})
        return {
            "request_id": snapshot.request_id,
            "request_version": snapshot.version,
            "leave_start_date": snapshot.leave_start_date,
            "leave_end_date": snapshot.leave_end_date,
            "targets": targets,
        }

    def record_customer_decision(
        self,
        command: RecordStaffLeaveCustomerDecision,
        fingerprint: str,
    ) -> StaffLeaveCustomerDecisionReceipt:
        """Persist one immutable customer choice without changing the leave aggregate state."""
        with self._connection.cursor() as cursor:
            cursor.execute(_CUSTOMER_DECISION_RECEIPT_SQL, (command.idempotency_key,))
            existing = cursor.fetchone()
            if existing is not None:
                if str(existing["request_fingerprint"]) != fingerprint:
                    raise ValueError("leave_customer_decision_idempotency_conflict")
                return _customer_decision_receipt(
                    existing["result_snapshot"], fingerprint, command.idempotency_key, replayed=True
                )

            cursor.execute(_ROOT_SQL + " FOR UPDATE", (command.request_id,))
            row = cursor.fetchone()
            if row is None:
                raise ValueError("leave_request_not_found")
            snapshot = _snapshot(row)
            if snapshot.version != command.expected_version:
                raise ValueError("leave_request_stale")
            if snapshot.status is not StaffLeaveRequestStatus.ACCEPTED_FOR_PROCESSING:
                raise ValueError("leave_request_not_accepted")
            if snapshot.leave_start_date is None or snapshot.leave_end_date is None:
                raise ValueError("leave_request_dates_missing")

            cursor.execute(
                _COORDINATION_TARGETS_SQL,
                (snapshot.staff_id, snapshot.leave_end_date, snapshot.leave_start_date),
            )
            rows = tuple(cursor.fetchall() or ())
            target = next(
                (
                    item for item in rows
                    if str(item.get("case_no") or "").strip() == command.case_no.strip()
                ),
                None,
            )
            if target is None:
                raise ValueError("leave_customer_case_not_affected")
            current_recipient = target.get("client_line_user_id")
            if not isinstance(current_recipient, str) or not current_recipient.strip():
                raise ValueError("leave_customer_recipient_unavailable")
            if current_recipient.strip() != command.line_user_id.strip():
                raise ValueError("leave_customer_recipient_mismatch")

            payload = {
                "family": "scheduling-staff-leave-customer-decision/v1",
                "request_id": snapshot.request_id,
                "request_version": snapshot.version,
                "case_no": command.case_no.strip(),
                "line_user_id": current_recipient.strip(),
                "decision": command.decision,
            }
            serialized = json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            cursor.execute(
                _RECEIPT_INSERT_SQL,
                (command.idempotency_key, snapshot.request_id, fingerprint, serialized),
            )
            return _customer_decision_receipt(
                serialized, fingerprint, command.idempotency_key, replayed=False
            )

    def customer_defer_intent(
        self,
        request_id: int,
        expected_version: int,
        case_no: str,
        original_assignment_id: int,
        *,
        lock: bool = False,
    ) -> LeaveSubstitutionBatchIntent:
        """Read saved consent and derive only current affected official service days.

        Apply calls this from the canonical workflow's linked-request lock hook;
        it owns neither a transaction nor a schedule write.
        """
        snapshot = self.load_for_update(request_id) if lock else self.load(request_id)
        if snapshot is None:
            raise ValueError("leave_request_not_found")
        if snapshot.version != expected_version:
            raise ValueError("leave_request_stale")
        if snapshot.status is not StaffLeaveRequestStatus.ACCEPTED_FOR_PROCESSING:
            raise ValueError("leave_request_not_accepted")
        if snapshot.leave_start_date is None or snapshot.leave_end_date is None:
            raise ValueError("leave_request_dates_missing")

        suffix = " FOR UPDATE" if lock else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                _CUSTOMER_DECISIONS_FOR_CASE_SQL + suffix,
                (request_id, expected_version, case_no),
            )
            decisions = tuple(cursor.fetchall() or ())
            if len(decisions) != 1:
                raise ValueError("leave_customer_agreement_missing_or_ambiguous")
            row = decisions[0]
            decision = _customer_decision_receipt(
                row["result_snapshot"], str(row["request_fingerprint"]),
                str(row["idempotency_key"]), replayed=True,
            )
            if decision.decision != "agree_defer":
                raise ValueError("leave_customer_defer_not_agreed")

            cursor.execute(
                _CUSTOMER_DEFER_DAYS_SQL + suffix,
                (case_no, original_assignment_id, snapshot.staff_id,
                 snapshot.leave_start_date, snapshot.leave_end_date),
            )
            days = tuple(cursor.fetchall() or ())
        if not days:
            raise ValueError("leave_customer_service_days_missing")
        recipients = {row["client_line_user_id"] for row in days}
        if recipients != {decision.line_user_id}:
            raise ValueError("leave_customer_binding_conflict")
        return LeaveSubstitutionBatchIntent(
            original_assignment_id,
            tuple(
                LeaveSubstitutionItem(
                    int(row["schedule_id"]), row["work_date"],
                    LeaveResolutionType.DEFER_FOLLOWING_ASSIGNMENTS,
                )
                for row in days
            ),
        )

    def has_pending_service_days(self, request_id: int, expected_version: int) -> bool:
        """Read remaining affected days after the canonical generation replacement."""
        snapshot = self.load_for_update(request_id)
        if snapshot is None or snapshot.version != expected_version:
            raise ValueError("leave_request_stale")
        if snapshot.status is not StaffLeaveRequestStatus.ACCEPTED_FOR_PROCESSING:
            raise ValueError("leave_request_not_accepted")
        if snapshot.leave_start_date is None or snapshot.leave_end_date is None:
            raise ValueError("leave_request_dates_missing")
        with self._connection.cursor() as cursor:
            cursor.execute(
                _PENDING_LEAVE_SERVICE_DAYS_SQL,
                (snapshot.staff_id, snapshot.leave_start_date, snapshot.leave_end_date),
            )
            return cursor.fetchone() is not None

    def replay_mutation(self, key: str, fingerprint: str) -> StaffLeaveRequestSnapshot | None:
        return self.replay(key, fingerprint)

    def list_requests(self, status: str, limit: int) -> list[dict[str, Any]]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT r.id,r.staff_id,s.name AS staff_name,r.leave_start_date,r.leave_end_date,"
                "r.request_reason,r.request_status,r.aggregate_version "
                "FROM scheduling_staff_leave_request_aggregates r JOIN staff s ON s.id=r.staff_id "
                "WHERE r.request_status=%s ORDER BY r.created_at,r.id LIMIT %s",
                (status, limit),
            )
            return list(cursor.fetchall() or ())

    def transition(self, snapshot, target, reason: str, actor_id: str, key: str, fingerprint: str) -> StaffLeaveRequestSnapshot:
        with self._connection.cursor() as cursor:
            cursor.execute(_ROOT_TRANSITION_SQL, (target.value, snapshot.request_id, snapshot.version))
            if cursor.rowcount != 1:
                raise ValueError("leave_request_stale")
            version = snapshot.version + 1
            cursor.execute(_EVENT_INSERT_SQL, (snapshot.request_id, version, target.value, actor_id, reason))
            cursor.execute(_RECEIPT_INSERT_SQL, (key, snapshot.request_id, fingerprint, _result_snapshot(snapshot.request_id, target.value, version)))
            cursor.execute(_ROOT_SQL, (snapshot.request_id,))
            return _snapshot(cursor.fetchone())

    def resolve(self, snapshot, receipt_key: str, key: str, fingerprint: str) -> StaffLeaveRequestSnapshot:
        with self._connection.cursor() as cursor:
            cursor.execute(_CANONICAL_RECEIPT_SQL, (receipt_key, snapshot.staff_id))
            if cursor.fetchone() is None:
                raise ValueError("leave_request_receipt_conflict")
            try:
                cursor.execute(_RESOLUTION_LINK_SQL, (snapshot.request_id, receipt_key))
            except Exception as error:
                if _duplicate_key(error):
                    raise ValueError("leave_request_receipt_conflict") from error
                raise
            cursor.execute(_ROOT_TRANSITION_SQL, (StaffLeaveRequestStatus.RESOLVED.value, snapshot.request_id, snapshot.version))
            if cursor.rowcount != 1:
                raise ValueError("leave_request_stale")
            version = snapshot.version + 1
            cursor.execute(_EVENT_INSERT_SQL, (snapshot.request_id, version, "resolved", "leave-substitution-receipt", receipt_key))
            cursor.execute(_RECEIPT_INSERT_SQL, (key, snapshot.request_id, fingerprint, _result_snapshot(snapshot.request_id, StaffLeaveRequestStatus.RESOLVED.value, version, receipt_key)))
            cursor.execute(_ROOT_SQL, (snapshot.request_id,))
            return _snapshot(cursor.fetchone())


def _snapshot(row) -> StaffLeaveRequestSnapshot:
    return StaffLeaveRequestSnapshot(
        int(row["id"]), int(row["staff_id"]), str(row["line_user_id"]),
        StaffLeaveRequestStatus(str(row["request_status"])), int(row["aggregate_version"]),
        str(row["request_fingerprint"]),
        row.get("leave_start_date") if hasattr(row, "get") else row["leave_start_date"],
        row.get("leave_end_date") if hasattr(row, "get") else row["leave_end_date"],
        str((row.get("request_reason") if hasattr(row, "get") else row["request_reason"]) or ""),
    )


_ROOT_COLUMNS = "id,staff_id,line_user_id,leave_start_date,leave_end_date,request_reason,request_status,aggregate_version,request_fingerprint"
_ROOT_SQL = f"SELECT {_ROOT_COLUMNS} FROM scheduling_staff_leave_request_aggregates WHERE id=%s"
_RECEIPT_ROOT_COLUMNS = (
    "a.id,a.staff_id,a.line_user_id,a.leave_start_date,a.leave_end_date,"
    "a.request_reason,a.request_status,a.aggregate_version,a.request_fingerprint"
)
_RECEIPT_SQL = (
    f"SELECT r.request_fingerprint,{_RECEIPT_ROOT_COLUMNS} "
    "FROM scheduling_staff_leave_request_receipts r "
    "JOIN scheduling_staff_leave_request_aggregates a ON a.id=r.request_id "
    "WHERE r.idempotency_key=%s"
)
_CUSTOMER_DECISION_RECEIPT_SQL = (
    "SELECT request_fingerprint,result_snapshot "
    "FROM scheduling_staff_leave_request_receipts WHERE idempotency_key=%s FOR UPDATE"
)
_ROOT_INSERT_SQL = "INSERT INTO scheduling_staff_leave_request_aggregates (staff_id,line_user_id,leave_start_date,leave_end_date,request_reason,request_status,request_fingerprint) VALUES (%s,%s,%s,%s,%s,'pending',%s)"
_EVENT_INSERT_SQL = "INSERT INTO scheduling_staff_leave_request_events (request_id,aggregate_version,event_type,actor_id,reason) VALUES (%s,%s,%s,%s,%s)"
_RECEIPT_INSERT_SQL = "INSERT INTO scheduling_staff_leave_request_receipts (idempotency_key,request_id,request_fingerprint,result_snapshot) VALUES (%s,%s,%s,%s)"
_ROOT_TRANSITION_SQL = "UPDATE scheduling_staff_leave_request_aggregates SET request_status=%s,aggregate_version=aggregate_version+1 WHERE id=%s AND aggregate_version=%s"
_RESOLUTION_LINK_SQL = "INSERT INTO scheduling_staff_leave_request_resolution_links (request_id,leave_substitution_receipt_key) VALUES (%s,%s)"
_CANONICAL_RECEIPT_SQL = (
    "SELECT b.batch_key FROM scheduling_leave_substitution_batches b "
    "JOIN scheduling_leave_substitution_outcomes o ON o.batch_key=b.batch_key "
    "WHERE b.batch_key=%s AND o.original_staff_id=%s LIMIT 1 FOR UPDATE"
)
# The leave window intersects actual owner-backed work days, not the bounding
# assignment period (which also contains rest days). Group membership and the
# legacy clients.line_user_id projection are not current binding authority.
_COORDINATION_TARGETS_SQL = (
    "SELECT DISTINCT g.case_no,binding.line_user_id AS client_line_user_id "
    "FROM scheduling_aggregates g JOIN case_staff_assignments a "
    "ON a.generation_id=g.effective_generation_id AND a.case_no=g.case_no "
    "JOIN staff_schedule ss ON ss.assignment_id=a.id AND ss.staff_id=a.staff_id "
    "JOIN orders o ON o.case_no=g.case_no "
    "LEFT JOIN line_identity_role_bindings binding "
    "ON binding.subject_type='customer' AND binding.binding_status='bound' "
    "AND binding.subject_reference=CAST(o.client_id AS CHAR) "
    "WHERE a.staff_id=%s AND a.status NOT IN ('cancelled','replaced') "
    "AND ss.is_work_day=1 AND ss.work_date<=%s AND ss.work_date>=%s "
    "ORDER BY g.case_no"
)


# Reuse the immutable customer-decision receipt; no second consent store.
_CUSTOMER_DECISIONS_FOR_CASE_SQL = (
    "SELECT idempotency_key,request_fingerprint,result_snapshot "
    "FROM scheduling_staff_leave_request_receipts WHERE request_id=%s "
    "AND JSON_UNQUOTE(JSON_EXTRACT(result_snapshot,'$.family'))="
    "'scheduling-staff-leave-customer-decision/v1' "
    "AND JSON_EXTRACT(result_snapshot,'$.request_version')=%s "
    "AND JSON_UNQUOTE(JSON_EXTRACT(result_snapshot,'$.case_no'))=%s"
)
_CUSTOMER_DEFER_DAYS_SQL = (
    "SELECT ss.id AS schedule_id,ss.work_date,binding.line_user_id AS client_line_user_id "
    "FROM scheduling_aggregates g JOIN case_staff_assignments a "
    "ON a.generation_id=g.effective_generation_id AND a.case_no=g.case_no "
    "JOIN staff_schedule ss ON ss.generation_id=g.effective_generation_id "
    "AND ss.assignment_id=a.id AND ss.staff_id=a.staff_id "
    "JOIN orders o ON o.case_no=g.case_no "
    "LEFT JOIN line_identity_role_bindings binding "
    "ON binding.subject_type='customer' AND binding.binding_status='bound' "
    "AND binding.subject_reference=CAST(o.client_id AS CHAR) "
    "WHERE g.case_no=%s AND a.id=%s AND a.staff_id=%s "
    "AND a.status NOT IN ('cancelled','replaced') "
    "AND ss.effective_marker=1 AND ss.is_work_day=1 "
    "AND ss.work_date>=%s AND ss.work_date<=%s ORDER BY ss.work_date,ss.id"
)
_PENDING_LEAVE_SERVICE_DAYS_SQL = (
    "SELECT ss.id FROM scheduling_aggregates g JOIN case_staff_assignments a "
    "ON a.generation_id=g.effective_generation_id AND a.case_no=g.case_no "
    "JOIN staff_schedule ss ON ss.generation_id=g.effective_generation_id "
    "AND ss.assignment_id=a.id AND ss.staff_id=a.staff_id "
    "WHERE a.staff_id=%s AND a.status NOT IN ('cancelled','replaced') "
    "AND ss.effective_marker=1 AND ss.is_work_day=1 "
    "AND ss.work_date>=%s AND ss.work_date<=%s LIMIT 1 FOR UPDATE"
)


def _result_snapshot(request_id: int, status: str, version: int, receipt_key: str | None = None) -> str:
    payload: dict[str, object] = {"request_id": request_id, "status": status, "version": version}
    if receipt_key is not None:
        payload["leave_substitution_receipt_key"] = receipt_key
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _customer_decision_receipt(
    raw_snapshot: object,
    fingerprint: str,
    idempotency_key: str,
    *,
    replayed: bool,
) -> StaffLeaveCustomerDecisionReceipt:
    try:
        payload = json.loads(str(raw_snapshot))
    except (TypeError, ValueError) as error:
        raise ValueError("leave_customer_decision_replay_readback_missing") from error
    if not isinstance(payload, dict) or payload.get("family") != "scheduling-staff-leave-customer-decision/v1":
        raise ValueError("leave_customer_decision_replay_readback_missing")
    try:
        return StaffLeaveCustomerDecisionReceipt(
            request_id=int(payload["request_id"]),
            request_version=int(payload["request_version"]),
            case_no=str(payload["case_no"]),
            line_user_id=str(payload["line_user_id"]),
            decision=str(payload["decision"]),
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            replayed=replayed,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("leave_customer_decision_replay_readback_missing") from error


def _duplicate_key(error: Exception) -> bool:
    arguments = getattr(error, "args", ())
    return bool(arguments and arguments[0] == 1062)