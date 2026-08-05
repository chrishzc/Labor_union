"""Internal typed API for the canonical Orders service-completion command."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.order_auto_completion import (
    OrderAutoCompletionApplication,
    get_order_auto_completion_application,
)
from api.schemas.base import BaseResponse
from api.schemas.order_auto_completion import OrderAutoCompletionReceiptView
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.auto_completion_workflow import (
    AutoCompletionApplyRequest,
    AutoCompletionWorkflowError,
)

router = APIRouter(prefix="/api/v1/orders", tags=["Order Service Completion"])


class OrderAutoCompletionApplyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_order_version: int = Field(ge=0)
    evaluation_at: datetime
    reason: str = Field(min_length=1, max_length=500)


@router.post("/{case_no}/service-completion/apply", response_model=BaseResponse[OrderAutoCompletionReceiptView])
def apply_order_auto_completion(
    body: OrderAutoCompletionApplyBody,
    case_no: str = Path(..., min_length=1, max_length=50),
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=191)] = ...,
    correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=1, max_length=191)] = ...,
    principal: AdminPrincipal = Depends(require_system_admin),
    application: OrderAutoCompletionApplication = Depends(get_order_auto_completion_application),
):
    request = AutoCompletionApplyRequest(case_no, ExpectedVersion(body.expected_order_version), body.evaluation_at, IdempotencyKey(idempotency_key), ActorContext(str(principal.username or "").strip()), body.reason, CorrelationId(correlation_id))
    try:
        return BaseResponse(data=application.apply(request), message="成功記錄服務完成")
    except AutoCompletionWorkflowError as error:
        raise _typed_http_error(error.error) from error
    except ValueError as error:
        typed = TypedError(ErrorCategory.VALIDATION, str(error) or "auto_completion_validation_error", "服務完成請求未通過驗證。", request.correlation_id)
        raise _typed_http_error(typed) from error


def _typed_http_error(error):
    status = 409 if error.category in {ErrorCategory.DOMAIN_BLOCKED, ErrorCategory.CONFLICT, ErrorCategory.IDEMPOTENCY_MISMATCH} else 422
    if error.category is ErrorCategory.INTERNAL:
        status = 500
    return HTTPException(status_code=status, detail={"error": {"category": error.category.value, "code": error.code, "message": error.message, "correlation_id": error.correlation_id.value, "domain_blockers": list(error.domain_blockers)}})
