"""Retired LINE review compatibility routes; canonical identity reviews replace them."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException


router = APIRouter(prefix="/api/v1/line/review-requests", tags=["Retired LINE Reviews"])


@router.api_route(
    "",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
@router.api_route(
    "/{legacy_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    include_in_schema=False,
)
def retired_line_review_route(legacy_path: str = "") -> None:
    raise HTTPException(
        status_code=410,
        detail={
            "code": "legacy_line_review_route_retired",
            "message": "請改用 /api/v1/line/identity/reviews。",
            "replacement": "/api/v1/line/identity/reviews",
        },
    )


__all__ = ["router"]
