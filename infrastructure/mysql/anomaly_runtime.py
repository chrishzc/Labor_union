"""MySQL composition root for the Anomalies subsystem.

This module is the outward adapter boundary.  No concrete MySQL dependency is
imported by ``subsystems.anomalies``; callers compose this runtime at the API
or operator entry point and pass it inward.
"""

from __future__ import annotations

from typing import Any

from domains.anomalies.registry import default_anomaly_registry
from infrastructure.mysql.anomaly_registry_repository import (
    AnomalyMySqlUnitOfWork,
    MySqlAnomalyRepository,
)
from infrastructure.mysql.current_anomaly_issue_repository import (
    CurrentIssueMySqlUnitOfWork,
    MySqlCurrentIssueRepository,
)
from infrastructure.mysql.hcm_resubmission_repository import MySqlHcmResubmissionRepository
from infrastructure.mysql.import_warning_auto_resolution import (
    HCM_FIELD_CORRECTION_TERMINAL_PREDICATE,
    auto_resolve_import_warning_occurrence,
    load_import_warning_review_resolution_state,
)
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.subsidy_advance_recovery_repository import MySqlSubsidyAdvanceRecoveryRepository
from subsystems.anomalies.alert_workflow import AnomalyApplication
from subsystems.anomalies.ports import AnomalyRuntime
from subsystems.anomalies.current_issue_recheck import CurrentIssueApplication
from domains.anomalies.current_issue import (
    RecheckScope,
    build_issue_key,
)


class MySqlAnomalyRuntime:
    """Concrete adapter bundle for one process's anomaly worker cycle."""

    hcm_field_correction_terminal_predicate = HCM_FIELD_CORRECTION_TERMINAL_PREDICATE

    def __init__(self, *, issue_identity_secret: str | bytes | None = None,
                 owner_snapshot_reader=None, current_issue_detectors=None) -> None:
        # The secret is process configuration only.  It is never passed to a
        # repository, serialized into a job, or included in a receipt.
        self._issue_identity_secret = issue_identity_secret
        self._owner_snapshot_reader = owner_snapshot_reader
        self._current_issue_detectors = dict(current_issue_detectors or {})

    def connection(self):
        return get_connection()

    def anomaly_repository(self, connection):
        return MySqlAnomalyRepository(connection)

    def failure_unit_of_work(self, connection):
        return AnomalyMySqlUnitOfWork(connection)

    def anomaly_application(self, connection):
        from subsystems.anomalies.alert_workflow import AnomalyApplication

        return AnomalyApplication(
            default_anomaly_registry(),
            self.anomaly_repository(connection),
            lambda: AnomalyMySqlUnitOfWork(connection),
        )

    def current_issue_repository(self, connection, *, owner_snapshot_reader=None):
        return MySqlCurrentIssueRepository(
            connection,
            owner_snapshot_reader=owner_snapshot_reader or self._owner_snapshot_reader,
        )

    def current_issue_key(self, definition_code, subject_identity) -> str:
        if self._issue_identity_secret is None:
            raise RuntimeError("anomaly issue identity secret not composed")
        return build_issue_key(
            self._issue_identity_secret, definition_code, subject_identity
        )

    def current_issue_application(self, connection, *, owner_snapshot_reader=None):
        repository = self.current_issue_repository(
            connection, owner_snapshot_reader=owner_snapshot_reader
        )
        return CurrentIssueApplication(
            repository,
            lambda: CurrentIssueMySqlUnitOfWork(connection),
        )

    def run_current_issue_recheck(self, connection, payload):
        """Run a typed queued recheck only when owner composition is present."""
        from subsystems.anomalies.current_issue_recheck import (
            recheck_intent_from_payload,
            scope_from_payload,
        )

        scope = scope_from_payload(payload)
        detector = self._current_issue_detectors.get(
            (scope.owner_domain, scope.owner_root_type, scope.subject_type)
        )
        owner_snapshot_reader = self._owner_snapshot_reader
        if detector is None:
            from infrastructure.mysql.line_notification_current_issue_adapter import (
                MySqlLineNotificationCurrentIssueAdapter,
            )
            from subsystems.anomalies.line_notification_current_issue_consumer import (
                LineNotificationCurrentIssueConsumer,
            )
            from subsystems.line.notification_failure_current_fact import (
                LINE_NOTIFICATION_FAILURE_OWNER_DOMAIN,
                LINE_NOTIFICATION_FAILURE_OWNER_ROOT_TYPE,
            )

            if (
                scope.owner_domain == LINE_NOTIFICATION_FAILURE_OWNER_DOMAIN
                and scope.owner_root_type
                == LINE_NOTIFICATION_FAILURE_OWNER_ROOT_TYPE
            ):
                adapter = MySqlLineNotificationCurrentIssueAdapter(connection)
                owner_snapshot_reader = adapter.read_owner_snapshot
                detector = LineNotificationCurrentIssueConsumer(
                    self.current_issue_key
                ).detect
        if detector is None:
            raise RuntimeError("anomaly_recheck_owner_detector_not_composed")
        intent = recheck_intent_from_payload(payload)
        result = self.current_issue_application(
            connection, owner_snapshot_reader=owner_snapshot_reader
        ).reconcile(
            scope, detector, completed_intent=intent
        )
        return {
            "present_issue_keys": list(result.present_issue_keys),
            "deleted_issue_keys": list(result.deleted_issue_keys),
            "owner_snapshot_token": result.owner_snapshot_token,
        }

    def hcm_resubmission_repository(self, connection):
        return MySqlHcmResubmissionRepository(connection)

    def subsidy_advance_recovery_repository(self, connection):
        return MySqlSubsidyAdvanceRecoveryRepository(connection)

    def auto_resolve_import_warning_occurrence(self, connection, **kwargs):
        return auto_resolve_import_warning_occurrence(connection, **kwargs)

    def load_import_warning_review_resolution_state(self, connection, **kwargs):
        return load_import_warning_review_resolution_state(connection, **kwargs)


def build_anomaly_runtime(
    *, issue_identity_secret: str | bytes | None = None
) -> AnomalyRuntime:
    return MySqlAnomalyRuntime(issue_identity_secret=issue_identity_secret)


__all__ = ["MySqlAnomalyRuntime", "build_anomaly_runtime"]
