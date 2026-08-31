"""Consume Case Import pairing facts without matching identities in Anomalies."""

from __future__ import annotations

from collections.abc import Callable

from domains.anomalies.current_issue import CurrentIssueCandidate, OwnerSnapshot
from subsystems.case_import.pairing_current_facts import (
    CASE_PAIRING_ANOMALY_OWNER_DOMAIN,
    CASE_PAIRING_ANOMALY_OWNER_ROOT_TYPE,
    BeClassCounterpartCurrentFact,
    CasePairingCurrentFact,
    CasePairingCurrentIssueCode,
    HcmCounterpartCurrentFact,
)


class CasePairingCurrentIssueConsumer:
    def __init__(self, issue_key_builder: Callable[[str, dict[str, str]], str]) -> None:
        self._issue_key_builder = issue_key_builder

    def detect(self, snapshot: OwnerSnapshot) -> tuple[CurrentIssueCandidate, ...]:
        scope = snapshot.scope
        if scope.owner_domain != CASE_PAIRING_ANOMALY_OWNER_DOMAIN or scope.owner_root_type != CASE_PAIRING_ANOMALY_OWNER_ROOT_TYPE:
            raise ValueError("case pairing owner scope is invalid")
        code = CasePairingCurrentIssueCode(scope.subject_type)
        if not isinstance(snapshot.facts, tuple) or not all(isinstance(fact, (HcmCounterpartCurrentFact, BeClassCounterpartCurrentFact)) for fact in snapshot.facts):
            raise TypeError("case pairing owner facts are invalid")
        if not snapshot.authoritative_complete or not all(fact.authoritative_complete for fact in snapshot.facts):
            raise ValueError("case pairing owner facts are incomplete")
        return tuple(self._candidate(fact, code) for fact in snapshot.facts if fact.predicate_active)

    def _candidate(self, fact: CasePairingCurrentFact, code: CasePairingCurrentIssueCode):
        actual, subject_id, identity = _identity(fact)
        if actual is not code:
            raise ValueError("case pairing owner fact code mismatch")
        return CurrentIssueCandidate(
            self._issue_key_builder(code.value, identity), code.value,
            CASE_PAIRING_ANOMALY_OWNER_DOMAIN, CASE_PAIRING_ANOMALY_OWNER_ROOT_TYPE,
            code.value, subject_id, fact.owner_version, "blocking", True,
            {"unresolved_reason_codes": tuple(reason.value for reason in fact.unresolved_reason_codes), "root_condition_active": True},
            identity,
        )


def _identity(fact: CasePairingCurrentFact):
    if isinstance(fact, HcmCounterpartCurrentFact):
        return CasePairingCurrentIssueCode.HCM_COUNTERPART_MISSING, fact.case_no, {"case_no": fact.case_no}
    subject = fact.entity_kind + ":" + fact.review_item_id
    return CasePairingCurrentIssueCode.BECLASS_COUNTERPART_MISSING, subject, {"entity_kind": fact.entity_kind, "review_item_id": fact.review_item_id}


__all__ = ["CasePairingCurrentIssueConsumer"]
