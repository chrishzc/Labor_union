"""
File: capabilities.py
Description: 定義 LINE 管理能力字串、角色相容投影與第二層能力檢查。
"""

from enum import StrEnum

from shared_kernel.identities import ActorContext


class LineCapability(StrEnum):
    IDENTITY_READ = "line.identity.read"
    IDENTITY_REVIEW = "line.identity.review"
    TASK_CONTROL = "line.task.control"
    MENU_PUBLISH = "line.menu.publish"
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
    AUDIT_READ = "line.audit.read"
    MATCHING_READ = "line.matching.read"
    MATCHING_SEND = "line.matching.send"
    MATCHING_OVERRIDE = "line.matching.override"
    CUSTOMER_SERVICE_READ = "line.customer_service.read"
    CUSTOMER_SERVICE_HANDLE = "line.customer_service.handle"
    IDENTITY_BINDING_READ = "line.identity.binding.read"
    IDENTITY_BINDING_MANAGE = "line.identity.binding.manage"
    IDENTITY_BINDING_OVERRIDE = "line.identity.binding.override"


class LineCapabilityDeniedError(PermissionError):
    """Raised when an authenticated actor lacks a LINE capability."""


_ROLE_CAPABILITIES = {
    role: set(LineCapability)
    for role in ("line_viewer", "line_agent", "line_manager", "system_admin")
}


def line_capabilities_for_role(role: str) -> tuple[str, ...]:
    capabilities = _ROLE_CAPABILITIES.get(role, set())
    return tuple(sorted(capability.value for capability in capabilities))


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
    "line_capabilities_for_role",
    "require_line_capability",
]
