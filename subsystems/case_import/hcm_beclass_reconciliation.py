"""
File: hcm_beclass_reconciliation.py
Description: 依 fresh HCM／BeClass 配對，以 typed Orders command補入下廚需求。
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable, Mapping, Protocol

from domains.case_import.cooking_requirement import CookingRequirementDomainError, normalize_cooking_requirement
from shared_kernel.ports import UnitOfWork


@dataclass(frozen=True, slots=True)
class HcmBeClassReconciliationResult:
    status: str
    requires_cooking: bool | None = None


class HcmBeClassReconciliationPort(Protocol):
    def load_pair_facts(self, case_no: str) -> Mapping[str, Any]: ...

    def record_cooking_review(
        self, case_no: str, facts: Mapping[str, Any], issue_code: str
    ) -> None: ...

    def apply_cooking_terms(
        self, case_no: str, beclass_id: int, requires_cooking: bool
    ) -> None: ...


class HcmBeClassReconciliationRunnerPort(Protocol):
    def reconcile(self, case_no: str) -> HcmBeClassReconciliationResult: ...


class CaseImportReconciliationApplication:
    """Own the outer transaction while adapters borrow the current UoW."""

    def __init__(
        self,
        port: HcmBeClassReconciliationRunnerPort,
        unit_of_work_factory: Callable[[], UnitOfWork],
    ) -> None:
        self._port = port
        self._unit_of_work_factory = unit_of_work_factory

    def reconcile(self, case_no: str) -> HcmBeClassReconciliationResult:
        with self._unit_of_work_factory() as unit_of_work:
            result = self._port.reconcile(case_no)
            unit_of_work.commit()
            return result

def reconcile_hcm_beclass_cooking(
    port: HcmBeClassReconciliationPort, case_no: str
) -> HcmBeClassReconciliationResult:
    facts = port.load_pair_facts(case_no)
    if facts["hcm_count"] != 1 or facts["beclass_count"] != 1:
        return _unmatched_result(facts)
    try:
        requires_cooking = normalize_cooking_requirement(_survey_object(facts["survey_details"]))
    except CookingRequirementDomainError as error:
        port.record_cooking_review(case_no, facts, error.issue.value)
        return HcmBeClassReconciliationResult("cooking_review_required")
    if facts["requires_cooking"] is not None and bool(facts["requires_cooking"]) == requires_cooking:
        return HcmBeClassReconciliationResult("reconciled", requires_cooking)
    port.apply_cooking_terms(case_no, int(facts["beclass_id"]), requires_cooking)
    return HcmBeClassReconciliationResult("reconciled", requires_cooking)


def _unmatched_result(facts):
    if int(facts["hcm_count"]) > 1 or int(facts["beclass_count"]) > 1:
        return HcmBeClassReconciliationResult("identity_conflict")
    return HcmBeClassReconciliationResult("pending_counterpart")


def _survey_object(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    return parsed if isinstance(parsed, dict) else {}
__all__ = [
    "CaseImportReconciliationApplication",
    "HcmBeClassReconciliationPort",
    "HcmBeClassReconciliationRunnerPort",
    "HcmBeClassReconciliationResult",
    "reconcile_hcm_beclass_cooking",
]
