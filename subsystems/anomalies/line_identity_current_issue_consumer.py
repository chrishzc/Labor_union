"""Current-only LINE-004 detector over the LINE-owned typed readback."""

from __future__ import annotations

from collections.abc import Callable

from domains.anomalies.current_issue import CurrentIssueCandidate, OwnerSnapshot
from domains.line.identity_binding import LineBindingSubjectType
from subsystems.line.identity_management_contracts import (
    LineIdentityCurrentFactFinding,
    LineIdentityCurrentFactReadback,
)


LINE_IDENTITY_OWNER_DOMAIN = "line"
LINE_IDENTITY_OWNER_ROOT_TYPE = "identity_binding"
LINE_IDENTITY_DEFINITION_CODE = "LINE-004"


class LineIdentityCurrentIssueConsumer:
    """Project actionable identity conflicts without owning LINE repair state."""

    def __init__(
        self,
        issue_key_builder: Callable[[str, dict[str, str]], str],
    ) -> None:
        self._issue_key_builder = issue_key_builder

    def detect(self, snapshot: OwnerSnapshot) -> tuple[CurrentIssueCandidate, ...]:
        scope = snapshot.scope
        if (
            scope.owner_domain != LINE_IDENTITY_OWNER_DOMAIN
            or scope.owner_root_type != LINE_IDENTITY_OWNER_ROOT_TYPE
        ):
            raise ValueError("LINE-004 owner scope is invalid")
        try:
            subject_type = LineBindingSubjectType(scope.subject_type)
        except ValueError as error:
            raise ValueError("LINE-004 subject type is invalid") from error
        if not isinstance(snapshot.facts, tuple) or not all(
            isinstance(item, LineIdentityCurrentFactReadback)
            for item in snapshot.facts
        ):
            raise TypeError("LINE-004 owner facts are invalid")

        by_line_user_id = {item.line_user_id: item for item in snapshot.facts}
        if len(by_line_user_id) != len(snapshot.facts) or set(by_line_user_id) != set(
            scope.subject_ids
        ):
            raise ValueError("LINE-004 owner facts are incomplete")

        candidates = tuple(
            candidate
            for line_user_id in scope.subject_ids
            if (
                candidate := self._candidate(
                    by_line_user_id[line_user_id], subject_type
                )
            )
            is not None
        )
        return tuple(sorted(candidates, key=lambda item: item.issue_key))

    def _candidate(
        self,
        readback: LineIdentityCurrentFactReadback,
        subject_type: LineBindingSubjectType,
    ) -> CurrentIssueCandidate | None:
        reasons: list[str] = []
        projections = tuple(
            item
            for item in readback.owner_projections
            if item.subject_type is subject_type
        )
        if len(projections) > 1:
            reasons.append(
                LineIdentityCurrentFactFinding.SAME_TYPE_MULTIPLE_ACTIVE_BINDING.value
            )
        if _role_projection_mismatch(readback, subject_type, projections):
            reasons.append(
                LineIdentityCurrentFactFinding.ROOT_OWNER_PROJECTION_MISMATCH.value
            )
        if not reasons:
            return None

        subject_identity = {
            "subject_type": subject_type.value,
            "line_user_id": readback.line_user_id,
        }
        return CurrentIssueCandidate(
            issue_key=self._issue_key_builder(
                LINE_IDENTITY_DEFINITION_CODE, subject_identity
            ),
            definition_code=LINE_IDENTITY_DEFINITION_CODE,
            owner_domain=LINE_IDENTITY_OWNER_DOMAIN,
            owner_root_type=LINE_IDENTITY_OWNER_ROOT_TYPE,
            subject_type=subject_type.value,
            subject_id=readback.line_user_id,
            owner_version=readback.root_version or 0,
            severity="warning",
            blocking=False,
            details={
                "reason_codes": tuple(sorted(set(reasons))),
                "root_condition_active": True,
            },
            subject_identity=subject_identity,
        )


def _role_projection_mismatch(
    readback: LineIdentityCurrentFactReadback,
    subject_type: LineBindingSubjectType,
    projections,
) -> bool:
    root = readback.root_binding
    if root is not None and root.subject_type is subject_type:
        return {
            (item.subject_type, item.subject_reference) for item in projections
        } != {(root.subject_type, root.subject_reference)}
    if not projections:
        return False

    # The current root can persist only one role.  A single customer and a
    # single staff projection are therefore legal even when the root records
    # the other role; that schema limitation is not LINE-004.
    counts = {
        role: sum(1 for item in readback.owner_projections if item.subject_type is role)
        for role in LineBindingSubjectType
    }
    legal_other_role = (
        root is not None
        and {root.subject_type, subject_type}
        == {LineBindingSubjectType.CUSTOMER, LineBindingSubjectType.STAFF}
        and counts[subject_type] == 1
        and counts[root.subject_type] >= 1
    )
    return not legal_other_role


__all__ = [
    "LINE_IDENTITY_DEFINITION_CODE",
    "LINE_IDENTITY_OWNER_DOMAIN",
    "LINE_IDENTITY_OWNER_ROOT_TYPE",
    "LineIdentityCurrentIssueConsumer",
]
