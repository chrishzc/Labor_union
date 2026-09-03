from __future__ import annotations

import inspect

from api.dependencies.admin_auth import require_persisted_admin, require_system_admin
from api.routes.order_intake_terms_bootstrap import (
    apply_order_intake_client_name,
    apply_order_intake_completion,
    apply_order_intake_terms_bootstrap,
    preview_order_intake_client_name,
    preview_order_intake_completion,
    preview_order_intake_terms_bootstrap,
)


def test_intake_repair_endpoints_require_persisted_user_not_system_admin():
    endpoints = (
        preview_order_intake_terms_bootstrap,
        apply_order_intake_terms_bootstrap,
        preview_order_intake_client_name,
        apply_order_intake_client_name,
        preview_order_intake_completion,
        apply_order_intake_completion,
    )

    for endpoint in endpoints:
        dependency = inspect.signature(endpoint).parameters["principal"].default.dependency
        assert dependency is require_persisted_admin
        assert dependency is not require_system_admin
