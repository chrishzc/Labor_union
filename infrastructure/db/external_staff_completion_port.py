"""
File: external_staff_completion_port.py
Description: 在外部簽約回報的 borrowed 交易內建立 commitment 與 deposit。
"""

from __future__ import annotations

from datetime import date

import hashlib
import json
from typing import Any

from domains.client_finance.obligation_planning import (
    build_precontract_deposit_candidate,
    precontract_deposit_terms_impact,
)
from infrastructure.mysql.client_finance_terms_writer import (
    persist_client_finance_terms_impact,
)
from infrastructure.mysql.order_terms_read_model import (
    load_contract_client_finance_facts,
    select_order,
)
from infrastructure.mysql.assignment_plan_repository import load_occupancy_snapshot
from subsystems.scheduling.segmented_availability import derive_segment_availability
from subsystems.scheduling.segmented_availability_query import _expand_staff_unavailability_days
from subsystems.scheduling.availability_lock_acquisition_workflow import _with_current_confirmed_service_dates
from shared_kernel.identities import IdempotencyKey
from subsystems.contract_signing.external_signing_contracts import (
    RecordExternalStaffSigningReport,
)
from subsystems.contract_signing.external_signing_workflow import (
    StaffCompletionPrerequisites,
)
from subsystems.contract_signing.staff_contract_application import (
    _commitment_service_days,
)
from subsystems.orders.contract_completion_workflow import (
    ContractCompletionClientFinanceCommand,
)


class MySqlExternalStaffCompletionPort:
    """Borrowed adapter; the external-signing workflow remains the only commit owner."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def signing_blockers(self, facts, *, for_update: bool = False) -> tuple[str, ...]:
        suffix = " FOR UPDATE" if for_update else ""
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id,staff_id,assigned_start_date,assigned_end_date "
                "FROM caregiver_matching_plan_segments WHERE plan_id=%s ORDER BY segment_order,id" + suffix,
                (facts.matching_plan_id,),
            )
            segments = tuple(cursor.fetchall())
        if {int(row["id"]) for row in segments} != {row.matching_segment_id for row in facts.staff_targets}:
            return ("signing_service_dates_unavailable",)
        snapshot = {"segments": [{"segment_id": row["id"], "staff_id": row["staff_id"],
            "assigned_start_date": row["assigned_start_date"].isoformat(),
            "assigned_end_date": row["assigned_end_date"].isoformat()} for row in segments]}
        try:
            with self._connection.cursor() as cursor:
                current = _with_current_confirmed_service_dates(cursor, facts.case_no, snapshot, for_update=for_update)
        except ValueError as error:
            if str(error) != "current confirmed service dates are required":
                return ("signing_service_dates_unavailable",)
            try:
                allocations = _commitment_service_days(self._connection, facts.case_no, segments)
            except ValueError as error:
                if str(error) in {"precontract_service_dates_incomplete", "precontract_service_days_mismatch"}:
                    return ("signing_service_dates_unavailable",)
                raise
        else:
            segments = tuple({"id": row["segment_id"], "staff_id": row["staff_id"],
                "assigned_start_date": date.fromisoformat(row["assigned_start_date"]),
                "assigned_end_date": date.fromisoformat(row["assigned_end_date"])} for row in current["segments"])
            by_segment = {row["id"]: row for row in segments}
            allocations = tuple((by_segment[row["segment_id"]], date.fromisoformat(row["lock_date"])) for row in current["lock_rows"])
        drafts = []
        for segment in segments:
            days = tuple(day for owner, day in allocations if owner["id"] == segment["id"])
            if not days:
                return ("signing_service_dates_unavailable",)
            drafts.append({"staff_id": int(segment["staff_id"]), "start_date": segment["assigned_start_date"].isoformat(), "end_date": segment["assigned_end_date"].isoformat()})
        start = min(row["assigned_start_date"] for row in segments)
        end = max(row["assigned_end_date"] for row in segments)
        staff_ids = tuple(sorted({int(row["staff_id"]) for row in segments}))
        with self._connection.cursor() as cursor:
            occupancy, _ = load_occupancy_snapshot(cursor, staff_ids, facts.case_no, lock=for_update)
            placeholders = ",".join("%s" for _ in staff_ids)
            cursor.execute(
                "SELECT id,staff_id,start_date,end_date FROM scheduling_staff_unavailability_blocks "
                "WHERE status='effective' AND staff_id IN (" + placeholders + ") "
                "AND start_date<=%s AND (end_date IS NULL OR end_date>=%s)" + suffix,
                (*staff_ids, end, start),
            )
            unavailable = tuple(cursor.fetchall())
        occupied_days = [{"staff_id": row.staff_id, "work_date": row.occupancy_date.isoformat(), "reason_code": "assignment"}
            for row in occupancy if row.source_case_no != facts.case_no]
        for row in unavailable:
            occupied_days.extend(_expand_staff_unavailability_days(row, start, end))
        availability = derive_segment_availability(start.isoformat(), end.isoformat(), len(drafts), drafts,
            list(staff_ids), assignment_schedule_days=occupied_days, active_lock_days=[])
        return ("signing_staff_occupancy_conflict",) if any(
            row["reason_code"] != "buffer" for row in availability["conflicts"]
        ) else ()

    def existing_commitment(self, facts, *, for_update: bool) -> int | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM precontract_service_commitments WHERE case_no=%s AND matching_plan_id=%s"
                + (" FOR UPDATE" if for_update else ""),
                (facts.case_no, facts.matching_plan_id),
            )
            row = cursor.fetchone()
        return None if row is None else int(row["id"])

    def establish_prerequisites(
        self,
        command: RecordExternalStaffSigningReport,
        facts,
        resulting_status_version: int,
    ) -> StaffCompletionPrerequisites:
        if resulting_status_version != facts.status_version + 1:
            raise RuntimeError("external_signing_result_version_invalid")
        commitment_id = self._ensure_commitment(command)
        self._ensure_precontract_deposit(command, commitment_id)
        return StaffCompletionPrerequisites(commitment_id)

    def preview_service_dates(self, facts) -> tuple:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT case_no FROM caregiver_matching_plans WHERE id=%s",
                (facts.matching_plan_id,),
            )
            plan = cursor.fetchone()
            if plan is None or str(plan["case_no"]) != facts.case_no:
                raise RuntimeError("external_signing_plan_identity_conflict")
            cursor.execute(
                "SELECT day.service_date FROM precontract_service_commitment_days day "
                "JOIN precontract_service_commitments commitment ON commitment.id=day.commitment_id "
                "WHERE commitment.case_no=%s AND commitment.matching_plan_id=%s "
                "ORDER BY day.service_date,day.id",
                (facts.case_no, facts.matching_plan_id),
            )
            existing = tuple(row["service_date"] for row in cursor.fetchall())
            if existing:
                return existing
            cursor.execute(
                "SELECT id,staff_id,assigned_start_date,assigned_end_date "
                "FROM caregiver_matching_plan_segments WHERE plan_id=%s "
                "ORDER BY segment_order,id",
                (facts.matching_plan_id,),
            )
            segments = list(cursor.fetchall())
        if not segments:
            raise RuntimeError("external_signing_commitment_segments_missing")
        service_days = _commitment_service_days(
            self._connection, facts.case_no, segments
        )
        return tuple(sorted({service_date for _, service_date in service_days}))

    def _ensure_commitment(self, command: RecordExternalStaffSigningReport) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT case_no FROM caregiver_matching_plans WHERE id=%s FOR UPDATE",
                (command.matching_plan_id,),
            )
            plan = cursor.fetchone()
            if plan is None or str(plan["case_no"]) != command.case_no:
                raise RuntimeError("external_signing_plan_identity_conflict")
            cursor.execute(
                "SELECT id,case_no,matching_plan_id FROM precontract_service_commitments "
                "WHERE matching_plan_id=%s FOR UPDATE",
                (command.matching_plan_id,),
            )
            existing = cursor.fetchone()
            if existing is not None:
                if (
                    str(existing["case_no"]) != command.case_no
                    or int(existing["matching_plan_id"]) != command.matching_plan_id
                ):
                    raise RuntimeError("external_signing_commitment_identity_conflict")
                return int(existing["id"])
            cursor.execute(
                "SELECT id,staff_id,assigned_start_date,assigned_end_date "
                "FROM caregiver_matching_plan_segments WHERE plan_id=%s "
                "ORDER BY segment_order,id FOR UPDATE",
                (command.matching_plan_id,),
            )
            segments = list(cursor.fetchall())
        if not segments:
            raise RuntimeError("external_signing_commitment_segments_missing")
        service_days = _commitment_service_days(
            self._connection, command.case_no, segments
        )
        snapshot = hashlib.sha256(_canonical_json(segments).encode("utf-8")).hexdigest()
        commitment_key = (
            f"precontract-commitment:{command.case_no}:"
            f"{command.matching_plan_id}:{snapshot[:16]}"
        )
        with self._connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO precontract_service_commitments "
                "(case_no,matching_plan_id,commitment_key,plan_snapshot_sha256,created_by) "
                "VALUES (%s,%s,%s,%s,%s)",
                (
                    command.case_no,
                    command.matching_plan_id,
                    commitment_key,
                    snapshot,
                    command.actor.actor_id,
                ),
            )
            commitment_id = int(cursor.lastrowid)
            for segment, service_date in service_days:
                cursor.execute(
                    "INSERT INTO precontract_service_commitment_days "
                    "(commitment_id,matching_segment_id,staff_id,service_date) "
                    "VALUES (%s,%s,%s,%s)",
                    (
                        commitment_id,
                        segment["id"],
                        segment["staff_id"],
                        service_date,
                    ),
                )
        return commitment_id

    def _ensure_precontract_deposit(
        self,
        command: RecordExternalStaffSigningReport,
        commitment_id: int,
    ) -> None:
        with self._connection.cursor() as cursor:
            order = select_order(cursor, command.case_no, lock=True)
            finance = load_contract_client_finance_facts(cursor, order, lock=True)
            candidate = build_precontract_deposit_candidate(
                finance, f"precontract-commitment:{commitment_id}"
            )
            if not candidate.mutates:
                return
            persist_client_finance_terms_impact(
                cursor,
                ContractCompletionClientFinanceCommand(
                    precontract_deposit_terms_impact(candidate),
                    _derived_key(command.idempotency_key, "deposit"),
                    command.actor,
                    "external signing established the precontract commitment",
                    command.correlation_id,
                    "precontract-commitment",
                    commitment_id,
                ),
            )

def _derived_key(parent: IdempotencyKey, lane: str) -> IdempotencyKey:
    digest = hashlib.sha256(f"{parent.value}:{lane}".encode("utf-8")).hexdigest()
    return IdempotencyKey(f"external-signing-{lane}:{digest}")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )


__all__ = ["MySqlExternalStaffCompletionPort"]
