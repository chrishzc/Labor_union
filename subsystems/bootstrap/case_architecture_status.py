"""Read-only status and approved recommendation for legacy case adoption."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from domains.bootstrap.case_architecture import CaseArchitectureBootstrapIntent
from subsystems.case_import.hcm_adapter import build_approved_case_architecture_bootstrap_intent


_PARTIAL_STATE_BLOCKER = "case_architecture_bootstrap_partial"


@dataclass(frozen=True)
class CaseArchitectureBootstrapStatus:
    case_no: str
    ready: bool
    scheduling_version: int
    scheduling_generation: int
    service_time_complete: bool
    recommendation: CaseArchitectureBootstrapIntent | None
    domain_blockers: tuple[str, ...]


class CaseArchitectureBootstrapStatusService:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def query(self, case_no: str) -> CaseArchitectureBootstrapStatus:
        row = self._load_case_state(case_no)
        if row is None:
            raise ValueError("case_not_found")
        readiness = _architecture_readiness(row)
        if readiness == "ready":
            return _ready_status(case_no, row)
        if readiness == "partial":
            return _partial_status(case_no, row)
        return _bootstrap_status(case_no, row)

    def _load_case_state(self, case_no: str) -> Mapping[str, object] | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT o.case_no,o.start_date,o.service_start_time,o.service_end_time,"
                "o.service_end_day_offset,c.identity_status,c.created_at AS client_created_at,"
                "cfa.case_no AS client_finance_case,cpt.case_no AS client_terms_case,"
                "pca.case_no AS payroll_account_case,cps.case_no AS payroll_policy_case,"
                "cae.case_no AS bootstrap_event_case,sag.case_no AS scheduling_case,"
                "sag.aggregate_version AS scheduling_version,sag.generation_counter AS scheduling_generation "
                "FROM orders o JOIN clients c ON c.id=o.client_id AND c.case_no=o.case_no "
                "LEFT JOIN client_finance_accounts cfa ON cfa.case_no=o.case_no "
                "LEFT JOIN client_payment_terms cpt ON cpt.case_no=o.case_no "
                "LEFT JOIN payroll_case_accounts pca ON pca.case_no=o.case_no "
                "LEFT JOIN case_payroll_rate_policy_snapshots cps ON cps.case_no=o.case_no "
                "LEFT JOIN case_architecture_bootstrap_events cae ON cae.case_no=o.case_no "
                "LEFT JOIN scheduling_aggregates sag ON sag.case_no=o.case_no WHERE o.case_no=%s",
                (case_no,),
            )
            row = cursor.fetchone()
        return row if isinstance(row, Mapping) else None


def _ready_status(case_no, row):
    return _status(case_no, row, ready=True)


def _partial_status(case_no, row):
    return _status(case_no, row, ready=False, blockers=(_PARTIAL_STATE_BLOCKER,))


def _bootstrap_status(case_no, row):
    return _status(case_no, row, ready=False, recommendation=_recommendation(row))


def _status(case_no, row, ready, recommendation=None, blockers=()):
    return CaseArchitectureBootstrapStatus(case_no, ready, _integer_or_zero(row["scheduling_version"]), _integer_or_zero(row["scheduling_generation"]), _service_time_complete(row), recommendation, blockers)


def _architecture_readiness(row):
    required_presence = tuple(row[name] is not None for name in ("client_finance_case", "client_terms_case", "payroll_account_case", "payroll_policy_case", "bootstrap_event_case"))
    if all(required_presence) and row["scheduling_case"] is not None:
        return "ready"
    if any(required_presence):
        return "partial"
    return "bootstrap_required"


def _recommendation(row):
    return build_approved_case_architecture_bootstrap_intent(str(row["case_no"]), str(row["identity_status"]), row["client_created_at"], row["start_date"])


def _integer_or_zero(value):
    return 0 if value is None else int(value)


def _service_time_complete(row):
    return all(row[name] is not None for name in ("service_start_time", "service_end_time", "service_end_day_offset"))


__all__ = ["CaseArchitectureBootstrapStatus", "CaseArchitectureBootstrapStatusService"]
