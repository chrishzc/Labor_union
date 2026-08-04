"""Shared typed HTTP error contracts for thin API query boundaries."""

from __future__ import annotations

from fastapi import HTTPException


def typed_http_error(
    status_code: int,
    category: str,
    code: str,
    message: str,
    correlation_id: str,
    *,
    retryable: bool = False,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error": {
                "category": category,
                "code": code,
                "message": message,
                "correlation_id": correlation_id,
                "field_errors": [],
                "domain_blockers": [],
                "retryable": retryable,
                "current_version": None,
            }
        },
    )


def internal_query_error(
    code: str,
    message: str,
    correlation_id: str,
) -> HTTPException:
    return typed_http_error(500, "internal", code, message, correlation_id)
