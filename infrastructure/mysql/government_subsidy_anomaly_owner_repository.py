"""Concrete MySQL owner repository for GOVSUB-003, GOVSUB-005 and GOVSUB-007."""

from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal

from domains.government_subsidy.anomaly_remediation import (
    GovernmentSubsidyClaimDriftOwnerFact,
    GovernmentSubsidyClaimDriftRepairPath,
    GovernmentSubsidyIntegrityOwnerFact,
    GovernmentSubsidyIntegrityRepairPath,
    GovernmentSubsidyRecoveryReconciliationCandidate,
    GovernmentSubsidyRecoveryRoot,
    GovernmentSubsidyRecoveryStatus,
)
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import IdempotencyKey
from shared_kernel.money import MoneyNTD
from subsystems.government_subsidy.anomaly_recovery_workflow import (
    ClaimDriftCorrectionApplyRequest,
    IntegrityRepairApplyRequest,
    RecoveryCreateApplyRequest,
    RecoveryReconcileApplyRequest,
    claim_correction_command_fingerprint,
    integrity_repair_command_fingerprint,
    recovery_reconcile_command_fingerprint,
)


class GovernmentSubsidyOwnerSourceUnavailable(RuntimeError):
    """A required owner source is absent, malformed, or ambiguous."""


class GovernmentSubsidyRecoveryAtomicCreationRequired(RuntimeError):
    """The lawful payout and excess root cannot yet share one owner UoW."""


class MySqlGovernmentSubsidyAnomalyRecoveryRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def read_integrity(self, batch_id: int) -> GovernmentSubsidyIntegrityOwnerFact:
        return self._integrity_fact(batch_id, for_update=False)

    def load_integrity(self, batch_id: int, *, for_update: bool) -> GovernmentSubsidyIntegrityOwnerFact:
        return self._integrity_fact(batch_id, for_update=for_update)

    def _integrity_fact(self, batch_id: int, *, for_update: bool) -> GovernmentSubsidyIntegrityOwnerFact:
        with self._connection.cursor() as cursor:
            if for_update:
                cursor.execute(_INTEGRITY_LOCK_SQL, (batch_id,))
                if cursor.fetchone() is None:
                    raise GovernmentSubsidyOwnerSourceUnavailable("government_subsidy_integrity_source_unavailable")
            cursor.execute(_INTEGRITY_READ_SQL, (batch_id,))
            row = _mapping_row(cursor.fetchone(), "government subsidy integrity")
        values = _integrity_values(row)
        immutable_valid = bool(values["immutable_roots_valid"])
        return GovernmentSubsidyIntegrityOwnerFact(
            batch_id,
            int(row["aggregate_version"]),
            fingerprint_payload(values).value,
            True,
            immutable_valid,
            bool(values["projection_consistent"]),
            GovernmentSubsidyIntegrityRepairPath.DERIVED_REBUILD
            if immutable_valid
            else GovernmentSubsidyIntegrityRepairPath.STRUCTURAL_AMBIGUITY,
        )

    def persist_integrity_repair(self, request: IntegrityRepairApplyRequest, fact: GovernmentSubsidyIntegrityOwnerFact) -> str:
        if request.repair_path is not GovernmentSubsidyIntegrityRepairPath.DERIVED_REBUILD:
            raise ValueError("government_subsidy_integrity_generic_repair_forbidden")
        with self._connection.cursor() as cursor:
            cursor.execute(_INTEGRITY_READ_SQL, (request.batch_id,))
            values = _mapping_row(cursor.fetchone(), "government subsidy integrity rebuild")
            derived = _integrity_values(values)
            if not bool(derived["immutable_roots_valid"]):
                raise ValueError("government_subsidy_integrity_repair_not_eligible")
            resulting_version = fact.owner_version + 1
            cursor.execute(
                _INTEGRITY_PROJECTION_UPDATE_SQL,
                (
                    derived["derived_requested_ntd"], derived["derived_approved_ntd"],
                    derived["derived_net_allocated_ntd"], derived["derived_outstanding_ntd"],
                    derived["batch_status"], resulting_version, request.batch_id, fact.owner_version,
                ),
            )
            _require_single_update(cursor, "government_subsidy_integrity_stale")
            cursor.execute(
                _INTEGRITY_EVENT_INSERT_SQL,
                (
                    request.batch_id, fact.owner_version, resulting_version,
                    fact.owner_snapshot_token, request.idempotency_key.value,
                    request.preview_fingerprint.value, request.actor.actor_id,
                    request.reason, request.correlation_id.value,
                ),
            )
            event_id = int(cursor.lastrowid)
            receipt = _receipt_reference("integrity-rebuild", request.idempotency_key)
            self._insert_receipt(
                cursor, request.idempotency_key, integrity_repair_command_fingerprint(request),
                request.preview_fingerprint, "integrity_rebuild", str(request.batch_id),
                {"receipt_reference": receipt, "batch_id": request.batch_id,
                 "event_id": event_id, "owner_version": resulting_version,
                 "repair_path": "derived_rebuild"},
            )
        return receipt

    def read_claim_drift(self, claim_item_id: int) -> GovernmentSubsidyClaimDriftOwnerFact:
        return self._claim_drift_fact(claim_item_id, for_update=False)

    def load_claim_drift(self, claim_item_id: int, *, for_update: bool) -> GovernmentSubsidyClaimDriftOwnerFact:
        return self._claim_drift_fact(claim_item_id, for_update=for_update)

    def _claim_drift_fact(self, claim_item_id: int, *, for_update: bool) -> GovernmentSubsidyClaimDriftOwnerFact:
        with self._connection.cursor() as cursor:
            if for_update:
                cursor.execute(_CLAIM_ITEM_LOCK_SQL, (claim_item_id,))
                if cursor.fetchone() is None:
                    raise GovernmentSubsidyOwnerSourceUnavailable("government_subsidy_claim_drift_source_unavailable")
            cursor.execute(_CLAIM_DRIFT_READ_SQL, (claim_item_id,))
            row = _mapping_row(cursor.fetchone(), "government subsidy claim drift")
        snapshot_identity = f"scheduling-assignment:{int(row['authoritative_assignment_id'])}"
        snapshot_version = _nonnegative_int(row["source_version"])
        schedule_payload = {
            "identity": snapshot_identity, "version": snapshot_version,
            "assignment_id": int(row["authoritative_assignment_id"]),
            "case_no": str(row["authoritative_case_no"]),
            "staff_id": int(row["authoritative_staff_id"]),
            "official_service_hours": _whole_ntd(row["official_service_hours"]),
            "assignment_effective": bool(row["assignment_effective"]),
        }
        snapshot_token = fingerprint_payload(schedule_payload).value
        drift = (
            int(row["frozen_assignment_id"]) != int(row["authoritative_assignment_id"])
            or str(row["frozen_case_no"]) != str(row["authoritative_case_no"])
            or int(row["frozen_staff_id"]) != int(row["authoritative_staff_id"])
            or _whole_ntd(row["frozen_claimed_hours"]) != _whole_ntd(row["official_service_hours"])
            or not bool(row["assignment_effective"])
        )
        lineage_exact = (
            row.get("lineage_id") is not None
            and str(row["lineage_snapshot_identity"]) == snapshot_identity
            and str(row["lineage_snapshot_token"]) == snapshot_token
            and int(row["lineage_snapshot_version"]) == snapshot_version
            and bool(str(row["successor_revision_identity"] or "").strip())
        )
        requested = _whole_ntd(row["requested_amount"])
        approved = _whole_ntd(row["approved_amount"])
        paid = _whole_ntd(row["paid_amount"])
        financial_valid = requested >= 0 and 0 <= approved <= requested and 0 <= paid <= approved
        submitted = row["submitted_at"] is not None
        path = (GovernmentSubsidyClaimDriftRepairPath.SUBMITTED_CORRECTION
                if submitted else GovernmentSubsidyClaimDriftRepairPath.DRAFT_REVISION)
        owner_version = max(snapshot_version, int(row.get("lineage_resulting_version") or 0))
        token = fingerprint_payload({
            "claim_item_id": claim_item_id, "batch_id": int(row["batch_id"]),
            "owner_version": owner_version, "drift_detected": drift,
            "submitted": submitted, "financial_invariants_valid": financial_valid,
            "scheduling_snapshot": schedule_payload, "lineage_exact": lineage_exact,
            "successor_revision_identity": row.get("successor_revision_identity"),
            "financial_consequence_reference": row.get("financial_consequence_reference"),
        }).value
        return GovernmentSubsidyClaimDriftOwnerFact(
            claim_item_id=claim_item_id, batch_id=int(row["batch_id"]),
            owner_version=owner_version, owner_snapshot_token=token,
            authoritative_complete=True, drift_detected=drift, submitted=submitted,
            frozen_claim_immutable=True, fresh_schedule_matches=not drift or lineage_exact,
            correction_lineage_complete=not drift or lineage_exact,
            financial_invariants_valid=financial_valid, repair_path=path,
            scheduling_snapshot_identity=snapshot_identity,
            scheduling_snapshot_token=snapshot_token,
            scheduling_snapshot_version=snapshot_version,
            revision_resolved=not drift or lineage_exact,
        )

    def persist_claim_drift_correction(self, request: ClaimDriftCorrectionApplyRequest, fact: GovernmentSubsidyClaimDriftOwnerFact) -> str:
        if request.repair_path is GovernmentSubsidyClaimDriftRepairPath.STRUCTURAL_AMBIGUITY:
            raise ValueError("government_subsidy_claim_drift_generic_repair_forbidden")
        resulting_version = fact.owner_version + 1
        with self._connection.cursor() as cursor:
            cursor.execute(
                _CLAIM_LINEAGE_INSERT_SQL,
                (
                    fact.claim_item_id, fact.batch_id, request.repair_path.value,
                    request.scheduling_snapshot_identity, request.scheduling_snapshot_version,
                    request.scheduling_snapshot_token, request.successor_revision_identity,
                    request.financial_consequence_reference, fact.owner_version,
                    resulting_version, request.idempotency_key.value,
                    request.preview_fingerprint.value, request.actor.actor_id,
                    request.reason, request.correlation_id.value,
                ),
            )
            lineage_id = int(cursor.lastrowid)
            receipt = _receipt_reference("claim-correction", request.idempotency_key)
            self._insert_receipt(
                cursor, request.idempotency_key, claim_correction_command_fingerprint(request),
                request.preview_fingerprint, "claim_correction", str(fact.claim_item_id),
                {"receipt_reference": receipt, "lineage_id": lineage_id,
                 "claim_item_id": fact.claim_item_id, "batch_id": fact.batch_id,
                 "owner_version": resulting_version,
                 "successor_revision_identity": request.successor_revision_identity},
            )
        return receipt

    def read_return_overage(self, payable_identity: str) -> GovernmentSubsidyRecoveryRoot | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_RECOVERY_BY_OBLIGATION_SQL, (payable_identity,))
            rows = cursor.fetchall()
        if not rows:
            return None
        if len(rows) != 1:
            raise GovernmentSubsidyOwnerSourceUnavailable("government_subsidy_recovery_ambiguous")
        return _recovery_root(_mapping_row(rows[0], "government subsidy recovery"))

    def create_recovery_root(self, request: RecoveryCreateApplyRequest) -> str:
        raise GovernmentSubsidyRecoveryAtomicCreationRequired(
            "government_subsidy_recovery_atomic_excess_uow_required"
        )

    def load_recovery(self, recovery_identity: str, *, for_update: bool) -> GovernmentSubsidyRecoveryRoot:
        with self._connection.cursor() as cursor:
            cursor.execute(_RECOVERY_BY_IDENTITY_SQL + (" FOR UPDATE" if for_update else ""), (recovery_identity,))
            row = cursor.fetchone()
        if row is None:
            raise ValueError("government_subsidy_recovery_not_found")
        return _recovery_root(_mapping_row(row, "government subsidy recovery"))

    def persist_recovery_reconciliation(self, request: RecoveryReconcileApplyRequest, candidate: GovernmentSubsidyRecoveryReconciliationCandidate) -> str:
        with self._connection.cursor() as cursor:
            _validate_incoming_fact(cursor, request)
            cursor.execute(
                _RECOVERY_UPDATE_SQL,
                (candidate.remaining_after_ntd.amount, candidate.resulting_status.value,
                 request.expected_version.value + 1, request.recovery_identity,
                 request.expected_version.value),
            )
            _require_single_update(cursor, "government_subsidy_recovery_stale")
            before = request.incoming.amount_ntd.amount + candidate.remaining_after_ntd.amount
            cursor.execute(
                _RECOVERY_EVENT_INSERT_SQL,
                (request.recovery_identity, request.incoming.bank_fact_identity,
                 request.incoming.amount_ntd.amount, before,
                 candidate.remaining_after_ntd.amount, request.expected_version.value,
                 request.expected_version.value + 1, candidate.resulting_status.value,
                 request.idempotency_key.value, request.preview_fingerprint.value,
                 request.actor.actor_id, request.reason, request.correlation_id.value),
            )
            event_id = int(cursor.lastrowid)
            receipt = _receipt_reference("recovery-reconcile", request.idempotency_key)
            self._insert_receipt(
                cursor, request.idempotency_key,
                recovery_reconcile_command_fingerprint(request),
                request.preview_fingerprint, "recovery_reconcile",
                request.recovery_identity,
                {"receipt_reference": receipt, "recovery_identity": request.recovery_identity,
                 "event_id": event_id,
                 "aggregate_version": request.expected_version.value + 1,
                 "remaining_excess_ntd": candidate.remaining_after_ntd.amount,
                 "status": candidate.resulting_status.value},
            )
        return receipt

    def find_receipt(self, idempotency_key: IdempotencyKey, command_fingerprint: PreviewFingerprint) -> str | None:
        with self._connection.cursor() as cursor:
            cursor.execute(_RECEIPT_SELECT_SQL, (idempotency_key.value,))
            row = cursor.fetchone()
        if row is None:
            return None
        row = _mapping_row(row, "government subsidy anomaly receipt")
        if str(row["command_fingerprint"]) != command_fingerprint.value:
            raise ValueError("government_subsidy_anomaly_idempotency_conflict")
        receipt = _json_object(row["result_snapshot"]).get("receipt_reference")
        if not isinstance(receipt, str) or not receipt:
            raise GovernmentSubsidyOwnerSourceUnavailable("government_subsidy_anomaly_receipt_incomplete")
        return receipt

    @staticmethod
    def _insert_receipt(cursor, key, command, preview, operation, subject, result) -> None:
        cursor.execute(
            _RECEIPT_INSERT_SQL,
            (key.value, command.value, preview.value, operation, subject, _canonical_json(result)),
        )


def _integrity_values(row: Mapping[str, object]) -> dict[str, object]:
    requested = _whole_ntd(row["derived_requested_ntd"])
    approved = _whole_ntd(row["derived_approved_ntd"])
    allocated = _whole_ntd(row["derived_net_allocated_ntd"])
    outstanding = approved - allocated
    valid = (int(row["item_count"]) > 0 and requested >= 0 and
             0 <= approved <= requested and 0 <= allocated <= approved and
             outstanding >= 0 and int(row["invalid_allocation_count"]) == 0)
    consistent = valid and (
        _whole_ntd(row["account_requested_ntd"]) == requested
        and _whole_ntd(row["account_approved_ntd"]) == approved
        and _whole_ntd(row["account_net_allocated_ntd"]) == allocated
        and _whole_ntd(row["account_outstanding_ntd"]) == outstanding
        and str(row["account_status"]) == str(row["batch_status"])
    )
    return {
        "batch_id": int(row["batch_id"]), "aggregate_version": int(row["aggregate_version"]),
        "derived_requested_ntd": requested, "derived_approved_ntd": approved,
        "derived_net_allocated_ntd": allocated, "derived_outstanding_ntd": outstanding,
        "batch_status": str(row["batch_status"]), "immutable_roots_valid": valid,
        "projection_consistent": consistent,
    }


def _recovery_root(row: Mapping[str, object]) -> GovernmentSubsidyRecoveryRoot:
    return GovernmentSubsidyRecoveryRoot(
        str(row["recovery_identity"]), str(row["source_outgoing_bank_fact_identity"]),
        str(row["original_return_obligation_identity"]), MoneyNTD(int(row["lawful_amount_ntd"])),
        MoneyNTD(int(row["actual_amount_ntd"])), str(row["government_payer_identity"]),
        int(row["aggregate_version"]), GovernmentSubsidyRecoveryStatus(str(row["status"])),
        str(row["actor"]), str(row["reason"]), str(row["evidence_reference"]),
        IdempotencyKey(str(row["idempotency_key"])), str(row["receipt_reference"]),
        MoneyNTD(int(row["remaining_excess_ntd"])),
    )


def _validate_incoming_fact(cursor, request: RecoveryReconcileApplyRequest) -> None:
    cursor.execute(_INCOMING_FACT_SQL, (request.incoming.bank_fact_identity,))
    row = _mapping_row(cursor.fetchone(), "government subsidy incoming bank fact")
    if (str(row["direction"]) != "incoming"
            or _whole_ntd(row["amount_ntd"]) != request.incoming.amount_ntd.amount
            or str(row["classification_type"]) != "government_subsidy"):
        raise ValueError("government_subsidy_recovery_bank_fact_invalid")


def _mapping_row(row, label: str) -> Mapping[str, object]:
    if row is None:
        raise GovernmentSubsidyOwnerSourceUnavailable(f"{label.replace(' ', '_')}_unavailable")
    if not isinstance(row, Mapping):
        raise TypeError(f"{label} row is invalid")
    return row


def _whole_ntd(value: object) -> int:
    if isinstance(value, bool):
        raise TypeError("government subsidy amount is invalid")
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    raise ValueError("government subsidy amount must be whole NTD")


def _nonnegative_int(value: object) -> int:
    result = _whole_ntd(value)
    if result < 0:
        raise ValueError("government subsidy version must be nonnegative")
    return result


def _require_single_update(cursor, error_code: str) -> None:
    if int(cursor.rowcount) != 1:
        raise ValueError(error_code)


def _json_object(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, (str, bytes, bytearray)):
        parsed = json.loads(value)
        if isinstance(parsed, Mapping):
            return parsed
    raise GovernmentSubsidyOwnerSourceUnavailable("government_subsidy_anomaly_receipt_invalid")


def _canonical_json(value: Mapping[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _receipt_reference(prefix: str, key: IdempotencyKey) -> str:
    return f"government-subsidy-{prefix}:{key.value}"


_INTEGRITY_LOCK_SQL = "SELECT batch_id FROM government_subsidy_batch_accounts WHERE batch_id=%s FOR UPDATE"
_INTEGRITY_READ_SQL = """
SELECT account.batch_id,account.aggregate_version,
 account.requested_total_ntd AS account_requested_ntd,
 account.approved_total_ntd AS account_approved_ntd,
 account.net_allocated_ntd AS account_net_allocated_ntd,
 account.outstanding_ntd AS account_outstanding_ntd,
 account.status AS account_status,
 CASE WHEN batch.submitted_at IS NULL THEN 'draft'
      WHEN batch.approved_at IS NULL THEN 'submitted'
      WHEN COALESCE(allocation.net_allocated_ntd,0)=0 THEN 'approved'
      WHEN COALESCE(allocation.net_allocated_ntd,0)=SUM(item.approved_amount) THEN 'paid'
      ELSE 'partially_paid' END AS batch_status,
 COUNT(item.id) AS item_count,
 COALESCE(SUM(item.requested_amount),0) AS derived_requested_ntd,
 COALESCE(SUM(item.approved_amount),0) AS derived_approved_ntd,
 COALESCE(allocation.net_allocated_ntd,0) AS derived_net_allocated_ntd,
 COALESCE(allocation.invalid_allocation_count,0) AS invalid_allocation_count
FROM government_subsidy_batch_accounts account
JOIN subsidy_claim_batches batch ON batch.id=account.batch_id
JOIN subsidy_claim_batch_items item ON item.batch_id=batch.id
LEFT JOIN (
 SELECT item_total.batch_id AS claim_batch_id,
  SUM(item_total.net_allocated_ntd) AS net_allocated_ntd,
  SUM(CASE WHEN item_total.net_allocated_ntd<0
                OR item_total.net_allocated_ntd>item_total.approved_amount
           THEN 1 ELSE 0 END) AS invalid_allocation_count
 FROM (
  SELECT item_root.batch_id,item_root.id,item_root.approved_amount,
   COALESCE(SUM(CASE WHEN allocation_root.allocation_type='receipt'
                     THEN allocation_root.allocated_amount
                     WHEN allocation_root.allocation_type='reversal'
                     THEN -allocation_root.allocated_amount ELSE 0 END),0)
     AS net_allocated_ntd
  FROM subsidy_claim_batch_items item_root
  LEFT JOIN government_subsidy_allocations allocation_root
    ON allocation_root.claim_batch_id=item_root.batch_id
   AND allocation_root.claim_item_id=item_root.id
  GROUP BY item_root.batch_id,item_root.id,item_root.approved_amount
 ) item_total
 GROUP BY item_total.batch_id
) allocation ON allocation.claim_batch_id=batch.id
WHERE account.batch_id=%s
GROUP BY account.batch_id,account.aggregate_version,account.requested_total_ntd,
 account.approved_total_ntd,account.net_allocated_ntd,account.outstanding_ntd,
 account.status,batch.submitted_at,batch.approved_at,allocation.net_allocated_ntd,
 allocation.invalid_allocation_count
"""
_INTEGRITY_PROJECTION_UPDATE_SQL = (
    "UPDATE government_subsidy_batch_accounts SET requested_total_ntd=%s,approved_total_ntd=%s,"
    "net_allocated_ntd=%s,outstanding_ntd=%s,status=%s,aggregate_version=%s "
    "WHERE batch_id=%s AND aggregate_version=%s"
)
_INTEGRITY_EVENT_INSERT_SQL = (
    "INSERT INTO government_subsidy_integrity_rebuild_events "
    "(batch_id,expected_owner_version,resulting_owner_version,source_snapshot_token,"
    "idempotency_key,preview_fingerprint,actor,reason,correlation_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_CLAIM_ITEM_LOCK_SQL = "SELECT id FROM subsidy_claim_batch_items WHERE id=%s FOR UPDATE"
_CLAIM_DRIFT_READ_SQL = """
SELECT item.id AS claim_item_id,item.batch_id,item.assignment_id AS frozen_assignment_id,
 item.case_no AS frozen_case_no,item.staff_id AS frozen_staff_id,
 item.claimed_hours AS frozen_claimed_hours,item.requested_amount,item.approved_amount,
 item.paid_amount,batch.submitted_at,assignment.id AS authoritative_assignment_id,
 assignment.case_no AS authoritative_case_no,assignment.staff_id AS authoritative_staff_id,
 CASE WHEN assignment.generation_id=aggregate.effective_generation_id
           AND generation.status='effective' AND generation.effective_marker=1
           AND assignment.status NOT IN ('cancelled','replaced') THEN 1 ELSE 0 END AS assignment_effective,
 CASE WHEN assignment.generation_id=aggregate.effective_generation_id
           AND generation.status='effective' AND generation.effective_marker=1
           AND assignment.status NOT IN ('cancelled','replaced')
      THEN (SELECT COUNT(DISTINCT schedule.work_date) FROM staff_schedule schedule
            WHERE schedule.assignment_id=assignment.id AND schedule.generation_id=assignment.generation_id
              AND schedule.effective_marker=1 AND schedule.is_work_day=1
              AND schedule.work_date>=MAKEDATE(batch.application_year,1)+INTERVAL ((batch.quarter-1)*3) MONTH
              AND schedule.work_date<MAKEDATE(batch.application_year,1)+INTERVAL (batch.quarter*3) MONTH)
           * orders.service_hours_per_day ELSE 0 END AS official_service_hours,
 CAST(UNIX_TIMESTAMP(item.updated_at) AS UNSIGNED)*4294967296+COALESCE(aggregate.aggregate_version,0) AS source_version,
 lineage.id AS lineage_id,lineage.scheduling_snapshot_identity AS lineage_snapshot_identity,
 lineage.scheduling_snapshot_version AS lineage_snapshot_version,
 lineage.scheduling_snapshot_token AS lineage_snapshot_token,lineage.successor_revision_identity,
 lineage.financial_consequence_reference,lineage.resulting_owner_version AS lineage_resulting_version
FROM subsidy_claim_batch_items item
JOIN subsidy_claim_batches batch ON batch.id=item.batch_id
JOIN case_staff_assignments assignment ON assignment.id=item.assignment_id
LEFT JOIN scheduling_aggregates aggregate ON aggregate.case_no=assignment.case_no
LEFT JOIN scheduling_generations generation ON generation.id=aggregate.effective_generation_id
JOIN orders orders ON orders.case_no=assignment.case_no
LEFT JOIN government_subsidy_claim_correction_lineages lineage ON lineage.original_claim_item_id=item.id
WHERE item.id=%s
"""
_CLAIM_LINEAGE_INSERT_SQL = (
    "INSERT INTO government_subsidy_claim_correction_lineages "
    "(original_claim_item_id,original_batch_id,correction_path,scheduling_snapshot_identity,"
    "scheduling_snapshot_version,scheduling_snapshot_token,successor_revision_identity,"
    "financial_consequence_reference,expected_owner_version,resulting_owner_version,"
    "idempotency_key,preview_fingerprint,actor,reason,correlation_id) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_RECOVERY_COLUMNS = (
    "recovery_identity,source_outgoing_bank_fact_identity,original_return_obligation_identity,"
    "lawful_amount_ntd,actual_amount_ntd,excess_amount_ntd,remaining_excess_ntd,"
    "government_payer_identity,aggregate_version,status,actor,reason,evidence_reference,"
    "idempotency_key,receipt_reference"
)
_RECOVERY_BY_OBLIGATION_SQL = f"SELECT {_RECOVERY_COLUMNS} FROM government_subsidy_recoveries WHERE original_return_obligation_identity=%s ORDER BY recovery_identity"
_RECOVERY_BY_IDENTITY_SQL = f"SELECT {_RECOVERY_COLUMNS} FROM government_subsidy_recoveries WHERE recovery_identity=%s"
_RECOVERY_UPDATE_SQL = "UPDATE government_subsidy_recoveries SET remaining_excess_ntd=%s,status=%s,aggregate_version=%s WHERE recovery_identity=%s AND aggregate_version=%s"
_RECOVERY_EVENT_INSERT_SQL = (
    "INSERT INTO government_subsidy_recovery_events (recovery_identity,incoming_bank_fact_identity,"
    "amount_ntd,before_remaining_ntd,after_remaining_ntd,expected_version,resulting_version,"
    "resulting_status,idempotency_key,preview_fingerprint,actor,reason,correlation_id) "
    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
)
_INCOMING_FACT_SQL = """
SELECT bank.direction,bank.credit AS amount_ntd,classification.classification_type
FROM finance_import_rows bank JOIN finance_import_classification_events classification
 ON classification.id=(SELECT MAX(latest.id) FROM finance_import_classification_events latest
   WHERE latest.finance_import_row_id=bank.id)
WHERE bank.dedup_fingerprint=%s FOR UPDATE
"""
_RECEIPT_SELECT_SQL = "SELECT command_fingerprint,result_snapshot FROM government_subsidy_anomaly_apply_receipts WHERE idempotency_key=%s"
_RECEIPT_INSERT_SQL = (
    "INSERT INTO government_subsidy_anomaly_apply_receipts "
    "(idempotency_key,command_fingerprint,preview_fingerprint,operation_type,subject_identity,result_snapshot) "
    "VALUES (%s,%s,%s,%s,%s,%s)"
)


__all__ = [
    "GovernmentSubsidyOwnerSourceUnavailable",
    "GovernmentSubsidyRecoveryAtomicCreationRequired",
    "MySqlGovernmentSubsidyAnomalyRecoveryRepository",
]
