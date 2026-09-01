"""
File: historical_staff_payables_completion_read_adapter.py
Description: 以單一唯讀快照重建案件 Staff Payables 完成根與完整來源版本向量。
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.validation import require_canonical_text
from subsystems.orders.historical_completion_oracle import (
    CompletionOwner,
    HistoricalSettlementReadback,
    HistoricalSettlementSourceVersion,
    SettlementSourceKind,
)

_CASE_NUMBER_MAXIMUM_LENGTH = 50
_IDENTITY_MAXIMUM_LENGTH = 191
_SIGNED_BIGINT_MAXIMUM = 9_223_372_036_854_775_807


# Every branch has the same shape so one execute obtains a statement-level
# snapshot without taking locks or inheriting transaction ownership.
_CURRENT_CASE_READ_SQL = """
SELECT 'payroll_account' row_kind, p.case_no, NULL identity, NULL related_identity,
       NULL staff_id, NULL assignment_id, p.aggregate_version version,
       NULL direction, NULL status, NULL amount_due_ntd, NULL current_event_id,
       NULL resulting_version, NULL event_type, NULL event_amount_ntd,
       NULL reversal_of_event_id, NULL allocated_amount_ntd, NULL allocation_ordinal,
       NULL projection_amount_ntd, NULL net_paid_ntd, NULL balance_ntd,
       NULL projection_status, NULL account_version, NULL target_event_id, NULL target_staff_id,
       NULL source_event_ids, NULL source_obligation_identities,
       NULL projection_version, NULL finance_import_row_id, NULL bank_identity_hash,
       NULL reconciliation_reference, NULL target_event_type, NULL target_event_amount_ntd,
       NULL linked_staff_id, NULL source_bank_fact_identities,
       NULL recovery_event_id, NULL recovery_before_ntd, NULL recovery_after_ntd,
       NULL recovery_event_status,
       NULL historical_projection_event_id, NULL historical_projection_case_no,
       NULL historical_projection_staff_id, NULL historical_confirmation_kind,
       NULL historical_amount_snapshot_ntd, NULL historical_obligation_payroll_version,
       NULL historical_staff_payables_version, NULL historical_event_identity,
       NULL historical_event_case_no, NULL historical_event_staff_id,
       NULL historical_event_confirmation_kind, NULL historical_event_payer_role,
       NULL historical_event_payee_role,
       NULL historical_event_expected_version, NULL historical_event_resulting_version,
       NULL historical_event_adoption_receipt_id,
       NULL historical_link_amount_snapshot_ntd, NULL historical_link_payroll_version,
       NULL historical_link_ordinal
FROM payroll_case_accounts p WHERE p.case_no=%s
UNION ALL
SELECT 'obligation', o.case_no, o.obligation_identity, NULL, o.staff_id,
       o.assignment_id, o.payroll_version, o.direction, o.status, o.amount_due_ntd,
       o.current_event_id, oe.resulting_payroll_version, oe.event_type,
       oe.after_amount_ntd, NULL, NULL, NULL, sp.obligation_amount_ntd,
       sp.net_paid_ntd, sp.balance_ntd, sp.status, sa.aggregate_version, sp.current_event_id,
       sp.staff_id, NULL, NULL
       , sp.aggregate_version, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       NULL, NULL, NULL, NULL,
       hp.current_event_id, hp.case_no, hp.staff_id, hp.confirmation_kind,
       hp.amount_snapshot_ntd, hp.obligation_payroll_version,
       hp.staff_payables_version, he.event_identity, he.case_no, he.staff_id,
       he.confirmation_kind, he.payer_role, he.payee_role,
       he.expected_staff_payables_version, he.resulting_staff_payables_version,
       he.historical_adoption_receipt_id, hl.amount_snapshot_ntd,
       hl.obligation_payroll_version, hl.link_ordinal
FROM staff_obligations o
LEFT JOIN staff_obligation_events oe ON oe.id=o.current_event_id
LEFT JOIN staff_payable_projections sp ON sp.obligation_identity=o.obligation_identity
LEFT JOIN staff_payable_accounts sa ON sa.staff_id=o.staff_id
LEFT JOIN historical_staff_payout_projections hp
       ON hp.obligation_identity=o.obligation_identity
LEFT JOIN historical_staff_payout_events he ON he.id=hp.current_event_id
LEFT JOIN historical_staff_payout_obligation_links hl
       ON hl.event_id=hp.current_event_id
      AND hl.obligation_identity=o.obligation_identity
WHERE o.case_no=%s AND o.status<>'cancelled'
UNION ALL
SELECT 'payout', linked.case_no,
       CAST(e.id AS CHAR CHARACTER SET utf8mb4) COLLATE utf8mb4_unicode_ci,
       l.obligation_identity,
       e.staff_id, NULL, e.id, NULL, NULL, NULL, NULL, NULL, e.event_type,
       e.amount_ntd, e.reversal_of_event_id, l.allocated_amount_ntd,
       l.allocation_ordinal, NULL, NULL, NULL, NULL, NULL, target.id, target.staff_id,
       NULL, NULL,
       NULL, e.finance_import_row_id, e.bank_account_identity_hash,
       e.reconciliation_reference, target.event_type, target.amount_ntd,
       linked.staff_id, NULL, NULL, NULL, NULL, NULL,
       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       NULL, NULL, NULL, NULL, NULL,
       NULL, NULL, NULL
FROM staff_payout_events e
JOIN staff_payout_obligation_links l ON l.payout_event_id=e.id
JOIN staff_obligations linked ON linked.obligation_identity=l.obligation_identity
LEFT JOIN staff_payout_events target ON target.id=e.reversal_of_event_id
WHERE e.id IN (
    SELECT DISTINCT case_link.payout_event_id
    FROM staff_payout_obligation_links case_link
    JOIN staff_obligations case_obligation
      ON case_obligation.obligation_identity=case_link.obligation_identity
    WHERE case_obligation.case_no=%s
      AND case_obligation.direction='payable_to_staff'
      AND case_obligation.status<>'cancelled'
)
UNION ALL
SELECT 'recovery', %s, r.recovery_identity, NULL, r.staff_id, NULL,
       r.aggregate_version, NULL, r.status, r.remaining_amount_ntd, NULL, NULL,
       NULL, r.original_amount_ntd, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       NULL, NULL, r.source_payout_event_ids, r.source_obligation_identities,
       NULL, NULL, NULL, NULL, NULL, NULL, NULL, r.source_bank_fact_identities,
       re.id, re.before_remaining_ntd, re.after_remaining_ntd, re.resulting_status,
       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
       NULL, NULL, NULL, NULL, NULL,
       NULL, NULL, NULL
FROM staff_overpayment_recoveries r
LEFT JOIN staff_overpayment_recovery_events re
       ON re.recovery_identity=r.recovery_identity
WHERE r.staff_id IN (
    SELECT DISTINCT staff_id FROM staff_obligations
    WHERE case_no=%s AND direction='payable_to_staff' AND status<>'cancelled'
)
"""


class MySqlStaffPayablesCompletionReadAdapter:
    """Build a case-scoped terminal readback without writes or scalar collapse."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_completion_readback(
        self, case_no: str, *, for_update: bool = False
    ) -> HistoricalSettlementReadback | None:
        require_canonical_text(case_no, "case number", _CASE_NUMBER_MAXIMUM_LENGTH)
        if for_update is not False:
            raise ValueError("historical Staff Payables completion read is read-only")
        with self._connection.cursor() as cursor:
            cursor.execute(
                _CURRENT_CASE_READ_SQL,
                (case_no, case_no, case_no, case_no, case_no),
            )
            rows = _mapping_rows(cursor.fetchall())
        return _build_readback(case_no, rows)


def _build_readback(
    case_no: str, rows: tuple[Mapping[str, Any], ...]
) -> HistoricalSettlementReadback | None:
    supported_row_kinds = {"payroll_account", "obligation", "payout", "recovery"}
    unexpected_row_kind = any(
        not isinstance(row.get("row_kind"), str)
        or row.get("row_kind") not in supported_row_kinds
        for row in rows
    )
    payroll = tuple(row for row in rows if row.get("row_kind") == "payroll_account")
    obligations = tuple(row for row in rows if row.get("row_kind") == "obligation")
    payouts = tuple(row for row in rows if row.get("row_kind") == "payout")
    recoveries = tuple(row for row in rows if row.get("row_kind") == "recovery")
    if not payroll and not obligations and not unexpected_row_kind:
        return None

    blockers: set[str] = set()
    if unexpected_row_kind:
        blockers.add("staff_payables_row_kind_invalid")
    versions: list[HistoricalSettlementSourceVersion] = []
    if len(payroll) != 1 or payroll[0].get("case_no") != case_no:
        blockers.add("staff_payables_payroll_case_account_missing")
    else:
        _add_source(versions, SettlementSourceKind.PAYROLL_CASE_ACCOUNT, case_no, payroll[0].get("version"), blockers)
    if not obligations:
        blockers.add("staff_payables_obligations_missing")

    obligation_index: dict[str, Mapping[str, Any]] = {}
    projection_payload: list[dict[str, Any]] = []
    historical_projection_payload: list[dict[str, Any]] = []
    open_identities: set[str] = set()
    for row in obligations:
        identity = _identity(row.get("identity"), "staff_payables_obligation_identity_invalid", blockers)
        if identity is None:
            continue
        if identity in obligation_index:
            blockers.add("staff_payables_obligation_duplicate")
            continue
        obligation_index[identity] = row
        if row.get("case_no") != case_no:
            blockers.add("staff_payables_obligation_case_mismatch")
        staff_id = _integer(row.get("staff_id"), "staff_payables_staff_identity_invalid", blockers, positive=True, maximum=_SIGNED_BIGINT_MAXIMUM)
        assignment_id = _integer(row.get("assignment_id"), "staff_payables_assignment_identity_invalid", blockers, positive=True, maximum=_SIGNED_BIGINT_MAXIMUM)
        direction = row.get("direction")
        if direction != "payable_to_staff":
            blockers.add("staff_payables_obligation_direction_invalid")
        payroll_version = _integer(row.get("version"), "staff_payables_obligation_version_invalid", blockers, positive=True)
        resulting_version = _integer(row.get("resulting_version"), "staff_payables_obligation_event_missing", blockers, positive=True)
        if payroll_version is not None:
            _add_source(versions, SettlementSourceKind.STAFF_OBLIGATION, identity, payroll_version, blockers)
        event_id = _integer(row.get("current_event_id"), "staff_payables_obligation_event_missing", blockers, positive=True, maximum=_SIGNED_BIGINT_MAXIMUM)
        if not isinstance(row.get("event_type"), str) or row.get("event_type") not in {"established", "rebuilt", "adjustment", "reversal"}:
            blockers.add("staff_payables_obligation_event_type_invalid")
        if event_id is not None:
            _add_source(versions, SettlementSourceKind.STAFF_OBLIGATION_EVENT, str(event_id), resulting_version, blockers)
        if payroll_version is not None and resulting_version != payroll_version:
            blockers.add("staff_payables_obligation_event_version_mismatch")
        obligation_status = row.get("status")
        amount_due = _integer(row.get("amount_due_ntd"), "staff_payables_obligation_amount_invalid", blockers)
        if obligation_status != "open":
            blockers.add("staff_payables_obligation_status_invalid")
        elif amount_due is not None and amount_due <= 0:
            blockers.add("staff_payables_open_obligation_amount_invalid")
        event_amount = _integer(row.get("event_amount_ntd"), "staff_payables_obligation_event_amount_invalid", blockers)
        if amount_due is not None and event_amount != amount_due:
            blockers.add("staff_payables_obligation_event_amount_mismatch")
        account_version = _integer(row.get("account_version"), "staff_payables_account_missing", blockers)
        if staff_id is not None and account_version is not None:
            _add_source(versions, SettlementSourceKind.STAFF_PAYABLE_ACCOUNT, str(staff_id), account_version, blockers)
        if direction != "payable_to_staff":
            open_identities.add(identity)
            continue

        historical_terminal = _historical_projection_terminal(
            row,
            identity=identity,
            case_no=case_no,
            staff_id=staff_id,
            amount_due=amount_due,
            payroll_version=payroll_version,
            account_version=account_version,
            versions=versions,
            blockers=blockers,
            payload=historical_projection_payload,
        )
        projection_status = row.get("projection_status")
        normal_terminal = False
        # Obligation and projection share a SQL row; target_event_id is the
        # projection's current event and target_staff_id is its staff owner.
        if row.get("projection_amount_ntd") is None:
            if not historical_terminal:
                open_identities.add(identity)
        else:
            projection_version = _integer(row.get("projection_version"), "staff_payables_projection_version_invalid", blockers)
            _add_source(versions, SettlementSourceKind.STAFF_PAYABLE_PROJECTION, identity, projection_version, blockers)
            if projection_version is not None and account_version is not None and projection_version != account_version:
                blockers.add("staff_payables_projection_account_version_mismatch")
            projection_staff_id = _integer(
                row.get("target_staff_id"),
                "staff_payables_projection_staff_mismatch",
                blockers,
                positive=True,
                maximum=_SIGNED_BIGINT_MAXIMUM,
            )
            if projection_staff_id != staff_id:
                blockers.add("staff_payables_projection_staff_mismatch")
            amount = row.get("projection_amount_ntd")
            net = row.get("net_paid_ntd")
            balance = row.get("balance_ntd")
            projection_event_id = _integer(row.get("target_event_id"), "staff_payables_projection_event_missing", blockers, positive=True, maximum=_SIGNED_BIGINT_MAXIMUM)
            if not all(_is_int(value) for value in (amount, net, balance)) or amount <= 0 or net < 0:
                blockers.add("staff_payables_projection_money_invalid")
                open_identities.add(identity)
            elif balance != amount - net:
                blockers.add("staff_payables_projection_balance_invalid")
                open_identities.add(identity)
            elif not isinstance(projection_status, str):
                blockers.add("staff_payables_projection_status_invalid")
                open_identities.add(identity)
            elif projection_status in {"completed", "recovery_required"}:
                if balance != 0 or net != amount:
                    blockers.add("staff_payables_terminal_projection_money_invalid")
                    open_identities.add(identity)
                else:
                    normal_terminal = True
            elif projection_status == "payable":
                if net != 0 or balance != amount:
                    blockers.add("staff_payables_payable_projection_money_invalid")
                open_identities.add(identity)
            elif projection_status == "partially_paid":
                if net <= 0 or balance <= 0:
                    blockers.add("staff_payables_partial_projection_money_invalid")
                open_identities.add(identity)
            elif projection_status == "anomaly":
                if balance >= 0:
                    blockers.add("staff_payables_anomaly_projection_money_invalid")
                open_identities.add(identity)
            else:
                blockers.add("staff_payables_projection_status_invalid")
                open_identities.add(identity)
            projection_payload.append({"identity": identity, "staff_id": staff_id, "assignment_id": assignment_id, "direction": direction, "obligation_status": obligation_status, "obligation_amount_ntd": amount_due, "obligation_version": payroll_version, "obligation_event_id": event_id, "obligation_event_type": row.get("event_type"), "obligation_event_amount_ntd": event_amount, "obligation_event_version": resulting_version, "amount": amount, "net": net, "balance": balance, "status": projection_status, "current_event_id": projection_event_id, "account_version": account_version, "projection_version": projection_version})
        if not normal_terminal and not historical_terminal:
            open_identities.add(identity)

    event_groups: dict[int, list[Mapping[str, Any]]] = {}
    allocations_by_obligation: dict[str, int] = {}
    for row in payouts:
        event_id = _numeric_identity(
            row.get("identity"),
            "staff_payables_payout_event_invalid",
            blockers,
        )
        if event_id is not None:
            event_groups.setdefault(event_id, []).append(row)
    payout_payload: list[dict[str, Any]] = []
    seen_bank_fact_ids: set[int] = set()
    for event_id, group in sorted(event_groups.items()):
        first = group[0]
        event_fields = (
            "staff_id",
            "event_type",
            "event_amount_ntd",
            "reversal_of_event_id",
            "target_event_id",
            "target_staff_id",
            "target_event_type",
            "target_event_amount_ntd",
            "finance_import_row_id",
            "bank_identity_hash",
            "reconciliation_reference",
        )
        if any(
            any(row.get(field) != first.get(field) for field in event_fields)
            for row in group[1:]
        ):
            blockers.add("staff_payables_payout_event_identity_conflict")
        event_type = first.get("event_type")
        event_kind = {
            "payout": SettlementSourceKind.STAFF_PAYOUT_EVENT,
            "return": SettlementSourceKind.STAFF_PAYOUT_RETURN_EVENT,
            "reversal": SettlementSourceKind.STAFF_PAYOUT_REVERSAL_EVENT,
        }.get(event_type, SettlementSourceKind.STAFF_PAYOUT_EVENT) if isinstance(event_type, str) else SettlementSourceKind.STAFF_PAYOUT_EVENT
        _add_source(versions, event_kind, str(event_id), event_id, blockers)
        amount = _integer(first.get("event_amount_ntd"), "staff_payables_payout_amount_invalid", blockers, positive=True)
        staff_id = _integer(first.get("staff_id"), "staff_payables_payout_staff_invalid", blockers, positive=True, maximum=_SIGNED_BIGINT_MAXIMUM)
        if not isinstance(event_type, str) or event_type not in {"payout", "return", "reversal"}:
            blockers.add("staff_payables_payout_event_type_invalid")
        bank_fact_id = None
        if isinstance(event_type, str) and event_type in {"payout", "return"}:
            bank_fact_id = _integer(first.get("finance_import_row_id"), "staff_payables_bank_fact_missing", blockers, positive=True, maximum=_SIGNED_BIGINT_MAXIMUM)
            bank_hash = first.get("bank_identity_hash")
            reconciliation = first.get("reconciliation_reference")
            if not isinstance(bank_hash, str) or re.fullmatch(r"[0-9a-f]{64}", bank_hash) is None:
                blockers.add("staff_payables_bank_identity_invalid")
            try:
                require_canonical_text(
                    reconciliation,
                    "Staff Payables reconciliation reference",
                    _IDENTITY_MAXIMUM_LENGTH,
                )
            except (TypeError, ValueError):
                blockers.add("staff_payables_reconciliation_reference_missing")
            if bank_fact_id is not None:
                if bank_fact_id in seen_bank_fact_ids:
                    blockers.add("staff_payables_bank_fact_reused")
                seen_bank_fact_ids.add(bank_fact_id)
                _add_source(versions, SettlementSourceKind.STAFF_BANK_FACT, str(bank_fact_id), 1, blockers)
        allocated_total = 0
        links: list[dict[str, Any]] = []
        seen_ordinals: set[int] = set()
        seen_obligations: set[str] = set()
        for row in group:
            obligation_identity = _identity(row.get("related_identity"), "staff_payables_allocation_identity_invalid", blockers)
            allocated = _integer(row.get("allocated_amount_ntd"), "staff_payables_allocation_amount_invalid", blockers, positive=True)
            ordinal = _integer(row.get("allocation_ordinal"), "staff_payables_allocation_ordinal_invalid", blockers, positive=True, maximum=_SIGNED_BIGINT_MAXIMUM)
            if obligation_identity is None or allocated is None or ordinal is None:
                continue
            linked_case_no = row.get("case_no")
            if linked_case_no != case_no:
                blockers.add("staff_payables_payout_allocation_case_mismatch")
            if obligation_identity not in obligation_index:
                blockers.add("staff_payables_payout_allocation_obligation_missing")
            _add_source(versions, SettlementSourceKind.STAFF_PAYOUT_ALLOCATION, f"{event_id}:{ordinal}", 1, blockers)
            if ordinal in seen_ordinals or obligation_identity in seen_obligations:
                blockers.add("staff_payables_payout_allocation_duplicate")
            seen_ordinals.add(ordinal)
            seen_obligations.add(obligation_identity)
            allocated_total += allocated
            links.append({"obligation_identity": obligation_identity, "amount": allocated, "ordinal": ordinal})
            if obligation_identity in obligation_index:
                sign = 1 if event_type == "payout" else -1
                allocations_by_obligation[obligation_identity] = allocations_by_obligation.get(obligation_identity, 0) + sign * allocated
            linked_staff_id = _integer(
                row.get("linked_staff_id"),
                "staff_payables_payout_staff_mismatch",
                blockers,
                positive=True,
                maximum=_SIGNED_BIGINT_MAXIMUM,
            )
            if linked_staff_id != staff_id:
                blockers.add("staff_payables_payout_staff_mismatch")
            obligation = obligation_index.get(obligation_identity)
            if obligation is not None and obligation.get("staff_id") != staff_id:
                blockers.add("staff_payables_payout_obligation_staff_mismatch")
        if amount is not None and allocated_total != amount:
            blockers.add("staff_payables_payout_allocation_incomplete")
        reversal_of = first.get("reversal_of_event_id")
        parsed_reversal_target_id = None
        target_amount = None
        if event_type == "payout" and any(
            first.get(field) is not None
            for field in (
                "reversal_of_event_id",
                "target_event_id",
                "target_staff_id",
                "target_event_type",
                "target_event_amount_ntd",
            )
        ):
            blockers.add("staff_payables_payout_reversal_shape_invalid")
        if isinstance(event_type, str) and event_type in {"return", "reversal"}:
            target_id = _integer(first.get("target_event_id"), "staff_payables_reversal_target_invalid", blockers, positive=True, maximum=_SIGNED_BIGINT_MAXIMUM)
            reversal_target_id = _integer(reversal_of, "staff_payables_reversal_target_invalid", blockers, positive=True, maximum=_SIGNED_BIGINT_MAXIMUM)
            target_staff_id = _integer(first.get("target_staff_id"), "staff_payables_reversal_target_invalid", blockers, positive=True, maximum=_SIGNED_BIGINT_MAXIMUM)
            target_amount = _integer(first.get("target_event_amount_ntd"), "staff_payables_reversal_target_invalid", blockers, positive=True)
            parsed_reversal_target_id = reversal_target_id
            if (
                target_id is None
                or target_id != reversal_target_id
                or target_staff_id != staff_id
                or target_amount is None
                or first.get("target_event_type") != "payout"
            ):
                blockers.add("staff_payables_reversal_target_invalid")
        payout_payload.append({"event_id": event_id, "staff_id": staff_id, "event_type": event_type, "amount": amount, "reversal_of": parsed_reversal_target_id, "target_amount": target_amount, "bank_fact_id": bank_fact_id, "bank_identity_hash": first.get("bank_identity_hash"), "reconciliation_reference": first.get("reconciliation_reference"), "links": tuple(sorted(links, key=lambda item: item["ordinal"]))})

    event_payload_index = {item["event_id"]: item for item in payout_payload}
    reopened_by_target: dict[tuple[int, str], int] = {}
    for event in payout_payload:
        if not isinstance(event["event_type"], str) or event["event_type"] not in {"return", "reversal"}:
            continue
        target_id = event["reversal_of"]
        target = event_payload_index.get(target_id)
        target_links = {
            item["obligation_identity"]: item["amount"] for item in target["links"]
        } if target and target["event_type"] == "payout" else {}
        if target is not None and event["target_amount"] != target["amount"]:
            blockers.add("staff_payables_reversal_target_amount_mismatch")
        if target is None or target["event_type"] != "payout":
            blockers.add("staff_payables_reversal_target_lineage_missing")
        elif target["staff_id"] != event["staff_id"]:
            blockers.add("staff_payables_reversal_target_staff_mismatch")
        for link in event["links"]:
            key = (target_id, link["obligation_identity"])
            remaining = target_links.get(link["obligation_identity"], 0) - reopened_by_target.get(key, 0)
            if link["amount"] > remaining:
                blockers.add("staff_payables_reversal_allocation_exceeds_target")
            reopened_by_target[key] = reopened_by_target.get(key, 0) + link["amount"]

    for identity, row in obligation_index.items():
        net = row.get("net_paid_ntd")
        if _is_int(net) and allocations_by_obligation.get(identity, 0) != net:
            blockers.add("staff_payables_projection_allocation_mismatch")
        projection_event_id = row.get("target_event_id")
        if _is_int(projection_event_id):
            projection_event = event_payload_index.get(projection_event_id)
            if projection_event is None:
                blockers.add("staff_payables_projection_event_lineage_missing")
            elif identity not in {
                link["obligation_identity"] for link in projection_event["links"]
            }:
                blockers.add("staff_payables_projection_event_obligation_mismatch")

    recovery_payload: list[dict[str, Any]] = []
    recovery_source_obligations: set[str] = set()
    claimed_recovery_source_events: set[int] = set()
    case_identities = set(obligation_index)
    recovery_groups: dict[str, list[Mapping[str, Any]]] = {}
    for row in recoveries:
        identity = _identity(row.get("identity"), "staff_payables_recovery_identity_invalid", blockers)
        if identity is not None:
            recovery_groups.setdefault(identity, []).append(row)
    for identity, group in sorted(recovery_groups.items()):
        row = group[0]
        if row.get("case_no") != case_no:
            blockers.add("staff_payables_recovery_case_mismatch")
        recovery_fields = (
            "staff_id",
            "version",
            "status",
            "amount_due_ntd",
            "event_amount_ntd",
            "source_event_ids",
            "source_obligation_identities",
            "source_bank_fact_identities",
        )
        if any(
            any(item.get(field) != row.get(field) for field in recovery_fields)
            for item in group[1:]
        ):
            blockers.add("staff_payables_recovery_identity_conflict")
        if len(group) > 1 and all(item.get("recovery_event_id") is None for item in group):
            blockers.add("staff_payables_recovery_duplicate")
        source_obligations = _json_string_list(row.get("source_obligation_identities"), "staff_payables_recovery_sources_invalid", blockers)
        source_event_ids = _json_integer_list(row.get("source_event_ids"), "staff_payables_recovery_event_sources_invalid", blockers)
        source_bank_facts = _json_string_list(row.get("source_bank_fact_identities"), "staff_payables_recovery_bank_sources_invalid", blockers)
        if not source_obligations or not source_event_ids or not source_bank_facts:
            blockers.add("staff_payables_recovery_sources_incomplete")
        if not case_identities.intersection(source_obligations):
            blockers.add("staff_payables_recovery_case_attribution_missing")
            continue
        if not set(source_obligations).issubset(case_identities):
            blockers.add("staff_payables_recovery_cross_case_ambiguous")
        recovery_source_obligations.update(set(source_obligations).intersection(case_identities))
        staff_id = _integer(row.get("staff_id"), "staff_payables_recovery_staff_invalid", blockers, positive=True, maximum=_SIGNED_BIGINT_MAXIMUM)
        case_staff_ids = {
            item.get("staff_id")
            for item in obligations
            if _is_int(item.get("staff_id"))
        }
        if staff_id not in case_staff_ids:
            blockers.add("staff_payables_recovery_staff_mismatch")
        if any(
            event_id not in event_payload_index
            or event_payload_index[event_id]["event_type"] != "payout"
            for event_id in source_event_ids
        ):
            blockers.add("staff_payables_recovery_payout_source_missing")
        source_payouts = [
            event_payload_index[event_id]
            for event_id in source_event_ids
            if event_id in event_payload_index
            and event_payload_index[event_id]["event_type"] == "payout"
        ]
        source_event_set = set(source_event_ids)
        if claimed_recovery_source_events.intersection(source_event_set):
            blockers.add("staff_payables_recovery_payout_source_reused")
        claimed_recovery_source_events.update(source_event_set)
        allocated_source_obligations = {
            link["obligation_identity"]
            for event in source_payouts
            for link in event["links"]
        }
        if set(source_obligations) != allocated_source_obligations:
            blockers.add("staff_payables_recovery_obligation_source_mismatch")
        if any(event["staff_id"] != staff_id for event in source_payouts) or any(
            obligation_index[obligation_identity].get("staff_id") != staff_id
            for obligation_identity in source_obligations
            if obligation_identity in obligation_index
        ):
            blockers.add("staff_payables_recovery_source_staff_mismatch")
        expected_bank_sources = {
            f"finance-import-row:{event_payload_index[event_id]['bank_fact_id']}"
            for event_id in source_event_ids
            if event_id in event_payload_index and event_payload_index[event_id].get("bank_fact_id") is not None
        }
        if set(source_bank_facts) != expected_bank_sources:
            blockers.add("staff_payables_recovery_bank_source_mismatch")
        original = _integer(row.get("event_amount_ntd"), "staff_payables_recovery_original_amount_invalid", blockers, positive=True)
        source_payout_total = sum(
            event["amount"]
            for event in source_payouts
            if _is_int(event.get("amount"))
        )
        if original is not None and original > source_payout_total:
            blockers.add("staff_payables_recovery_amount_exceeds_sources")
        remaining = _integer(row.get("amount_due_ntd"), "staff_payables_recovery_remaining_invalid", blockers)
        status = row.get("status")
        if original is not None and remaining is not None and remaining > original:
            blockers.add("staff_payables_recovery_remaining_invalid")
        if not isinstance(status, str):
            blockers.add("staff_payables_recovery_status_invalid")
        elif status in {"recovered", "adjusted"}:
            if remaining != 0:
                blockers.add("staff_payables_recovery_terminal_amount_invalid")
        elif status == "open":
            if original is not None and remaining != original:
                blockers.add("staff_payables_recovery_open_amount_invalid")
        elif status == "partially_recovered":
            if remaining is None or original is None or not 0 < remaining < original:
                blockers.add("staff_payables_recovery_partial_amount_invalid")
        else:
            blockers.add("staff_payables_recovery_status_invalid")
        recovery_version = _integer(row.get("version"), "staff_payables_source_version_invalid", blockers)
        if recovery_version is not None:
            versions.append(HistoricalSettlementSourceVersion(SettlementSourceKind.STAFF_OVERPAYMENT_RECOVERY, identity, recovery_version))
        recovery_events: list[dict[str, Any]] = []
        seen_recovery_event_ids: set[int] = set()
        for event_row in group:
            recovery_event_id = event_row.get("recovery_event_id")
            if recovery_event_id is None:
                continue
            parsed_event_id = _integer(recovery_event_id, "staff_payables_recovery_event_invalid", blockers, positive=True, maximum=_SIGNED_BIGINT_MAXIMUM)
            before = _integer(event_row.get("recovery_before_ntd"), "staff_payables_recovery_event_amount_invalid", blockers, positive=True)
            after = _integer(event_row.get("recovery_after_ntd"), "staff_payables_recovery_event_amount_invalid", blockers)
            if parsed_event_id is not None:
                if parsed_event_id in seen_recovery_event_ids:
                    blockers.add("staff_payables_recovery_event_duplicate")
                seen_recovery_event_ids.add(parsed_event_id)
                _add_source(versions, SettlementSourceKind.STAFF_OVERPAYMENT_RECOVERY_EVENT, f"{identity}:{parsed_event_id}", parsed_event_id, blockers)
            if before is not None and after is not None and after >= before:
                blockers.add("staff_payables_recovery_event_amount_invalid")
            event_status = event_row.get("recovery_event_status")
            if not isinstance(event_status, str) or (after == 0 and event_status not in {"recovered", "adjusted"}) or (
                after is not None and after > 0 and event_status != "partially_recovered"
            ):
                blockers.add("staff_payables_recovery_event_status_invalid")
            recovery_events.append({"event_id": parsed_event_id, "before": before, "after": after, "status": event_status})
        recovery_events.sort(key=lambda item: -1 if item["event_id"] is None else item["event_id"])
        if recovery_version is not None and recovery_version != len(recovery_events):
            blockers.add("staff_payables_recovery_event_version_mismatch")
        if isinstance(status, str) and status in {"partially_recovered", "recovered", "adjusted"} and not recovery_events:
            blockers.add("staff_payables_recovery_event_lineage_missing")
        if recovery_events:
            if recovery_events[0]["before"] != original:
                blockers.add("staff_payables_recovery_event_lineage_discontinuous")
            for previous, current in zip(recovery_events, recovery_events[1:], strict=False):
                if current["before"] != previous["after"]:
                    blockers.add("staff_payables_recovery_event_lineage_discontinuous")
            current_event = recovery_events[-1]
            if current_event["after"] != remaining or current_event["status"] != status:
                blockers.add("staff_payables_recovery_event_projection_mismatch")
        recovery_payload.append({"identity": identity, "staff_id": staff_id, "status": status, "original_amount_ntd": original, "remaining_amount_ntd": remaining, "source_bank_facts": tuple(source_bank_facts), "source_event_ids": tuple(source_event_ids), "source_obligations": tuple(source_obligations), "events": tuple(recovery_events)})

    if any(
        item["status"] == "recovery_required"
        and item["identity"] not in recovery_source_obligations
        for item in projection_payload
    ):
        blockers.add("staff_payables_recovery_required_root_missing")

    source_versions = tuple(sorted(set(versions)))
    lineage_payload = {
        "case_no": case_no,
        "source_versions": tuple((item.kind.value, item.identity, item.version) for item in source_versions),
        "projections": tuple(sorted(projection_payload, key=lambda item: item["identity"])),
        "historical_projections": tuple(
            sorted(historical_projection_payload, key=lambda item: item["identity"])
        ),
        "payouts": tuple(payout_payload),
        "recoveries": tuple(sorted(recovery_payload, key=lambda item: str(item["identity"]))),
    }
    allocation_payload = {
        "case_no": case_no,
        "obligations": tuple(
            sorted(projection_payload, key=lambda item: item["identity"])
        ),
        "historical_obligations": tuple(
            sorted(historical_projection_payload, key=lambda item: item["identity"])
        ),
        "payouts": tuple(payout_payload),
    }
    available = not blockers
    return HistoricalSettlementReadback(
        case_no=case_no,
        owner=CompletionOwner.STAFF_PAYABLES,
        aggregate_version=None,
        settlement_lineage_identity=fingerprint_payload(lineage_payload).value if source_versions and available else None,
        obligation_count=len(obligation_index),
        open_obligation_count=len(open_identities),
        allocation_lineage_identity=fingerprint_payload(allocation_payload).value if (payout_payload or historical_projection_payload) and available else None,
        source_versions=source_versions,
        readback_available=available,
        integrity_blockers=tuple(sorted(blockers)),
    )


def _historical_projection_terminal(
    row: Mapping[str, Any],
    *,
    identity: str,
    case_no: str,
    staff_id: int | None,
    amount_due: int | None,
    payroll_version: int | None,
    account_version: int | None,
    versions: list[HistoricalSettlementSourceVersion],
    blockers: set[str],
    payload: list[dict[str, Any]],
) -> bool:
    event_id_value = row.get("historical_projection_event_id")
    if event_id_value is None:
        return False

    event_id = _integer(
        event_id_value,
        "staff_payables_historical_projection_event_invalid",
        blockers,
        positive=True,
        maximum=_SIGNED_BIGINT_MAXIMUM,
    )
    projection_staff_id = _integer(
        row.get("historical_projection_staff_id"),
        "staff_payables_historical_projection_staff_mismatch",
        blockers,
        positive=True,
        maximum=_SIGNED_BIGINT_MAXIMUM,
    )
    amount_snapshot = _integer(
        row.get("historical_amount_snapshot_ntd"),
        "staff_payables_historical_projection_amount_invalid",
        blockers,
        positive=True,
    )
    projection_payroll_version = _integer(
        row.get("historical_obligation_payroll_version"),
        "staff_payables_historical_projection_payroll_version_invalid",
        blockers,
    )
    projection_owner_version = _integer(
        row.get("historical_staff_payables_version"),
        "staff_payables_historical_projection_owner_version_invalid",
        blockers,
    )
    expected_version = _integer(
        row.get("historical_event_expected_version"),
        "staff_payables_historical_event_version_invalid",
        blockers,
    )
    resulting_version = _integer(
        row.get("historical_event_resulting_version"),
        "staff_payables_historical_event_version_invalid",
        blockers,
        positive=True,
    )
    adoption_receipt_id = _integer(
        row.get("historical_event_adoption_receipt_id"),
        "staff_payables_historical_adoption_receipt_missing",
        blockers,
        positive=True,
        maximum=_SIGNED_BIGINT_MAXIMUM,
    )
    link_amount = _integer(
        row.get("historical_link_amount_snapshot_ntd"),
        "staff_payables_historical_link_amount_invalid",
        blockers,
        positive=True,
    )
    link_payroll_version = _integer(
        row.get("historical_link_payroll_version"),
        "staff_payables_historical_link_payroll_version_invalid",
        blockers,
    )
    link_ordinal = _integer(
        row.get("historical_link_ordinal"),
        "staff_payables_historical_link_ordinal_invalid",
        blockers,
        positive=True,
        maximum=_SIGNED_BIGINT_MAXIMUM,
    )
    event_identity = _identity(
        row.get("historical_event_identity"),
        "staff_payables_historical_event_identity_invalid",
        blockers,
    )
    if row.get("historical_projection_case_no") != case_no:
        blockers.add("staff_payables_historical_projection_case_mismatch")
    if projection_staff_id != staff_id:
        blockers.add("staff_payables_historical_projection_staff_mismatch")
    if row.get("historical_confirmation_kind") not in {"paid", "settled"}:
        blockers.add("staff_payables_historical_confirmation_kind_invalid")
    if row.get("historical_event_case_no") != case_no:
        blockers.add("staff_payables_historical_event_case_mismatch")
    if row.get("historical_event_staff_id") != staff_id:
        blockers.add("staff_payables_historical_event_staff_mismatch")
    if row.get("historical_event_confirmation_kind") != row.get(
        "historical_confirmation_kind"
    ):
        blockers.add("staff_payables_historical_event_confirmation_mismatch")
    if (
        row.get("historical_event_payer_role") != "union"
        or row.get("historical_event_payee_role") != "staff"
    ):
        blockers.add("staff_payables_historical_event_direction_invalid")
    if expected_version is not None and resulting_version != expected_version + 1:
        blockers.add("staff_payables_historical_event_version_mismatch")
    if projection_owner_version != resulting_version:
        blockers.add("staff_payables_historical_projection_event_version_mismatch")
    if account_version != projection_owner_version:
        blockers.add("staff_payables_historical_projection_account_version_mismatch")
    if link_amount != amount_snapshot:
        blockers.add("staff_payables_historical_link_amount_mismatch")
    if link_payroll_version != projection_payroll_version:
        blockers.add("staff_payables_historical_link_payroll_version_mismatch")

    structurally_complete = all(
        value is not None
        for value in (
            event_id,
            event_identity,
            projection_staff_id,
            amount_snapshot,
            projection_payroll_version,
            projection_owner_version,
            expected_version,
            resulting_version,
            adoption_receipt_id,
            link_amount,
            link_payroll_version,
            link_ordinal,
        )
    )
    if structurally_complete:
        _add_source(
            versions,
            SettlementSourceKind.HISTORICAL_STAFF_PAYOUT_PROJECTION,
            identity,
            projection_owner_version,
            blockers,
        )
        _add_source(
            versions,
            SettlementSourceKind.HISTORICAL_STAFF_PAYOUT_EVENT,
            event_identity,
            resulting_version,
            blockers,
        )
        _add_source(
            versions,
            SettlementSourceKind.HISTORICAL_STAFF_PAYOUT_LINK,
            f"{event_id}:{link_ordinal}",
            projection_payroll_version,
            blockers,
        )
        payload.append(
            {
                "identity": identity,
                "staff_id": staff_id,
                "amount_snapshot_ntd": amount_snapshot,
                "obligation_payroll_version": projection_payroll_version,
                "staff_payables_version": projection_owner_version,
                "event_id": event_id,
                "event_identity": event_identity,
                "event_expected_version": expected_version,
                "event_resulting_version": resulting_version,
                "adoption_receipt_id": adoption_receipt_id,
                "link_ordinal": link_ordinal,
            }
        )
    return bool(
        structurally_complete
        and amount_snapshot == amount_due
        and projection_payroll_version == payroll_version
    )


def _add_source(versions: list[HistoricalSettlementSourceVersion], kind: SettlementSourceKind, identity: str, version: Any, blockers: set[str]) -> None:
    parsed = _integer(version, "staff_payables_source_version_invalid", blockers)
    if parsed is None:
        return
    for existing in versions:
        if existing.kind is kind and existing.identity == identity:
            if existing.version != parsed:
                blockers.add("staff_payables_source_version_mismatch")
            return
    try:
        versions.append(HistoricalSettlementSourceVersion(kind, identity, parsed))
    except (TypeError, ValueError):
        blockers.add("staff_payables_source_identity_invalid")


def _identity(value: Any, blocker: str, blockers: set[str]) -> str | None:
    if not isinstance(value, str) or not value:
        blockers.add(blocker)
        return None
    try:
        require_canonical_text(value, "Staff Payables source identity", _IDENTITY_MAXIMUM_LENGTH)
    except ValueError:
        blockers.add(blocker)
        return None
    return value


def _integer(
    value: Any,
    blocker: str,
    blockers: set[str],
    *,
    positive: bool = False,
    maximum: int | None = None,
) -> int | None:
    if isinstance(value, Decimal) and value.is_finite() and value == value.to_integral_value():
        parsed = int(value)
    elif _is_int(value):
        parsed = value
    else:
        blockers.add(blocker)
        return None
    if parsed < (1 if positive else 0):
        blockers.add(blocker)
        return None
    if maximum is not None and parsed > maximum:
        blockers.add(blocker)
        return None
    return parsed


def _numeric_identity(value: Any, blocker: str, blockers: set[str]) -> int | None:
    if _is_int(value):
        parsed = value
    elif (
        isinstance(value, str)
        and value.isascii()
        and value.isdecimal()
        and len(value) <= 20
    ):
        parsed = int(value)
    else:
        blockers.add(blocker)
        return None
    if parsed <= 0 or parsed > _SIGNED_BIGINT_MAXIMUM:
        blockers.add(blocker)
        return None
    return parsed


def _json_string_list(value: Any, blocker: str, blockers: set[str]) -> tuple[str, ...]:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        parsed = None
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        blockers.add(blocker)
        return ()
    for item in parsed:
        try:
            require_canonical_text(item, "Staff Payables recovery source identity", _IDENTITY_MAXIMUM_LENGTH)
        except ValueError:
            blockers.add(blocker)
    if len(set(parsed)) != len(parsed):
        blockers.add(blocker)
    return tuple(parsed)


def _json_integer_list(value: Any, blocker: str, blockers: set[str]) -> tuple[int, ...]:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        parsed = None
    if not isinstance(parsed, list) or any(
        not _is_int(item) or item < 1 or item > _SIGNED_BIGINT_MAXIMUM
        for item in parsed
    ):
        blockers.add(blocker)
        return ()
    if len(set(parsed)) != len(parsed):
        blockers.add(blocker)
    return tuple(parsed)


def _is_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int)


def _mapping_rows(rows: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(rows, (list, tuple)) or any(not isinstance(row, Mapping) for row in rows):
        raise ValueError("Staff Payables current roots are invalid")
    return tuple(rows)


__all__ = ["MySqlStaffPayablesCompletionReadAdapter"]
