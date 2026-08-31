"""Compose Case Import pairing rechecks into the existing Anomalies queue."""

from domains.anomalies.current_issue import RecheckIntent, RecheckScope, build_owner_lock_key
from infrastructure.mysql.current_anomaly_issue_repository import MySqlCurrentIssueRepository
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.case_import.pairing_current_facts import (
    CASE_PAIRING_ANOMALY_OWNER_DOMAIN,
    CASE_PAIRING_ANOMALY_OWNER_ROOT_TYPE,
    CasePairingAnomalyRecheckRequest,
)


class MySqlCasePairingAnomalyRecheckSink:
    def __init__(self, connection) -> None:
        self._repository = MySqlCurrentIssueRepository(connection)

    def append_case_pairing_recheck(self, request: CasePairingAnomalyRecheckRequest) -> None:
        scope = RecheckScope(
            CASE_PAIRING_ANOMALY_OWNER_DOMAIN,
            CASE_PAIRING_ANOMALY_OWNER_ROOT_TYPE,
            request.definition_code.value,
            request.subject_ids,
            tuple(build_owner_lock_key(CASE_PAIRING_ANOMALY_OWNER_DOMAIN, CASE_PAIRING_ANOMALY_OWNER_ROOT_TYPE, root_id) for root_id in request.owner_root_ids),
        )
        fingerprint = fingerprint_payload({"definition_code": request.definition_code.value, "subject_ids": request.subject_ids, "owner_version": request.owner_version, "owner_snapshot_token": request.owner_snapshot_token})
        self._repository.append_recheck_intent(RecheckIntent(request.intent_identity, scope, request.owner_version, fingerprint))


__all__ = ["MySqlCasePairingAnomalyRecheckSink"]
