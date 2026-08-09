"""Internal service-key and administrator-session dependencies."""

from __future__ import annotations

import hmac
import os
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, Request, status

from shared_kernel.identities import ActorContext
from subsystems.access.authentication_session import (
    AdminPrincipal,
    get_admin_session,
    has_required_role,
)
from subsystems.line.capabilities import (
    LineCapability,
    line_capabilities_for_role,
)
from subsystems.access.integration_capabilities import (
    IntegrationCapability,
    integration_capabilities_for_role,
)


DEVELOPMENT_ENVIRONMENTS = {"development", "dev", "local", "test"}


def admin_auth_is_enabled() -> bool:
    """Return False only for an explicit bypass in a development environment."""
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    configured = os.getenv("ENABLE_ADMIN_AUTH", "true").strip().lower()
    requested_bypass = configured in {"0", "false", "no", "off"}
    return not (app_env in DEVELOPMENT_ENVIRONMENTS and requested_bypass)


def require_internal_service(
    x_internal_api_key: str | None = Header(default=None, alias="X-Internal-API-Key"),
) -> None:
    expected = os.getenv("INTERNAL_API_KEY", "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="INTERNAL_API_KEY 尚未設定",
        )
    if not x_internal_api_key or not hmac.compare_digest(x_internal_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="內部服務金鑰錯誤",
        )


def get_bearer_token(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少有效的管理員 Session",
        )
    return token.strip()


def require_admin(
    request: Request,
    authorization: str | None = Header(default=None),
    _: None = Depends(require_internal_service),
) -> AdminPrincipal:
    if not admin_auth_is_enabled():
        principal = AdminPrincipal(
            id=None,
            username="development-bypass",
            display_name="開發模式管理員",
            role="system_admin",
        )
        request.state.admin_principal = principal
        request.state.admin_auth_bypassed = True
        return principal

    token = get_bearer_token(authorization)
    principal = get_admin_session(token)
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="管理員 Session 已失效或過期",
        )
    request.state.admin_principal = principal
    request.state.admin_session_token = token
    return principal


def require_role(minimum_role: str) -> Callable[..., AdminPrincipal]:
    def dependency(principal: AdminPrincipal = Depends(require_admin)) -> AdminPrincipal:
        if not has_required_role(principal, minimum_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"需要 {minimum_role} 或更高權限",
            )
        return principal

    return dependency


def admin_actor_context(principal: AdminPrincipal) -> ActorContext:
    actor_id = f"admin:{principal.id}" if principal.id is not None else "admin:development"
    return ActorContext(actor_id, line_capabilities_for_role(principal.role))


def require_capability(capability: LineCapability) -> Callable[..., AdminPrincipal]:
    def dependency(
        request: Request,
        principal: AdminPrincipal = Depends(require_admin),
    ) -> AdminPrincipal:
        scope = line_capabilities_for_role(principal.role)
        if capability.value not in scope:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"缺少操作權限：{capability.value}",
            )
        request.state.admin_actor = admin_actor_context(principal)
        return principal

    return dependency


def require_integration_capability(
    capability: IntegrationCapability,
) -> Callable[..., AdminPrincipal]:
    def dependency(principal: AdminPrincipal = Depends(require_admin)) -> AdminPrincipal:
        scope = integration_capabilities_for_role(principal.role)
        if capability.value not in scope:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"缺少操作權限：{capability.value}",
            )
        return principal

    return dependency


require_line_viewer = require_role("line_viewer")
require_line_agent = require_role("line_agent")
require_line_manager = require_role("line_manager")
require_system_admin = require_role("system_admin")
require_line_identity_reader = require_capability(LineCapability.IDENTITY_READ)
require_line_identity_reviewer = require_capability(LineCapability.IDENTITY_REVIEW)
require_line_task_reader = require_capability(LineCapability.TASK_READ)
require_line_task_controller = require_capability(LineCapability.TASK_CONTROL)
require_line_configuration_reader = require_capability(LineCapability.CONFIG_READ)
require_line_configuration_manager = require_capability(LineCapability.CONFIG_MANAGE)
require_line_menu_publisher = require_capability(LineCapability.MENU_PUBLISH)
require_line_order_group_reader = require_capability(LineCapability.ORDER_GROUP_READ)
require_line_order_group_binder = require_capability(LineCapability.ORDER_GROUP_BIND)
require_line_monitor_reader = require_capability(LineCapability.MONITOR_READ)
require_line_alert_manager = require_capability(LineCapability.ALERT_MANAGE)
require_line_matching_reader = require_capability(LineCapability.MATCHING_READ)
require_line_matching_sender = require_capability(LineCapability.MATCHING_SEND)
require_line_matching_override = require_capability(LineCapability.MATCHING_OVERRIDE)
require_contract_evidence_reader = require_integration_capability(
    IntegrationCapability.CONTRACT_EVIDENCE_READ
)
require_contract_evidence_manager = require_integration_capability(
    IntegrationCapability.CONTRACT_EVIDENCE_MANAGE
)
require_knowledge_reader = require_integration_capability(
    IntegrationCapability.KNOWLEDGE_READ
)
require_knowledge_manager = require_integration_capability(
    IntegrationCapability.KNOWLEDGE_MANAGE
)
require_knowledge_publisher = require_integration_capability(
    IntegrationCapability.KNOWLEDGE_PUBLISH
)
require_knowledge_reindexer = require_integration_capability(
    IntegrationCapability.KNOWLEDGE_REINDEX
)
