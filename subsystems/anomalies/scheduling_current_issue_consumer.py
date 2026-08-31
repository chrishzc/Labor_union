"""Consume Scheduling-owned current facts without reproducing Scheduling rules."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, replace

from domains.anomalies.current_issue import CurrentIssueCandidate, OwnerSnapshot
from domains.anomalies.registry import default_anomaly_registry
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
            details={
                "unresolved_reason_codes": tuple(item.value for item in fact.unresolved_reason_codes),
                "root_condition_active": True,
                **_available_actions(fact, code),
            },
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


def _available_actions(
    fact: SchedulingCurrentFact,
    code: SchedulingCurrentIssueCode,
) -> dict[str, object]:
    if code is SchedulingCurrentIssueCode.REPLACEMENT_INCOMPLETE:
        if not isinstance(fact, SchedulingReplacementCurrentFact):
            raise TypeError("Scheduling replacement action fact is invalid")
        action_key = (
            "complete_replacement_leave_substitution"
            if fact.service_started
            else "rebuild_replacement_assignment_plan"
        )
        descriptor = next(
            action
            for action in default_anomaly_registry().available_actions(code.value)
            if action.action_key == action_key
        )
        bound = replace(
            descriptor,
            source_bindings={
                "assignment_id": fact.assignment_id,
                "case_no": fact.case_no,
                "source_version": fact.owner_version,
            },
        )
        return {"available_actions": (asdict(bound),)}
    if code is SchedulingCurrentIssueCode.ASSIGNMENT_OVERLAP:
        if not isinstance(fact, SchedulingOverlapCurrentFact):
            raise TypeError("Scheduling overlap action fact is invalid")
        descriptor = default_anomaly_registry().available_actions(code.value)[0]
        bound = replace(
            descriptor,
            source_bindings={
                "assignment_id_a": fact.assignment_id_a,
                "assignment_id_b": fact.assignment_id_b,
                "case_no_a": fact.case_no_a,
                "case_no_b": fact.case_no_b,
                "source_version": fact.owner_version,
            },
        )
        return {"available_actions": (asdict(bound),)}
    if code is not SchedulingCurrentIssueCode.COVERAGE_INVALID:
        return {}
    if not isinstance(fact, SchedulingCoverageCurrentFact):
        raise TypeError("Scheduling coverage action fact is invalid")
    descriptor = default_anomaly_registry().available_actions(code.value)[0]
    bound = replace(
        descriptor,
        source_bindings={
            "case_no": fact.case_no,
            "source_version": fact.owner_version,
        },
    )
    return {"available_actions": (asdict(bound),)}


__all__ = ["SchedulingCurrentIssueConsumer"]
