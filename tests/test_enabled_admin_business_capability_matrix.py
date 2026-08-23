"""
File: test_enabled_admin_business_capability_matrix.py
Description: 驗證 enabled 內部使用者的 LINE／Knowledge 業務能力同權。
"""

from fastapi import HTTPException

from api.dependencies.admin_auth import require_root
from subsystems.access.authentication_session import (
    AdminPrincipal,
    has_required_capability,
)
from subsystems.access.integration_capabilities import IntegrationCapability
from subsystems.line.capabilities import LineCapability


ROLES = ("line_viewer", "line_agent", "line_manager", "system_admin")
BUSINESS_CAPABILITIES = tuple(
    sorted(
        {
            *(capability.value for capability in LineCapability),
            *(capability.value for capability in IntegrationCapability),
        }
    )
)


def test_enabled_internal_roles_share_line_and_knowledge_capabilities():
    principals = tuple(
        AdminPrincipal(index, role, role, role)
        for index, role in enumerate(ROLES, start=1)
    )
    projections = {principal.effective_capabilities() for principal in principals}

    assert len(projections) == 1
    for principal in principals:
        for capability in BUSINESS_CAPABILITIES:
            assert has_required_capability(principal, capability)


def test_non_root_enabled_user_cannot_enter_account_center():
    principal = AdminPrincipal(1, "operator", "Operator", "line_viewer")

    try:
        require_root(principal)
    except HTTPException as error:
        assert error.status_code == 403
    else:
        raise AssertionError("non-root enabled user must not enter Account Center")
