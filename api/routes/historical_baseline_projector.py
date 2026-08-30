"""Stable retirement boundary for the former Anomalies historical projector URLs."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path

from api.dependencies.admin_auth import require_historical_order_review_remediator
from shared_kernel.identities import CorrelationId
from subsystems.access.authentication_session import AdminPrincipal


router = APIRouter(prefix="/api/v1/orders", tags=["Orders"])
_CorrelationHeader = Annotated[
    str | None,
    Header(alias="X-Correlation-ID", min_length=1, max_length=191),
]
_REPLACEMENT = "/api/v1/orders/{case_no}/historical-operational-baseline"


@router.get(
    "/{case_no}/historical-baseline-projector",
    response_model=None,
    deprecated=True,
    include_in_schema=False,
)
def query_latest_historical_baseline_projection(
    case_no: str = Path(..., min_length=1, max_length=50, pattern=r"^[^\s]+$"),
    correlation_header: _CorrelationHeader = None,
    principal: AdminPrincipal = Depends(require_historical_order_review_remediator),
) -> None:
    del principal
    raise _retired_error(
        CorrelationId(
            correlation_header or f"legacy-historical-baseline-projector:{case_no}"
        ),
        _REPLACEMENT.format(case_no=case_no),
    )


@router.get(
    "/historical-baseline-projector/deliveries/{delivery_identity}",
    response_model=None,
    deprecated=True,
    include_in_schema=False,
)
def query_historical_baseline_projection_delivery(
    delivery_identity: str = Path(..., pattern=r"^[0-9a-f]{64}$"),
    correlation_header: _CorrelationHeader = None,
    principal: AdminPrincipal = Depends(require_historical_order_review_remediator),
) -> None:
    del principal, delivery_identity
    raise _retired_error(
        CorrelationId(correlation_header or "legacy-historical-baseline-delivery"),
        _REPLACEMENT.format(case_no="{case_no}"),
    )


def _retired_error(correlation: CorrelationId, replacement: str) -> HTTPException:
    """Keep old URLs stable while directing callers to the owning Orders Query."""
    return HTTPException(
        status_code=410,
        detail={
            "error": {
                "category": "domain_blocked",
                "code": "historical_baseline_projector_endpoint_retired",
                "message": "歷史基線 projector 已由 Orders 作業基準 Query 取代。",
                "correlation_id": correlation.value,
                "field_errors": [],
                "domain_blockers": [f"replacement_identifier:{replacement}"],
                "retryable": False,
                "current_version": None,
            }
        },
    )


__all__ = [
    "query_historical_baseline_projection_delivery",
    "query_latest_historical_baseline_projection",
    "router",
]
