"""Anomalies consumer for the LINE-owned LINE-006 current-fact predicate."""

from __future__ import annotations

from collections.abc import Callable

from domains.anomalies.current_issue import CurrentIssueCandidate, OwnerSnapshot
from subsystems.line.notification_failure_current_fact import (
    LINE_NOTIFICATION_FAILURE_OWNER_DOMAIN,
    LINE_NOTIFICATION_FAILURE_OWNER_ROOT_TYPE,
    LineNotificationFailureCurrentFactReadback,
    LineNotificationFailureReason,
)


LINE_NOTIFICATION_FAILURE_DEFINITION_CODE = "LINE-006"


class LineNotificationCurrentIssueConsumer:
    def __init__(
        self, issue_key_builder: Callable[[str, dict[str, str]], str]
    ) -> None:
        self._issue_key_builder = issue_key_builder

    def detect(self, snapshot: OwnerSnapshot) -> tuple[CurrentIssueCandidate, ...]:
        scope = snapshot.scope
        if (
            scope.owner_domain != LINE_NOTIFICATION_FAILURE_OWNER_DOMAIN
            or scope.owner_root_type != LINE_NOTIFICATION_FAILURE_OWNER_ROOT_TYPE
        ):
            raise ValueError("LINE-006 owner scope is invalid")
        try:
            reason = LineNotificationFailureReason(scope.subject_type)
        except ValueError as error:
            raise ValueError("LINE-006 notification reason is invalid") from error
        if not isinstance(snapshot.facts, tuple) or not all(
            isinstance(item, LineNotificationFailureCurrentFactReadback)
            for item in snapshot.facts
        ):
            raise TypeError("LINE-006 owner facts are invalid")
        by_case = {item.case_no: item for item in snapshot.facts}
        if len(by_case) != len(snapshot.facts) or set(by_case) != set(scope.subject_ids):
            raise ValueError("LINE-006 owner facts are incomplete")

        candidates = tuple(
            candidate
            for case_no in scope.subject_ids
            if (candidate := self._candidate(by_case[case_no], reason)) is not None
        )
        return tuple(sorted(candidates, key=lambda item: item.issue_key))

    def _candidate(
        self,
        readback: LineNotificationFailureCurrentFactReadback,
        reason: LineNotificationFailureReason,
    ) -> CurrentIssueCandidate | None:
        if readback.notification_reason is not reason:
            raise ValueError("LINE-006 owner fact reason mismatch")
        if not readback.predicate_active:
            return None
        subject_identity = {
            "case_no": readback.case_no,
            "notification_reason": reason.value,
        }
        return CurrentIssueCandidate(
            issue_key=self._issue_key_builder(
                LINE_NOTIFICATION_FAILURE_DEFINITION_CODE, subject_identity
            ),
            definition_code=LINE_NOTIFICATION_FAILURE_DEFINITION_CODE,
            owner_domain=LINE_NOTIFICATION_FAILURE_OWNER_DOMAIN,
            owner_root_type=LINE_NOTIFICATION_FAILURE_OWNER_ROOT_TYPE,
            subject_type=reason.value,
            subject_id=readback.case_no,
            owner_version=readback.owner_version,
            severity="warning",
            blocking=False,
            details={
                "applicable_source_count": readback.applicable_source_count,
                "unresolved_source_count": readback.unresolved_source_count,
                "unresolved_reason_codes": tuple(
                    item.value for item in readback.unresolved_reason_codes
                ),
                "root_condition_active": True,
            },
            subject_identity=subject_identity,
        )


__all__ = [
    "LINE_NOTIFICATION_FAILURE_DEFINITION_CODE",
    "LineNotificationCurrentIssueConsumer",
]
