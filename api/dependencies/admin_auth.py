"""Internal service-key and administrator-session dependencies."""

from __future__ import annotations

import hmac
import os
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, Request, status

from shared_kernel.identities import ActorContext
from subsystems.access.authentication_session import (
    AdminPrincipal,
    AdminSessionStorageError,
    get_admin_session,
    has_required_capability,
    has_required_role,
)
from subsystems.line.capabilities import LineCapability
from subsystems.access.integration_capabilities import IntegrationCapability


DEVELOPMENT_ENVIRONMENTS = {"development", "dev", "local", "test"}
DEVELOPMENT_BYPASS_DENIED_CAPABILITIES = frozenset(
    {"line.menu.publish", "line.rich_menu.publish"}
)


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
        principal = _development_bypass_principal()
        request.state.admin_principal = principal
        request.state.admin_auth_bypassed = True
        return principal

    token = get_bearer_token(authorization)
    try:
        principal = get_admin_session(token)
    except AdminSessionStorageError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "admin_session_storage_unavailable",
                "message": str(error),
                "retryable": True,
            },
        ) from error
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="管理員 Session 已失效或過期",
        )
    request.state.admin_principal = principal
    request.state.admin_session_token = token
    return principal


def _development_bypass_principal() -> AdminPrincipal:
    base = AdminPrincipal(None, "development-bypass", "開發模式管理員", "system_admin")
    capabilities = frozenset(
        base.effective_capabilities() - DEVELOPMENT_BYPASS_DENIED_CAPABILITIES
    )
    return AdminPrincipal(
        base.id,
        base.username,
        base.display_name,
        base.role,
        capabilities=capabilities,
    )


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
    return ActorContext(actor_id, tuple(sorted(principal.effective_capabilities())))


def require_capability(
    capability: str | LineCapability | IntegrationCapability,
) -> Callable[..., AdminPrincipal]:
    capability_name = str(capability.value if hasattr(capability, "value") else capability)

    def dependency(
        request: Request,
        principal: AdminPrincipal = Depends(require_admin),
    ) -> AdminPrincipal:
        if not has_required_capability(principal, capability_name):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"缺少必要能力：{capability_name}",
            )
        request.state.admin_actor = admin_actor_context(principal)
        return principal

    return dependency


def require_integration_capability(
    capability: IntegrationCapability,
) -> Callable[..., AdminPrincipal]:
    return require_capability(capability)


require_line_viewer = require_capability("line.identity.read")
require_line_agent = require_capability("line.review.read")
require_line_manager = require_capability("system.configuration.manage")
require_line_identity_reader = require_capability(LineCapability.IDENTITY_READ)
require_line_identity_reviewer = require_capability(LineCapability.IDENTITY_REVIEW)
require_line_review_reader = require_capability(LineCapability.REVIEW_READ)
require_line_review_decider = require_capability(LineCapability.REVIEW_DECIDE)
require_line_task_reader = require_capability(LineCapability.TASK_READ)
require_line_task_controller = require_capability(LineCapability.TASK_CONTROL)
require_line_configuration_reader = require_capability(LineCapability.CONFIG_READ)
require_line_configuration_manager = require_capability(LineCapability.CONFIG_MANAGE)
require_line_menu_publisher = require_capability(LineCapability.MENU_PUBLISH)
require_line_order_group_reader = require_capability(LineCapability.ORDER_GROUP_READ)
require_line_order_group_binder = require_capability(LineCapability.ORDER_GROUP_BIND)
require_line_monitor_reader = require_capability(LineCapability.MONITOR_READ)
require_line_alert_manager = require_capability(LineCapability.ALERT_MANAGE)
require_line_audit_reader = require_capability(LineCapability.AUDIT_READ)
require_line_matching_reader = require_capability(LineCapability.MATCHING_READ)
require_line_matching_sender = require_capability(LineCapability.MATCHING_SEND)
require_line_matching_override = require_capability(LineCapability.MATCHING_OVERRIDE)
require_customer_service_reader = require_capability(LineCapability.CUSTOMER_SERVICE_READ)
require_customer_service_handler = require_capability(LineCapability.CUSTOMER_SERVICE_HANDLE)
require_line_identity_binding_reader = require_capability(
    LineCapability.IDENTITY_BINDING_READ
)
require_line_identity_binding_manager = require_capability(
    LineCapability.IDENTITY_BINDING_MANAGE
)
require_line_identity_binding_override = require_capability(
    LineCapability.IDENTITY_BINDING_OVERRIDE
)
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
require_system_config_manager = require_capability("system.configuration.manage")
require_system_admin = require_capability("system.administration")
