"""Consume Government Subsidy-owned current facts without recalculating money."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, replace

from domains.anomalies.current_issue import CurrentIssueCandidate, OwnerSnapshot
from domains.anomalies.registry import default_anomaly_registry
from subsystems.government_subsidy.current_anomaly_facts import (
    GOVERNMENT_SUBSIDY_ANOMALY_OWNER_DOMAIN,
    GOVERNMENT_SUBSIDY_ANOMALY_OWNER_ROOT_TYPE,
    GovernmentSubsidyAllocationCurrentFact,
    GovernmentSubsidyCurrentFact,
    GovernmentSubsidyCurrentIssueCode,
    GovernmentSubsidyReceiptCurrentFact,
    GovernmentSubsidyReversalCurrentFact,
)

_OWNER_FACT_TYPES = (
    GovernmentSubsidyReceiptCurrentFact,
    GovernmentSubsidyAllocationCurrentFact,
    GovernmentSubsidyReversalCurrentFact,
)


class GovernmentSubsidyCurrentIssueConsumer:
    def __init__(self, issue_key_builder: Callable[[str, dict[str, str]], str]) -> None:
        self._issue_key_builder = issue_key_builder

    def detect(self, snapshot: OwnerSnapshot) -> tuple[CurrentIssueCandidate, ...]:
        scope = snapshot.scope
        if scope.owner_domain != GOVERNMENT_SUBSIDY_ANOMALY_OWNER_DOMAIN or scope.owner_root_type != GOVERNMENT_SUBSIDY_ANOMALY_OWNER_ROOT_TYPE:
            raise ValueError("government subsidy anomaly owner scope is invalid")
        code = GovernmentSubsidyCurrentIssueCode(scope.subject_type)
        if not isinstance(snapshot.facts, tuple) or not all(isinstance(fact, _OWNER_FACT_TYPES) for fact in snapshot.facts):
            raise TypeError("government subsidy owner facts are invalid")
        if not snapshot.authoritative_complete or not all(fact.authoritative_complete for fact in snapshot.facts):
            raise ValueError("government subsidy owner facts are incomplete")
        candidates = tuple(self._candidate(fact, code) for fact in snapshot.facts if fact.predicate_active)
        return tuple(sorted(candidates, key=lambda candidate: candidate.issue_key))

    def _candidate(self, fact: GovernmentSubsidyCurrentFact, code: GovernmentSubsidyCurrentIssueCode) -> CurrentIssueCandidate:
        actual_code, subject_id, identity = _identity(fact)
        if actual_code is not code:
            raise ValueError("government subsidy owner fact code mismatch")
        return CurrentIssueCandidate(
            issue_key=self._issue_key_builder(code.value, identity),
            definition_code=code.value,
            owner_domain=GOVERNMENT_SUBSIDY_ANOMALY_OWNER_DOMAIN,
            owner_root_type=GOVERNMENT_SUBSIDY_ANOMALY_OWNER_ROOT_TYPE,
            subject_type=code.value,
            subject_id=subject_id,
            owner_version=fact.owner_version,
            severity="blocking",
            blocking=True,
            details={**_details(fact), **_available_actions(fact, code)},
            subject_identity=identity,
        )


def _identity(fact: GovernmentSubsidyCurrentFact):
    if isinstance(fact, GovernmentSubsidyReceiptCurrentFact):
        return GovernmentSubsidyCurrentIssueCode.RECEIPT_UNMATCHED, fact.bank_fact_identity, {"bank_fact_identity": fact.bank_fact_identity}
    if isinstance(fact, GovernmentSubsidyAllocationCurrentFact):
        subject = fact.bank_fact_identity + ":" + str(fact.batch_id)
        return GovernmentSubsidyCurrentIssueCode.RECEIPT_ALLOCATION_AMBIGUOUS, subject, {"bank_fact_identity": fact.bank_fact_identity, "batch_id": str(fact.batch_id)}
    if isinstance(fact, GovernmentSubsidyReversalCurrentFact):
        subject = fact.reversal_bank_fact_identity + ":" + str(fact.source_receipt_id)
        return GovernmentSubsidyCurrentIssueCode.REVERSAL_INVALID, subject, {"reversal_bank_fact_identity": fact.reversal_bank_fact_identity, "source_receipt_id": str(fact.source_receipt_id)}
    raise TypeError("government subsidy owner fact is invalid")


def _details(fact):
    details = {
        "unresolved_reason_codes": tuple(
            reason.value if hasattr(reason, "value") else str(reason)
            for reason in fact.unresolved_reason_codes
        ),
        "root_condition_active": True,
    }
    return details


def _available_actions(fact, code) -> dict[str, object]:
    bindings: dict[str, str | int | None]
    if isinstance(fact, GovernmentSubsidyReceiptCurrentFact):
        bindings = {
            "bank_fact_identity": fact.bank_fact_identity,
            "finance_import_row_id": fact.finance_import_row_id,
            "source_version": fact.owner_version,
        }
    elif isinstance(fact, GovernmentSubsidyAllocationCurrentFact):
        bindings = {
            "bank_fact_identity": fact.bank_fact_identity,
            "batch_id": fact.batch_id,
            "finance_import_row_id": fact.finance_import_row_id,
            "source_version": fact.owner_version,
        }
    elif isinstance(fact, GovernmentSubsidyReversalCurrentFact):
        bindings = {
            "finance_import_row_id": fact.finance_import_row_id,
            "reversal_bank_fact_identity": fact.reversal_bank_fact_identity,
            "source_receipt_id": fact.source_receipt_id,
            "source_version": fact.owner_version,
        }
    else:
        return {}
    descriptor = default_anomaly_registry().available_actions(code.value)[0]
    return {
        "available_actions": (
            asdict(replace(descriptor, source_bindings=bindings)),
        )
    }


__all__ = ["GovernmentSubsidyCurrentIssueConsumer"]
