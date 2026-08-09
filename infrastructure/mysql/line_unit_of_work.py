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
from infrastructure.mysql.line_identity_owner_adapters import (
    MySqlAdminIdentityOwnerAdapter,
    MySqlCustomerIdentityOwnerAdapter,
    MySqlStaffIdentityOwnerAdapter,
)
from infrastructure.mysql.line_platform_identity_repository import (
    MySqlLineIdentityFlowRepository,
    MySqlLinePlatformUserRepository,
)
from infrastructure.mysql.line_media_order_group_repository import (
    MySqlLineMediaMetadataRepository,
    MySqlLineOrderGroupBindingRepository,
)
from infrastructure.mysql.line_order_group_adapters import (
    MySqlOrdersLineAudienceAdapter,
)
from infrastructure.mysql.runtime_monitor_repository import MySqlRuntimeMonitorRepository
from infrastructure.mysql.line_receipt_outbox_audit import (
    MySqlLineAuditRepository,
    MySqlLineIdempotencyReceiptRepository,
    MySqlLineOutboxWriter,
)
from infrastructure.mysql.line_webhook_inbox_repository import (
    MySqlLineWebhookInboxRepository,
)
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.matching_notification_repository import (
    MySqlMatchingNotificationRepository,
)


class LineMySqlUnitOfWork(MySqlUnitOfWork):
    def __init__(self, connection: Any) -> None:
        super().__init__(connection)
        self.webhook_inbox = MySqlLineWebhookInboxRepository(connection)
        self.platform_users = MySqlLinePlatformUserRepository(connection)
        self.identity_flows = MySqlLineIdentityFlowRepository(connection)
        self.identities = MySqlLineIdentityRepository(connection)
        self.reviews = MySqlLineIdentityReviewRepository(connection)
        self.customers = MySqlCustomerIdentityOwnerAdapter(connection)
        self.staff = MySqlStaffIdentityOwnerAdapter(connection)
        self.admins = MySqlAdminIdentityOwnerAdapter(connection)
        self.delivery_tasks = MySqlLineDeliveryTaskRepository(connection)
        self.configurations = MySqlLineConfigurationRepository(connection)
        self.rich_menu_publications = MySqlLineRichMenuPublicationRepository(connection)
        self.media_metadata = MySqlLineMediaMetadataRepository(connection)
        self.order_groups = MySqlLineOrderGroupBindingRepository(connection)
        self.order_audiences = MySqlOrdersLineAudienceAdapter(connection)
        self.runtime_monitor = MySqlRuntimeMonitorRepository(connection)
        self.receipts = MySqlLineIdempotencyReceiptRepository(connection)
        self.audit = MySqlLineAuditRepository(connection)
        self.outbox = MySqlLineOutboxWriter(connection)
        self.matching_notifications = MySqlMatchingNotificationRepository(connection)


class ManagedLineMySqlUnitOfWork(LineMySqlUnitOfWork):
    """A process-bound LINE transaction that also owns its DB connection."""

    def __exit__(self, exception_type, exception, traceback) -> bool:
        try:
            return super().__exit__(exception_type, exception, traceback)
        finally:
            self._connection.close()


def open_line_unit_of_work() -> ManagedLineMySqlUnitOfWork:
    return ManagedLineMySqlUnitOfWork(get_connection())


__all__ = ["LineMySqlUnitOfWork", "ManagedLineMySqlUnitOfWork", "open_line_unit_of_work"]
