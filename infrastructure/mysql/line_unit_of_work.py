"""Outer MySQL transaction owner exposing all canonical LINE repositories."""

from __future__ import annotations

from typing import Any

from infrastructure.mysql.line_configuration_publication_repository import (
    MySqlLineConfigurationRepository,
    MySqlLineRichMenuPublicationRepository,
)
from infrastructure.mysql.line_delivery_task_repository import (
    MySqlLineDeliveryTaskRepository,
)
from infrastructure.mysql.line_identity_review_repository import (
    MySqlLineIdentityRepository,
    MySqlLineIdentityReviewRepository,
)
from infrastructure.mysql.line_media_order_group_repository import (
    MySqlLineMediaMetadataRepository,
    MySqlLineOrderGroupBindingRepository,
)
from infrastructure.mysql.line_receipt_outbox_audit import (
    MySqlLineAuditRepository,
    MySqlLineIdempotencyReceiptRepository,
    MySqlLineOutboxWriter,
)
from infrastructure.mysql.line_webhook_inbox_repository import (
    MySqlLineWebhookInboxRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork


class LineMySqlUnitOfWork(MySqlUnitOfWork):
    def __init__(self, connection: Any) -> None:
        super().__init__(connection)
        self.webhook_inbox = MySqlLineWebhookInboxRepository(connection)
        self.identities = MySqlLineIdentityRepository(connection)
        self.reviews = MySqlLineIdentityReviewRepository(connection)
        self.delivery_tasks = MySqlLineDeliveryTaskRepository(connection)
        self.configurations = MySqlLineConfigurationRepository(connection)
        self.rich_menu_publications = MySqlLineRichMenuPublicationRepository(connection)
        self.media_metadata = MySqlLineMediaMetadataRepository(connection)
        self.order_groups = MySqlLineOrderGroupBindingRepository(connection)
        self.receipts = MySqlLineIdempotencyReceiptRepository(connection)
        self.audit = MySqlLineAuditRepository(connection)
        self.outbox = MySqlLineOutboxWriter(connection)


__all__ = ["LineMySqlUnitOfWork"]
