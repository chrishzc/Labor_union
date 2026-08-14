"""
File: hcm_beclass_reconciliation.py
Description: 依 fresh HCM／BeClass 配對，以 typed Orders command補入下廚需求。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import json

from domains.case_import.cooking_requirement import CookingRequirementDomainError, normalize_cooking_requirement
from domains.case_import.beclass_import_review import BeClassImportSourceKind
from infrastructure.mysql.order_terms_repository import MySqlOrderTermsRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.clock import SystemBusinessClock
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.case_import.beclass_review_intake import (
    masked_review_identifier,
    record_invalid_beclass_row,
)
from subsystems.orders.terms_workflow import OrderTermsApplyRequest, OrderTermsWorkflow


@dataclass(frozen=True, slots=True)
class HcmBeClassReconciliationResult:
    status: str
    requires_cooking: bool | None = None


def reconcile_hcm_beclass_cooking(connection, case_no: str) -> HcmBeClassReconciliationResult:
    facts = _load_pair_facts(connection, case_no)
    if facts["hcm_count"] != 1 or facts["beclass_count"] != 1:
        return _unmatched_result(facts)
    try:
        requires_cooking = normalize_cooking_requirement(_survey_object(facts["survey_details"]))
    except CookingRequirementDomainError:
        _record_cooking_review(connection, case_no, facts)
        return HcmBeClassReconciliationResult("cooking_review_required")
    if facts["requires_cooking"] is not None and bool(facts["requires_cooking"]) == requires_cooking:
        return HcmBeClassReconciliationResult("reconciled", requires_cooking)
    _apply_cooking_terms(connection, case_no, int(facts["beclass_id"]), requires_cooking)
    return HcmBeClassReconciliationResult("reconciled", requires_cooking)


def _load_pair_facts(connection, case_no):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT (SELECT COUNT(*) FROM orders WHERE case_no=%s) AS hcm_count,"
            "(SELECT COUNT(*) FROM beclass_records WHERE bound_case_no=%s "
            "OR (bound_case_no IS NULL AND query_no=%s)) AS beclass_count",
            (case_no, case_no, case_no),
        )
        counts = cursor.fetchone()
        if int(counts["hcm_count"]) != 1 or int(counts["beclass_count"]) != 1:
            return counts
        cursor.execute(
            "SELECT o.requires_cooking,b.id AS beclass_id,b.survey_details "
            "FROM orders o JOIN beclass_records b ON (b.bound_case_no=o.case_no "
            "OR (b.bound_case_no IS NULL AND b.query_no=o.case_no)) WHERE o.case_no=%s",
            (case_no,),
        )
        return {**counts, **cursor.fetchone()}


def _unmatched_result(facts):
    if int(facts["hcm_count"]) > 1 or int(facts["beclass_count"]) > 1:
        return HcmBeClassReconciliationResult("identity_conflict")
    return HcmBeClassReconciliationResult("pending_counterpart")


def _record_cooking_review(connection, case_no, facts):
    beclass_id = int(facts["beclass_id"])
    digest = fingerprint_payload(
        {"beclass_id": beclass_id, "survey_details": _survey_object(facts["survey_details"])}
    ).value
    with MySqlUnitOfWork(connection) as unit_of_work:
        record_invalid_beclass_row(
            connection,
            source_kind=BeClassImportSourceKind.CLIENT,
            source_content_digest=digest,
            source_sheet="case-import-reconciliation",
            source_row=beclass_id,
            masked_identifier=masked_review_identifier(
                BeClassImportSourceKind.CLIENT, case_no, beclass_id
            ),
            source_payload={
                "beclass_record_id": beclass_id,
                "case_no_present": True,
                "cooking_answer_state": "ambiguous",
            },
            issue_codes=("case_import_cooking_requirement_ambiguous",),
        )
        unit_of_work.commit()


def _survey_object(value):
    parsed = json.loads(value) if isinstance(value, str) else value
    return parsed if isinstance(parsed, dict) else {}


def _apply_cooking_terms(connection, case_no, beclass_id, requires_cooking):
    repository = MySqlOrderTermsRepository(connection)
    workflow = OrderTermsWorkflow(
        repository,
        lambda: MySqlUnitOfWork(connection),
        SystemBusinessClock(),
    )
    current = workflow.preview(case_no, _proposed_terms(repository, case_no, requires_cooking))
    identity = fingerprint_payload(
        {"beclass_id": beclass_id, "case_no": case_no, "requires_cooking": requires_cooking}
    ).value
    workflow.apply(
        OrderTermsApplyRequest(
            case_no,
            current.after,
            ExpectedVersion(current.order_version),
            ExpectedVersion(current.scheduling_version),
            ExpectedVersion(current.client_finance_version),
            ExpectedVersion(current.payroll_version),
            current.fingerprint,
            IdempotencyKey(f"case-import-cooking:{identity}"),
            ActorContext("case-import-reconciliation"),
            "Reconcile uniquely paired Client BeClass cooking requirement.",
            CorrelationId(f"case-import-cooking:{identity}"),
        )
    )


def _proposed_terms(repository, case_no, requires_cooking):
    facts = repository.load_for_preview(case_no)
    return replace(facts.order.terms, requires_cooking=requires_cooking)


__all__ = ["HcmBeClassReconciliationResult", "reconcile_hcm_beclass_cooking"]
