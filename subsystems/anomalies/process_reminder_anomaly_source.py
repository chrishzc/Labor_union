"""
File: process_reminder_anomaly_source.py
Description: 由根事實建立流程提醒與 HCM／BeClass 對稱異常命令。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Mapping

from domains.anomalies.registry import DesiredAlertState
from domains.client_finance.subsidy_advance import (
    SubsidyAdvanceDecisionKind,
    SubsidyAdvanceFacts,
    build_subsidy_advance_decision,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.money import MoneyNTD
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


def build_hcm_missing_requests(
    rows: list[Mapping[str, Any]], *, as_of: date
) -> tuple[ProjectAlertRequest, ...]:
    """Project BeClass rows waiting for their independently imported HCM case."""
    version = as_of.toordinal()
    requests = []
    for row in rows:
        query_no = str(row["query_no"])
        active = row.get("beclass_id") is not None and row.get("hcm_case_no") is None
        review_item_id = f"counterpart:{query_no}"
        snapshot = {
            "entity_kind": "client_counterpart",
            "error_codes": ("beclass_hcm_mismatch",),
            "masked_identifier": f"case-***-{query_no[-4:]}",
            "review_item_id": review_item_id,
            "source_row": 1,
            "source_sheet": "current-state",
            "version": version,
        }
        requests.append(
            _request(
                "IMPORT-003",
                f"beclass-counterpart:{query_no}",
                version,
                active,
                snapshot,
                {"entity_kind": "client_counterpart", "review_item_id": review_item_id},
            )
        )
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


_RECEIVABLE_STAGE_LABELS = {
    "deposit": "訂金",
    "first": "第一期",
    "second": "第二期",
    "adjustment": "調整款",
}


def build_client_receivable_requests(
    rows: list[Mapping[str, Any]], *, as_of: date
) -> tuple[ProjectAlertRequest, ...]:
    """rows: canonical client-obligation candidates, including inactive alert cases."""
    version = as_of.toordinal()
    requests: list[ProjectAlertRequest] = []
    for case_no, obligations in _obligations_by_case(rows).items():
        overdue_obligations = [
            _overdue_obligation_snapshot(obligation, _RECEIVABLE_STAGE_LABELS, "未收")
            for obligation in obligations
            if _is_open_overdue_of_type(
                obligation, as_of, "receivable_from_client", _RECEIVABLE_STAGE_LABELS
            )
        ]
        overdue_obligations = [item for item in overdue_obligations if item is not None]
        snapshot = {
            "case_no": case_no,
            "action": "核對應收資料、銀行對帳單與匯入結果",
            "overdue_obligations": overdue_obligations,
        }
        active = bool(overdue_obligations)
        requests.append(_request("RECEIVABLE-001", case_no, version, active, snapshot, {"case_no": case_no}))
    return tuple(requests)


def build_subsidy_return_requests(
    rows: list[Mapping[str, Any]], *, as_of: date
) -> tuple[ProjectAlertRequest, ...]:
    """rows: canonical client-obligation candidates, including inactive alert cases."""
    version = as_of.toordinal()
    requests: list[ProjectAlertRequest] = []
    for case_no, obligations in _obligations_by_case(rows).items():
        overdue_obligations = [
            _overdue_obligation_snapshot(
                obligation, {"subsidy_return": "客戶補助退還"}, "未付"
            )
            for obligation in obligations
            if _is_open_overdue_of_type(
                obligation, as_of, "payable_to_client", {"subsidy_return": "客戶補助退還"}
            )
        ]
        overdue_obligations = [item for item in overdue_obligations if item is not None]
        snapshot = {
            "case_no": case_no,
            "action": "核對應付資料、銀行對帳單與匯入結果",
            "overdue_obligations": overdue_obligations,
        }
        active = bool(overdue_obligations)
        requests.append(_request("RETURN-001", case_no, version, active, snapshot, {"case_no": case_no}))
    return tuple(requests)


def build_client_payable_requests(
    rows: list[Mapping[str, Any]], *, as_of: date
) -> tuple[ProjectAlertRequest, ...]:
    """rows: canonical client-obligation candidates, including inactive alert cases."""
    version = as_of.toordinal()
    requests: list[ProjectAlertRequest] = []
    labels = {"refund": "一般客戶退款", "adjustment": "客戶調整應付"}
    for case_no, obligations in _obligations_by_case(rows).items():
        overdue_obligations = [
            _overdue_obligation_snapshot(obligation, labels, "未付")
            for obligation in obligations
            if _is_open_overdue_of_type(obligation, as_of, "payable_to_client", labels)
        ]
        overdue_obligations = [item for item in overdue_obligations if item is not None]
        snapshot = {
            "case_no": case_no,
            "action": "核對應付資料、銀行對帳單與匯入結果",
            "overdue_obligations": overdue_obligations,
        }
        requests.append(
            _request("CLIENTPAYABLE-001", case_no, version, bool(overdue_obligations), snapshot, {"case_no": case_no})
        )
    return tuple(requests)


def build_subsidy_advance_due_requests(
    rows: list[Mapping[str, Any]], *, as_of: date
) -> tuple[ProjectAlertRequest, ...]:
    """rows: claim-linked subsidy-return candidates plus prior alert identities."""
    version = as_of.toordinal()
    requests: list[ProjectAlertRequest] = []
    for case_no, candidates in _obligations_by_case(rows).items():
        ready = [_subsidy_advance_snapshot(row, as_of) for row in candidates]
        ready = [item for item in ready if item is not None]
        snapshot = {
            "case_no": case_no,
            "action": "核對補助撥款、應付資料、銀行對帳單與匯入結果",
            "advance_candidates": ready,
        }
        requests.append(
            _request("SUBSIDYADVANCE-001", case_no, version, bool(ready), snapshot, {"case_no": case_no})
        )
    return tuple(requests)


def _subsidy_advance_snapshot(row: Mapping[str, Any], as_of: date) -> dict[str, str] | None:
    completed_on = row.get("actual_end_date")
    entitled_amount = _whole_ntd(row.get("entitled_amount_ntd"))
    allocated_amount = _whole_ntd(row.get("allocated_amount_ntd"))
    if not isinstance(completed_on, date) or entitled_amount is None:
        return None
    if allocated_amount is None or entitled_amount <= 0:
        return None
    decision = build_subsidy_advance_decision(
        SubsidyAdvanceFacts(
            row["case_no"], completed_on, MoneyNTD(entitled_amount), MoneyNTD(allocated_amount)
        ),
        as_of,
    )
    if decision.kind is not SubsidyAdvanceDecisionKind.READY:
        return None
    return {"到期日": decision.refund_due_on.isoformat(), "待墊付": str(entitled_amount)}


def _whole_ntd(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if not isinstance(value, (int, float, Decimal)) or int(value) != value:
        return None
    return int(value)


def _obligations_by_case(rows: list[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    obligations: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        obligations.setdefault(row["case_no"], []).append(row)
    return obligations


def _is_open_overdue_of_type(
    row: Mapping[str, Any], as_of: date, direction: str, labels: Mapping[str, str]
) -> bool:
    if row.get("direction") != direction or row.get("obligation_type") not in labels:
        return False
    due_date = row.get("due_date")
    return (
        due_date is not None
        and due_date < as_of
        and row.get("status") == "open"
        and row.get("amount_due_ntd", 0) > 0
    )


def _overdue_obligation_snapshot(
    row: Mapping[str, Any], labels: Mapping[str, str], amount_label: str
) -> dict[str, str] | None:
    label = labels.get(str(row.get("obligation_type")))
    if label is None:
        return None
    snapshot = {
        "階段": label,
        "到期日": str(row["due_date"]),
    }
    snapshot[amount_label] = str(row["amount_due_ntd"])
    return snapshot


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
            "staff_name": row.get("staff_name"),
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
            "staff_name": row.get("staff_name"),
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
            "staff_name": row.get("staff_name"),
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
    "build_client_payable_requests",
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
    "build_subsidy_advance_due_requests",
]
