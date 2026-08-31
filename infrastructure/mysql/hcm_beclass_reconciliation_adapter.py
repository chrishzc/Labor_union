"""
File: hcm_beclass_reconciliation_adapter.py
Description: 以同一 MySQL 工作單元提供 HCM／BeClass 配對與 Orders 條款補正 port。
"""

from __future__ import annotations

from dataclasses import replace

from domains.case_import.beclass_import_review import BeClassImportSourceKind
from infrastructure.mysql.order_terms_repository import MySqlOrderTermsRepository
from infrastructure.mysql.beclass_import_review_repository import MySqlBeClassImportReviewRepository
from shared_kernel.clock import SystemBusinessClock
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.case_import.beclass_review_intake import (
    masked_review_identifier,
    record_invalid_beclass_row,
)
from subsystems.case_import.hcm_beclass_reconciliation import (
    reconcile_hcm_beclass_cooking as reconcile_with_port,
)
from subsystems.case_import.pairing_current_facts import (
    beclass_counterpart_recheck,
    hcm_counterpart_recheck,
)
from subsystems.orders.terms_workflow import (
    OrderTermsApplyRequest,
    OrderTermsWorkflow,
)


def _nested_uow_forbidden():
    raise RuntimeError("hcm_reconciliation_requires_caller_owned_uow")


class MySqlHcmBeClassReconciliationAdapter:
    def __init__(self, connection, pairing_rechecks=None) -> None:
        self._connection = connection
        self._pairing_rechecks = pairing_rechecks

    def reconcile(self, case_no: str):
        result = reconcile_with_port(self, case_no)
        if self._pairing_rechecks is not None:
            facts = self.load_pair_facts(case_no)
            token = fingerprint_payload({"case_no": case_no, "facts": dict(facts)}).value
            version = max(int(facts.get("beclass_id") or 0), int(facts.get("hcm_version") or 0))
            self._pairing_rechecks.append_case_pairing_recheck(
                hcm_counterpart_recheck(
                    case_no,
                    version,
                    token,
                    "case-pairing:" + token + ":BECLASS-001",
                )
            )
            query_no = facts.get("query_no")
            if isinstance(query_no, str) and query_no:
                review_item_id = "counterpart:" + query_no
                self._pairing_rechecks.append_case_pairing_recheck(
                    beclass_counterpart_recheck(
                        "client_counterpart",
                        review_item_id,
                        version,
                        token,
                        "case-pairing:" + token + ":IMPORT-003",
                    )
                )
        return result

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
            masked_identifier=masked_review_identifier(
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
        workflow = OrderTermsWorkflow(
            repository,
            _nested_uow_forbidden,
            SystemBusinessClock(),
        )
        proposed_terms = replace(
            repository.load_for_preview(case_no).order.terms,
            requires_cooking=requires_cooking,
        )
        preview = workflow.preview(case_no, proposed_terms)
        identity = fingerprint_payload(
            {
                "beclass_id": beclass_id,
                "case_no": case_no,
                "requires_cooking": requires_cooking,
            }
        ).value
        workflow.apply_in_current_uow(
            OrderTermsApplyRequest(
                case_no,
                preview.after,
                ExpectedVersion(preview.order_version),
                ExpectedVersion(preview.scheduling_version),
                ExpectedVersion(preview.client_finance_version),
                ExpectedVersion(preview.payroll_version),
                preview.fingerprint,
                IdempotencyKey(f"case-import-cooking:{identity}"),
                ActorContext("case-import-reconciliation"),
                "Reconcile uniquely paired Client BeClass cooking requirement.",
                CorrelationId(f"case-import-cooking:{identity}"),
            )
        )


__all__ = [
    "MySqlHcmBeClassReconciliationAdapter",
]
