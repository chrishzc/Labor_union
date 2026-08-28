"""
File: historical_completion.py
Description: 提供 authenticated HOB-E owner-terminal completion fresh Query API。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path

from api.dependencies.admin_auth import require_historical_order_review_remediator
from api.dependencies.historical_completion import (
    HistoricalCompletionApplication,
    get_historical_completion_application,
)
from api.schemas.base import BaseResponse
from api.schemas.historical_completion import HistoricalCompletionView
from shared_kernel.identities import CorrelationId
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.historical_completion_projector import (
    HistoricalCompletionTerminalProjection,
)
from subsystems.orders.historical_completion_query import HistoricalCompletionQueryError


router = APIRouter(prefix="/api/v1/orders", tags=["Orders"])
_CorrelationHeader = Annotated[
    str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)
]


@router.get(
    "/{case_no}/historical-completion",
    response_model=BaseResponse[HistoricalCompletionView],
)
def query_historical_completion(
    case_no: str = Path(..., min_length=1, max_length=50),
    correlation_id: _CorrelationHeader = "historical-completion-query",
    principal: AdminPrincipal = Depends(require_historical_order_review_remediator),
    application: HistoricalCompletionApplication = Depends(
        get_historical_completion_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    try:
        projection = application.query(case_no.strip(), correlation)
    except HistoricalCompletionQueryError as error:
        status = 409 if error.error.category.value == "conflict" else 422
        raise HTTPException(
            status_code=status,
            detail={
                "code": error.error.code,
                "message": error.error.message,
                "domain_blockers": list(error.error.domain_blockers),
                "correlation_id": error.error.correlation_id.value,
            },
        ) from error
    return BaseResponse(
        data=_projection_payload(projection),
        message="成功載入歷史案件 owner-terminal completion",
    )


def _projection_payload(
    projection: HistoricalCompletionTerminalProjection,
) -> dict[str, object]:
    return {
        "case_no": projection.case_no,
        "state": projection.state.value,
        "step_11_status": projection.step_11_status,
        "step_11_completed": projection.step_11_completed,
        "historical_alerts_completed": projection.historical_alerts_completed,
        "active_alerts": [
            {
                "code": alert.code,
                "owner": alert.owner.value,
                "field_path": alert.field_path,
                "referral": alert.referral.value,
                "message": alert.message,
            }
            for alert in projection.active_alerts
        ],
        "owner_versions": [
            {"owner": owner, "version": str(version)}
            for owner, version in projection.owner_versions
        ],
        "owner_source_versions": [
            {
                "kind": source.kind.value,
                "identity": source.identity,
                "version": str(source.version),
            }
            for source in projection.owner_source_versions
        ],
        "source_fingerprint": projection.source_fingerprint.value,
        "projection_fingerprint": projection.projection_fingerprint.value,
    }


__all__ = ["router"]
