"""
File: line_unit_of_work.py
Description: 提供同一 MySQL outer transaction 的 canonical LINE repositories 與通知規則取消操作。
"""

from __future__ import annotations

from typing import Any, Callable

from infrastructure.mysql.line_configuration_publication_repository import (
    MySqlLineConfigurationRepository,
    MySqlLineRichMenuPublicationRepository,
)
from infrastructure.mysql.line_delivery_task_repository import (
    MySqlLineDeliveryTaskRepository,
)
from infrastructure.mysql.line_notification_repository import (
    MySqlLineNotificationRepository,
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
from infrastructure.mysql.line_media_asset_query_repository import (
    MySqlLineRichMenuMediaAssetQueryRepository,
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
from infrastructure.mysql.knowledge_retrieval_repository import (
    MySqlKnowledgeQuestionIntakeAdapter,
)
from infrastructure.mysql.customer_service_repository import (
    MySqlCustomerServiceRepository,
)
from infrastructure.mysql.customer_service_escalation_repository import (
    MySqlCustomerServiceEscalationRepository,
)
from infrastructure.mysql.line_identity_management_repository import (
    MySqlLineIdentityManagementRepository,
)
from infrastructure.mysql.provisional_registration_repository import (
    MySqlProvisionalRegistrationRepository,
)
from infrastructure.mysql.matching_schedule_confirmation_repository import (
    MySqlMatchingScheduleConfirmationRepository,
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
        self.notification_rules = MySqlLineNotificationRepository(connection)
        self.configurations = MySqlLineConfigurationRepository(connection)
        self.rich_menu_publications = MySqlLineRichMenuPublicationRepository(connection)
        self.rich_menu_media_assets = MySqlLineRichMenuMediaAssetQueryRepository(connection)
        self.media_metadata = MySqlLineMediaMetadataRepository(connection)
        self.order_groups = MySqlLineOrderGroupBindingRepository(connection)
        self.order_audiences = MySqlOrdersLineAudienceAdapter(connection)
        self.runtime_monitor = MySqlRuntimeMonitorRepository(connection)
        self.escalation_source = self.runtime_monitor
        self.receipts = MySqlLineIdempotencyReceiptRepository(connection)
        self.audit = MySqlLineAuditRepository(connection)
        self.outbox = MySqlLineOutboxWriter(connection)
        self.matching_notifications = MySqlMatchingNotificationRepository(connection)
        self.matching_schedule_confirmations = MySqlMatchingScheduleConfirmationRepository(connection)
        self.knowledge_questions = MySqlKnowledgeQuestionIntakeAdapter(connection)
        self.customer_service = MySqlCustomerServiceRepository(connection)
        self.escalations = MySqlCustomerServiceEscalationRepository(connection)
        self.identity_management = MySqlLineIdentityManagementRepository(connection)
        # Registration remains Case Import-owned, but shares this outer transaction.
        self.provisional_registrations = MySqlProvisionalRegistrationRepository(connection)
        self._after_completion_hooks: list[Callable[[], None]] = []

    def add_after_completion(self, hook: Callable[[], None]) -> None:
        """註冊 transaction finalized 後執行一次的同 connection cleanup。"""
        if self._committed or self._rolled_back:
            raise RuntimeError("transaction is already finalized")
        self._after_completion_hooks.append(hook)

    def __exit__(self, exception_type, exception, traceback) -> bool:
        if self._committed:
            return False
        return super().__exit__(exception_type, exception, traceback)

    def commit(self) -> None:
        self._finalize(super().commit)

    def rollback(self) -> None:
        self._finalize(super().rollback)

    def _finalize(self, operation: Callable[[], None]) -> None:
        primary_error: BaseException | None = None
        try:
            operation()
        except BaseException as error:
            primary_error = error
        hook_error: BaseException | None = None
        hooks, self._after_completion_hooks = self._after_completion_hooks, []
        for hook in hooks:
            try:
                hook()
            except BaseException as error:
                hook_error = hook_error or error
        if primary_error is not None:
            if hook_error is not None:
                primary_error.add_note(f"after_completion failed: {hook_error!r}")
            raise primary_error
        if hook_error is not None:
            raise hook_error


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
