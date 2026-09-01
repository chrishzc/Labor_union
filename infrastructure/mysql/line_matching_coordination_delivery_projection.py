"""LINE-owned recipient/configuration projection for committed M3 intents."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any, Mapping

from subsystems.line.matching_coordination_delivery import (
    MatchingCoordinationDeliveryError,
)
from subsystems.scheduling.matching_line_cards import customer_profiles_card


class MySqlLineMatchingCoordinationDeliveryProjection:
    """Read exact Scheduling snapshot and LINE binding/config in one connection.

    The projection is called by the M3 repository before its immutable owner
    intent is inserted.  It only reads owner facts and returns a redacted,
    deterministic delivery envelope; it never creates a root or sends LINE.
    """

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def project(
        self,
        command: Any,
        receipt: Any,
        reference_id: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        selector = str(payload.get("recipient_selector", ""))
        audience, staff_id = self._audience(selector, payload)
        recipient = self._recipient(command.case_no, audience, staff_id)
        line_user_id = recipient.get("recipient_line_user_id")
        if not isinstance(line_user_id, str) or not line_user_id.strip():
            raise MatchingCoordinationDeliveryError(
                "line_matching_recipient_binding_missing"
            )
        binding = self._binding(line_user_id)
        configuration = self._configuration()
        interaction = None
        if selector == "matching.request.participants":
            # Keep the raw token only in the transient delivery envelope.  The
            # LINE consumer stores its hash in the existing interaction owner.
            token = "p6" + hashlib.sha256(
                f"{reference_id}:{line_user_id}".encode("utf-8")
            ).hexdigest()
            expires_at = datetime.now(timezone.utc) + timedelta(days=7)
            message = json.loads(
                customer_profiles_card(
                    command.case_no,
                    (),
                    token,
                    "請確認這項具體協商建議。",
                )
            )
            interaction = {
                "token": token,
                "plan_id": int(recipient["plan_id"]),
                "segment_id": None,
                "action_scope": "customer_decision",
                "expires_at_utc": expires_at.isoformat(),
            }
        else:
            message = {"type": "text", "text": _message_text(payload)}
        result = {
            "source_event_identity": payload.get("source_event_identity")
            or getattr(receipt, "decision_event_id", None)
            or reference_id,
            "recipient_snapshot": {
                "snapshot_id": str(recipient["snapshot_id"]),
                "snapshot_fingerprint": str(recipient["snapshot_fingerprint"]),
                "recipient_type": "user",
                "recipient_identity": line_user_id,
            },
            "binding": binding,
            "configuration": configuration,
            "message_kind": "flex" if interaction is not None else "text",
            "message": message,
            # Persist the handoff schedule so replay reconstructs the exact
            # delivery fingerprint instead of defaulting to a new wall clock.
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
            "notification_reason": "recipient_unavailable",
        }
        if interaction is not None:
            result["interaction"] = interaction
        return result

    def _audience(self, selector: str, payload: Mapping[str, Any]) -> tuple[str, int | None]:
        if selector in {"assignment.client_snapshot", "matching.request.participants"}:
            return "customer", None
        if selector == "assignment.staff_snapshot":
            candidate_id = payload.get("candidate_id")
            try:
                candidate_id = int(candidate_id)
            except (TypeError, ValueError) as error:
                raise MatchingCoordinationDeliveryError(
                    "line_matching_recipient_snapshot_missing"
                ) from error
            with self._connection.cursor() as cursor:
                cursor.execute(
                    "SELECT staff_id FROM caregiver_candidate_contact_entries WHERE id=%s",
                    (candidate_id,),
                )
                row = cursor.fetchone()
            if not isinstance(row, Mapping) or row.get("staff_id") is None:
                raise MatchingCoordinationDeliveryError(
                    "line_matching_recipient_snapshot_missing"
                )
            return "caregiver", int(row["staff_id"])
        raise MatchingCoordinationDeliveryError(
            "line_matching_recipient_selector_unsupported"
        )

    def _recipient(
        self, case_no: str, audience: str, staff_id: int | None
    ) -> Mapping[str, Any]:
        if audience == "customer":
            predicate = "r.audience_type='customer'"
            params: tuple[Any, ...] = (case_no,)
        else:
            predicate = "r.audience_type='caregiver' AND p.staff_id=%s"
            params = (case_no, staff_id)
        sql = (
                "SELECT r.id AS snapshot_id,r.recipient_line_user_id,"
                "r.payload_fingerprint AS snapshot_fingerprint,s.plan_id "
            "FROM matching_schedule_recipient_snapshots r "
            "JOIN matching_schedule_snapshots s ON s.id=r.parent_snapshot_id "
            "LEFT JOIN caregiver_matching_plan_segments p ON p.id=r.segment_id "
            "WHERE s.case_no=%s AND s.current_marker=1 AND s.status='sent' AND "
            + predicate
            + " ORDER BY r.id DESC LIMIT 1"
        )
        with self._connection.cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
        if not isinstance(row, Mapping):
            raise MatchingCoordinationDeliveryError(
                "line_matching_recipient_snapshot_missing"
            )
        return row

    def _binding(self, line_user_id: str) -> dict[str, Any]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT binding_status,aggregate_version FROM line_identity_role_bindings "
                "WHERE line_user_id=%s",
                (line_user_id,),
            )
            row = cursor.fetchone()
        if not isinstance(row, Mapping) or row.get("binding_status") != "bound":
            raise MatchingCoordinationDeliveryError(
                "line_matching_recipient_binding_invalid"
            )
        return {"active": True, "revision": int(row["aggregate_version"])}

    def _configuration(self) -> dict[str, Any]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT revision FROM line_configuration_current "
                "WHERE configuration_kind='message_templates'"
            )
            row = cursor.fetchone()
        if not isinstance(row, Mapping) or row.get("revision") is None:
            raise MatchingCoordinationDeliveryError(
                "line_matching_configuration_invalid"
            )
        return {"active": True, "revision": int(row["revision"])}


def _message_text(payload: Mapping[str, Any]) -> str:
    if payload.get("result_state") == "accepted":
        return "媒合結果已確認，請查看最新服務安排。"
    if payload.get("result_state") in {"leave_deferred", "rematch_required"}:
        return "服務安排已更新，請查看最新通知。"
    return "媒合通知已更新，請查看最新通知。"


__all__ = ["MySqlLineMatchingCoordinationDeliveryProjection"]
