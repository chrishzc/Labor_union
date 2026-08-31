"""Consume Payroll-owned PAYOUT-002 facts without repairing Payroll."""

from __future__ import annotations

from collections.abc import Callable

from domains.anomalies.current_issue import CurrentIssueCandidate, OwnerSnapshot
from subsystems.payroll.current_anomaly_facts import (
    PAYROLL_ANOMALY_OWNER_DOMAIN,
    PAYROLL_ANOMALY_OWNER_ROOT_TYPE,
    PAYOUT_002_SUBJECT_TYPE,
    PayrollLateObligationCurrentFact,
)


class PayrollCurrentIssueConsumer:
    """Create a current issue only from complete Payroll readback."""

    def __init__(self, issue_key_builder: Callable[[str, dict[str, str]], str]) -> None:
        self._issue_key_builder = issue_key_builder

    def detect(self, snapshot: OwnerSnapshot) -> tuple[CurrentIssueCandidate, ...]:
        if (
            snapshot.scope.owner_domain != PAYROLL_ANOMALY_OWNER_DOMAIN
            or snapshot.scope.owner_root_type != PAYROLL_ANOMALY_OWNER_ROOT_TYPE
            or snapshot.scope.subject_type != PAYOUT_002_SUBJECT_TYPE
        ):
            raise ValueError("PAYOUT-002 Payroll owner scope is invalid")
        if not isinstance(snapshot.facts, tuple) or not all(
            isinstance(item, PayrollLateObligationCurrentFact) for item in snapshot.facts
        ):
            raise TypeError("PAYOUT-002 Payroll owner facts are invalid")
        if not snapshot.authoritative_complete or not all(
            item.authoritative_complete for item in snapshot.facts
        ):
            raise ValueError("PAYOUT-002 Payroll owner facts are incomplete")
        by_subject = {
            _subject_id(item): item for item in snapshot.facts
        }
        if len(by_subject) != len(snapshot.facts) or set(by_subject) != set(snapshot.scope.subject_ids):
            raise ValueError("PAYOUT-002 Payroll owner facts are incomplete")
        return tuple(
            sorted(
                (
                    self._candidate(item)
                    for item in by_subject.values()
                    if item.predicate_active
                ),
                key=lambda item: item.issue_key,
            )
        )

    def _candidate(self, fact: PayrollLateObligationCurrentFact) -> CurrentIssueCandidate:
        identity = {
            "obligation_identity": fact.obligation_identity,
            "source_event_identity": fact.source_event_identity,
        }
        return CurrentIssueCandidate(
            issue_key=self._issue_key_builder("PAYOUT-002", identity),
            definition_code="PAYOUT-002",
            owner_domain=PAYROLL_ANOMALY_OWNER_DOMAIN,
            owner_root_type=PAYROLL_ANOMALY_OWNER_ROOT_TYPE,
            subject_type=PAYOUT_002_SUBJECT_TYPE,
            subject_id=_subject_id(fact),
            owner_version=fact.owner_version,
            severity="blocking",
            blocking=True,
            details={
                "before_amount_ntd": fact.before_amount_ntd,
                "after_amount_ntd": fact.after_amount_ntd,
                "delta_amount_ntd": fact.after_amount_ntd - fact.before_amount_ntd,
                "root_condition_active": True,
            },
            subject_identity=identity,
        )


def _subject_id(fact: PayrollLateObligationCurrentFact) -> str:
    return f"{fact.obligation_identity}:{fact.source_event_identity}"


Payout002PayrollCurrentIssueConsumer = PayrollCurrentIssueConsumer


__all__ = ["PayrollCurrentIssueConsumer", "Payout002PayrollCurrentIssueConsumer"]
