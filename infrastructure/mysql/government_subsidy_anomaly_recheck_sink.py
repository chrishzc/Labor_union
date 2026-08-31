"""Compose owner recheck requests into the existing Anomalies queue."""

from __future__ import annotations

from domains.anomalies.current_issue import RecheckIntent, RecheckScope, build_owner_lock_key
from infrastructure.mysql.current_anomaly_issue_repository import MySqlCurrentIssueRepository
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.government_subsidy.current_anomaly_facts import (
    GOVERNMENT_SUBSIDY_ANOMALY_OWNER_DOMAIN,
    GOVERNMENT_SUBSIDY_ANOMALY_OWNER_ROOT_TYPE,
    GovernmentSubsidyAnomalyRecheckRequest,
    GovernmentSubsidyCurrentIssueCode,
    GovernmentSubsidyOverpaymentRecheckRequest,
)


class MySqlGovernmentSubsidyAnomalyRecheckSink:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._repository = MySqlCurrentIssueRepository(connection)

    def append_government_subsidy_recheck(self, request: GovernmentSubsidyAnomalyRecheckRequest) -> None:
        scope = RecheckScope(
            GOVERNMENT_SUBSIDY_ANOMALY_OWNER_DOMAIN,
            GOVERNMENT_SUBSIDY_ANOMALY_OWNER_ROOT_TYPE,
            request.definition_code.value,
            request.subject_ids,
            tuple(build_owner_lock_key(GOVERNMENT_SUBSIDY_ANOMALY_OWNER_DOMAIN, GOVERNMENT_SUBSIDY_ANOMALY_OWNER_ROOT_TYPE, root_id) for root_id in request.owner_root_ids),
        )
        fingerprint = fingerprint_payload({"definition_code": request.definition_code.value, "subject_ids": request.subject_ids, "owner_version": request.owner_version, "owner_snapshot_token": request.owner_snapshot_token})
        self._repository.append_recheck_intent(RecheckIntent(request.intent_identity, scope, request.owner_version, fingerprint))

    def append_government_subsidy_overpayment_rechecks(
        self, request: GovernmentSubsidyOverpaymentRecheckRequest
    ) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(_OVERPAYMENT_SOURCE_SQL, (request.overpayment_identity,))
            row = cursor.fetchone()
        if not isinstance(row, dict):
            raise RuntimeError("government_subsidy_overpayment_source_unavailable")
        bank = str(row["bank_fact_identity"])
        batch_id = int(row["batch_id"])
        roots = tuple(sorted(("bank:" + bank, "batch:" + str(batch_id))))
        for code, subject in (
            (GovernmentSubsidyCurrentIssueCode.RECEIPT_UNMATCHED, bank),
            (GovernmentSubsidyCurrentIssueCode.RECEIPT_ALLOCATION_AMBIGUOUS, bank + ":" + str(batch_id)),
        ):
            self.append_government_subsidy_recheck(
                GovernmentSubsidyAnomalyRecheckRequest(
                    code,
                    (subject,),
                    roots,
                    request.owner_version,
                    request.owner_snapshot_token,
                    request.intent_identity + ":" + code.value,
                )
            )


_OVERPAYMENT_SOURCE_SQL = (
    "SELECT bank.dedup_fingerprint AS bank_fact_identity,transaction.claim_batch_id AS batch_id "
    "FROM government_subsidy_overpayments overpayment "
    "JOIN government_subsidy_transactions transaction ON transaction.id=overpayment.source_transaction_id "
    "JOIN finance_import_rows bank ON bank.id=transaction.finance_import_row_id "
    "WHERE overpayment.overpayment_identity=%s"
)


__all__ = ["MySqlGovernmentSubsidyAnomalyRecheckSink"]
