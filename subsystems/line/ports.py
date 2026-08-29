"""
File: ports.py
Description: 定義 LINE repository、Rich Menu 媒體查詢、durable step、cleanup 與 provider typed ports。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from domains.line.configuration import (
    LineConfigurationKind,
    LineConfigurationSnapshot,
)
from domains.line.delivery import (
    LineDeliveryRequest,
    LineDeliveryTaskSnapshot,
)
from domains.line.identities import (
    LineConfigurationRevision,
    LineDeliveryTaskId,
    LineIdentityFlowId,
    LineRichMenuPublicationId,
    LineReviewRequestId,
    LineUserId,
    LineWebhookEventId,
)
from domains.line.identity_binding import (
    LineBindingSubjectType,
    LineIdentityBindingSnapshot,
    LineIdentityClaim,
)
from domains.line.identity_flow import (
    LineIdentityFlowPurpose,
    LineIdentityFlowSnapshot,
)
from domains.line.media import LineMediaMetadata
from domains.line.media_asset import RichMenuMediaAsset
from domains.line.order_group import LineOrderGroupBindingSnapshot
from domains.line.review import LineReviewDecisionCandidate, LineReviewSnapshot
from domains.line.platform_user import LineFriendEvent, LinePlatformUserSnapshot
from domains.line.rich_menu import (
    LineRichMenuPublicationSnapshot,
    LineRichMenuPublicationStatus,
)
from domains.line.webhook import (
    CanonicalLineWebhookEvent,
    LineWebhookInboxSnapshot,
    LineWebhookProcessingStatus,
)
from shared_kernel.clock import BusinessClock
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
    IdempotencyReceipt,
)
from shared_kernel.ports import OutboxWriter, UnitOfWork
from shared_kernel.validation import (
    require_canonical_text,
    require_nonnegative_integer,
    require_positive_integer,
)
from subsystems.line.configuration_contracts import (
    ApplyLineConfigurationCommand,
    ApplyLineConfigurationResult,
)
from subsystems.line.delivery_contracts import (
    CancelLineDeliveryTaskCommand,
    ClaimLineDeliveryTasksQuery,
    EnqueueLineDeliveryResult,
    LineProviderOutcome,
    RecordLineDeliveryAttemptCommand,
    RecordLineDeliveryAttemptResult,
)
from subsystems.line.delivery_admin_contracts import (
    LineDeliveryAdminPage,
    LineDeliveryAdminQuery,
    LineDeliveryAdminRecord,
    LineDeliveryAttemptRecord,
)
from subsystems.line.identity_contracts import (
    AdminCredentialProof,
    CustomerIdentityProof,
    LineIdentityCandidate,
    OpenLineIdentityFlowCommand,
    OpenLineIdentityFlowResult,
    StaffIdentityProof,
    VerifiedLiffIdentity,
)
from subsystems.line.media_contracts import (
    ArchiveLineMediaResult,
    LineMediaDownload,
)
from subsystems.line.media_asset_contracts import (
    RichMenuMediaAssetDetailQuery,
    RichMenuMediaAssetListQuery,
    RichMenuMediaAssetPage,
)
from subsystems.line.outbox_contracts import (
    ClaimLineOutboxQuery,
    CompleteLineOutboxCommand,
    LineOutboxWorkItem,
)
from subsystems.line.order_group_contracts import (
    BindLineOrderGroupCommand,
    BindLineOrderGroupResult,
    LineOrderGroupEventPage,
    LineOrderGroupEventRecord,
    LineOrderGroupNumberedPage,
    LineOrderGroupPage,
    LinkedLineAdmin,
    OrderLineAudience,
)
from subsystems.line.review_contracts import (
    CreateLineReviewCommand,
    CreateLineReviewResult,
    DecideLineReviewCommand,
    DecideLineReviewResult,
    LineReviewListQuery,
    LineReviewPage,
    LineReviewQueueSummary,
)
from subsystems.line.rich_menu_contracts import (
    ClaimLineRichMenuPublicationsQuery,
    LineRichMenuProviderOutcome,
    LineRichMenuProviderRequest,
    LineRichMenuPublicationQuery,
    LineRichMenuPublicationWorkItem,
    QueueLineRichMenuPublicationCommand,
    QueueLineRichMenuPublicationResult,
    RecordLineRichMenuPublicationCommand,
    RetryLineRichMenuPublicationCommand,
)
from subsystems.line.runtime_contracts import (
    LineWebhookSecurityReceipt,
    LineWorkerHeartbeat,
)
from subsystems.line.webhook_contracts import AcceptLineWebhookEventResult
from subsystems.line.webhook_contracts import (
    ClaimLineWebhookEventsQuery,
    CompleteLineWebhookEventCommand,
)

_AUDIT_IDENTITY_MAXIMUM_LENGTH = 191


@dataclass(frozen=True, slots=True)
class LineAuditIntent:
    action: str
    actor_id: str
    aggregate_type: str
    aggregate_identity: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("action", self.action),
            ("actor ID", self.actor_id),
            ("aggregate type", self.aggregate_type),
            ("aggregate identity", self.aggregate_identity),
        ):
            require_canonical_text(
                value,
                f"LINE audit {field_name}",
                _AUDIT_IDENTITY_MAXIMUM_LENGTH,
            )


@dataclass(frozen=True, slots=True)
class LineNotificationCancellationLineage:
    intent_ids: tuple[int, ...]
    task_ids: tuple[LineDeliveryTaskId, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.intent_ids, tuple):
            raise TypeError("LINE notification intent IDs must be a tuple")
        for intent_id in self.intent_ids:
            require_positive_integer(intent_id, "LINE notification intent ID")
        if self.intent_ids != tuple(sorted(set(self.intent_ids))):
            raise ValueError("LINE notification intent IDs must be sorted and unique")
        if not isinstance(self.task_ids, tuple) or any(
            not isinstance(task_id, LineDeliveryTaskId) for task_id in self.task_ids
        ):
            raise TypeError("LINE notification task IDs must be a typed tuple")
        values = tuple(task_id.value for task_id in self.task_ids)
        if values != tuple(sorted(set(values))):
            raise ValueError("LINE notification task IDs must be sorted and unique")


class LineRichMenuPublicationStep(StrEnum):
    CREATE = "create"
    UPLOAD = "upload"
    LINK = "link"
    SWITCH = "switch"
    CLEANUP = "cleanup"


@dataclass(frozen=True, slots=True)
class LineRichMenuStepReceipt:
    publication_id: LineRichMenuPublicationId
    step: LineRichMenuPublicationStep
    request_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    acknowledged_at: datetime
    provider_menu_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.publication_id, LineRichMenuPublicationId):
            raise TypeError("LINE Rich Menu publication ID is invalid")
        if not isinstance(self.step, LineRichMenuPublicationStep):
            raise TypeError("LINE Rich Menu publication step is invalid")
        if not isinstance(self.request_fingerprint, PreviewFingerprint):
            raise TypeError("LINE Rich Menu step fingerprint is invalid")
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise TypeError("LINE Rich Menu step idempotency key is invalid")
        if self.acknowledged_at.tzinfo is None or self.acknowledged_at.utcoffset() is None:
            raise ValueError("LINE Rich Menu step acknowledgement must be timezone-aware")
        if self.provider_menu_id is not None:
            require_canonical_text(
                self.provider_menu_id,
                "LINE provider Rich Menu ID",
                191,
            )


class LineRichMenuStepAttemptOutcome(StrEnum):
    SUCCESS = "success"
    RATE_LIMITED = "rate_limited"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    LOST_ACK = "lost_ack"


@dataclass(frozen=True, slots=True)
class LineRichMenuStepAttemptEvent:
    publication_id: LineRichMenuPublicationId
    step: LineRichMenuPublicationStep
    attempt_number: int
    request_fingerprint: PreviewFingerprint
    idempotency_key: IdempotencyKey
    outcome: LineRichMenuStepAttemptOutcome
    attempted_at: datetime
    correlation_id: CorrelationId
    provider_menu_id: str | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.publication_id, LineRichMenuPublicationId):
            raise TypeError("LINE Rich Menu publication ID is invalid")
        if not isinstance(self.step, LineRichMenuPublicationStep):
            raise TypeError("LINE Rich Menu publication step is invalid")
        require_positive_integer(
            self.attempt_number,
            "LINE Rich Menu step attempt number",
        )
        if not isinstance(self.request_fingerprint, PreviewFingerprint):
            raise TypeError("LINE Rich Menu step attempt fingerprint is invalid")
        if not isinstance(self.idempotency_key, IdempotencyKey):
            raise TypeError("LINE Rich Menu step attempt idempotency key is invalid")
        if not isinstance(self.outcome, LineRichMenuStepAttemptOutcome):
            raise TypeError("LINE Rich Menu step attempt outcome is invalid")
        if self.attempted_at.tzinfo is None or self.attempted_at.utcoffset() is None:
            raise ValueError("LINE Rich Menu step attempt time must be timezone-aware")
        if not isinstance(self.correlation_id, CorrelationId):
            raise TypeError("LINE Rich Menu step attempt correlation ID is invalid")
        if self.outcome is LineRichMenuStepAttemptOutcome.SUCCESS:
            require_canonical_text(
                self.provider_menu_id,
                "LINE provider Rich Menu ID",
                191,
            )
            if self.error_code is not None:
                raise ValueError("successful Rich Menu attempt cannot contain an error")
        else:
            if self.provider_menu_id is not None:
                raise ValueError("failed Rich Menu attempt cannot contain provider menu ID")
            require_canonical_text(
                self.error_code,
                "LINE Rich Menu step attempt error code",
                191,
            )


@dataclass(frozen=True, slots=True)
class LineRichMenuCleanupAnomaly:
    publication_id: LineRichMenuPublicationId
    error_code: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.publication_id, LineRichMenuPublicationId):
            raise TypeError("LINE Rich Menu publication ID is invalid")
        require_canonical_text(self.error_code, "LINE Rich Menu cleanup error code", 191)
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("LINE Rich Menu cleanup anomaly time must be timezone-aware")


@dataclass(frozen=True, slots=True)
class LineRichMenuPublicationPage:
    items: tuple[LineRichMenuPublicationSnapshot, ...]
    total: int
    offset: int
    page_size: int

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple) or any(
            not isinstance(item, LineRichMenuPublicationSnapshot)
            for item in self.items
        ):
            raise TypeError("LINE Rich Menu publication page items are invalid")
        require_nonnegative_integer(self.total, "LINE Rich Menu publication total")
        require_nonnegative_integer(self.offset, "LINE Rich Menu publication offset")
        require_positive_integer(self.page_size, "LINE Rich Menu publication page size")
        if self.page_size > 100:
            raise ValueError("LINE Rich Menu publication page size exceeds maximum")
        if len(self.items) > self.page_size:
            raise ValueError("LINE Rich Menu publication page exceeds requested size")


@dataclass(frozen=True, slots=True)
class LineRichMenuCleanupWorkItem(LineRichMenuPublicationWorkItem):
    published_provider_menu_id: str
    previous_provider_menu_id: str | None

    def __post_init__(self) -> None:
        LineRichMenuPublicationWorkItem.__post_init__(self)
        if self.publication.status is not LineRichMenuPublicationStatus.PUBLISHED:
            raise ValueError("LINE Rich Menu cleanup work must remain published")
        require_canonical_text(
            self.published_provider_menu_id,
            "published LINE provider Rich Menu ID",
            191,
        )
        if self.previous_provider_menu_id is not None:
            require_canonical_text(
                self.previous_provider_menu_id,
                "previous LINE provider Rich Menu ID",
                191,
            )


class LineWebhookInboxRepositoryPort(Protocol):
    def register(
        self,
        event: CanonicalLineWebhookEvent,
    ) -> AcceptLineWebhookEventResult: ...

    def get(self, event_id: LineWebhookEventId) -> LineWebhookInboxSnapshot | None: ...

    def transition(
        self,
        event_id: LineWebhookEventId,
        expected_version: ExpectedVersion,
        target_status: LineWebhookProcessingStatus,
    ) -> LineWebhookInboxSnapshot: ...

    def claim(
        self,
        query: ClaimLineWebhookEventsQuery,
    ) -> tuple[LineWebhookInboxSnapshot, ...]: ...

    def complete(
        self,
        command: CompleteLineWebhookEventCommand,
    ) -> LineWebhookInboxSnapshot: ...

    def next_due_at(self) -> datetime | None: ...

    def retry(
        self,
        command: RetryLineRichMenuPublicationCommand,
    ) -> LineRichMenuPublicationSnapshot: ...


class LineWakeupPublisherPort(Protocol):
    def publish(self) -> None: ...


class LineWakeupSubscriberPort(Protocol):
    def wait(self, timeout_seconds: float) -> bool: ...


class LineRuntimeRepositoryPort(Protocol):
    def record_heartbeat(self, heartbeat: LineWorkerHeartbeat) -> None: ...

    def latest_heartbeat(self) -> LineWorkerHeartbeat | None: ...

    def append_security_receipt(self, receipt: LineWebhookSecurityReceipt) -> None: ...

    def queue_counts(self) -> dict[str, int]: ...


class LineIdentityRepositoryPort(Protocol):
    def get(self, line_user_id: LineUserId) -> LineIdentityBindingSnapshot | None: ...

    def list_bound_by_subject_type(
        self,
        subject_type: LineBindingSubjectType,
    ) -> tuple[LineIdentityBindingSnapshot, ...]: ...

    def save_claim(
        self,
        claim: LineIdentityClaim,
        expected_version: ExpectedVersion,
    ) -> LineIdentityBindingSnapshot: ...

    def bind(
        self,
        claim: LineIdentityClaim,
        expected_version: ExpectedVersion,
        actor_id: str,
        idempotency_key: IdempotencyKey,
        correlation_id: str,
    ) -> LineIdentityBindingSnapshot: ...

    def revoke(
        self,
        line_user_id: LineUserId,
        expected_version: ExpectedVersion,
        actor_id: str,
        idempotency_key: IdempotencyKey,
        correlation_id: str,
    ) -> LineIdentityBindingSnapshot: ...

    def request_revocation(
        self,
        line_user_id: LineUserId,
        expected_version: ExpectedVersion,
        actor_id: str,
        idempotency_key: IdempotencyKey,
        correlation_id: str,
    ) -> LineIdentityBindingSnapshot: ...

    def complete_revocation(
        self,
        line_user_id: LineUserId,
        expected_version: ExpectedVersion,
        actor_id: str,
        idempotency_key: IdempotencyKey,
        correlation_id: str,
    ) -> LineIdentityBindingSnapshot: ...

    def replace_subject(
        self,
        claim: LineIdentityClaim,
        expected_version: ExpectedVersion,
        actor_id: str,
        idempotency_key: IdempotencyKey,
        correlation_id: str,
    ) -> LineIdentityBindingSnapshot: ...

    def get_by_subject(
        self,
        subject_type: LineBindingSubjectType,
        subject_reference: str,
    ) -> LineIdentityBindingSnapshot | None: ...


class LinePlatformUserRepositoryPort(Protocol):
    def get(self, line_user_id: LineUserId) -> LinePlatformUserSnapshot | None: ...

    def ensure_verified_user(self, line_user_id: LineUserId) -> LinePlatformUserSnapshot: ...

    def apply_friend_event(self, event: LineFriendEvent) -> LinePlatformUserSnapshot: ...


class LineIdentityFlowRepositoryPort(Protocol):
    def open(self, command: OpenLineIdentityFlowCommand) -> OpenLineIdentityFlowResult: ...

    def get(self, flow_id: LineIdentityFlowId) -> LineIdentityFlowSnapshot | None: ...

    def consume(
        self,
        flow_id: LineIdentityFlowId,
        purpose: LineIdentityFlowPurpose,
        line_user_id: LineUserId,
        now: datetime,
    ) -> LineIdentityFlowSnapshot: ...

    def record_failed_attempt(
        self,
        flow_id: LineIdentityFlowId,
        maximum_attempts: int,
    ) -> LineIdentityFlowSnapshot: ...


class LineIdentityReviewRepositoryPort(Protocol):
    def create(self, command: CreateLineReviewCommand) -> CreateLineReviewResult: ...

    def get(self, request_id: LineReviewRequestId) -> LineReviewSnapshot | None: ...

    def list(self, query: LineReviewListQuery) -> LineReviewPage: ...

    def summary(self, stale_hours: int) -> LineReviewQueueSummary: ...

    def decide(
        self,
        command: DecideLineReviewCommand,
        candidate: LineReviewDecisionCandidate,
    ) -> DecideLineReviewResult: ...


class LineDeliveryTaskRepositoryPort(Protocol):
    def enqueue(self, request: LineDeliveryRequest) -> EnqueueLineDeliveryResult: ...

    def get(self, task_id: LineDeliveryTaskId) -> LineDeliveryTaskSnapshot | None: ...

    def claim(
        self,
        query: ClaimLineDeliveryTasksQuery,
    ) -> tuple[LineDeliveryTaskSnapshot, ...]: ...

    def record_attempt(
        self,
        command: RecordLineDeliveryAttemptCommand,
    ) -> RecordLineDeliveryAttemptResult: ...

    def cancel(
        self,
        command: CancelLineDeliveryTaskCommand,
    ) -> LineDeliveryTaskSnapshot: ...

    def next_due_at(self) -> datetime | None: ...

    def cancel_pending_for_recipient(self, line_user_id: LineUserId) -> int: ...

    def cancel_pending_for_notification_rule(
        self,
        task_ids: tuple[LineDeliveryTaskId, ...],
        *,
        reason: str,
    ) -> tuple[LineDeliveryTaskId, ...]: ...

    def list_admin(self, query: LineDeliveryAdminQuery) -> LineDeliveryAdminPage: ...

    def get_admin(
        self,
        task_id: LineDeliveryTaskId,
    ) -> LineDeliveryAdminRecord | None: ...

    def attempts(
        self,
        task_id: LineDeliveryTaskId,
    ) -> tuple[LineDeliveryAttemptRecord, ...]: ...

    def summary(self, now: datetime) -> dict[str, int]: ...

    def run_now(
        self,
        task_id: LineDeliveryTaskId,
        now: datetime,
    ) -> LineDeliveryTaskSnapshot: ...

    def retry_failed(
        self,
        task_id: LineDeliveryTaskId,
        now: datetime,
    ) -> LineDeliveryTaskSnapshot: ...


class LineNotificationRuleRepositoryPort(Protocol):
    def cancel_rule(self, rule_id: str, *, reason: str) -> int: ...

    def lock_and_cancel_rule_intents(
        self,
        rule_id: str,
        *,
        reason: str,
    ) -> LineNotificationCancellationLineage: ...

    def register_source_event(self, event: object) -> int: ...


class LineConfigurationRepositoryPort(Protocol):
    def get(self, kind: LineConfigurationKind) -> LineConfigurationSnapshot: ...

    def apply(
        self,
        command: ApplyLineConfigurationCommand,
    ) -> ApplyLineConfigurationResult: ...


class LineRichMenuPublicationRepositoryPort(Protocol):
    def get(
        self,
        publication_id: LineRichMenuPublicationId,
    ) -> LineRichMenuPublicationSnapshot | None: ...

    def list(
        self,
        query: LineRichMenuPublicationQuery,
    ) -> tuple[LineRichMenuPublicationSnapshot, ...]: ...

    def list_page(
        self,
        query: LineRichMenuPublicationQuery,
        *,
        offset: int = 0,
    ) -> LineRichMenuPublicationPage: ...

    def list_for_configuration_revision(
        self,
        configuration_revision: LineConfigurationRevision,
    ) -> tuple[LineRichMenuPublicationSnapshot, ...]: ...

    def published_provider_menu_id(self, menu_definition_id: str) -> str | None: ...

    def queue(
        self,
        command: QueueLineRichMenuPublicationCommand,
    ) -> QueueLineRichMenuPublicationResult: ...

    def claim(
        self,
        query: ClaimLineRichMenuPublicationsQuery,
    ) -> tuple[
        LineRichMenuPublicationWorkItem | LineRichMenuCleanupWorkItem,
        ...,
    ]: ...

    def persist_cleanup_target(
        self,
        publication_id: LineRichMenuPublicationId,
        lease_owner: str,
        provider_menu_id: str,
    ) -> None: ...

    def record(
        self,
        command: RecordLineRichMenuPublicationCommand,
    ) -> LineRichMenuPublicationSnapshot: ...

    def list_step_receipts(
        self,
        publication_id: LineRichMenuPublicationId,
    ) -> tuple[LineRichMenuStepReceipt, ...]: ...

    def append_step_receipt(
        self,
        receipt: LineRichMenuStepReceipt,
    ) -> LineRichMenuStepReceipt: ...

    def list_step_attempt_events(
        self,
        publication_id: LineRichMenuPublicationId,
        step: LineRichMenuPublicationStep | None = None,
    ) -> tuple[LineRichMenuStepAttemptEvent, ...]: ...

    def append_step_attempt_event(
        self,
        event: LineRichMenuStepAttemptEvent,
    ) -> LineRichMenuStepAttemptEvent: ...

    def append_cleanup_anomaly(
        self,
        anomaly: LineRichMenuCleanupAnomaly,
    ) -> None: ...

    def next_due_at(self) -> datetime | None: ...


class LineMediaMetadataRepositoryPort(Protocol):
    def get(self, provider_media_id: str) -> LineMediaMetadata | None: ...

    def register(
        self,
        metadata: LineMediaMetadata,
        object_reference: str,
        idempotency_key: IdempotencyKey,
    ) -> ArchiveLineMediaResult: ...


class LineRichMenuMediaAssetQueryRepositoryPort(Protocol):
    def list(
        self,
        query: RichMenuMediaAssetListQuery,
    ) -> RichMenuMediaAssetPage: ...

    def get(
        self,
        query: RichMenuMediaAssetDetailQuery,
    ) -> RichMenuMediaAsset | None: ...

    def get_for_update(
        self,
        query: RichMenuMediaAssetDetailQuery,
    ) -> RichMenuMediaAsset | None: ...


class LineOrderGroupBindingRepositoryPort(Protocol):
    def get(self, case_no: str) -> LineOrderGroupBindingSnapshot | None: ...

    def get_by_group(self, group_id: str) -> LineOrderGroupBindingSnapshot | None: ...

    def list(self, *, status: str | None, limit: int) -> LineOrderGroupPage: ...

    def list_numbered(
        self, *, status: str | None, page: int, page_size: int
    ) -> LineOrderGroupNumberedPage: ...

    def events(self, case_no: str, *, limit: int) -> tuple[LineOrderGroupEventRecord, ...]: ...

    def events_numbered(
        self, case_no: str, *, page: int, page_size: int
    ) -> LineOrderGroupEventPage: ...

    def bind(
        self,
        command: BindLineOrderGroupCommand,
    ) -> BindLineOrderGroupResult: ...

    def sync_participants(self, audience: OrderLineAudience) -> None: ...

    def record_invitation_relay(
        self,
        relay,
        idempotency_key: IdempotencyKey,
    ) -> bool: ...

    def record_membership_event(
        self,
        *,
        group_id: str,
        line_user_id: LineUserId,
        event_type: str,
        idempotency_key: IdempotencyKey,
        occurred_at: datetime,
    ) -> bool: ...


class LineIdempotencyReceiptPort(Protocol):
    def get(self, key: IdempotencyKey) -> IdempotencyReceipt | None: ...

    def append(self, receipt: IdempotencyReceipt) -> None: ...


class LineOutboxRepositoryPort(OutboxWriter, Protocol):
    def claim(self, query: ClaimLineOutboxQuery) -> tuple[LineOutboxWorkItem, ...]: ...

    def complete(self, command: CompleteLineOutboxCommand) -> None: ...

    def next_due_at(self, intent_type: str = "line.media.archive") -> datetime | None: ...


class LineAuditPort(Protocol):
    def append(self, intent: LineAuditIntent) -> None: ...


class LineMessagingProviderPort(Protocol):
    def send(self, request: LineDeliveryRequest) -> LineProviderOutcome: ...


class LiffTokenVerifierPort(Protocol):
    def verify(self, id_token: str) -> VerifiedLiffIdentity: ...


class LineRichMenuProviderPort(Protocol):
    def publish(
        self,
        request: LineRichMenuProviderRequest,
    ) -> LineRichMenuProviderOutcome: ...

    def create(
        self,
        request: LineRichMenuProviderRequest,
    ) -> LineRichMenuProviderOutcome: ...

    def upload(
        self,
        request: LineRichMenuProviderRequest,
        provider_menu_id: str,
    ) -> LineRichMenuProviderOutcome: ...

    def upsert_alias(
        self,
        request: LineRichMenuProviderRequest,
        provider_menu_id: str,
    ) -> LineRichMenuProviderOutcome: ...

    def switch_default(
        self,
        request: LineRichMenuProviderRequest,
        provider_menu_id: str,
    ) -> LineRichMenuProviderOutcome: ...

    def delete(self, provider_menu_id: str) -> LineRichMenuProviderOutcome: ...

    def link_to_user(
        self,
        provider_menu_id: str,
        line_user_id: LineUserId,
    ) -> LineRichMenuProviderOutcome: ...


class LineMediaProviderPort(Protocol):
    def download(self, provider_media_id: str) -> LineMediaDownload: ...


class LineMediaObjectStorePort(Protocol):
    def put(self, metadata: LineMediaMetadata, content: bytes) -> str: ...


class CustomerIdentityOwnerPort(Protocol):
    def resolve_customer(self, proof: CustomerIdentityProof) -> LineIdentityCandidate | None: ...

    def bind_customer(
        self,
        subject_reference: str,
        line_user_id: LineUserId,
        expected_current_line_user_id: LineUserId | None,
    ) -> None: ...

    def clear_customer(
        self,
        subject_reference: str,
        line_user_id: LineUserId,
    ) -> None: ...


class StaffIdentityOwnerPort(Protocol):
    def resolve_staff(self, proof: StaffIdentityProof) -> LineIdentityCandidate | None: ...

    def bind_staff(
        self,
        subject_reference: str,
        line_user_id: LineUserId,
        expected_current_line_user_id: LineUserId | None,
    ) -> None: ...

    def clear_staff(
        self,
        subject_reference: str,
        line_user_id: LineUserId,
    ) -> None: ...


class AdminIdentityOwnerPort(Protocol):
    def authenticate_admin(
        self,
        proof: AdminCredentialProof,
    ) -> LineIdentityCandidate | None: ...

    def bind_admin(
        self,
        subject_reference: str,
        line_user_id: LineUserId,
        expected_current_line_user_id: LineUserId | None,
    ) -> None: ...

    def clear_admin(
        self,
        subject_reference: str,
        line_user_id: LineUserId,
    ) -> None: ...

    def get_linked_admin(self, line_user_id: LineUserId) -> LinkedLineAdmin | None: ...


class OrdersLineAudiencePort(Protocol):
    def get(self, case_no: str) -> OrderLineAudience | None: ...

    def set_group_projection(
        self,
        case_no: str,
        group_id: str,
        expected_group_id: str | None,
    ) -> None: ...


class LineUnitOfWorkPort(UnitOfWork, Protocol):
    webhook_inbox: LineWebhookInboxRepositoryPort
    platform_users: LinePlatformUserRepositoryPort
    identity_flows: LineIdentityFlowRepositoryPort
    identities: LineIdentityRepositoryPort
    reviews: LineIdentityReviewRepositoryPort
    customers: CustomerIdentityOwnerPort
    staff: StaffIdentityOwnerPort
    admins: AdminIdentityOwnerPort
    delivery_tasks: LineDeliveryTaskRepositoryPort
    notification_rules: LineNotificationRuleRepositoryPort
    configurations: LineConfigurationRepositoryPort
    rich_menu_publications: LineRichMenuPublicationRepositoryPort
    rich_menu_media_assets: LineRichMenuMediaAssetQueryRepositoryPort
    media_metadata: LineMediaMetadataRepositoryPort
    order_groups: LineOrderGroupBindingRepositoryPort
    order_audiences: OrdersLineAudiencePort
    runtime_monitor: object
    receipts: LineIdempotencyReceiptPort
    audit: LineAuditPort
    outbox: LineOutboxRepositoryPort
    matching_notifications: object
    knowledge_questions: object
    customer_service: object
    identity_management: object


__all__ = [
    "AdminIdentityOwnerPort",
    "BusinessClock",
    "CustomerIdentityOwnerPort",
    "LineAuditIntent",
    "LineAuditPort",
    "LineConfigurationRepositoryPort",
    "LineDeliveryTaskRepositoryPort",
    "LineIdentityRepositoryPort",
    "LineIdentityFlowRepositoryPort",
    "LineIdentityReviewRepositoryPort",
    "LineIdempotencyReceiptPort",
    "LineMediaMetadataRepositoryPort",
    "LineRichMenuMediaAssetQueryRepositoryPort",
    "LineMediaObjectStorePort",
    "LineMediaProviderPort",
    "LiffTokenVerifierPort",
    "LineMessagingProviderPort",
    "LineNotificationCancellationLineage",
    "LineNotificationRuleRepositoryPort",
    "LineOrderGroupBindingRepositoryPort",
    "LineOutboxRepositoryPort",
    "LineRichMenuProviderPort",
    "LineRichMenuCleanupAnomaly",
    "LineRichMenuCleanupWorkItem",
    "LineRichMenuPublicationStep",
    "LineRichMenuPublicationPage",
    "LineRichMenuPublicationRepositoryPort",
    "LineRichMenuStepAttemptEvent",
    "LineRichMenuStepAttemptOutcome",
    "LineRichMenuStepReceipt",
    "LineUnitOfWorkPort",
    "LineRuntimeRepositoryPort",
    "LinePlatformUserRepositoryPort",
    "LineWebhookInboxRepositoryPort",
    "LineWakeupPublisherPort",
    "LineWakeupSubscriberPort",
    "OrdersLineAudiencePort",
    "StaffIdentityOwnerPort",
]
