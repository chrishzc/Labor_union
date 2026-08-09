from datetime import datetime, timedelta

import pytest

from infrastructure.mysql.admin_capability_grant_repository import (
    CapabilityGrantCommand,
    CapabilityGrantError,
    _event_type,
    _validate_command,
)
from subsystems.access.authentication_session import AdminPrincipal, has_required_capability


def _command(**overrides):
    values = {
        "target_admin_user_id": 9,
        "capability": "knowledge.source.review",
        "action": "grant",
        "expected_authorization_version": 2,
        "reason": "代理覆核補助公告",
        "idempotency_key": "grant-9-review-1",
        "correlation_id": "corr-9",
        "expires_at": datetime.now() + timedelta(days=14),
    }
    values.update(overrides)
    return CapabilityGrantCommand(**values)


def test_dynamic_grant_requires_expiry_and_known_capability():
    actor = AdminPrincipal(1, "sysadmin", "系統管理員", "system_admin")
    with pytest.raises(CapabilityGrantError, match="grant_expiry_required"):
        _validate_command(_command(expires_at=None), actor)
    with pytest.raises(CapabilityGrantError, match="unknown_capability"):
        _validate_command(_command(capability="invented.capability"), actor)


def test_effective_principal_uses_persisted_grant_overlay_not_role_hierarchy():
    reviewer = AdminPrincipal(
        9, "temp-reviewer", "代理覆核", "line_agent",
        capabilities=frozenset({"line.identity.read", "knowledge.source.review"}),
    )

    assert has_required_capability(reviewer, "knowledge.source.review")
    assert not has_required_capability(reviewer, "knowledge.source.publish")
    assert _event_type("grant") == "capability_granted"
    assert _event_type("revoke") == "capability_revoked"
