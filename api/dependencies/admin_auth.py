"""
File: admin_auth.py
Description: 管理後台 Bearer Session、業務能力與 root 帳號中心授權依賴。
"""

from __future__ import annotations

import os
from collections.abc import Callable

from fastapi import Depends, Header, HTTPException, Request, status

from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.identities import ActorContext
from subsystems.access.authentication_session import (
    AdminPrincipal,
    AdminSessionStorageError,
    ConnectionFactory,
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

ACCESS_CONTROL_PROFILES = frozenset(
    {"local_bypass", "local_auth", "local_developer_session", "production"}
)


def get_access_control_connection_factory() -> ConnectionFactory:
    """Compose the production connection provider at the API boundary."""
    return get_connection


def access_control_profile() -> str:
    """Return the explicit auth profile; an absent or invalid profile fails closed."""
    profile = os.getenv("ACCESS_CONTROL_PROFILE", "").strip().lower()
    return profile if profile in ACCESS_CONTROL_PROFILES else "production"


def admin_auth_is_enabled() -> bool:
    """Return False only for the named local_bypass profile with both safeguards."""
    app_env = os.getenv("APP_ENV", "").strip().lower()
    configured = os.getenv("ENABLE_ADMIN_AUTH", "true").strip().lower()
    requested_bypass = configured in {"0", "false", "no", "off"}
    return not (
        access_control_profile() == "local_bypass"
        and app_env in DEVELOPMENT_ENVIRONMENTS
        and requested_bypass
    )


def ensure_development_root_admin() -> None:
    """開發環境啟動時自動確認並建立 root 管理員帳號與預設 TOTP factor，防止重啟後無法登入。"""
    if os.getenv("APP_ENV", "").strip().lower() not in DEVELOPMENT_ENVIRONMENTS:
        return
    username = os.getenv("DEV_ROOT_USERNAME", "").strip()
    password = os.getenv("DEV_ROOT_PASSWORD", "").strip()
    if not username or not password:
        return
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM admin_users WHERE username=%s", (username.lower(),))
            user = cursor.fetchone()
            if user is None:
                from subsystems.access.authentication_session import (
                    bootstrap_root_admin,
                    totp_cipher_from_environment,
                )
                import hashlib
                admin_id = bootstrap_root_admin(
                    connection_factory=get_connection,
                    username=username,
                    password=password,
                    display_name="系統最高管理員",
                )
                totp_secret = "WWTMUTCHGVOQ3MK6JPOV4KLRYGR3IN5R"
                try:
                    cipher = totp_cipher_from_environment()
                    encrypted = cipher.encrypt(totp_secret)
                    dummy_hash = hashlib.sha256(b"initial_enrollment").hexdigest()
                    cursor.execute(
                        """
                        INSERT INTO admin_totp_factors (
                            admin_user_id, factor_state, seed_ciphertext, encryption_key_version,
                            enrollment_challenge_hash, enrollment_expires_at,
                            activated_at, created_at, updated_at
                        ) VALUES (%s, 'active', %s, %s, %s, UTC_TIMESTAMP(6), UTC_TIMESTAMP(6), UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))
                        """,
                        (admin_id, encrypted.ciphertext, encrypted.key_version, dummy_hash),
                    )
                    conn.commit()
                except Exception:
                    pass
        conn.close()
    except Exception:
        pass


def ensure_development_line_configuration() -> None:
    """開發環境啟動時自動確認並初始化 6 大基準 LINE 設定（Rich Menu、通知規則、LIFF等），防止空設定。"""
    if os.getenv("APP_ENV", "").strip().lower() not in DEVELOPMENT_ENVIRONMENTS:
        return
    try:
        from pathlib import Path
        import json
        from domains.line.configuration import LineConfigurationKind
        from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
        from shared_kernel.identities import ActorContext, CorrelationId
        from subsystems.line.capabilities import LineCapability
        from subsystems.line.configuration_application import LineConfigurationApplication

        root = Path(__file__).resolve().parents[2]
        config_files = {
            LineConfigurationKind.MESSAGE_TEMPLATES: root / "config" / "message_templates.json",
            LineConfigurationKind.MESSAGE_SCHEDULES: root / "config" / "message_schedules.json",
            LineConfigurationKind.RICH_MENUS: root / "config" / "line_menu.json",
            LineConfigurationKind.LIFF: root / "config" / "liff_settings.json",
            LineConfigurationKind.CUSTOMER_SERVICE: root / "config" / "customer_service.json",
            LineConfigurationKind.NOTIFICATION_RULES: root / "config" / "notification_rules.json",
        }
        definitions = {
            kind: json.loads(path.read_text(encoding="utf-8"))
            for kind, path in config_files.items()
            if path.is_file()
        }
        if len(definitions) == len(config_files):
            actor = ActorContext(
                "system:line-configuration-bootstrap",
                tuple(sorted({LineCapability.CONFIG_MANAGE.value})),
            )
            app = LineConfigurationApplication(open_line_unit_of_work)
            app.bootstrap_missing(
                definitions,
                actor,
                reason="開發環境自動初始化基準設定",
                correlation_id=CorrelationId("line-configuration-bootstrap"),
            )
    except Exception:
        pass


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
    connection_factory: ConnectionFactory = Depends(get_access_control_connection_factory),
) -> AdminPrincipal:
    if not admin_auth_is_enabled():
        principal = _development_bypass_principal()
        request.state.admin_principal = principal
        request.state.admin_auth_bypassed = True
        return principal

    token = get_bearer_token(authorization)
    try:
        principal = get_admin_session(token, connection_factory=connection_factory)
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
        is_root=True,
    )


def require_root(principal: AdminPrincipal = Depends(require_admin)) -> AdminPrincipal:
    """Allow the sole root fact holder to access Account Center only."""
    if principal.id is None or not principal.is_root:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="僅 root 帳號可管理帳號中心",
        )
    return principal


def require_persisted_admin(
    request: Request,
    principal: AdminPrincipal = Depends(require_admin),
) -> AdminPrincipal:
    """Require an enabled, persisted human session for durable business commands."""
    local_bypass = (
        not admin_auth_is_enabled()
        and principal.id is None
        and principal.username == "development-bypass"
        and principal.role == "system_admin"
    )
    if (principal.id is None and not local_bypass) or not principal.enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要已登入且啟用的內部使用者 Session",
        )
    request.state.admin_actor = admin_actor_context(principal)
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
    if principal.id is not None:
        actor_id = f"admin:{principal.id}"
    elif (
        not admin_auth_is_enabled()
        and principal.username == "development-bypass"
        and principal.role == "system_admin"
    ):
        actor_id = "system:local_bypass"
    else:
        actor_id = "admin:development"
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
require_historical_order_review_remediator = require_capability(
    "orders.historical_review.remediate"
)
