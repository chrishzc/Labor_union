"""Focused regression for Scheduling-owned staff-leave review boundaries."""

import pytest

from subsystems.line.webhook_identity_handlers import _identity_purpose_for_text
from domains.line.identity_flow import LineIdentityFlowPurpose


@pytest.mark.parametrize(
    ("command", "purpose"),
    [
        ("綁定訂單", LineIdentityFlowPurpose.CUSTOMER_BINDING),
        ("訂單查詢", LineIdentityFlowPurpose.CUSTOMER_BINDING),
        ("綁定後台帳號", LineIdentityFlowPurpose.ADMIN_BINDING),
    ],
)
def test_existing_identity_aliases_keep_binding_semantics(command, purpose):
    assert _identity_purpose_for_text(command) is purpose
