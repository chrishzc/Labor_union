"""LINE-004 consumes only the LINE-owned typed current-fact readback."""

from __future__ import annotations

from domains.anomalies.current_issue import (
    OwnerSnapshot,
    RecheckScope,
    build_issue_key,
    build_owner_lock_key,
)
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingStatus,
)
from infrastructure.mysql.line_identity_current_issue_adapter import (
    MySqlLineIdentityCurrentIssueAdapter,
)
from subsystems.anomalies.line_identity_current_issue_consumer import (
    LINE_IDENTITY_OWNER_DOMAIN,
    LINE_IDENTITY_OWNER_ROOT_TYPE,
    LineIdentityCurrentIssueConsumer,
)
from subsystems.line.identity_management_contracts import (
    LineIdentityCurrentFactBinding,
    LineIdentityCurrentFactFinding,
    LineIdentityCurrentFactReadback,
    LineIdentityCurrentFactReadbackStatus,
)


def _scope(subject_type: str = "customer") -> RecheckScope:
    return RecheckScope(
        LINE_IDENTITY_OWNER_DOMAIN,
        LINE_IDENTITY_OWNER_ROOT_TYPE,
        subject_type,
        ("U-line-1",),
        (
            build_owner_lock_key(
                LINE_IDENTITY_OWNER_DOMAIN,
                LINE_IDENTITY_OWNER_ROOT_TYPE,
                "U-line-1",
            ),
        ),
    )


def _binding(subject_type: str, reference: str) -> LineIdentityCurrentFactBinding:
    return LineIdentityCurrentFactBinding(
        LineBindingSubjectType(subject_type),
        reference,
        owner_line_user_id="U-line-1",
    )


def _readback(
    *,
    root: LineIdentityCurrentFactBinding | None,
    projections: tuple[LineIdentityCurrentFactBinding, ...],
    findings: tuple[LineIdentityCurrentFactFinding, ...],
    status: LineIdentityCurrentFactReadbackStatus,
) -> LineIdentityCurrentFactReadback:
    return LineIdentityCurrentFactReadback(
        line_user_id="U-line-1",
        root_status=(LineIdentityBindingStatus.BOUND if root else None),
        root_version=(7 if root else None),
        root_binding=root,
        owner_projections=projections,
        findings=findings,
        readback_status=status,
        manual_actions=(),
        dual_role_persistence_supported=False,
    )


def _detect(readback, subject_type: str = "customer"):
    scope = _scope(subject_type)
    snapshot = OwnerSnapshot(scope, "owner-snapshot", readback.root_version or 0, (readback,))
    consumer = LineIdentityCurrentIssueConsumer(
        lambda code, subject: build_issue_key("integration-secret", code, subject)
    )
    return consumer.detect(snapshot)


def test_legal_customer_staff_dual_role_is_not_line_004() -> None:
    root = _binding("customer", "7")
    readback = _readback(
        root=root,
        projections=(root, _binding("staff", "42")),
        findings=(
            LineIdentityCurrentFactFinding.LEGAL_CUSTOMER_STAFF_DUAL_ROLE,
            LineIdentityCurrentFactFinding.ROOT_OWNER_PROJECTION_MISMATCH,
        ),
        status=LineIdentityCurrentFactReadbackStatus.ROOT_PERSISTENCE_LIMITED,
    )

    assert _detect(readback, "customer") == ()
    assert _detect(readback, "staff") == ()


def test_same_type_multiple_active_binding_emits_closed_redacted_candidate() -> None:
    root = _binding("customer", "7")
    readback = _readback(
        root=root,
        projections=(root, _binding("customer", "8")),
        findings=(
            LineIdentityCurrentFactFinding.SAME_TYPE_MULTIPLE_ACTIVE_BINDING,
            LineIdentityCurrentFactFinding.ROOT_OWNER_PROJECTION_MISMATCH,
        ),
        status=LineIdentityCurrentFactReadbackStatus.PROJECTION_MULTIPLE,
    )

    candidate = _detect(readback)[0]

    assert candidate.definition_code == "LINE-004"
    assert candidate.subject_identity == {
        "subject_type": "customer",
        "line_user_id": "U-line-1",
    }
    assert candidate.subject_id == "U-line-1"
    assert candidate.owner_version == 7
    assert candidate.details == {
        "reason_codes": (
            "root_owner_projection_mismatch",
            "same_type_multiple_active_binding",
        ),
        "root_condition_active": True,
    }
    assert "available_actions" not in candidate.details


def test_root_projection_mismatch_emits_only_the_affected_subject_type() -> None:
    root = _binding("customer", "7")
    readback = _readback(
        root=root,
        projections=(_binding("customer", "8"),),
        findings=(LineIdentityCurrentFactFinding.ROOT_OWNER_PROJECTION_MISMATCH,),
        status=LineIdentityCurrentFactReadbackStatus.MISMATCH,
    )

    assert len(_detect(readback, "customer")) == 1
    assert _detect(readback, "staff") == ()


def test_mysql_adapter_builds_snapshot_via_typed_line_repository_contract() -> None:
    readback = _readback(
        root=_binding("customer", "7"),
        projections=(_binding("customer", "7"),),
        findings=(LineIdentityCurrentFactFinding.CONSISTENT,),
        status=LineIdentityCurrentFactReadbackStatus.COMPLETE,
    )

    class TypedRepository:
        def __init__(self) -> None:
            self.queries = []

        def current_fact(self, query):
            self.queries.append(query)
            return readback

    repository = TypedRepository()
    adapter = MySqlLineIdentityCurrentIssueAdapter(None)
    adapter._repository = repository

    first = adapter.read_owner_snapshot(_scope())
    second = adapter.read_owner_snapshot(_scope())

    assert len(repository.queries) == 2
    assert repository.queries[0].line_user_id.value == "U-line-1"
    assert first.facts == (readback,)
    assert first.snapshot_token == second.snapshot_token
    assert first.authoritative_complete is True
