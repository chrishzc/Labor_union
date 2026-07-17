"""Backward-compatible imports for the former ASGI module.

New deployments must use ``api.main:app``.  This shim keeps older tests and
local integrations working while the LINE routes live in ``line.line_bot``.
"""

from api.main import app
from line.line_bot import ensure_order_for_case_no

__all__ = ["app", "ensure_order_for_case_no"]
