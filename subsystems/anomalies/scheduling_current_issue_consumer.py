"""Consume Scheduling-owned current facts without reproducing Scheduling rules."""

from __future__ import annotations

from collections.abc import Callable

from domains.anomalies.current_issue import CurrentIssueCandidate, OwnerSnapshot
from subsystems.scheduling.current_anomaly_facts import (
    SCHEDULING_ANOMALY_OWNER_DOMAIN, SCHEDULING_ANOMALY_OWNER_ROOT_TYPE,
    SchedulingCoverageCurrentFact, SchedulingCurrentFact, SchedulingCurrentIssueCode,
    SchedulingOverlapCurrentFact, SchedulingReplacementCurrentFact,
)


class SchedulingCurrentIssueConsumer:
    def __init__(self, issue_key_builder: Callable[[str, dict[str, str]], str]) -> None:
        self._issue_key_builder = issue_key_builder

    def detect(self, snapshot: OwnerSnapshot) -> tuple[CurrentIssueCandidate, ...]:
        scope = snapshot.scope
        if scope.owner_domain != SCHEDULING_ANOMALY_OWNER_DOMAIN or scope.owner_root_type != SCHEDULING_ANOMALY_OWNER_ROOT_TYPE:
            raise ValueError("Scheduling anomaly owner scope is invalid")
        try:
            code = SchedulingCurrentIssueCode(scope.subject_type)
        except ValueError as error:
            raise ValueError("Scheduling anomaly subject type is invalid") from error
        if not isinstance(snapshot.facts, tuple) or not all(isinstance(item, (SchedulingReplacementCurrentFact, SchedulingOverlapCurrentFact, SchedulingCoverageCurrentFact)) for item in snapshot.facts):
            raise TypeError("Scheduling owner facts are invalid")
        if not snapshot.authoritative_complete or not all(item.authoritative_complete for item in snapshot.facts):
            raise ValueError("Scheduling owner facts are incomplete")
        candidates = tuple(self._candidate(item, code) for item in snapshot.facts if item.predicate_active)
        return tuple(sorted(candidates, key=lambda item: item.issue_key))

    def _candidate(self, fact: SchedulingCurrentFact, code: SchedulingCurrentIssueCode) -> CurrentIssueCandidate:
        actual_code, subject_id, subject_identity = _identity(fact)
        if actual_code is not code:
            raise ValueError("Scheduling owner fact code mismatch")
        return CurrentIssueCandidate(
            issue_key=self._issue_key_builder(code.value, subject_identity), definition_code=code.value,
            owner_domain=SCHEDULING_ANOMALY_OWNER_DOMAIN, owner_root_type=SCHEDULING_ANOMALY_OWNER_ROOT_TYPE,
            subject_type=code.value, subject_id=subject_id, owner_version=fact.owner_version,
            severity="blocking", blocking=True,
            details={"unresolved_reason_codes": tuple(item.value for item in fact.unresolved_reason_codes), "root_condition_active": True},
            subject_identity=subject_identity,
        )


def _identity(fact: SchedulingCurrentFact):
    if isinstance(fact, SchedulingReplacementCurrentFact):
        value = str(fact.assignment_id)
        return SchedulingCurrentIssueCode.REPLACEMENT_INCOMPLETE, value, {"assignment_id": value}
    if isinstance(fact, SchedulingOverlapCurrentFact):
        left, right = str(fact.assignment_id_a), str(fact.assignment_id_b)
        return SchedulingCurrentIssueCode.ASSIGNMENT_OVERLAP, left + ":" + right, {"assignment_id_a": left, "assignment_id_b": right}
    value = fact.case_no + ":" + str(fact.generation)
    return SchedulingCurrentIssueCode.COVERAGE_INVALID, value, {"case_no": fact.case_no, "generation": str(fact.generation)}


__all__ = ["SchedulingCurrentIssueConsumer"]
