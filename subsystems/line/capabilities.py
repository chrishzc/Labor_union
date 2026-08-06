"""Stable human capability names for LINE administration."""

from enum import StrEnum

from shared_kernel.identities import ActorContext


class LineCapability(StrEnum):
    REVIEW_READ = "line.review.read"
    REVIEW_DECIDE = "line.review.decide"
    TASK_READ = "line.task.read"
    TASK_RETRY = "line.task.retry"
    TASK_CANCEL = "line.task.cancel"
    TASK_SEND = "line.task.send"
    CONFIG_READ = "line.config.read"
    CONFIG_MANAGE = "line.config.manage"
    RICH_MENU_PUBLISH = "line.rich_menu.publish"
    IDENTITY_BIND_ADMIN = "line.identity.bind_admin"
    IDENTITY_REVIEW_STAFF = "line.identity.review_staff"
    ORDER_GROUP_READ = "line.order_group.read"
    ORDER_GROUP_BIND = "line.order_group.bind"
    MONITOR_READ = "line.monitor.read"
    ALERT_MANAGE = "line.alert.manage"


class LineCapabilityDeniedError(PermissionError):
    """Raised when an authenticated actor lacks a LINE capability."""


def require_line_capability(
    actor: ActorContext,
    capability: LineCapability,
) -> None:
    if not isinstance(capability, LineCapability):
        raise TypeError("LINE capability is invalid")
    if capability.value not in actor.permission_scope:
        raise LineCapabilityDeniedError(
            f"actor lacks required LINE capability {capability.value}"
        )


__all__ = [
    "LineCapability",
    "LineCapabilityDeniedError",
    "require_line_capability",
]
