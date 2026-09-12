"""Matching plan version persistence service."""

from __future__ import annotations

import re
import json
from datetime import datetime, timedelta
from typing import Any, Callable

from subsystems.scheduling.ports import (
    SegmentedAvailabilityFactsPort,
    unconfigured_connection_factory,
)
from subsystems.scheduling.segmented_availability_query import (
    search_segmented_caregiver_availability,
)
from subsystems.scheduling.candidate_contact_pool_workflow import query_pool
from shared_kernel.fingerprints import fingerprint_payload


get_connection = unconfigured_connection_factory

_STRICT_YMD = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_EVENT_KEY = re.compile(r"^.{1,191}$", re.DOTALL)


def _run_in_application_uow(
    operation: Callable[[Any, Any], dict[str, Any]],
    *,
    commit: bool = True,
) -> dict[str, Any]:
    """Own matching-plan persistence in one Application transaction."""
    connection = cursor = None
    cursor_closed = {"closed": False}
    connection_closed = {"closed": False}
    unit_of_work = None
    try:
        connection = get_connection()
        unit_of_work = connection
        cursor = connection.cursor()
        result = operation(connection, cursor)
        if not commit:
            unit_of_work.rollback()
        elif result.get("event_key") is not None:
            unit_of_work.commit()
        elif result.get("result") != "existing" and result.get("status") != "idempotent_replay":
            unit_of_work.commit()
        else:
            unit_of_work.rollback()
        return result
    except Exception:
        if unit_of_work is not None:
            try:
                unit_of_work.rollback()
            except BaseException:
                pass
        raise
    finally:
        cursor_error = None
        connection_error = None
        if cursor is not None:
            cursor_error = _safe_close(cursor, cursor_closed)
        if connection is not None:
            connection_error = _safe_close(connection, connection_closed)
        if cursor_error is not None:
            raise cursor_error
        if connection_error is not None:
            raise connection_error


def _normalize_case_no(case_no: Any) -> str:
    if not isinstance(case_no, str):
        raise ValueError("case_no is required")
    normalized = case_no.strip()
    if not normalized:
        raise ValueError("case_no is required")
    return normalized


def _normalize_created_by(created_by: Any) -> str:
    if not isinstance(created_by, str):
        raise ValueError("created_by is required")
    normalized = created_by.strip()
    if not normalized:
        raise ValueError("created_by is required")
    return normalized


def _normalize_event_key(event_key: Any) -> str:
    if not isinstance(event_key, str):
        raise ValueError("event_key is required")
    normalized = event_key.strip()
    if not _EVENT_KEY.fullmatch(normalized):
        raise ValueError("event_key is required")
    return normalized


def _normalize_ymd(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be YYYY-MM-DD")
    if not _STRICT_YMD.fullmatch(value):
        raise ValueError(f"{field_name} must be YYYY-MM-DD")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field_name} must be YYYY-MM-DD")
    return value


def _normalize_db_date(value: Any, field_name: str) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if hasattr(value, "isoformat"):
        value_str = value.isoformat()
    elif isinstance(value, str):
        value_str = value
    else:
        raise ValueError(f"{field_name} must be YYYY-MM-DD")
    return _normalize_ymd(value_str, field_name)


def _normalize_segments(segments: Any) -> list[dict[str, Any]]:
    if not isinstance(segments, list):
        raise ValueError("segments must be a list")
    if len(segments) not in (1, 2, 3, 4):
        raise ValueError("segments must contain 1, 2, 3, or 4 items")

    normalized: list[dict[str, Any]] = []
    seen_staff: set[int] = set()
    for segment in segments:
        if not isinstance(segment, dict):
            raise ValueError("segment must be a dict")
        start_value = segment.get("start_date", segment.get("assigned_start_date"))
        end_value = segment.get("end_date", segment.get("assigned_end_date"))
        if start_value is None or end_value is None:
            raise ValueError("segment.start_date and segment.end_date are required")
        extra_fields = set(segment.keys()) - {
            "staff_id",
            "start_date",
            "end_date",
            "assigned_start_date",
            "assigned_end_date",
        }
        if extra_fields:
            raise ValueError("segment contains unknown fields")
        if "start_date" in segment and "assigned_start_date" in segment:
            if segment["start_date"] != segment["assigned_start_date"]:
                raise ValueError("segment start_date mismatch")
        if "end_date" in segment and "assigned_end_date" in segment:
            if segment["end_date"] != segment["assigned_end_date"]:
                raise ValueError("segment end_date mismatch")

        staff_id = segment.get("staff_id")
        if isinstance(staff_id, bool) or not isinstance(staff_id, int):
            raise ValueError("segment.staff_id must be a positive integer")
        if staff_id <= 0:
            raise ValueError("segment.staff_id must be a positive integer")
        if staff_id in seen_staff:
            raise ValueError("segment staff_id must be unique")
        seen_staff.add(staff_id)

        start_date = _normalize_ymd(start_value, "segment.start_date")
        end_date = _normalize_ymd(end_value, "segment.end_date")
        if start_date > end_date:
            raise ValueError("segment.start_date cannot be after segment.end_date")
        normalized.append(
            {
                "staff_id": staff_id,
                "assigned_start_date": start_date,
                "assigned_end_date": end_date,
            }
        )

    for previous, current in zip(normalized, normalized[1:]):
        previous_end = datetime.strptime(
            previous["assigned_end_date"], "%Y-%m-%d"
        ).date()
        current_start = datetime.strptime(
            current["assigned_start_date"], "%Y-%m-%d"
        ).date()
        expected_start = previous_end + timedelta(days=1)
        if current_start < expected_start:
            raise ValueError("segments must not overlap or be out of order")
        if current_start > expected_start:
            raise ValueError("segments must be contiguous without gaps")

    return normalized


def _segments_signature(segments: list[dict[str, Any]]) -> tuple[tuple[int, int, str, str], ...]:
    return tuple(
        (
            idx,
            segment["staff_id"],
            segment["assigned_start_date"],
            segment["assigned_end_date"],
        )
        for idx, segment in enumerate(segments)
    )


def _completion_signature(combo: list[dict[str, Any]]) -> tuple[tuple[int, int, str, str], ...]:
    return tuple(
        (
            int(item["segment_index"]),
            int(item["staff_id"]),
            _normalize_ymd(item["start_date"], "combo.start_date"),
            _normalize_ymd(item["end_date"], "combo.end_date"),
        )
        for item in combo
    )


def _safe_close(resource: Any, state: dict[str, bool]) -> BaseException | None:
    if state.get("closed"):
        return None

    state["closed"] = True
    try:
        resource.close()
    except BaseException as exc:  # noqa: BLE001
        return exc
    return None


def _as_sql_payload(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "staff_id": segment["staff_id"],
            "start_date": segment["assigned_start_date"],
            "end_date": segment["assigned_end_date"],
        }
        for segment in segments
    ]


def _create_command_fingerprint(
    case_no: str,
    segments: list[dict[str, Any]],
    actor: str,
    as_of: str,
) -> str:
    return fingerprint_payload({
        "case_no": case_no,
        "segments": [
            {
                "segment_order": index,
                "staff_id": segment["staff_id"],
                "assigned_start_date": segment["assigned_start_date"],
                "assigned_end_date": segment["assigned_end_date"],
            }
            for index, segment in enumerate(segments, start=1)
        ],
        "actor": actor,
        "as_of": as_of,
    }).value


def create_matching_plan_version(
    case_no: Any,
    segments: Any,
    created_by: Any,
    as_of: Any,
    *,
    facts_port: SegmentedAvailabilityFactsPort,
    require_willing_candidate: bool = False,
    event_key: Any,
) -> dict[str, Any]:
    """Create or reuse a proposed matching plan version for one case.

    Validation uses the latest availability result first. If payload matches an
    exact complete combination, persistence is done in one transaction.
    """

    case_no_value = _normalize_case_no(case_no)
    created_by_value = _normalize_created_by(created_by)
    as_of_value = _normalize_ymd(as_of, "as_of")
    normalized_segments = _normalize_segments(segments)

    event_key_value = _normalize_event_key(event_key)
    command_fingerprint = _create_command_fingerprint(
        case_no_value, normalized_segments, created_by_value, as_of_value,
    )
    return _run_in_application_uow(
        lambda connection, cursor: _create_matching_plan_version_with_receipt(
            connection,
            cursor,
            case_no_value,
            normalized_segments,
            created_by_value,
            as_of_value,
            event_key_value,
            command_fingerprint,
            facts_port,
            require_willing_candidate,
        )
    )


def _validate_current_availability(
    case_no_value: str,
    normalized_segments: list[dict[str, Any]],
    as_of_value: str,
    facts_port: SegmentedAvailabilityFactsPort,
    require_willing_candidate: bool,
) -> None:
    del require_willing_candidate
    availability_kwargs = {
        "case_no": case_no_value,
        "segment_count": len(normalized_segments),
        "segment_drafts": _as_sql_payload(normalized_segments),
        "as_of": as_of_value,
        "include_candidate_options": False,
        "filter_policy": {
            "region": False,
            "cooking": False,
            "preferred_service_days": False,
            "daily_service_hours": False,
        },
    }
    availability_kwargs["facts_port"] = facts_port
    # The selected segments already came from a preference-aware query (or an
    # auditable manual selection).  Apply must fresh-check schedule occupancy,
    # not reintroduce optional discovery filters that can reject the exact
    # combination the UI just offered.
    availability = search_segmented_caregiver_availability(**availability_kwargs)

    complete_combinations = availability.get("complete_combinations")
    if not isinstance(complete_combinations, list):
        raise ValueError("availability result malformed")

    feasibility = availability.get("feasibility")
    if feasibility != "complete":
        raise ValueError("submitted segments must match a complete combination")

    conflicts = availability.get("conflicts")
    if not isinstance(conflicts, list):
        raise ValueError("availability result malformed")
    if conflicts:
        raise ValueError("submitted segments must match a complete combination")

    target_signature = _segments_signature(normalized_segments)
    matched = any(
        _completion_signature(item) == target_signature for item in complete_combinations
    )
    if not matched:
        raise ValueError("submitted segments must match a complete combination")

    return None


def _create_matching_plan_version_with_receipt(
    connection: Any,
    cursor: Any,
    case_no_value: str,
    normalized_segments: list[dict[str, Any]],
    created_by_value: str,
    as_of_value: str,
    event_key: str,
    command_fingerprint: str,
    facts_port: SegmentedAvailabilityFactsPort,
    require_willing_candidate: bool,
) -> dict[str, Any]:
    # Lock the case root before the idempotency row.  A concurrent command with
    # this key must see a committed original receipt before it rechecks current
    # availability, otherwise the original plan can make its own replay stale.
    _lock_matching_plan_case_root(cursor, case_no_value)
    replay = _load_matching_plan_create_receipt(cursor, event_key, for_update=True)
    if replay is not None:
        if replay["command_fingerprint"] != command_fingerprint:
            raise ValueError("matching plan create idempotency key does not match original command")
        if replay["case_no"] != case_no_value:
            raise ValueError("matching plan create idempotency key does not match original command")
        return {**replay, "replayed": True}

    _validate_current_availability(
        case_no_value,
        normalized_segments,
        as_of_value,
        facts_port,
        require_willing_candidate,
    )
    result = _create_matching_plan_version_in_transaction(
        connection,
        cursor,
        case_no_value,
        normalized_segments,
        created_by_value,
        _segments_signature(normalized_segments),
        require_willing_candidate,
    )
    receipt = {
        **result,
        "actor": created_by_value,
        "as_of": as_of_value,
        "event_key": event_key,
        "command_fingerprint": command_fingerprint,
        "replayed": False,
    }
    _save_matching_plan_create_receipt(cursor, receipt)
    return receipt


def _create_matching_plan_version_in_transaction(
    connection: Any,
    cursor: Any,
    case_no_value: str,
    normalized_segments: list[dict[str, Any]],
    created_by_value: str,
    target_signature: tuple[tuple[int, int, str, str], ...],
    require_willing_candidate: bool = False,
) -> dict[str, Any]:
    try:
        _lock_matching_plan_case_root(cursor, case_no_value)

        if require_willing_candidate:
            _require_current_willing_candidate(
                connection,
                case_no_value,
                normalized_segments,
            )

        cursor.execute(
            "SELECT id, version, status, is_active\n"
            "FROM caregiver_matching_plans\n"
            "WHERE case_no = %s\n"
            "ORDER BY version DESC\n"
            "FOR UPDATE",
            (case_no_value,),
        )
        plans = cursor.fetchall() or []
        if any(row["status"] == "accepted" for row in plans):
            raise ValueError("case is not editable while an accepted plan exists")

        cursor.execute(
            "SELECT p.id AS plan_id,\n"
            "       s.segment_order,\n"
            "       s.staff_id,\n"
            "       s.assigned_start_date,\n"
            "       s.assigned_end_date\n"
            "FROM caregiver_matching_plan_segments s\n"
            "INNER JOIN caregiver_matching_plans p ON p.id = s.plan_id\n"
            "WHERE p.case_no = %s\n"
            "ORDER BY p.id, s.segment_order\n"
            "FOR UPDATE",
            (case_no_value,),
        )
        plan_segments = cursor.fetchall() or []
        segments_by_plan: dict[int, list[dict[str, Any]]] = {}
        for row in plan_segments:
            normalized_row = {
                "plan_id": row["plan_id"],
                "segment_order": row["segment_order"],
                "staff_id": row["staff_id"],
                "assigned_start_date": _normalize_db_date(
                    row["assigned_start_date"],
                    "assigned_start_date",
                ),
                "assigned_end_date": _normalize_db_date(
                    row["assigned_end_date"],
                    "assigned_end_date",
                ),
            }
            segments_by_plan.setdefault(row["plan_id"], []).append(normalized_row)

        cursor.execute(
            "SELECT l.id,\n"
            "       l.plan_id,\n"
            "       l.status,\n"
            "       l.is_active\n"
            "FROM caregiver_availability_locks l\n"
            "INNER JOIN caregiver_matching_plans p ON p.id = l.plan_id\n"
            "WHERE p.case_no = %s\n"
            "  AND l.status = 'active'\n"
            "  AND l.is_active = 1\n"
            "FOR UPDATE",
            (case_no_value,),
        )
        active_locks = cursor.fetchall() or []

        cursor.execute(
            "SELECT ld.id,\n"
            "       ld.lock_id,\n"
            "       ld.segment_id,\n"
            "       ld.staff_id,\n"
            "       ld.lock_date,\n"
            "       ld.active_marker\n"
            "FROM caregiver_availability_lock_days ld\n"
            "INNER JOIN caregiver_availability_locks l ON l.id = ld.lock_id\n"
            "INNER JOIN caregiver_matching_plans p ON p.id = l.plan_id\n"
            "WHERE p.case_no = %s\n"
            "  AND l.status = 'active'\n"
            "  AND l.is_active = 1\n"
            "  AND ld.active_marker = 1\n"
            "FOR UPDATE",
            (case_no_value,),
        )
        active_lock_days = cursor.fetchall() or []

        if active_locks or active_lock_days:
            raise ValueError("case has an active availability lock")

        for plan in plans:
            if plan.get("status") != "proposed" or plan.get("is_active") != 1:
                continue
            current_segments = sorted(
                segments_by_plan.get(plan["id"], []),
                key=lambda item: item["segment_order"],
            )
            if _segments_signature(current_segments) == target_signature:
                return {
                    "plan_id": plan["id"],
                    "case_no": plan.get("case_no", case_no_value),
                    "version": plan["version"],
                    "status": "proposed",
                    "result": "existing",
                    "segments": [
                        {
                            "segment_order": row["segment_order"],
                            "staff_id": row["staff_id"],
                            "assigned_start_date": row["assigned_start_date"],
                            "assigned_end_date": row["assigned_end_date"],
                        }
                        for row in current_segments
                    ],
                }

        cursor.execute(
            "SELECT MAX(version) AS max_version\n"
            "FROM caregiver_matching_plans\n"
            "WHERE case_no = %s",
            (case_no_value,),
        )
        max_version_row = cursor.fetchone() or {}
        max_version = int(max_version_row.get("max_version") or 0)
        new_version = max_version + 1

        cursor.execute(
            "UPDATE caregiver_matching_plans\n"
            "SET status = 'superseded', is_active = NULL\n"
            "WHERE case_no = %s\n"
            "  AND is_active = 1\n"
            "  AND status IN ('draft', 'proposed')",
            (case_no_value,),
        )
        cursor.execute(
            "INSERT INTO caregiver_matching_plans\n"
            "(case_no, version, status, is_active, start_date, end_date, created_by)\n"
            "VALUES (%s, %s, 'proposed', 1, %s, %s, %s)",
            (
                case_no_value,
                new_version,
                normalized_segments[0]["assigned_start_date"],
                normalized_segments[-1]["assigned_end_date"],
                created_by_value,
            ),
        )
        plan_id = cursor.lastrowid
        for index, segment in enumerate(normalized_segments, start=1):
            cursor.execute(
                "INSERT INTO caregiver_matching_plan_segments\n"
                "(plan_id, segment_order, staff_id, assigned_start_date, assigned_end_date)\n"
                "VALUES (%s, %s, %s, %s, %s)",
                (
                    plan_id,
                    index,
                    segment["staff_id"],
                    segment["assigned_start_date"],
                    segment["assigned_end_date"],
                ),
            )

        return {
            "plan_id": plan_id,
            "case_no": case_no_value,
            "version": new_version,
            "status": "proposed",
            "result": "created",
            "segments": [
                {
                    "segment_order": index + 1,
                    "staff_id": segment["staff_id"],
                    "assigned_start_date": segment["assigned_start_date"],
                    "assigned_end_date": segment["assigned_end_date"],
                }
                for index, segment in enumerate(normalized_segments)
            ],
        }
    finally:
        pass


def _lock_matching_plan_case_root(cursor: Any, case_no_value: str) -> None:
    cursor.execute(
        "SELECT o.case_no, o.status, o.start_date, o.end_date\n"
        "FROM orders o\n"
        "WHERE o.case_no = %s FOR UPDATE",
        (case_no_value,),
    )
    order_row = cursor.fetchone()
    if order_row is None:
        raise ValueError("case not found")
    if order_row["status"] not in {"洽談中", "訂單成立"}:
        raise ValueError("case is not in negotiation stage")
    _normalize_db_date(order_row["start_date"], "start_date")
    _normalize_db_date(order_row["end_date"], "end_date")


def get_matching_plan_create_receipt(case_no: Any, event_key: Any) -> dict[str, Any]:
    case_no_value = _normalize_case_no(case_no)
    event_key_value = _normalize_event_key(event_key)

    def read_receipt(_connection: Any, cursor: Any) -> dict[str, Any]:
        receipt = _load_matching_plan_create_receipt(cursor, event_key_value, for_update=False)
        if receipt is None or receipt["case_no"] != case_no_value:
            raise ValueError("matching plan create receipt not found")
        return receipt

    return _run_in_application_uow(read_receipt, commit=False)


def _load_matching_plan_create_receipt(
    cursor: Any,
    event_key: str,
    *,
    for_update: bool,
) -> dict[str, Any] | None:
    cursor.execute(
        "SELECT case_no, plan_id, plan_version, plan_status, actor, as_of, "
        "idempotency_key, command_fingerprint, result_kind, ordered_segments, result_snapshot "
        "FROM matching_plan_create_receipts WHERE idempotency_key = %s"
        + (" FOR UPDATE" if for_update else ""),
        (event_key,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    raw_snapshot = row["result_snapshot"]
    try:
        snapshot = raw_snapshot if isinstance(raw_snapshot, dict) else json.loads(raw_snapshot)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError("matching plan create receipt is invalid") from error
    if not isinstance(snapshot, dict):
        raise ValueError("matching plan create receipt is invalid")
    required = {
        "case_no", "plan_id", "version", "status", "result", "segments",
        "actor", "as_of", "event_key", "command_fingerprint", "replayed",
    }
    if set(snapshot) != required or snapshot["replayed"] is not False:
        raise ValueError("matching plan create receipt is invalid")
    try:
        stored_segments = (
            row["ordered_segments"]
            if isinstance(row["ordered_segments"], list)
            else json.loads(row["ordered_segments"])
        )
        receipt_segments = _receipt_command_segments(snapshot["segments"])
    except (KeyError, TypeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("matching plan create receipt is invalid") from error
    if (
        snapshot["case_no"] != row["case_no"]
        or snapshot["plan_id"] != row["plan_id"]
        or snapshot["version"] != row["plan_version"]
        or snapshot["status"] != row["plan_status"]
        or snapshot["actor"] != row["actor"]
        or snapshot["as_of"] != _normalize_db_date(row["as_of"], "as_of")
        or snapshot["event_key"] != row["idempotency_key"]
        or snapshot["command_fingerprint"] != row["command_fingerprint"]
        or snapshot["result"] != row["result_kind"]
        or stored_segments != snapshot["segments"]
        or snapshot["command_fingerprint"] != _create_command_fingerprint(
            snapshot["case_no"], receipt_segments, snapshot["actor"], snapshot["as_of"],
        )
    ):
        raise ValueError("matching plan create receipt is invalid")
    return snapshot


def _save_matching_plan_create_receipt(cursor: Any, receipt: dict[str, Any]) -> None:
    cursor.execute(
        "INSERT INTO matching_plan_create_receipts "
        "(idempotency_key, command_fingerprint, case_no, plan_id, plan_version, "
        "plan_status, actor, as_of, result_kind, ordered_segments, result_snapshot) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            receipt["event_key"],
            receipt["command_fingerprint"],
            receipt["case_no"],
            receipt["plan_id"],
            receipt["version"],
            receipt["status"],
            receipt["actor"],
            receipt["as_of"],
            receipt["result"],
            json.dumps(receipt["segments"], ensure_ascii=False, separators=(",", ":")),
            json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        ),
    )


def _receipt_command_segments(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("receipt segments are invalid")
    drafts = []
    for index, segment in enumerate(value, start=1):
        if not isinstance(segment, dict) or set(segment) != {
            "segment_order", "staff_id", "assigned_start_date", "assigned_end_date",
        }:
            raise ValueError("receipt segments are invalid")
        if segment["segment_order"] != index:
            raise ValueError("receipt segments are invalid")
        drafts.append({
            "staff_id": segment["staff_id"],
            "assigned_start_date": segment["assigned_start_date"],
            "assigned_end_date": segment["assigned_end_date"],
        })
    return _normalize_segments(drafts)


def _require_current_willing_candidate(connection, case_no, segments):
    if len(segments) != 1:
        raise ValueError("willing candidate selection requires exactly one segment")
    segment = segments[0]
    state = query_pool(case_no, connection=connection, for_update=True)
    matches = tuple(
        candidate
        for candidate in state.candidates
        if candidate.status in {"active", "selected"}
        and candidate.willingness == "willing"
        and candidate.staff_id == segment["staff_id"]
        and candidate.service_start_date.isoformat()
        == segment["assigned_start_date"]
        and candidate.service_end_date.isoformat()
        == segment["assigned_end_date"]
    )
    if len(matches) != 1:
        raise ValueError("current willing candidate is required")
