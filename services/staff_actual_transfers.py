"""Reconcile one explicit staff bank debit with one monthly settlement."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any, Mapping, Sequence


_FINGERPRINT = re.compile(r"^[0-9a-f]{64}$")
_PHASES = {"normal", "first_salary", "second_subsidy"}
_COMPONENT_COLUMNS = {
    "regular_salary": "service_salary",
    "legacy_subsidy": "legacy_subsidy_payable",
    "floor_fee": "floor_fee_amount",
    "adjustment": "adjustment_amount",
}


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a decimal amount")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a decimal amount") from exc
    if not amount.is_finite():
        raise ValueError(f"{field} must be finite")
    return amount


def _bank_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10]).isoformat()
        except ValueError as exc:
            raise ValueError("transaction_date must be an ISO date") from exc
    raise ValueError("transaction_date is required")


def _identity_ids(value: Any) -> list[int] | None:
    if isinstance(value, (str, bytes, bytearray)):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
            return None
    if not isinstance(value, list):
        return None
    if any(isinstance(item, bool) or not isinstance(item, int) for item in value):
        return None
    return value


def _settlement(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": row["settlement_id"],
        "staff_id": row["staff_id"],
        "settlement_month": row.get("settlement_month"),
        "total_payable": _decimal(row.get("total_payable", 0), "total_payable"),
        "total_paid": _decimal(row.get("total_paid", 0), "total_paid"),
        "status": row.get("settlement_status"),
    }


def _pending(
    settlement: Mapping[str, Any], reason: str, *, review_required: bool = False
) -> dict[str, Any]:
    return {
        "result": "pending",
        "transfer_id": None,
        "settlement": dict(settlement),
        "reason": reason,
        "review_required": review_required,
    }


def _normalize_allocations(
    allocations: Sequence[Mapping[str, Any]], payment_phase: str
) -> tuple[list[dict[str, Any]] | None, str | None]:
    if isinstance(allocations, (str, bytes, bytearray)) or not isinstance(allocations, Sequence):
        raise ValueError("allocations must be a non-empty sequence")
    if not allocations:
        return None, "explicit_allocations_required"

    normalized: list[dict[str, Any]] = []
    allocation_keys: set[tuple[int, str]] = set()
    for allocation in allocations:
        if not isinstance(allocation, Mapping):
            return None, "allocation_must_be_a_mapping"
        detail_id = allocation.get("settlement_detail_id")
        if isinstance(detail_id, bool) or not isinstance(detail_id, int) or detail_id < 1:
            return None, "settlement_detail_id_invalid"
        component_type = allocation.get("component_type")
        if component_type not in _COMPONENT_COLUMNS:
            return None, "component_type_invalid"
        allocation_key = (detail_id, component_type)
        if allocation_key in allocation_keys:
            return None, "duplicate_settlement_detail_component_allocation"
        allocation_keys.add(allocation_key)
        if allocation.get("allocation_method") != "explicit":
            return None, "allocation_method_must_be_explicit"
        if payment_phase == "second_subsidy":
            if component_type != "legacy_subsidy":
                return None, "second_subsidy_requires_legacy_subsidy_component"
        elif component_type == "legacy_subsidy":
            return None, "salary_phase_cannot_allocate_legacy_subsidy"

        try:
            amount = _decimal(allocation.get("allocated_amount"), "allocated_amount")
        except ValueError:
            return None, "allocated_amount_invalid"
        if amount <= 0:
            return None, "allocated_amount_must_be_positive"
        normalized.append(
            {
                "settlement_detail_id": detail_id,
                "component_type": component_type,
                "allocated_amount": amount,
                "allocation_method": "explicit",
            }
        )
    return normalized, None


def _same_existing_transfer(
    existing: Mapping[str, Any],
    *,
    settlement_id: int,
    staff_id: int,
    payment_phase: str,
    amount: Decimal,
    occurred_at: str,
    source_bank: str,
    source_account: Any,
    counterparty_account: str,
    external_reference: str,
    raw_import_reference: str,
) -> bool:
    try:
        existing_amount = _decimal(existing.get("amount"), "existing amount")
        existing_date = _bank_date(existing.get("occurred_at"))
    except ValueError:
        return False
    return (
        existing.get("settlement_id") == settlement_id
        and existing.get("staff_id") == staff_id
        and existing.get("payment_phase") == payment_phase
        and existing.get("transaction_type") == "transfer"
        and existing.get("transaction_status") == "succeeded"
        and existing_amount == amount
        and existing_date == occurred_at
        and existing.get("source_bank") == source_bank
        and existing.get("source_account") == source_account
        and existing.get("counterparty_account") == counterparty_account
        and existing.get("external_reference") == external_reference
        and existing.get("raw_import_reference") == raw_import_reference
        and existing.get("reversal_of_transfer_id") is None
        and existing.get("review_status") == "confirmed"
    )


def _same_existing_allocations(
    existing: Sequence[Mapping[str, Any]], requested: Sequence[Mapping[str, Any]]
) -> bool:
    if len(existing) != len(requested):
        return False
    try:
        existing_values = sorted(
            (
                row.get("settlement_detail_id"),
                row.get("component_type"),
                _decimal(row.get("allocated_amount"), "existing allocated_amount"),
                row.get("allocation_method"),
                row.get("review_status"),
                row.get("reversal_of_allocation_id"),
            )
            for row in existing
        )
    except (TypeError, ValueError):
        return False
    requested_values = sorted(
        (
            row["settlement_detail_id"],
            row["component_type"],
            row["allocated_amount"],
            "explicit",
            "approved",
            None,
        )
        for row in requested
    )
    return existing_values == requested_values


def reconcile_staff_actual_transfer(
    cursor: Any,
    finance_import_row_id: int,
    settlement_id: int,
    payment_phase: str,
    allocations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Create one immutable transfer and explicit allocations in the caller transaction."""
    assert callable(getattr(cursor, "execute", None)), "cursor must provide execute()"
    for value, name in (
        (finance_import_row_id, "finance_import_row_id"),
        (settlement_id, "settlement_id"),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer")
    if payment_phase not in _PHASES:
        raise ValueError("payment_phase must be normal, first_salary or second_subsidy")

    normalized, allocation_error = _normalize_allocations(allocations, payment_phase)

    cursor.execute(
        """SELECT fir.id AS finance_import_row_id, fir.dedup_fingerprint,
                  fir.format_id, fir.source_bank_account, fir.transaction_date,
                  fir.direction, fir.debit, fir.credit, fir.counterparty_account,
                  fir.resolved_counterparty_account,
                  fir.classification_type, fir.reconciliation_status,
                  fir.reconciliation_reference, fir.matched_identity_ids,
                  sms.id AS settlement_id, sms.staff_id, sms.settlement_month,
                  sms.total_payable, sms.total_paid,
                  sms.status AS settlement_status
           FROM finance_import_rows fir
           JOIN staff_monthly_settlements sms ON sms.id=%s
           WHERE fir.id=%s
           FOR UPDATE""",
        (settlement_id, finance_import_row_id),
    )
    row = cursor.fetchone()
    if row is None:
        raise ValueError("finance import row or staff settlement was not found")
    if not isinstance(row, Mapping):
        raise TypeError("cursor must return mapping rows")
    settlement = _settlement(row)

    if allocation_error:
        return _pending(settlement, allocation_error)
    assert normalized is not None

    fingerprint = row.get("dedup_fingerprint")
    if not isinstance(fingerprint, str) or not _FINGERPRINT.fullmatch(fingerprint):
        return _pending(settlement, "fingerprint_missing_or_invalid")
    external_reference = f"fp:{fingerprint}"
    raw_import_reference = f"finance_import_row:{finance_import_row_id}"

    expected_classification = (
        "staff_legacy_subsidy" if payment_phase == "second_subsidy" else "staff_salary"
    )
    try:
        debit = _decimal(row.get("debit"), "debit")
        bank_date = _bank_date(row.get("transaction_date"))
    except ValueError:
        return _pending(settlement, "bank_event_invalid")
    credit = row.get("credit")
    if credit is not None:
        try:
            if _decimal(credit, "credit") != 0:
                return _pending(settlement, "staging_row_not_outgoing_debit")
        except ValueError:
            return _pending(settlement, "staging_row_not_outgoing_debit")
    if (
        row.get("direction") != "outgoing"
        or debit <= 0
        or row.get("classification_type") != expected_classification
    ):
        return _pending(settlement, "staging_row_not_eligible")
    # The raw bank column is retained for audit only.  A formal staff transfer
    # may use only the account resolved by the classifier, never a fallback to
    # the raw counterparty value.
    counterparty_account = row.get("resolved_counterparty_account")
    if not isinstance(counterparty_account, str) or not counterparty_account.strip():
        return _pending(settlement, "resolved_counterparty_account_missing")
    counterparty_account = counterparty_account.strip()
    if _identity_ids(row.get("matched_identity_ids")) != [settlement["staff_id"]]:
        return _pending(settlement, "matched_staff_identity_not_unique")

    cursor.execute(
        """SELECT id, staff_id, account_no
           FROM staff_bank_accounts
           WHERE account_no=%s
           FOR UPDATE""",
        (counterparty_account,),
    )
    account_owners = cursor.fetchall()
    if (
        len(account_owners) != 1
        or account_owners[0].get("staff_id") != settlement["staff_id"]
        or account_owners[0].get("account_no") != counterparty_account
    ):
        return _pending(settlement, "counterparty_account_owner_not_unique")

    allocation_total = sum(
        (allocation["allocated_amount"] for allocation in normalized), Decimal("0")
    )
    if allocation_total != debit:
        return _pending(settlement, "allocation_total_must_equal_bank_debit")

    cursor.execute(
        """SELECT id, settlement_id, staff_id, payment_phase,
                  transaction_type, transaction_status, amount, occurred_at,
                  source_bank, source_account, counterparty_account,
                  external_reference, reversal_of_transfer_id,
                  raw_import_reference, review_status
           FROM staff_actual_transfers
           WHERE external_reference=%s OR raw_import_reference=%s
           FOR UPDATE""",
        (external_reference, raw_import_reference),
    )
    conflicts = cursor.fetchall()
    if conflicts:
        if len(conflicts) != 1 or not _same_existing_transfer(
            conflicts[0],
            settlement_id=settlement_id,
            staff_id=settlement["staff_id"],
            payment_phase=payment_phase,
            amount=debit,
            occurred_at=bank_date,
            source_bank=row.get("format_id"),
            source_account=row.get("source_bank_account"),
            counterparty_account=counterparty_account,
            external_reference=external_reference,
            raw_import_reference=raw_import_reference,
        ):
            return _pending(
                settlement, "existing_transfer_differs", review_required=True
            )
        existing = conflicts[0]
        cursor.execute(
            """SELECT settlement_detail_id, component_type, allocated_amount,
                      allocation_method, review_status, reversal_of_allocation_id
               FROM staff_transfer_allocations
               WHERE transfer_id=%s
               ORDER BY settlement_detail_id, component_type
               FOR UPDATE""",
            (existing["id"],),
        )
        if (
            not _same_existing_allocations(cursor.fetchall(), normalized)
            or row.get("reconciliation_status") != "reconciled"
            or row.get("reconciliation_reference") != external_reference
        ):
            return _pending(
                settlement, "existing_transfer_differs", review_required=True
            )
        return {
            "result": "existing",
            "transfer_id": existing["id"],
            "settlement": settlement,
        }

    if row.get("reconciliation_status") != "pending":
        return _pending(
            settlement,
            "non_pending_staging_row_has_no_identical_transfer",
            review_required=True,
        )
    if settlement["status"] not in {"finalized", "partially_paid"}:
        return _pending(settlement, "settlement_not_payable")

    cursor.execute(
        """SELECT id, settlement_id, staff_id, service_salary,
                  legacy_subsidy_payable, floor_fee_amount, adjustment_amount,
                  payable_amount, legacy_subsidy_status, review_required
           FROM staff_monthly_settlement_details
           WHERE settlement_id=%s
           ORDER BY id
           FOR UPDATE""",
        (settlement_id,),
    )
    details = cursor.fetchall()
    details_by_id = {detail["id"]: detail for detail in details}
    if len(details_by_id) != len(details):
        raise ValueError("settlement contains duplicate detail ids")

    cursor.execute(
        """SELECT sta.settlement_detail_id, sta.component_type,
                  sta.allocated_amount, sat.transaction_type
           FROM staff_transfer_allocations sta
           JOIN staff_actual_transfers sat ON sat.id=sta.transfer_id
           JOIN staff_monthly_settlement_details smsd
             ON smsd.id=sta.settlement_detail_id
           WHERE smsd.settlement_id=%s
             AND sat.transaction_status='succeeded'
             AND sta.review_status='approved'
           ORDER BY sta.id
           FOR UPDATE""",
        (settlement_id,),
    )
    ledger = cursor.fetchall()
    paid_by_component: dict[tuple[int, str], Decimal] = {}
    ledger_total = Decimal("0")
    for allocation in ledger:
        amount = _decimal(allocation.get("allocated_amount"), "ledger allocated_amount")
        sign = Decimal("1") if allocation.get("transaction_type") == "transfer" else Decimal("-1")
        key = (allocation.get("settlement_detail_id"), allocation.get("component_type"))
        paid_by_component[key] = paid_by_component.get(key, Decimal("0")) + sign * amount
        ledger_total += sign * amount
    if ledger_total != settlement["total_paid"]:
        return _pending(
            settlement, "settlement_paid_projection_mismatch", review_required=True
        )

    for allocation in normalized:
        detail = details_by_id.get(allocation["settlement_detail_id"])
        if (
            detail is None
            or detail.get("settlement_id") != settlement_id
            or detail.get("staff_id") != settlement["staff_id"]
        ):
            return _pending(settlement, "allocation_crosses_settlement_or_staff")
        component_type = allocation["component_type"]
        if component_type == "legacy_subsidy" and (
            detail.get("legacy_subsidy_status") != "confirmed"
            or bool(detail.get("review_required"))
        ):
            return _pending(settlement, "legacy_subsidy_component_not_confirmed")
        component_amount = _decimal(
            detail.get(_COMPONENT_COLUMNS[component_type]),
            _COMPONENT_COLUMNS[component_type],
        )
        already_paid = paid_by_component.get(
            (allocation["settlement_detail_id"], component_type), Decimal("0")
        )
        remaining = component_amount - already_paid
        if already_paid < 0 or remaining <= 0 or allocation["allocated_amount"] != remaining:
            return _pending(settlement, "component_balance_not_paid_exactly")

    new_total_paid = ledger_total + debit
    if new_total_paid <= 0 or new_total_paid > settlement["total_payable"]:
        return _pending(settlement, "settlement_total_would_be_invalid")
    new_status = (
        "paid" if new_total_paid == settlement["total_payable"] else "partially_paid"
    )

    cursor.execute(
        """INSERT INTO staff_actual_transfers (
                  settlement_id, staff_id, payment_phase, transaction_type,
                  transaction_status, amount, occurred_at, source_bank,
                  source_account, counterparty_account, external_reference,
                  raw_import_reference, review_status
              ) VALUES (%s,%s,%s,'transfer','succeeded',%s,%s,%s,%s,%s,%s,%s,'confirmed')""",
        (
            settlement_id,
            settlement["staff_id"],
            payment_phase,
            debit,
            bank_date,
            row.get("format_id"),
            row.get("source_bank_account"),
            counterparty_account,
            external_reference,
            raw_import_reference,
        ),
    )
    transfer_id = cursor.lastrowid
    if not transfer_id:
        raise RuntimeError("staff actual transfer id was not generated")
    for allocation in normalized:
        cursor.execute(
            """INSERT INTO staff_transfer_allocations (
                      transfer_id, settlement_detail_id, allocated_amount,
                      component_type, allocation_method, review_status
                  ) VALUES (%s,%s,%s,%s,'explicit','approved')""",
            (
                transfer_id,
                allocation["settlement_detail_id"],
                allocation["allocated_amount"],
                allocation["component_type"],
            ),
        )

    cursor.execute(
        """UPDATE staff_monthly_settlements
           SET total_paid=%s, status=%s
           WHERE id=%s AND status IN ('finalized','partially_paid')""",
        (new_total_paid, new_status, settlement_id),
    )
    if getattr(cursor, "rowcount", 1) != 1:
        raise RuntimeError("staff settlement projection update failed")
    cursor.execute(
        """UPDATE finance_import_rows
           SET reconciliation_status='reconciled', reconciliation_reference=%s,
               reconciled_at=CURRENT_TIMESTAMP
           WHERE id=%s AND reconciliation_status='pending'""",
        (external_reference, finance_import_row_id),
    )
    if getattr(cursor, "rowcount", 1) != 1:
        raise RuntimeError("staging row reconciliation update failed")

    settlement = {
        **settlement,
        "total_paid": new_total_paid,
        "status": new_status,
    }
    return {
        "result": "reconciled",
        "transfer_id": transfer_id,
        "settlement": settlement,
    }
