"""Typed contracts for administrative LINE identity management."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from domains.line.identities import LineUserId
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingStatus,
)
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from shared_kernel.fingerprints import PreviewFingerprint


class LineIdentityRevocationStatus(StrEnum):
    PENDING_MENU_RESET = "pending_menu_reset"
    MENU_RESET_FAILED = "menu_reset_failed"
    COMPLETED = "completed"
    MANUAL_COMPLETED = "manual_completed"


class LineIdentityCurrentFactFinding(StrEnum):
    """Deterministic findings from a zero-write root/projection readback."""

    CONSISTENT = "consistent"
    LEGAL_CUSTOMER_STAFF_DUAL_ROLE = "legal_customer_staff_dual_role"
    SAME_TYPE_MULTIPLE_ACTIVE_BINDING = "same_type_multiple_active_binding"
    ROOT_OWNER_PROJECTION_MISMATCH = "root_owner_projection_mismatch"


class LineIdentityCurrentFactReadbackStatus(StrEnum):
    COMPLETE = "complete"
    ROOT_MISSING = "root_missing"
    ROOT_PERSISTENCE_LIMITED = "root_persistence_limited"
    PROJECTION_MISSING = "projection_missing"
    PROJECTION_MULTIPLE = "projection_multiple"
    MISMATCH = "mismatch"


class LineIdentityRoleContextStatus(StrEnum):
    NO_BINDING = "no_binding"
    SINGLE_ROLE = "single_role"
    SELECTION_REQUIRED = "selection_required"
    SELECTED = "selected"
    STALE_SELECTION = "stale_selection"


@dataclass(frozen=True, slots=True)
class LineIdentityCurrentFactQuery:
    """Read-only request for the LINE-004 current identity fact."""

    line_user_id: LineUserId


@dataclass(frozen=True, slots=True)
class LineIdentityCurrentFactBinding:
    """One root or owner-projection observation, never a mutation command."""

    subject_type: LineBindingSubjectType
    subject_reference: str
    subject_name: str = "-"
    owner_line_user_id: str | None = None


@dataclass(frozen=True, slots=True)
class LineIdentityCurrentFactReadback:
    """Typed, zero-write LINE-004 diagnosis and reconciliation guidance."""

    line_user_id: str
    root_status: LineIdentityBindingStatus | None
    root_version: int | None
    root_binding: LineIdentityCurrentFactBinding | None
    owner_projections: tuple[LineIdentityCurrentFactBinding, ...]
    findings: tuple[LineIdentityCurrentFactFinding, ...]
    readback_status: LineIdentityCurrentFactReadbackStatus
    manual_actions: tuple[str, ...]
    root_bindings: tuple[LineIdentityCurrentFactBinding, ...] = ()
    dual_role_persistence_supported: bool = False

    @property
    def primary_finding(self) -> LineIdentityCurrentFactFinding:
        return self.findings[0]

    @property
    def classification(self) -> LineIdentityCurrentFactFinding:
        """Primary deterministic classification for a renderer or caller."""

        return self.primary_finding

    @property
    def is_legal_dual_role(self) -> bool:
        return LineIdentityCurrentFactFinding.LEGAL_CUSTOMER_STAFF_DUAL_ROLE in self.findings

    @property
    def has_root_owner_projection_mismatch(self) -> bool:
        return LineIdentityCurrentFactFinding.ROOT_OWNER_PROJECTION_MISMATCH in self.findings

    @property
    def is_conflict(self) -> bool:
        """Dual-role is legal, while an independently observed drift remains actionable."""

        return (
            LineIdentityCurrentFactFinding.SAME_TYPE_MULTIPLE_ACTIVE_BINDING in self.findings
            or self.has_root_owner_projection_mismatch
        )

    @property
    def suggested_manual_action(self) -> str | None:
        return self.manual_actions[0] if self.manual_actions else None

    @property
    def version(self) -> int | None:
        """Compatibility alias for consumers rendering the root aggregate version."""

        return self.root_version

    @property
    def requires_manual_action(self) -> bool:
        return bool(self.manual_actions)


@dataclass(frozen=True, slots=True)
class LineIdentityBindingListQuery:
    status: LineIdentityBindingStatus | None = LineIdentityBindingStatus.BOUND
    subject_type: LineBindingSubjectType | None = None
    search: str = ""
    page: int = 1
    page_size: int = 25


@dataclass(frozen=True, slots=True)
class LineIdentityBindingManagementView:
    line_user_id: str
    status: LineIdentityBindingStatus
    version: int
    subject_type: LineBindingSubjectType
    subject_reference: str
    subject_name: str
    updated_at: datetime | None
    revocation_request_id: int | None = None
    revocation_status: LineIdentityRevocationStatus | None = None
    revoked_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class LineIdentityBindingPage:
    items: tuple[LineIdentityBindingManagementView, ...]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class LineIdentityRoleContextReadback:
    line_user_id: LineUserId
    available_roles: tuple[LineBindingSubjectType, ...]
    selected_role: LineBindingSubjectType | None
    effective_role: LineBindingSubjectType | None
    context_version: ExpectedVersion
    status: LineIdentityRoleContextStatus


@dataclass(frozen=True, slots=True)
class LineIdentityRoleSelectionPreview:
    readback: LineIdentityRoleContextReadback
    target_role: LineBindingSubjectType
    preview_fingerprint: PreviewFingerprint
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SelectLineIdentityRoleCommand:
    line_user_id: LineUserId
    target_role: LineBindingSubjectType
    expected_context_version: ExpectedVersion
    preview_fingerprint: PreviewFingerprint
    actor: ActorContext
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class LineIdentityRoleSelectionReceipt:
    readback: LineIdentityRoleContextReadback
    replayed: bool
    receipt_identity: str


@dataclass(frozen=True, slots=True)
class LineIdentityRevocationPreview:
    binding: LineIdentityBindingManagementView
    default_menu_publication_id: int | None
    provider_menu_id: str | None
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LineIdentityReplacementPreview:
    binding: LineIdentityBindingManagementView
    target_subject_reference: str
    target_subject_name: str
    blockers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RequestLineIdentityRevocationCommand:
    line_user_id: LineUserId
    expected_version: ExpectedVersion
    actor: ActorContext
    reason: str
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class ReplaceLineIdentitySubjectCommand:
    line_user_id: LineUserId
    expected_version: ExpectedVersion
    target_subject_reference: str
    actor: ActorContext
    reason: str
    idempotency_key: IdempotencyKey
    correlation_id: CorrelationId


@dataclass(frozen=True, slots=True)
class LineIdentityRevocationRequest:
    request_id: int
    line_user_id: LineUserId
    subject_type: LineBindingSubjectType
    subject_reference: str
    status: LineIdentityRevocationStatus
    requested_binding_version: ExpectedVersion
    pending_binding_version: ExpectedVersion
    publication_id: int
    provider_menu_id: str
    requested_by_actor_id: str
    reason: str
    idempotency_key: str
    correlation_id: str
    attempt_count: int
    last_error_code: str | None
    last_error_message: str | None


__all__ = [
    "LineIdentityCurrentFactBinding",
    "LineIdentityCurrentFactFinding",
    "LineIdentityCurrentFactQuery",
    "LineIdentityCurrentFactReadback",
    "LineIdentityCurrentFactReadbackStatus",
    "LineIdentityBindingListQuery",
    "LineIdentityBindingManagementView",
    "LineIdentityBindingPage",
    "LineIdentityRoleContextReadback",
    "LineIdentityRoleContextStatus",
    "LineIdentityRoleSelectionPreview",
    "LineIdentityRoleSelectionReceipt",
    "LineIdentityRevocationPreview",
    "LineIdentityReplacementPreview",
    "LineIdentityRevocationRequest",
    "LineIdentityRevocationStatus",
    "RequestLineIdentityRevocationCommand",
    "ReplaceLineIdentitySubjectCommand",
    "SelectLineIdentityRoleCommand",
]
