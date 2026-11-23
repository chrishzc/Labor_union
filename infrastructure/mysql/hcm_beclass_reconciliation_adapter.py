"""
File: hcm_beclass_reconciliation_adapter.py
Description: 以同一 MySQL 工作單元提供 HCM／BeClass 配對與 Orders 條款補正 port。
"""

from __future__ import annotations

from domains.case_import.beclass_import_review import BeClassImportSourceKind
from infrastructure.mysql.order_terms_repository import MySqlOrderTermsRepository
from infrastructure.mysql.beclass_import_review_repository import MySqlBeClassImportReviewRepository
from shared_kernel.clock import SystemBusinessClock
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import (
    CorrelationId,
    ExpectedVersion,
)
from subsystems.case_import.beclass_review_intake import (
    canonical_review_identifier,
    record_invalid_beclass_row,
)
from subsystems.case_import.hcm_beclass_reconciliation import (
    reconcile_hcm_beclass_cooking as reconcile_with_port,
)
from subsystems.orders.terms_workflow import (
    OrderCookingRequirementCorrectionRequest,
    OrderTermsWorkflow,
)


def _nested_uow_forbidden():
    raise RuntimeError("hcm_reconciliation_requires_caller_owned_uow")


class MySqlHcmBeClassReconciliationAdapter:
    def __init__(self, connection, pairing_rechecks=None) -> None:
        self._connection = connection
        self._pairing_rechecks = pairing_rechecks

    def reconcile(self, case_no: str):
        return reconcile_with_port(self, case_no)

    def load_pair_facts(self, case_no: str):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT (SELECT COUNT(*) FROM orders WHERE case_no=%s) AS hcm_count,"
                "(SELECT lifecycle_version FROM orders WHERE case_no=%s) AS hcm_version,"
                "(SELECT COUNT(*) FROM beclass_records "
                "WHERE bound_case_no=%s) AS beclass_count",
                (case_no, case_no, case_no),
            )
            counts = cursor.fetchone()
            if int(counts["hcm_count"]) != 1 or int(counts["beclass_count"]) != 1:
                return counts
            cursor.execute(
                "SELECT o.requires_cooking,b.id AS beclass_id,b.query_no,b.survey_details "
                "FROM orders o JOIN beclass_records b "
                "ON b.bound_case_no=o.case_no WHERE o.case_no=%s",
                (case_no,),
            )
            return {**counts, **cursor.fetchone()}

    def record_cooking_review(self, case_no, facts, issue_code) -> None:
        beclass_id = int(facts["beclass_id"])
        digest = fingerprint_payload(
            {"beclass_id": beclass_id, "survey_details": facts["survey_details"]}
        ).value
        record_invalid_beclass_row(
            self._connection,
            source_kind=BeClassImportSourceKind.CLIENT,
            source_content_digest=digest,
            source_sheet="case-import-reconciliation",
            source_row=beclass_id,
            identifier=canonical_review_identifier(
                BeClassImportSourceKind.CLIENT, case_no, beclass_id
            ),
            source_payload={
                "beclass_record_id": beclass_id,
                "case_no_present": True,
                "cooking_answer_state": issue_code,
            },
            issue_codes=("case_import_cooking_requirement_ambiguous",),
            repository=MySqlBeClassImportReviewRepository(self._connection),
        )

    def apply_cooking_terms(
        self, case_no: str, beclass_id: int, requires_cooking: bool
    ) -> None:
        repository = MySqlOrderTermsRepository(self._connection)
        cooking_facts = repository.load_cooking_requirement(case_no, for_update=True)
        if cooking_facts.requires_cooking is not None:
            return
        workflow = OrderTermsWorkflow(
            repository,
            _nested_uow_forbidden,
            SystemBusinessClock(),
        )
        workflow.correct_cooking_requirement_in_current_uow(
            OrderCookingRequirementCorrectionRequest(
                case_no, requires_cooking, ExpectedVersion(cooking_facts.version),
                CorrelationId(f"case-import-cooking:{beclass_id}"),
            )
        )


__all__ = [
    "MySqlHcmBeClassReconciliationAdapter",
]
