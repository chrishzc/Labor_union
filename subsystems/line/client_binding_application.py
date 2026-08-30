"""Retired legacy client-binding adapter.

The canonical LIFF Preview→Apply workflow owns identity bindings and owner
projections.  This module remains as a compatibility symbol only so callers
receive a deterministic failure instead of silently writing ``clients``.
"""

from __future__ import annotations

from typing import Any


class LegacyClientBindingRetiredError(RuntimeError):
    """Raised when a caller attempts to use the pre-canonical binding flow."""

    code = "legacy_client_binding_retired"


def bind_client(
    connection,
    *,
    name: str,
    phone: str,
    line_user_id: str,
    force_rebind: bool,
    unit_of_work_factory: Any = None,
) -> dict:
    """Fail closed until a canonical verified LIFF Apply caller is supplied."""
    raise LegacyClientBindingRetiredError(
        "use /api/v1/line/identity/customer/preview and /customer/apply"
    )


__all__ = ["LegacyClientBindingRetiredError", "bind_client"]
