"""Compose LINE-006 owner readbacks into an Anomalies owner snapshot."""

from __future__ import annotations

from domains.anomalies.current_issue import OwnerSnapshot, RecheckScope
from infrastructure.mysql.line_notification_repository import (
    MySqlLineNotificationRepository,
)
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.line.notification_failure_current_fact import (
    LINE_NOTIFICATION_FAILURE_OWNER_DOMAIN,
    LINE_NOTIFICATION_FAILURE_OWNER_ROOT_TYPE,
    LineNotificationFailureCurrentFactQuery,
    LineNotificationFailureReason,
)


class MySqlLineNotificationCurrentIssueAdapter:
    """Read only through the LINE Integration typed current-fact contract."""

    def __init__(self, connection) -> None:
        self._repository = MySqlLineNotificationRepository(connection)

    def read_owner_snapshot(self, scope: RecheckScope) -> OwnerSnapshot:
        if (
            scope.owner_domain != LINE_NOTIFICATION_FAILURE_OWNER_DOMAIN
            or scope.owner_root_type != LINE_NOTIFICATION_FAILURE_OWNER_ROOT_TYPE
        ):
            raise ValueError("LINE-006 owner scope is invalid")
        try:
            reason = LineNotificationFailureReason(scope.subject_type)
        except ValueError as error:
            raise ValueError("LINE-006 notification reason is invalid") from error
        readbacks = tuple(
            self._repository.current_failure_fact(
                LineNotificationFailureCurrentFactQuery(case_no, reason)
            )
            for case_no in scope.subject_ids
        )
        snapshot_token = fingerprint_payload(
            {
                "readbacks": [
                    {
                        "case_no": item.case_no,
                        "notification_reason": item.notification_reason.value,
                        "owner_snapshot_token": item.owner_snapshot_token,
                        "authoritative_complete": item.authoritative_complete,
                    }
                    for item in readbacks
                ]
            }
        ).value
        return OwnerSnapshot(
            scope=scope,
            snapshot_token=snapshot_token,
            owner_version=max((item.owner_version for item in readbacks), default=0),
            facts=readbacks,
            authoritative_complete=all(
                item.authoritative_complete for item in readbacks
            ),
        )


__all__ = ["MySqlLineNotificationCurrentIssueAdapter"]
