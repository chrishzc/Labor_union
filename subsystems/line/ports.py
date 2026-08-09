"""Typed ports for LINE repositories, providers, and cross-domain queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
from domains.line.order_group import LineOrderGroupBindingSnapshot
from domains.line.review import LineReviewDecisionCandidate, LineReviewSnapshot
from domains.line.platform_user import LineFriendEvent, LinePlatformUserSnapshot
from domains.line.rich_menu import LineRichMenuPublicationSnapshot
from domains.line.webhook import (
    CanonicalLineWebhookEvent,
    LineWebhookInboxSnapshot,
    LineWebhookProcessingStatus,
)
from shared_kernel.clock import BusinessClock
from shared_kernel.identities import ExpectedVersion, IdempotencyKey, IdempotencyReceipt
from shared_kernel.ports import OutboxWriter, UnitOfWork
from shared_kernel.validation import require_canonical_text
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
from subsystems.line.outbox_contracts import (
    ClaimLineOutboxQuery,
    CompleteLineOutboxCommand,
    LineOutboxWorkItem,
)
from subsystems.line.order_group_contracts import (
    BindLineOrderGroupCommand,
    BindLineOrderGroupResult,
    LineOrderGroupEventRecord,
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

    def get_by_subject(
        self,
        subject_type: LineBindingSubjectType,
        subject_reference: str,
    ) -> LineIdentityBindingSnapshot | None: ...


class LinePlatformUserRepositoryPort(Protocol):
    def get(self, line_user_id: LineUserId) -> LinePlatformUserSnapshot | None: ...

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

    def queue(
        self,
        command: QueueLineRichMenuPublicationCommand,
    ) -> QueueLineRichMenuPublicationResult: ...

    def claim(
        self,
        query: ClaimLineRichMenuPublicationsQuery,
    ) -> tuple[LineRichMenuPublicationWorkItem, ...]: ...

    def record(self, command: RecordLineRichMenuPublicationCommand): ...

    def next_due_at(self) -> datetime | None: ...


class LineMediaMetadataRepositoryPort(Protocol):
    def get(self, provider_media_id: str) -> LineMediaMetadata | None: ...

    def register(
        self,
        metadata: LineMediaMetadata,
        object_reference: str,
        idempotency_key: IdempotencyKey,
    ) -> ArchiveLineMediaResult: ...


class LineOrderGroupBindingRepositoryPort(Protocol):
    def get(self, case_no: str) -> LineOrderGroupBindingSnapshot | None: ...

    def get_by_group(self, group_id: str) -> LineOrderGroupBindingSnapshot | None: ...

    def list(self, *, status: str | None, limit: int) -> LineOrderGroupPage: ...

    def events(self, case_no: str, *, limit: int) -> tuple[LineOrderGroupEventRecord, ...]: ...

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

    def next_due_at(self) -> datetime | None: ...


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


class StaffIdentityOwnerPort(Protocol):
    def resolve_staff(self, proof: StaffIdentityProof) -> LineIdentityCandidate | None: ...

    def bind_staff(
        self,
        subject_reference: str,
        line_user_id: LineUserId,
        expected_current_line_user_id: LineUserId | None,
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
    configurations: LineConfigurationRepositoryPort
    rich_menu_publications: LineRichMenuPublicationRepositoryPort
    media_metadata: LineMediaMetadataRepositoryPort
    order_groups: LineOrderGroupBindingRepositoryPort
    order_audiences: OrdersLineAudiencePort
    runtime_monitor: object
    receipts: LineIdempotencyReceiptPort
    audit: LineAuditPort
    outbox: LineOutboxRepositoryPort
    matching_notifications: object
    knowledge_questions: object


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
    "LineMediaObjectStorePort",
    "LineMediaProviderPort",
    "LiffTokenVerifierPort",
    "LineMessagingProviderPort",
    "LineOrderGroupBindingRepositoryPort",
    "LineOutboxRepositoryPort",
    "LineRichMenuProviderPort",
    "LineRichMenuPublicationRepositoryPort",
    "LineUnitOfWorkPort",
    "LineRuntimeRepositoryPort",
    "LinePlatformUserRepositoryPort",
    "LineWebhookInboxRepositoryPort",
    "LineWakeupPublisherPort",
    "LineWakeupSubscriberPort",
    "OrdersLineAudiencePort",
    "StaffIdentityOwnerPort",
]
