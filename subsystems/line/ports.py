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
    LineRichMenuPublicationId,
    LineReviewRequestId,
    LineUserId,
    LineWebhookEventId,
)
from domains.line.identity_binding import (
    LineIdentityBindingSnapshot,
    LineIdentityClaim,
)
from domains.line.media import LineMediaMetadata
from domains.line.order_group import LineOrderGroupBindingSnapshot
from domains.line.review import LineReviewDecisionCandidate, LineReviewSnapshot
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
from subsystems.line.identity_contracts import LineIdentityCandidate
from subsystems.line.media_contracts import (
    ArchiveLineMediaResult,
    LineMediaDownload,
)
from subsystems.line.order_group_contracts import (
    BindLineOrderGroupCommand,
    BindLineOrderGroupResult,
    OrderLineAudience,
)
from subsystems.line.review_contracts import (
    DecideLineReviewCommand,
    DecideLineReviewResult,
    LineReviewListQuery,
    LineReviewPage,
)
from subsystems.line.rich_menu_contracts import (
    LineRichMenuProviderOutcome,
    LineRichMenuProviderRequest,
    LineRichMenuPublicationQuery,
    QueueLineRichMenuPublicationResult,
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


class LineIdentityReviewRepositoryPort(Protocol):
    def get(self, request_id: LineReviewRequestId) -> LineReviewSnapshot | None: ...

    def list(self, query: LineReviewListQuery) -> LineReviewPage: ...

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
        snapshot: LineRichMenuPublicationSnapshot,
        idempotency_key: IdempotencyKey,
    ) -> QueueLineRichMenuPublicationResult: ...


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

    def bind(
        self,
        command: BindLineOrderGroupCommand,
    ) -> BindLineOrderGroupResult: ...


class LineIdempotencyReceiptPort(Protocol):
    def get(self, key: IdempotencyKey) -> IdempotencyReceipt | None: ...

    def append(self, receipt: IdempotencyReceipt) -> None: ...


class LineAuditPort(Protocol):
    def append(self, intent: LineAuditIntent) -> None: ...


class LineMessagingProviderPort(Protocol):
    def send(self, request: LineDeliveryRequest) -> LineProviderOutcome: ...


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


class CustomerIdentityLookupPort(Protocol):
    def resolve(self, claim: LineIdentityClaim) -> LineIdentityCandidate | None: ...


class StaffIdentityLookupPort(Protocol):
    def resolve(self, claim: LineIdentityClaim) -> LineIdentityCandidate | None: ...


class AdminIdentityLookupPort(Protocol):
    def resolve(self, claim: LineIdentityClaim) -> LineIdentityCandidate | None: ...


class OrdersLineAudiencePort(Protocol):
    def get(self, case_no: str) -> OrderLineAudience | None: ...


class LineUnitOfWorkPort(UnitOfWork, Protocol):
    webhook_inbox: LineWebhookInboxRepositoryPort
    identities: LineIdentityRepositoryPort
    reviews: LineIdentityReviewRepositoryPort
    delivery_tasks: LineDeliveryTaskRepositoryPort
    configurations: LineConfigurationRepositoryPort
    rich_menu_publications: LineRichMenuPublicationRepositoryPort
    media_metadata: LineMediaMetadataRepositoryPort
    order_groups: LineOrderGroupBindingRepositoryPort
    receipts: LineIdempotencyReceiptPort
    audit: LineAuditPort
    outbox: OutboxWriter


__all__ = [
    "AdminIdentityLookupPort",
    "BusinessClock",
    "CustomerIdentityLookupPort",
    "LineAuditIntent",
    "LineAuditPort",
    "LineConfigurationRepositoryPort",
    "LineDeliveryTaskRepositoryPort",
    "LineIdentityRepositoryPort",
    "LineIdentityReviewRepositoryPort",
    "LineIdempotencyReceiptPort",
    "LineMediaMetadataRepositoryPort",
    "LineMediaObjectStorePort",
    "LineMediaProviderPort",
    "LineMessagingProviderPort",
    "LineOrderGroupBindingRepositoryPort",
    "LineRichMenuProviderPort",
    "LineRichMenuPublicationRepositoryPort",
    "LineUnitOfWorkPort",
    "LineRuntimeRepositoryPort",
    "LineWebhookInboxRepositoryPort",
    "LineWakeupPublisherPort",
    "LineWakeupSubscriberPort",
    "OrdersLineAudiencePort",
    "StaffIdentityLookupPort",
]
