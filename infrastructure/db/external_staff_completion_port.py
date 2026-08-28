"""
File: external_staff_completion_port.py
Description: 在外部簽約回報的 borrowed 交易內建立 commitment、deposit 與無 URL 客戶提醒。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from domains.client_finance.obligation_planning import (
    build_precontract_deposit_candidate,
    precontract_deposit_terms_impact,
)
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryRequest,
    LineMessageKind,
)
from infrastructure.mysql.client_finance_terms_writer import (
    persist_client_finance_terms_impact,
)
from infrastructure.mysql.line_delivery_task_repository import (
    MySqlLineDeliveryTaskRepository,
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
from subsystems.contract_signing.line_delivery import (
    ContractLineBinding,
    require_contract_line_recipient,
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
        reminder_id = self._enqueue_client_reminder(command)
        self._ensure_precontract_deposit(command, commitment_id)
        return StaffCompletionPrerequisites(commitment_id, reminder_id)

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
                    "all external staff signing reports were recorded",
                    command.correlation_id,
                    "precontract-commitment",
                    commitment_id,
                ),
            )

    def _enqueue_client_reminder(
        self, command: RecordExternalStaffSigningReport
    ) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT client_id FROM orders WHERE case_no=%s FOR UPDATE",
                (command.case_no,),
            )
            order = cursor.fetchone()
            if order is None:
                raise RuntimeError("external_signing_order_missing")
            client_reference = str(order["client_id"])
            cursor.execute(
                "SELECT line_user_id,binding_status,subject_type,subject_reference "
                "FROM line_identity_bindings WHERE subject_type='customer' "
                "AND subject_reference=%s FOR UPDATE",
                (client_reference,),
            )
            binding_row = cursor.fetchone()
        binding = (
            ContractLineBinding(None, None, None, None)
            if binding_row is None
            else ContractLineBinding(
                str(binding_row["line_user_id"]),
                str(binding_row["binding_status"]),
                str(binding_row["subject_type"]),
                str(binding_row["subject_reference"]),
            )
        )
        recipient = require_contract_line_recipient(
            binding,
            subject_type="customer",
            subject_reference=client_reference,
        )
        request = LineDeliveryRequest(
            recipient=recipient,
            message_kind=LineMessageKind.TEXT,
            payload_json=canonical_line_payload_json(
                {
                    "text": (
                        f"案件 {command.case_no} 的服務人員外部簽署已全數回報完成；"
                        "請依既定外部簽約平台流程完成客戶簽署。"
                    )
                }
            ),
            scheduled_at=command.occurred_at,
            idempotency_key=_derived_key(command.idempotency_key, "client-reminder"),
            correlation_id=command.correlation_id,
            source_aggregate_type="contract_external_signing_session",
            source_aggregate_identity=command.session_id,
        )
        result = MySqlLineDeliveryTaskRepository(self._connection).enqueue(request)
        return int(result.task_id.value)


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
