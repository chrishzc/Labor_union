"""
File: external_staff_completion_port.py
Description: 在外部簽約回報的 borrowed 交易內建立 commitment 與 deposit。
"""

from __future__ import annotations

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
