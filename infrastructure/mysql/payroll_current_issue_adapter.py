"""Read-only Payroll composition for the PAYOUT-002 current issue."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime

from domains.anomalies.current_issue import OwnerSnapshot, RecheckScope
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.payroll.current_anomaly_facts import (
    PAYROLL_ANOMALY_OWNER_DOMAIN,
    PAYROLL_ANOMALY_OWNER_ROOT_TYPE,
    PAYOUT_002_SUBJECT_TYPE,
    PayrollLateObligationCurrentFact,
)


class MySqlPayrollCurrentIssueAdapter:
    """Compose a complete, bounded Payroll owner snapshot without writes."""

    def __init__(self, connection) -> None:
        self._connection = connection

    def read_owner_snapshot(self, scope: RecheckScope) -> OwnerSnapshot:
        if (
            scope.owner_domain != PAYROLL_ANOMALY_OWNER_DOMAIN
            or scope.owner_root_type != PAYROLL_ANOMALY_OWNER_ROOT_TYPE
            or scope.subject_type != PAYOUT_002_SUBJECT_TYPE
        ):
            raise ValueError("PAYOUT-002 Payroll owner scope is invalid")
        facts = tuple(self._read_fact(subject) for subject in scope.subject_ids)
        token = fingerprint_payload({
            "scope": tuple(scope.subject_ids),
            "facts": tuple(_fact_payload(item) for item in facts),
        }).value
        return OwnerSnapshot(
            scope,
            token,
            max((item.owner_version for item in facts), default=0),
            facts,
            all(item.authoritative_complete for item in facts),
        )

    def _read_fact(self, subject: str) -> PayrollLateObligationCurrentFact:
        obligation_identity, separator, event_identity = subject.partition(":staff-obligation-event:")
        if not separator or not obligation_identity or not event_identity.isdecimal() or int(event_identity) <= 0:
            raise ValueError("PAYOUT-002 Payroll subject is invalid")
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT o.obligation_identity,o.case_no,o.amount_due_ntd,o.payroll_version,"
                "a.aggregate_version,ev.id,ev.created_at,ev.before_amount_ntd,ev.after_amount_ntd,"
                "o.due_date FROM staff_obligations o "
                "JOIN payroll_case_accounts a ON a.case_no=o.case_no "
                "JOIN staff_obligation_events ev ON ev.obligation_identity=o.obligation_identity "
                "WHERE o.obligation_identity=%s AND ev.id=%s",
                (obligation_identity, int(event_identity)),
            )
            row = cursor.fetchone()
        if not isinstance(row, Mapping):
            raise ValueError("PAYOUT-002 Payroll source is unavailable")
        due_date = _date(row["due_date"])
        created_at = _datetime(row["created_at"])
        payload = {
            "obligation_identity": str(row["obligation_identity"]),
            "source_event_identity": subject[len(obligation_identity) + 1:],
            "before_amount_ntd": int(row["before_amount_ntd"]),
            "after_amount_ntd": int(row["after_amount_ntd"]),
            "created_at": created_at.isoformat(),
            "due_date": due_date.isoformat(),
            "payroll_version": int(row["payroll_version"]),
            "aggregate_version": int(row["aggregate_version"]),
        }
        return PayrollLateObligationCurrentFact(
            str(row["obligation_identity"]),
            subject[len(obligation_identity) + 1:],
            fingerprint_payload(payload).value,
            max(int(row["aggregate_version"]), int(row["payroll_version"]), int(event_identity)),
            int(row["before_amount_ntd"]),
            int(row["after_amount_ntd"]),
            created_at.date() > due_date,
            True,
        )


def _fact_payload(fact: PayrollLateObligationCurrentFact) -> dict[str, object]:
    return {
        "obligation_identity": fact.obligation_identity,
        "source_event_identity": fact.source_event_identity,
        "owner_snapshot_token": fact.owner_snapshot_token,
        "owner_version": fact.owner_version,
        "before_amount_ntd": fact.before_amount_ntd,
        "after_amount_ntd": fact.after_amount_ntd,
        "predicate_active": fact.predicate_active,
    }


def _date(value) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value))


def _datetime(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


__all__ = ["MySqlPayrollCurrentIssueAdapter"]
