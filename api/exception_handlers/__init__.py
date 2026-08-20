"""
File: __init__.py
Description: 匯出受控管理端 FastAPI typed error 與 correlation 邊界。
"""

from api.exception_handlers.typed_errors import (
    CorrelationBoundaryMiddleware,
    install_typed_error_handlers,
)

__all__ = ["CorrelationBoundaryMiddleware", "install_typed_error_handlers"]
