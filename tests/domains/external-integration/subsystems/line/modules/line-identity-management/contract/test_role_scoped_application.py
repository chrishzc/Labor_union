"""Contract tests for the single role-scoped LINE identity application surface."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

from domains.line.identities import LineIdentityFlowId, LineUserId
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingSnapshot,
    LineIdentityBindingStatus,
)
from domains.line.identity_flow import (
    LineIdentityFlowPurpose,
    LineIdentityFlowSnapshot,
    LineIdentityFlowStatus,
)
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.line.identity_management_application import (
    LineIdentityManagementApplication,
)
from subsystems.line.identity_revocation_worker import LineIdentityRevocationWorker
from subsystems.line.identity_application import (
    LineIdentityApplication,
    LineIdentityConflictError,
)
from subsystems.line.identity_contracts import (
    LineIdentityCandidate,
    LineIdentityPreviewStatus,
    StaffIdentityProof,
)
from subsystems.line.identity_management_contracts import (
    LineIdentityBindingManagementView,
    LineIdentityRevocationRequest,
    LineIdentityRevocationStatus,
    LineIdentityRoleContextStatus,
    ReplaceLineIdentitySubjectCommand,
    SelectLineIdentityRoleCommand,
)
from subsystems.line.rich_menu_binding import schedule_revocation_successor_menu
from subsystems.line.outbox_contracts import LineOutboxWorkItem
from subsystems.line.rich_menu_contracts import (
    LineRichMenuProviderOutcome,
    LineRichMenuProviderOutcomeType,
)


class _Identities:
    def __init__(self, line_user_id: LineUserId) -> None:
        self.bindings = (
            LineIdentityBindingSnapshot(
                line_user_id,
                LineIdentityBindingStatus.BOUND,
                ExpectedVersion(1),
                LineBindingSubjectType.CUSTOMER,
                "customer:7",
            ),
            LineIdentityBindingSnapshot(
                line_user_id,
                LineIdentityBindingStatus.BOUND,
                ExpectedVersion(1),
                LineBindingSubjectType.STAFF,
                "staff:8",
            ),
        )
        self.selected = None
        self.context_version = ExpectedVersion(0)

    def list_by_user(self, line_user_id):
        assert line_user_id == self.bindings[0].line_user_id
        return self.bindings

    def selected_role(self, line_user_id):
        assert line_user_id == self.bindings[0].line_user_id
        return self.selected, self.context_version

    def select_role(self, line_user_id, subject_type, expected_version):
        assert expected_version == self.context_version
        self.selected = subject_type
        self.context_version = ExpectedVersion(expected_version.value + 1)
        return self.context_version


class _AppendOnly:
    def __init__(self) -> None:
        self.items = []

    def append(self, item) -> None:
        self.items.append(item)


class _Receipts(_AppendOnly):
    def get(self, key):
        return next((item for item in self.items if item.key == key), None)


class _UnitOfWork:
    def __init__(self, identities) -> None:
        self.identities = identities
        self.receipts = _Receipts()
        self.audit = _AppendOnly()
        self.outbox = _AppendOnly()
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def commit(self) -> None:
        self.commits += 1


@pytest.mark.parametrize(
    "canonical_binding",
    [False, True],
    ids=("owner_projection", "canonical_binding"),
)
def test_staff_preview_rejects_duplicate_binding_instead_of_requesting_review(
    canonical_binding,
) -> None:
    now = datetime(2026, 9, 9, tzinfo=timezone.utc)
    requested_line_user_id = LineUserId("U-new-staff")
    existing_line_user_id = LineUserId("U-existing-staff")
    flow = LineIdentityFlowSnapshot(
        LineIdentityFlowId("flow-staff-duplicate"),
        LineIdentityFlowPurpose.STAFF_VERIFICATION,
        requested_line_user_id,
        LineIdentityFlowStatus.ACTIVE,
        now + timedelta(minutes=15),
        "staff-duplicate-flow",
    )
    existing = LineIdentityBindingSnapshot(
        existing_line_user_id,
        LineIdentityBindingStatus.BOUND,
        ExpectedVersion(1),
        LineBindingSubjectType.STAFF,
        "12",
    )
    identities = _StaffPreviewIdentities(
        existing if canonical_binding else None,
    )
    candidate = LineIdentityCandidate(
        LineBindingSubjectType.STAFF,
        "12",
        None if canonical_binding else existing_line_user_id,
    )
    unit_of_work = _PreviewUnitOfWork(flow, identities, candidate)
    application = LineIdentityApplication(lambda: unit_of_work, lambda: now)

    with pytest.raises(LineIdentityConflictError, match="此月嫂已綁定其他 LINE 帳號"):
        application.preview_staff(
            flow.flow_id,
            requested_line_user_id,
            StaffIdentityProof("王月嫂", "A123456789", date(1980, 1, 2)),
        )

    assert unit_of_work.commits == 0


def test_staff_preview_allows_fresh_binding_after_completed_revocation() -> None:
    now = datetime(2026, 9, 9, tzinfo=timezone.utc)
    line_user_id = LineUserId("U-revoked-staff")
    flow = LineIdentityFlowSnapshot(
        LineIdentityFlowId("flow-staff-rebind"),
        LineIdentityFlowPurpose.STAFF_VERIFICATION,
        line_user_id,
        LineIdentityFlowStatus.ACTIVE,
        now + timedelta(minutes=15),
        "staff-rebind-flow",
    )
    revoked = LineIdentityBindingSnapshot(
        line_user_id,
        LineIdentityBindingStatus.REVOKED,
        ExpectedVersion(3),
        LineBindingSubjectType.STAFF,
        "12",
    )
    identities = _StaffPreviewIdentities(None, revoked)
    candidate = LineIdentityCandidate(LineBindingSubjectType.STAFF, "12")
    application = LineIdentityApplication(
        lambda: _PreviewUnitOfWork(flow, identities, candidate),
        lambda: now,
    )

    preview = application.preview_staff(
        flow.flow_id,
        line_user_id,
        StaffIdentityProof("王月嫂", "A123456789", date(1980, 1, 2)),
    )

    assert preview.status is LineIdentityPreviewStatus.MATCHED
    assert preview.expected_version == ExpectedVersion(3)


def test_staff_apply_rechecks_duplicate_binding_after_preview() -> None:
    now = datetime(2026, 9, 9, tzinfo=timezone.utc)
    line_user_id = LineUserId("U-staff-race")
    flow = LineIdentityFlowSnapshot(
        LineIdentityFlowId("flow-staff-race"),
        LineIdentityFlowPurpose.STAFF_VERIFICATION,
        line_user_id,
        LineIdentityFlowStatus.ACTIVE,
        now + timedelta(minutes=15),
        "staff-race-flow",
    )
    identities = _StaffPreviewIdentities(None)
    candidate = LineIdentityCandidate(LineBindingSubjectType.STAFF, "12")
    unit_of_work = _PreviewUnitOfWork(flow, identities, candidate)
    application = LineIdentityApplication(lambda: unit_of_work, lambda: now)
    proof = StaffIdentityProof("王月嫂", "A123456789", date(1980, 1, 2))
    preview = application.preview_staff(flow.flow_id, line_user_id, proof)
    identities.subject_binding = LineIdentityBindingSnapshot(
        LineUserId("U-racing-winner"),
        LineIdentityBindingStatus.BOUND,
        ExpectedVersion(1),
        LineBindingSubjectType.STAFF,
        "12",
    )

    with pytest.raises(LineIdentityConflictError, match="此月嫂已綁定其他 LINE 帳號"):
        application.apply_staff(
            flow.flow_id,
            line_user_id,
            proof,
            preview.expected_version,
            preview.preview_fingerprint,
            CorrelationId("staff-race-apply"),
        )

    assert unit_of_work.commits == 0


class _StaffPreviewIdentities:
    def __init__(self, subject_binding, current_binding=None) -> None:
        self.subject_binding = subject_binding
        self.current_binding = current_binding

    def get(self, *_):
        return self.current_binding

    def get_by_subject(self, *_):
        return self.subject_binding


class _PreviewUnitOfWork:
    def __init__(self, flow, identities, candidate) -> None:
        self.identity_flows = SimpleNamespace(get=lambda _: flow)
        self.identities = identities
        self.candidate = candidate
        self.staff = SimpleNamespace(resolve_staff=lambda _: self.candidate)
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def commit(self) -> None:
        self.commits += 1


def test_customer_and_staff_share_one_context_and_one_selected_role_state() -> None:
    line_user_id = LineUserId("U-role-context")
    unit_of_work = _UnitOfWork(_Identities(line_user_id))
    application = LineIdentityManagementApplication(
        lambda: unit_of_work,
        lambda: datetime(2026, 8, 30, tzinfo=timezone.utc),
    )

    before = application.role_context(line_user_id)
    assert before.available_roles == (
        LineBindingSubjectType.CUSTOMER,
        LineBindingSubjectType.STAFF,
    )
    assert before.status is LineIdentityRoleContextStatus.SELECTION_REQUIRED
    assert before.effective_role is None

    preview = application.preview_role_selection(
        line_user_id,
        LineBindingSubjectType.STAFF,
    )
    command = SelectLineIdentityRoleCommand(
        line_user_id,
        LineBindingSubjectType.STAFF,
        preview.readback.context_version,
        preview.preview_fingerprint,
        ActorContext("staff:operator"),
        IdempotencyKey("select-role:u-role-context:staff"),
        CorrelationId("select-role:u-role-context"),
    )
    receipt = application.select_role(command)

    assert receipt.replayed is False
    assert receipt.readback.status is LineIdentityRoleContextStatus.SELECTED
    assert receipt.readback.effective_role is LineBindingSubjectType.STAFF
    assert len(unit_of_work.outbox.items) == 1
    assert unit_of_work.outbox.items[0].idempotency_identity == (
        "rich-menu-bind:U-role-context:staff:1"
    )

    replay = application.select_role(command)
    assert replay.replayed is True
    assert replay.receipt_identity == receipt.receipt_identity
    assert len(unit_of_work.outbox.items) == 1


def test_staff_revocation_queues_a_distinct_customer_successor_menu() -> None:
    line_user_id = LineUserId("U-role-context")
    identities = _Identities(line_user_id)
    identities.bindings = (identities.bindings[0],)
    unit_of_work = _UnitOfWork(identities)

    assert schedule_revocation_successor_menu(unit_of_work, line_user_id, 70) is True
    assert unit_of_work.outbox.items[0].idempotency_identity == (
        "rich-menu-bind:U-role-context:customer:1:revocation:70"
    )


def test_new_customer_case_replaces_only_customer_role_and_rechecks_line_004() -> None:
    line_user_id = LineUserId("U-role-context")

    class ReplacementIdentities(_Identities):
        def get(self, queried_line_user_id):
            assert queried_line_user_id == line_user_id
            return self.bindings[0]

        def replace_subject(
            self,
            claim,
            expected_version,
            actor_id,
            idempotency_key,
            correlation_id,
        ):
            assert claim.subject_type is LineBindingSubjectType.CUSTOMER
            assert claim.subject_reference == "9"
            assert expected_version == ExpectedVersion(1)
            assert actor_id == "admin:1"
            assert idempotency_key.value == "replace-customer-case:7:9"
            assert correlation_id == "replace-customer-case:7:9"
            customer = LineIdentityBindingSnapshot(
                line_user_id,
                LineIdentityBindingStatus.BOUND,
                ExpectedVersion(2),
                LineBindingSubjectType.CUSTOMER,
                "9",
            )
            self.bindings = (customer, self.bindings[1])
            return customer

    class CustomerOwner:
        def __init__(self):
            self.cleared = []
            self.bound = []

        def clear_customer(self, subject_reference, actual_line_user_id):
            self.cleared.append((subject_reference, actual_line_user_id))

        def bind_customer(
            self,
            subject_reference,
            actual_line_user_id,
            expected_current_line_user_id,
        ):
            self.bound.append(
                (
                    subject_reference,
                    actual_line_user_id,
                    expected_current_line_user_id,
                )
            )

    class StaffOwner:
        def __init__(self):
            self.calls = []

        def clear_staff(self, *args):
            self.calls.append(("clear", args))

        def bind_staff(self, *args):
            self.calls.append(("bind", args))

    class Management:
        def subject_candidate(self, subject_type, subject_reference):
            assert subject_type is LineBindingSubjectType.CUSTOMER
            assert subject_reference == "9"
            return {
                "subject_reference": "9",
                "subject_name": "新案件客戶",
                "line_user_id": line_user_id.value,
            }

        def detail(self, queried_line_user_id):
            assert queried_line_user_id == line_user_id
            return LineIdentityBindingManagementView(
                line_user_id.value,
                LineIdentityBindingStatus.BOUND,
                2,
                LineBindingSubjectType.CUSTOMER,
                "9",
                "新案件客戶",
                None,
            )

    identities = ReplacementIdentities(line_user_id)
    customer = CustomerOwner()
    staff = StaffOwner()
    unit_of_work = _UnitOfWork(identities)
    unit_of_work.identity_management = Management()
    unit_of_work.customers = customer
    unit_of_work.staff = staff
    unit_of_work.admins = object()
    application = LineIdentityManagementApplication(
        lambda: unit_of_work,
        lambda: datetime(2026, 8, 31, tzinfo=timezone.utc),
    )

    result = application.replace_subject(
        ReplaceLineIdentitySubjectCommand(
            line_user_id,
            ExpectedVersion(1),
            "9",
            ActorContext("admin:1", ("line.identity.binding.manage",)),
            "新案件取代舊案件",
            IdempotencyKey("replace-customer-case:7:9"),
            CorrelationId("replace-customer-case:7:9"),
        )
    )

    assert result.subject_reference == "9"
    assert identities.bindings[1].subject_type is LineBindingSubjectType.STAFF
    assert identities.bindings[1].subject_reference == "staff:8"
    assert customer.cleared == [("customer:7", line_user_id)]
    assert customer.bound == [("9", line_user_id, line_user_id)]
    assert staff.calls == []
    assert unit_of_work.commits == 1


def _revocation_request(status: LineIdentityRevocationStatus):
    return LineIdentityRevocationRequest(
        91,
        LineUserId("U-menu-repair"),
        LineBindingSubjectType.STAFF,
        "12",
        status,
        ExpectedVersion(1),
        ExpectedVersion(2),
        1,
        "richmenu-missing",
        "admin:1",
        "解除月嫂身分",
        "revoke:91",
        "revoke:91",
        2,
        "line_http_404",
        "richmenu not found",
    )


class _RevocationRepairManagement:
    def __init__(self, status: LineIdentityRevocationStatus) -> None:
        self.request = _revocation_request(status)
        self.retargets = []
        self.repairs = []

    def get_request(self, request_id, *, lock=False):
        assert request_id == 91
        return self.request

    def default_menu_publication(self):
        return {"id": 7, "line_rich_menu_id": "richmenu-visitor-current"}

    def retarget_menu(self, request_id, publication):
        self.retargets.append((request_id, publication))
        self.request = replace(
            self.request,
            publication_id=publication["id"],
            provider_menu_id=publication["line_rich_menu_id"],
        )
        return self.request

    def complete_manual_menu_repair(self, request_id):
        self.repairs.append(request_id)
        self.request = replace(
            self.request,
            status=LineIdentityRevocationStatus.COMPLETED,
            attempt_count=self.request.attempt_count + 1,
            last_error_code=None,
            last_error_message=None,
        )


def test_revocation_retry_retargets_latest_canonical_default_menu() -> None:
    management = _RevocationRepairManagement(
        LineIdentityRevocationStatus.MENU_RESET_FAILED
    )
    unit_of_work = _UnitOfWork(object())
    unit_of_work.identity_management = management
    application = LineIdentityManagementApplication(
        lambda: unit_of_work,
        lambda: datetime(2026, 9, 9, tzinfo=timezone.utc),
    )

    result = application.retry(
        91,
        ActorContext("admin:1", ("line.identity.binding.manage",)),
        "訪客選單已重新發布",
    )

    assert result.publication_id == 7
    assert result.provider_menu_id == "richmenu-visitor-current"
    assert management.retargets == [
        (91, {"id": 7, "line_rich_menu_id": "richmenu-visitor-current"})
    ]
    assert json.loads(unit_of_work.outbox.items[0].payload_json)[
        "provider_menu_id"
    ] == "richmenu-visitor-current"
    assert unit_of_work.commits == 1


def test_provider_success_promotes_manual_completion_after_menu_repair() -> None:
    management = _RevocationRepairManagement(
        LineIdentityRevocationStatus.MANUAL_COMPLETED
    )
    unit_of_work = _UnitOfWork(object())
    unit_of_work.identity_management = management
    application = LineIdentityManagementApplication(
        lambda: unit_of_work,
        lambda: datetime(2026, 9, 9, tzinfo=timezone.utc),
    )

    result = application.finalize(91)

    assert result.status is LineIdentityRevocationStatus.COMPLETED
    assert management.repairs == [91]
    assert unit_of_work.audit.items[0].action == "line.identity.revocation.menu_repaired"
    assert unit_of_work.commits == 1


def test_manual_menu_repair_failure_keeps_authorization_revoked_and_records_error() -> None:
    management = _RevocationRepairManagement(
        LineIdentityRevocationStatus.MANUAL_COMPLETED
    )
    failures = []
    management.mark_manual_menu_repair_failure = (
        lambda request_id, code, message: failures.append(
            (request_id, code, message)
        )
    )

    class CompletingOutbox(_AppendOnly):
        def complete(self, command):
            self.items.append(command)

    unit_of_work = _UnitOfWork(object())
    unit_of_work.identity_management = management
    unit_of_work.outbox = CompletingOutbox()
    now = datetime(2026, 9, 9, tzinfo=timezone.utc)
    provider = SimpleNamespace(
        link_to_user=lambda *_: LineRichMenuProviderOutcome(
            LineRichMenuProviderOutcomeType.REJECTED,
            error_code="line_http_404",
            error_message="richmenu not found",
        )
    )
    worker = LineIdentityRevocationWorker(
        lambda: unit_of_work,
        provider,
        "identity-worker",
        lambda: now,
    )
    item = LineOutboxWorkItem(
        7,
        "line_identity_revocation",
        "91",
        "line.identity.revocation.menu_reset",
        json.dumps(
            {
                "request_id": 91,
                "line_user_id": "U-menu-repair",
                "provider_menu_id": "richmenu-visitor-current",
            }
        ),
        0,
        3,
        "identity-worker",
        now + timedelta(minutes=1),
    )

    worker._process(item)

    assert failures == [(91, "line_http_404", "richmenu not found")]
    assert management.request.status is LineIdentityRevocationStatus.MANUAL_COMPLETED
    assert unit_of_work.outbox.items[0].retryable is False
    assert unit_of_work.commits == 1
