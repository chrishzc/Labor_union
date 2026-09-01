"""MySQL adapter for the bounded Full Contract owner projection query."""

from __future__ import annotations

import json
from datetime import date, datetime
import re
from typing import Any

from domains.case_import.order_information import project_order_information
from domains.client_finance.subsidy_coverage import derive_subsidy_coverage
from infrastructure.mysql.contract_context_repository import MySqlContractContextRepository
from infrastructure.mysql.order_terms_read_model import (
    load_contract_client_finance_facts,
    load_preview_facts,
    select_order,
)
from domains.client_finance.obligation_planning import build_client_finance_terms_candidate
from subsystems.contract_signing.full_contract_preview import (
    ContractPreviewScope,
    FullContractOwnerProjection,
    projection_fingerprint,
)

_CANONICAL_SERVICE_MODES = frozenset({"週休1日", "週休2日", "連續服務"})


class MySqlFullContractProjectionRepository:
    """Read-only adapter; it never owns a transaction or business formula."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._context = MySqlContractContextRepository(connection)

    def load_client_projection(self, case_no: str) -> FullContractOwnerProjection | None:
        case = self._context.load_case_facts(case_no)
        if case is None:
            return None
        assignments = self._context.load_assignments(case_no)
        facts = _common_facts(case)
        facts["service_type"] = _canonical_service_mode(facts.get("service_type"))
        # A client contract may project the staff selected by Scheduling when
        # there is one unambiguous current assignment (planned or active).
        # Cancelled/replaced assignments are not current; ambiguity remains a
        # closed blocker.
        current = tuple(
            row for row in assignments
            if row.get("status") not in {"cancelled", "replaced"}
        )
        if len(current) == 1:
            facts["staff_name"] = current[0].get("staff_name")
            facts["assignment_hourly_rate"] = current[0].get("hourly_rate")
            # Scheduling owns the assignment's planned hours.  This is a
            # read-through of the exact assignment value, never an
            # order-days × hours formula in Contract Signing.
            facts["total_hours"] = current[0].get("planned_hours")
            active_assignment_id = int(current[0]["assignment_id"])
        else:
            active_assignment_id = None
        owners = {
            "orders": projection_fingerprint(_owner_values(facts, "order")),
            "client": projection_fingerprint(_owner_values(facts, "client")),
            "scheduling": projection_fingerprint(
                {"assignments": tuple(_assignment_values(row) for row in assignments)}
            ),
            "case_import": projection_fingerprint(
                {"multi_birth_count": facts.get("multi_birth_count")}
            ),
        }
        _extend_owner_facts(
            self._connection,
            case_no,
            facts,
            owners,
            active_assignment_id,
            current[0].get("staff_id") if active_assignment_id is not None else None,
        )
        return FullContractOwnerProjection(
            case_no=case_no,
            scope=ContractPreviewScope.CLIENT,
            assignment_id=None,
            facts=facts,
            owner_fingerprints=owners,
        )

    def load_staff_projection(
        self, case_no: str, assignment_id: int
    ) -> FullContractOwnerProjection | None:
        case = self._context.load_case_facts(case_no)
        if case is None:
            return None
        assignment = next(
            (
                row
                for row in self._context.load_assignments(case_no)
                if row.get("assignment_id") == assignment_id
            ),
            None,
        )
        if assignment is None:
            return None
        facts = _common_facts(case)
        facts.update(
            {
                "staff_name": assignment.get("staff_name"),
                "staff_phone": assignment.get("staff_phone"),
                "start_date": assignment.get("assigned_start_date"),
                "end_date": assignment.get("assigned_end_date"),
                "assignment_start_date": assignment.get("assigned_start_date"),
                "assignment_end_date": assignment.get("assigned_end_date"),
                "assignment_service_days": _service_day_count(assignment),
                "service_unit_price": assignment.get("hourly_rate"),
                "total_hours": assignment.get("planned_hours"),
            }
        )
        # Client.service_type is the typed HCM root used by the existing
        # Scheduling/Staff contract workflow to select rest weekdays.  Only
        # canonical service-mode values may populate the staff template's
        # leave-method cell; values such as legacy "care" remain missing and
        # therefore fail closed.
        facts["service_type"] = _canonical_service_mode(facts.get("service_type"))
        owners = {
            "orders": projection_fingerprint(_owner_values(facts, "order")),
            "client": projection_fingerprint(_owner_values(facts, "client")),
            "scheduling": projection_fingerprint(_assignment_values(assignment)),
            "staff": projection_fingerprint(_owner_values(facts, "staff")),
            "case_import": projection_fingerprint(
                {"multi_birth_count": facts.get("multi_birth_count")}
            ),
        }
        _extend_owner_facts(
            self._connection,
            case_no,
            facts,
            owners,
            assignment_id,
            assignment.get("staff_id"),
        )
        return FullContractOwnerProjection(
            case_no=case_no,
            scope=ContractPreviewScope.STAFF,
            assignment_id=assignment_id,
            facts=facts,
            owner_fingerprints=owners,
        )


def _common_facts(case: dict[str, object]) -> dict[str, object]:
    """Map typed scalar context fields; raw survey is normalized and excluded."""
    # Case Import owns normalization of the legacy payload.  Contract Signing
    # receives only this named projection, never the raw survey mapping.
    case_import = project_order_information(case.get("survey_details"))
    return {
        "case_no": case.get("case_no"),
        "client_name": case.get("client_name"),
        "phone": case.get("client_phone"),
        "address": case.get("client_address"),
        "city": case.get("client_city"),
        "service_time": case.get("service_time"),
        "service_type": case.get("service_type"),
        "baby_info": case.get("baby_info"),
        "delivery_type": case.get("delivery_type"),
        "residence_type": case.get("residence_type"),
        "notes": case.get("client_notes"),
        "start_date": case.get("start_date"),
        "end_date": case.get("end_date"),
        "service_days": case.get("service_days"),
        "service_hours_per_day": case.get("service_hours_per_day"),
        "floor_fee": case.get("floor_fee"),
        "identity_status": case.get("client_identity_status"),
        # ``due_month`` is legacy-named and may contain only a month.  It is
        # accepted as the contract due-date fact only when the stored value is
        # an explicit YYYY/MM/DD date; month-only values remain absent.
        "due_date": _due_date_from_due_month(case.get("due_month")),
        "multi_birth_count": case_import.values.get("multi_birth_count"),
        # Orders owns the typed custom rest-date projection.  It is already
        # normalized JSON, never the legacy survey payload.
        "special_holidays": _special_holidays_text(case.get("custom_rest_dates")),
    }


def _service_day_count(row: dict[str, object]) -> int | None:
    start = row.get("assigned_start_date")
    end = row.get("assigned_end_date")
    if start is None or end is None:
        return None
    try:
        return (end - start).days + 1
    except (AttributeError, TypeError):
        return None


def _owner_values(facts: dict[str, object], owner: str) -> dict[str, object]:
    prefixes = {
        "order": {"case_no", "start_date", "end_date", "service_days", "service_hours_per_day", "floor_fee", "special_holidays"},
        "client": {
            "client_name", "phone", "address", "city", "service_time",
            "service_type", "baby_info", "delivery_type", "residence_type", "notes", "email", "identity_status",
        },
        "staff": {"staff_name", "staff_phone", "city", "address"},
    }[owner]
    return {key: facts.get(key) for key in sorted(prefixes)}


def _assignment_values(row: dict[str, object]) -> dict[str, object]:
    return {
        key: row.get(key)
        for key in (
            "assignment_id",
            "case_no",
            "staff_id",
            "assigned_start_date",
            "assigned_end_date",
            "planned_hours",
            "hourly_rate",
            "status",
        )
    }


def _extend_owner_facts(
    connection: Any,
    case_no: str,
    facts: dict[str, object],
    owners: dict[str, str],
    assignment_id: int | None,
    staff_id: int | None,
) -> None:
    """Borrow existing typed Finance/Payroll/Scheduling readers when bootstrapped."""
    # Client/Case Import is an independent owner.  Its normalized email read
    # must remain available even when an unrelated optional Finance/Payroll
    # bootstrap is absent.
    client_email: str | None = None
    subsidy_claim: dict[str, object] | None = None
    try:
        with connection.cursor() as cursor:
            client_email = _load_client_email(cursor, case_no)
            subsidy_claim = _load_approved_subsidy_claim(cursor, case_no, assignment_id)
    except Exception:
        client_email = None
    try:
        with connection.cursor() as cursor:
            typed = load_preview_facts(cursor, case_no)
            order_row = select_order(cursor, case_no, lock=False)
            finance = load_contract_client_finance_facts(
                cursor, order_row, lock=False
            )
            commitment = _load_commitment(cursor, case_no)
            rate = _load_assignment_payroll_rate(cursor, assignment_id)
            bank = _load_primary_staff_bank_account(cursor, staff_id)
            refund_destination = _load_client_refund_destination(cursor, case_no)
        payment = finance.payment_terms
        facts.update(
            {
                "client_finance_account_version": finance.account_version,
                "deposit_service_days": payment.deposit_service_days,
                "client_hourly_rate": payment.client_hourly_rate.amount,
                "deposit_due_date": payment.deposit_due_date,
                "first_payment_due_date": payment.first_payment_due_date,
                "second_payment_due_date": payment.second_payment_due_date,
            }
        )
        finance_candidate = build_client_finance_terms_candidate(
            finance, f"contract-preview:{case_no}"
        )
        for stage in finance_candidate.stage_plans:
            facts[_stage_fact_key(stage.payment_stage.value, "amount")] = stage.amount.amount
            facts[_stage_fact_key(stage.payment_stage.value, "date")] = stage.due_date
        # Client Finance already owns the typed stage plan.  Expose its
        # aggregate as a named projection so the XLSX renderer does not
        # recalculate or combine money fields.
        facts["total_employer_self_pay_payable"] = sum(
            stage.amount.amount for stage in finance_candidate.stage_plans
        )
        facts["first_payment_amount"] = facts.get("first_amount")
        facts["second_payment_amount"] = facts.get("second_amount")
        facts["client_finance_self_pay_days"] = sum(
            len(stage.service_dates)
            for stage in finance_candidate.stage_plans
            if stage.payment_stage.value != "deposit"
        )
        owners["client_finance"] = projection_fingerprint(
            {
                "account_version": finance.account_version,
                "payment_terms": {
                    "deposit_service_days": payment.deposit_service_days,
                    "client_hourly_rate": payment.client_hourly_rate.amount,
                    "deposit_due_date": payment.deposit_due_date,
                    "first_payment_due_date": payment.first_payment_due_date,
                    "second_payment_due_date": payment.second_payment_due_date,
                },
                "candidate": finance_candidate.fingerprint.value,
            }
        )
        owners["payroll"] = projection_fingerprint(
            {
                "payroll_version": typed.payroll.payroll_version,
                "staff_payment_due_date": typed.payroll.staff_payment_due_date,
                "source_terms": tuple(
                    {
                        "assignment_id": item.source_assignment_id,
                        "staff_id": item.staff_id,
                        "policy_version": item.policy_version,
                        "policy_kind": item.policy_kind.value,
                    }
                    for item in typed.payroll.source_terms
                ),
            }
        )
        service_obligations = tuple(
            item
            for item in typed.payroll.existing_obligations
            if item.obligation_kind.value == "service_pay"
            and item.direction.value == "payable_to_staff"
        )
        if len(service_obligations) == 1:
            obligation = service_obligations[0]
            facts["staff_payable_total"] = obligation.contracted_amount.amount
            facts["staff_payable_due_date"] = obligation.due_date
            owners["staff_payables"] = projection_fingerprint(
                {
                    "obligation_identity": obligation.obligation_identity,
                    "assignment_id": obligation.source_assignment_id,
                    "staff_id": obligation.staff_id,
                    "contracted_amount": obligation.contracted_amount.amount,
                    "due_date": obligation.due_date,
                }
            )
        if commitment is not None:
            facts.update(
                {
                    "committed_service_start_date": commitment["start_date"],
                    "committed_service_end_date": commitment["end_date"],
                }
            )
            owners["scheduling"] = projection_fingerprint(
                {
                    "assignment": owners["scheduling"],
                    "commitment_id": commitment["id"],
                    "matching_plan_id": commitment["matching_plan_id"],
                    "plan_snapshot_sha256": commitment["plan_snapshot_sha256"],
                    "start_date": commitment["start_date"],
                    "end_date": commitment["end_date"],
                    "service_day_count": commitment["service_day_count"],
                }
            )
        if assignment_id is not None:
            source = next(
                (item for item in typed.payroll.source_terms if item.source_assignment_id == assignment_id),
                None,
            )
            if source is not None:
                facts["payroll_payment_date"] = typed.payroll.staff_payment_due_date
            if rate is not None:
                facts["service_unit_price"] = rate["hourly_rate_ntd"]
                facts["assignment_hourly_rate"] = rate["hourly_rate_ntd"]
                owners["payroll"] = projection_fingerprint(
                    {
                        "payroll": owners["payroll"],
                        "assignment_id": assignment_id,
                        "hourly_rate_ntd": rate["hourly_rate_ntd"],
                        "policy_version": rate["policy_version"],
                        "policy_kind": rate["policy_kind"],
                    }
                )
        if bank is not None:
            facts["staff_bank_account"] = bank["account_no"]
            owners["staff_payables"] = projection_fingerprint(
                {
                    "staff_id": staff_id,
                    "account_id": bank["id"],
                    "account_no": bank["account_no"],
                    "is_primary": bank["is_primary"],
                }
            )
        if refund_destination is not None:
            facts["bank_code"] = refund_destination["bank_code"]
            facts["bank_account"] = refund_destination["bank_account"]
            owners["client_finance"] = projection_fingerprint(
                {
                    "client_finance": owners["client_finance"],
                    "refund_obligation_identity": refund_destination["refund_obligation_identity"],
                    "bank_code": refund_destination["bank_code"],
                    "bank_account": refund_destination["bank_account"],
                }
            )
        if client_email is not None:
            facts["email"] = client_email
            owners["client"] = projection_fingerprint(
                {"client": owners.get("client"), "email": client_email}
            )
        _project_subsidy_coverage(facts, owners)
        if subsidy_claim is not None:
            # B40 is the Government Subsidy service claim, not a staff wage.
            # Only an exact approved claim item may populate it.
            facts["subsidy_hours"] = subsidy_claim["claimed_hours"]
            facts["subsidy_salary"] = subsidy_claim["approved_amount"]
            owners["government_subsidy"] = projection_fingerprint(subsidy_claim)
    except Exception:
        # Missing owner bootstrap is represented by missing typed facts and is
        # surfaced by the Preview mapping blockers; no fallback formula exists.
        owners.setdefault(
            "client_finance",
            projection_fingerprint({"status": "unavailable", "case_no": case_no}),
        )
        owners.setdefault(
            "payroll",
            projection_fingerprint({"status": "unavailable", "case_no": case_no}),
        )


def _load_commitment(cursor: Any, case_no: str) -> dict[str, object] | None:
    cursor.execute(
        "SELECT commitment.id,commitment.matching_plan_id,commitment.plan_snapshot_sha256,"
        "MIN(days.service_date) AS start_date,MAX(days.service_date) AS end_date,"
        "COUNT(*) AS service_day_count "
        "FROM precontract_service_commitments commitment "
        "JOIN precontract_service_commitment_days days "
        "ON days.commitment_id=commitment.id "
        "WHERE commitment.case_no=%s GROUP BY commitment.id,commitment.matching_plan_id,"
        "commitment.plan_snapshot_sha256 ORDER BY commitment.id DESC LIMIT 1",
        (case_no,),
    )
    return cursor.fetchone()


def _load_assignment_payroll_rate(cursor: Any, assignment_id: int | None) -> dict[str, object] | None:
    if assignment_id is None:
        return None
    cursor.execute(
        "SELECT hourly_rate_ntd,policy_version,policy_kind "
        "FROM assignment_payroll_rate_snapshots WHERE assignment_id=%s",
        (assignment_id,),
    )
    return cursor.fetchone()


def _load_primary_staff_bank_account(cursor: Any, staff_id: int | None) -> dict[str, object] | None:
    if staff_id is None:
        return None
    cursor.execute(
        "SELECT id,account_no,is_primary FROM staff_bank_accounts "
        "WHERE staff_id=%s AND is_primary=1 ORDER BY id",
        (staff_id,),
    )
    rows = tuple(cursor.fetchall() or ())
    return rows[0] if len(rows) == 1 else None


def _load_client_refund_destination(cursor: Any, case_no: str) -> dict[str, object] | None:
    """Read the immutable Client Finance refund recipient, if one is unique."""
    cursor.execute(
        "SELECT snapshot.refund_obligation_identity,snapshot.bank_code,snapshot.bank_account "
        "FROM client_refund_recipient_snapshots snapshot "
        "JOIN client_obligations obligation "
        "ON obligation.obligation_identity=snapshot.refund_obligation_identity "
        "WHERE snapshot.case_no=%s AND obligation.obligation_type='refund' "
        "ORDER BY snapshot.refund_obligation_identity",
        (case_no,),
    )
    rows = tuple(cursor.fetchall() or ())
    return rows[0] if len(rows) == 1 else None


def _load_client_email(cursor: Any, case_no: str) -> str | None:
    """Read the normalized Case Import email column, not survey_details."""
    cursor.execute(
        "SELECT email FROM beclass_records WHERE bound_case_no=%s "
        "AND email IS NOT NULL AND TRIM(email)<>'' ORDER BY id",
        (case_no,),
    )
    rows = tuple(cursor.fetchall() or ())
    if len(rows) != 1:
        return None
    value = rows[0].get("email") if isinstance(rows[0], dict) else None
    value = str(value).strip() if value is not None else ""
    return value or None


def _load_approved_subsidy_claim(
    cursor: Any, case_no: str, assignment_id: int | None
) -> dict[str, object] | None:
    """Read one exact approved Government Subsidy claim item, if present."""
    if assignment_id is None:
        return None
    cursor.execute(
        "SELECT item.id,item.batch_id,item.assignment_id,item.staff_id,"
        "item.claimed_hours,item.unit_price,item.requested_amount,"
        "item.approved_amount,b.status,account.aggregate_version "
        "FROM subsidy_claim_batch_items item "
        "JOIN subsidy_claim_batches b ON b.id=item.batch_id "
        "JOIN government_subsidy_batch_accounts account ON account.batch_id=item.batch_id "
        "WHERE item.case_no=%s AND item.assignment_id=%s AND b.status='approved' "
        "ORDER BY item.batch_id DESC,item.id DESC LIMIT 2",
        (case_no, assignment_id),
    )
    rows = tuple(cursor.fetchall() or ())
    if len(rows) != 1:
        return None
    row = rows[0]
    try:
        approved_amount = row["approved_amount"]
        if approved_amount is None or approved_amount <= 0:
            return None
        return {
            "claim_item_id": int(row["id"]),
            "batch_id": int(row["batch_id"]),
            "assignment_id": int(row["assignment_id"]),
            "staff_id": int(row["staff_id"]),
            "claimed_hours": row["claimed_hours"],
            "unit_price": row["unit_price"],
            "requested_amount": row["requested_amount"],
            "approved_amount": approved_amount,
            "batch_version": int(row["aggregate_version"]),
        }
    except (KeyError, TypeError, ValueError):
        return None


def _stage_fact_key(stage: str, suffix: str) -> str:
    return f"{stage}_{suffix}"


def _canonical_service_mode(value: object) -> str | None:
    return value if isinstance(value, str) and value in _CANONICAL_SERVICE_MODES else None


def _special_holidays_text(value: object) -> str | None:
    """Project Orders' normalized rest-date JSON to the template's text cell."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        return None
    return "、".join(item.strip() for item in value)


def _project_subsidy_coverage(
    facts: dict[str, object], owners: dict[str, str]
) -> None:
    """Expose the existing Client Finance typed coverage result by name."""
    identity = facts.get("identity_status")
    total_hours = facts.get("total_hours")
    if not isinstance(identity, str) or total_hours is None:
        return
    try:
        from decimal import Decimal

        coverage = derive_subsidy_coverage(
            identity,
            Decimal(str(total_hours)),
            Decimal(str(facts.get("floor_fee") or 0)),
        )
    except (TypeError, ValueError, ArithmeticError):
        return
    if coverage.subsidy_hours <= 0:
        return
    facts["subsidy_hours"] = coverage.subsidy_hours
    owners["client_finance"] = projection_fingerprint(
        {
            "client_finance": owners.get("client_finance"),
            "coverage": {
                "identity_status": coverage.identity_status,
                "total_service_hours": coverage.total_service_hours,
                "subsidy_hours": coverage.subsidy_hours,
                "subsidy_claim_hourly_rate": coverage.subsidy_claim_hourly_rate,
            },
        }
    )


_FULL_DUE_DATE = re.compile(r"^\d{4}/\d{2}/\d{2}$")


def _due_date_from_due_month(value: object) -> date | None:
    """Accept only a fully specified legacy date, never infer a day."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not _FULL_DUE_DATE.fullmatch(text):
        return None
    try:
        return datetime.strptime(text, "%Y/%m/%d").date()
    except ValueError:
        return None


__all__ = ["MySqlFullContractProjectionRepository"]
