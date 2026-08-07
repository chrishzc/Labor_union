"""Root-fact consumers for the process-reminder anomaly group.

Covers ORDER-001~004, BECLASS-001, DOC-SEND-001, RECEIVABLE-001, RETURN-001,
SCHEDULE-001/002/003/005 and LINE-001/002/004/005. Business rules are ported
1:1 from the legacy services/anomaly_alert_detection.py scanners.

Unlike that legacy module (which pre-filters queries to only currently-matching
rows and relies on a separate resolve_absent_alerts() bulk close), every
builder here is handed the full stable candidate universe (e.g. every order,
every client_payments row) and computes an explicit active flag per row. That
lets the canonical reducer (domains.anomalies.registry.reduce_current_alert)
auto-resolve rows that fall out of the matching condition on the next scan,
without a separate bulk-close step.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from domains.anomalies.registry import DesiredAlertState
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.anomalies.alert_workflow import ProjectAlertRequest

_CONSUMER_IDENTITY = "process-reminder-anomaly-source-v1"

_ORDER_PIPELINE_REASONS = {
    "ORDER-001": "尚未發送訂單資訊-1給任何候選月嫂",
    "ORDER-002": "已有候選月嫂願意接案，但尚未發送訂單資訊-2",
    "ORDER-003": "已發送訂單資訊-1，候選月嫂尚未回覆意願",
    "ORDER-004": "已發送訂單資訊-2，尚待後續回覆與定案",
}


def _request(
    code: str,
    source_identity: str,
    source_version: int,
    active: bool,
    snapshot: Mapping[str, Any],
    fingerprint_values: Mapping[str, str],
) -> ProjectAlertRequest:
    desired = DesiredAlertState(code, source_identity, source_version, active, dict(fingerprint_values))
    event = (
        f"process-reminder:{code}:"
        f"{fingerprint_payload({'active': active, 'code': code, 'snapshot': dict(snapshot), 'source_identity': source_identity, 'source_version': source_version}).value}"
    )
    partition = (
        f"process-reminder:{code}:"
        f"{fingerprint_payload({'code': code, 'fingerprint_values': dict(fingerprint_values)}).value}"
    )
    return ProjectAlertRequest(desired, event, _CONSUMER_IDENTITY, partition, dict(snapshot))


def _classify_order_matching_state(matches: list[Mapping[str, Any]]) -> str | None:
    info1_sent = [m for m in matches if m.get("sent_info_1_at") is not None]
    if not info1_sent:
        return "ORDER-001"
    accepted = [m for m in info1_sent if m.get("caregiver_accepted") == 1]
    if not accepted:
        pending = [m for m in info1_sent if m.get("caregiver_accepted") is None]
        return "ORDER-003" if pending else "ORDER-001"
    info2_sent = [m for m in accepted if m.get("sent_info_2_at") is not None]
    return "ORDER-004" if info2_sent else "ORDER-002"


def build_order_matching_requests(
    rows: list[Mapping[str, Any]], *, as_of: date
) -> tuple[ProjectAlertRequest, ...]:
    """rows: one row per (order, matching_record) pair via LEFT JOIN over ALL orders."""
    by_case: dict[str, list[Mapping[str, Any]]] = {}
    case_status: dict[str, tuple[Any, Any]] = {}
    for row in rows:
        case_no = row["case_no"]
        case_status[case_no] = (row.get("status"), row.get("staff_id"))
        matches = by_case.setdefault(case_no, [])
        if row.get("match_id") is not None:
            matches.append(row)
    version = as_of.toordinal()
    requests: list[ProjectAlertRequest] = []
    for case_no, (status, staff_id) in case_status.items():
        eligible = status == "洽談中" and staff_id is None
        classification = _classify_order_matching_state(by_case.get(case_no, [])) if eligible else None
        for code, reason in _ORDER_PIPELINE_REASONS.items():
            active = classification == code
            snapshot = {"case_no": case_no, "reason": reason}
            requests.append(_request(code, case_no, version, active, snapshot, {"case_no": case_no}))
    return tuple(requests)


def build_beclass_missing_requests(
    rows: list[Mapping[str, Any]], *, as_of: date
) -> tuple[ProjectAlertRequest, ...]:
    """rows: one row per order, LEFT JOIN beclass_records, over ALL orders."""
    version = as_of.toordinal()
    requests = []
    for row in rows:
        case_no = row["case_no"]
        active = row.get("beclass_id") is None
        snapshot = {"case_no": case_no}
        requests.append(_request("BECLASS-001", case_no, version, active, snapshot, {"case_no": case_no}))
    return tuple(requests)


def build_resume_not_sent_requests(
    rows: list[Mapping[str, Any]], *, as_of: date
) -> tuple[ProjectAlertRequest, ...]:
    """rows: one row per order with an aggregated pending_resume flag over ALL orders."""
    version = as_of.toordinal()
    requests = []
    for row in rows:
        case_no = row["case_no"]
        active = row.get("staff_id") is None and bool(row.get("pending_resume"))
        snapshot = {"case_no": case_no}
        requests.append(_request("DOC-SEND-001", case_no, version, active, snapshot, {"case_no": case_no}))
    return tuple(requests)


_RECEIVABLE_STAGES = (
    ("訂金", "deposit_due_date", "deposit_receivable", "deposit_received"),
    ("第一期", "first_payment_due_date", "first_payment_receivable", "first_payment_received"),
    ("第二期", "second_payment_due_date", "second_payment_receivable", "second_payment_received"),
)


def build_client_receivable_requests(
    rows: list[Mapping[str, Any]], *, as_of: date
) -> tuple[ProjectAlertRequest, ...]:
    """rows: every client_payments row (no WHERE filtering)."""
    version = as_of.toordinal()
    requests = []
    for row in rows:
        case_no = row["case_no"]
        overdue_stages = []
        for label, due_col, receivable_col, received_col in _RECEIVABLE_STAGES:
            due = row.get(due_col)
            if due is not None and due < as_of and row.get(received_col) < row.get(receivable_col):
                overdue_stages.append(
                    {"階段": label, "到期日": str(due), "應收": str(row.get(receivable_col)), "已收": str(row.get(received_col))}
                )
        active = bool(overdue_stages)
        snapshot = {"case_no": case_no, "overdue_stages": overdue_stages}
        requests.append(_request("RECEIVABLE-001", case_no, version, active, snapshot, {"case_no": case_no}))
    return tuple(requests)


def build_subsidy_return_requests(
    rows: list[Mapping[str, Any]], *, as_of: date
) -> tuple[ProjectAlertRequest, ...]:
    """rows: every client_payments row (no WHERE filtering)."""
    version = as_of.toordinal()
    requests = []
    for row in rows:
        case_no = row["case_no"]
        due = row.get("subsidy_return_due_date")
        active = (
            due is not None
            and due < as_of
            and row.get("subsidy_return_refunded") < row.get("subsidy_return_receivable")
        )
        needs_review = row.get("subsidy_return_review_status") == "review_required"
        snapshot = {
            "case_no": case_no,
            "due_date": str(due) if due else None,
            "needs_review": needs_review,
            "review_reason": row.get("subsidy_return_review_reason"),
        }
        requests.append(_request("RETURN-001", case_no, version, active, snapshot, {"case_no": case_no}))
    return tuple(requests)


def build_schedule_holiday_undecided_requests(
    rows: list[Mapping[str, Any]], *, as_of: date
) -> tuple[ProjectAlertRequest, ...]:
    """rows: case_staff_assignments x holidays within range, LEFT JOIN staff_schedule, any status."""
    version = as_of.toordinal()
    requests = []
    for row in rows:
        staff_id = row["staff_id"]
        holiday_date = row["holiday_date"]
        source_identity = f"{staff_id}:{holiday_date}"
        active = row.get("status") in ("planned", "active") and row.get("schedule_id") is None
        snapshot = {
            "case_no": row.get("case_no"),
            "staff_id": staff_id,
            "holiday_date": str(holiday_date),
            "holiday_name": row.get("holiday_name"),
        }
        requests.append(
            _request(
                "SCHEDULE-001",
                source_identity,
                version,
                active,
                snapshot,
                {"holiday_date": str(holiday_date), "staff_id": str(staff_id)},
            )
        )
    return tuple(requests)


def build_schedule_replaced_assignment_requests(
    rows: list[Mapping[str, Any]],
    *,
    as_of: date,
    already_resolved_assignment_ids: frozenset[int] = frozenset(),
) -> tuple[ProjectAlertRequest, ...]:
    """rows: case_staff_assignments where status='replaced'.

    This alert never auto-resolves: once a human resolves it in the alert
    center, re-scanning must not reopen it, matching the legacy comment that
    there is no data-driven signal for "financial split already reviewed".
    """
    version = as_of.toordinal()
    requests = []
    for row in rows:
        assignment_id = row["id"]
        active = assignment_id not in already_resolved_assignment_ids
        snapshot = {
            "assignment_id": assignment_id,
            "case_no": row.get("case_no"),
            "staff_id": row.get("staff_id"),
            "assigned_start_date": str(row.get("assigned_start_date")) if row.get("assigned_start_date") else None,
            "assigned_end_date": str(row.get("assigned_end_date")) if row.get("assigned_end_date") else None,
            "floor_fee_allocated": str(row.get("floor_fee_allocated")),
            "replacement_reason": row.get("replacement_reason"),
        }
        requests.append(
            _request(
                "SCHEDULE-002",
                str(assignment_id),
                version,
                active,
                snapshot,
                {"assignment_id": str(assignment_id)},
            )
        )
    return tuple(requests)


def build_schedule_overlap_requests(
    rows: list[Mapping[str, Any]], *, as_of: date
) -> tuple[ProjectAlertRequest, ...]:
    """rows: self-joined case_staff_assignments pairs sharing a staff_id, any status."""
    version = as_of.toordinal()
    requests = []
    for row in rows:
        a_id, b_id = row["a_id"], row["b_id"]
        source_identity = f"{a_id}:{b_id}"
        active = (
            row.get("a_status") in ("planned", "active")
            and row.get("b_status") in ("planned", "active")
            and row.get("a_start") <= row.get("b_end")
            and row.get("b_start") <= row.get("a_end")
        )
        snapshot = {
            "staff_id": row.get("staff_id"),
            "assignment_a": {"id": a_id, "case_no": row.get("a_case_no"), "start": str(row.get("a_start")), "end": str(row.get("a_end"))},
            "assignment_b": {"id": b_id, "case_no": row.get("b_case_no"), "start": str(row.get("b_start")), "end": str(row.get("b_end"))},
        }
        requests.append(
            _request(
                "SCHEDULE-003",
                source_identity,
                version,
                active,
                snapshot,
                {"assignment_id_a": str(a_id), "assignment_id_b": str(b_id)},
            )
        )
    return tuple(requests)


def build_schedule_holiday_preference_requests(
    rows: list[Mapping[str, Any]], *, as_of: date
) -> tuple[ProjectAlertRequest, ...]:
    """rows: staff_schedule x holidays x staff_holiday_availability('國定假日必休')."""
    version = as_of.toordinal()
    requests = []
    for row in rows:
        staff_id, work_date = row["staff_id"], row["work_date"]
        source_identity = f"{staff_id}:{work_date}"
        active = bool(row.get("is_work_day"))
        snapshot = {
            "case_no": row.get("case_no"),
            "staff_id": staff_id,
            "work_date": str(work_date),
            "holiday_name": row.get("holiday_name"),
        }
        requests.append(
            _request(
                "SCHEDULE-005",
                source_identity,
                version,
                active,
                snapshot,
                {"staff_id": str(staff_id), "work_date": str(work_date)},
            )
        )
    return tuple(requests)


def build_client_missing_line_requests(
    rows: list[Mapping[str, Any]], *, as_of: date
) -> tuple[ProjectAlertRequest, ...]:
    """rows: every order JOIN clients (case_no is required, so INNER JOIN is safe)."""
    version = as_of.toordinal()
    requests = []
    for row in rows:
        case_no = row["case_no"]
        active = not row.get("line_user_id")
        snapshot = {"case_no": case_no}
        requests.append(_request("LINE-001", case_no, version, active, snapshot, {"case_no": case_no}))
    return tuple(requests)


def build_staff_missing_line_requests(
    rows: list[Mapping[str, Any]], *, as_of: date
) -> tuple[ProjectAlertRequest, ...]:
    """rows: every order LEFT JOIN staff."""
    version = as_of.toordinal()
    requests = []
    for row in rows:
        case_no = row["case_no"]
        active = row.get("staff_id") is not None and not row.get("staff_line_user_id")
        snapshot = {"case_no": case_no}
        requests.append(_request("LINE-005", case_no, version, active, snapshot, {"case_no": case_no}))
    return tuple(requests)


def build_line_task_no_reply_requests(
    rows: list[Mapping[str, Any]], *, as_of: date
) -> tuple[ProjectAlertRequest, ...]:
    """rows: every sent line_push task, with a has_reply flag already computed by the caller."""
    version = as_of.toordinal()
    requests = []
    for row in rows:
        task_id = row["id"]
        active = not row.get("has_reply")
        snapshot = {
            "task_id": task_id,
            "to_user_id": row.get("to_user_id"),
            "sent_at": str(row.get("sent_at")) if row.get("sent_at") else None,
            "message_content": row.get("message_content"),
        }
        requests.append(
            _request("LINE-002", str(task_id), version, active, snapshot, {"task_id": str(task_id)})
        )
    return tuple(requests)


def build_line_identity_conflict_requests(
    rows: list[Mapping[str, Any]], *, as_of: date
) -> tuple[ProjectAlertRequest, ...]:
    """rows: every distinct non-empty line_user_id used by clients or staff, with
    conflict details (client/staff name pairs) already resolved by the caller."""
    version = as_of.toordinal()
    requests = []
    for row in rows:
        line_user_id = row["line_user_id"]
        active = bool(row.get("is_conflicting"))
        snapshot = {
            "line_user_id": line_user_id,
            "client_case_no": row.get("client_case_no"),
            "client_name": row.get("client_name"),
            "staff_id": row.get("staff_id"),
            "staff_name": row.get("staff_name"),
        }
        requests.append(
            _request("LINE-004", line_user_id, version, active, snapshot, {"line_user_id": line_user_id})
        )
    return tuple(requests)


__all__ = [
    "build_beclass_missing_requests",
    "build_client_missing_line_requests",
    "build_client_receivable_requests",
    "build_line_identity_conflict_requests",
    "build_line_task_no_reply_requests",
    "build_order_matching_requests",
    "build_resume_not_sent_requests",
    "build_schedule_holiday_preference_requests",
    "build_schedule_holiday_undecided_requests",
    "build_schedule_overlap_requests",
    "build_schedule_replaced_assignment_requests",
    "build_staff_missing_line_requests",
    "build_subsidy_return_requests",
]
