"""Resolve an explicit BeClass birth-count correction to the approved service rate."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from domains.bootstrap.case_architecture import payroll_policy_kind_for_case


@dataclass(frozen=True, slots=True)
class EffectiveCaseServiceRate:
    policy_version: str
    policy_kind: str
    hourly_rate_ntd: int
    multi_birth_count: str


def load_explicit_case_service_rate(
    cursor: Any,
    case_no: str,
    *,
    lock: bool = False,
) -> EffectiveCaseServiceRate | None:
    """Return a rate only when an administrator explicitly corrected birth count."""

    lock_clause = " FOR UPDATE" if lock else ""
    cursor.execute(
        "SELECT clients.identity_status,orders.start_date,state.effective_values_json "
        "FROM orders JOIN clients ON clients.id=orders.client_id "
        "LEFT JOIN (SELECT bound_case_no,MAX(id) AS id FROM beclass_records "
        "WHERE bound_case_no IS NOT NULL GROUP BY bound_case_no HAVING COUNT(*)=1) source "
        "ON source.bound_case_no=orders.case_no "
        "LEFT JOIN beclass_record_correction_states state ON state.beclass_record_id=source.id "
        "WHERE orders.case_no=%s" + lock_clause,
        (case_no,),
    )
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise ValueError("order_not_found")
    values = _mapping(row.get("effective_values_json"))
    birth_count = values.get("multi_birth_count")
    if birth_count not in {"單胞胎", "雙胞胎"}:
        return None
    policy_kind = payroll_policy_kind_for_case(
        str(row["identity_status"]),
        str(birth_count),
    ).value
    service_start = row.get("start_date")
    if not isinstance(service_start, date):
        raise ValueError("planned_service_start_date_required")
    cursor.execute(
        "SELECT policy_version,policy_kind,hourly_rate_ntd "
        "FROM payroll_rate_policies WHERE policy_kind=%s AND effective_from<=%s "
        "AND (effective_until IS NULL OR effective_until>=%s) "
        "ORDER BY effective_from DESC,policy_version DESC LIMIT 2" + lock_clause,
        (policy_kind, service_start, service_start),
    )
    policies = tuple(cursor.fetchall() or ())
    if len(policies) != 1:
        raise ValueError("payroll_rate_policy_not_found")
    policy = policies[0]
    return EffectiveCaseServiceRate(
        str(policy["policy_version"]),
        str(policy["policy_kind"]),
        int(policy["hourly_rate_ntd"]),
        str(birth_count),
    )


def _mapping(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str):
        return {}
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return dict(decoded) if isinstance(decoded, Mapping) else {}


__all__ = ["EffectiveCaseServiceRate", "load_explicit_case_service_rate"]
