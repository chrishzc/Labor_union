"""Restore NAS LIFF operations while keeping management DB credentials private."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from api.dependencies.internal_service_auth import require_internal_service, require_operation_service
from api.error_contracts import typed_http_error
from api.routes import (
    line_candidate_contact, line_deposit_payment, line_feedback, line_mobile_admin,
    line_mobile_staff_leave_coordination, line_service_help, notification_task_actions,
)
from infrastructure.http.line_operations_client import LineOperationsClient, LineOperationsUnavailable, PREFIX
from infrastructure.runtime.worker_credentials import LINE_OPERATIONS_SERVICE


def get_line_operations_client():
    try:
        return LineOperationsClient.from_environment()
    except (LineOperationsUnavailable, ValueError):
        raise typed_http_error(503, "unavailable", "line_operations_configuration_unavailable",
                               "LINE 功能的私人服務尚未設定完成", "line-operations", retryable=False) from None


def require_private_line_operations(principal=Depends(require_internal_service)):
    if principal.authentication_method != "nas_service_token":
        raise typed_http_error(403, "forbidden", "line_operations_machine_auth_required",
                               "此服務需要獨立機器憑證", "line-operations")
    require_operation_service(principal, LINE_OPERATIONS_SERVICE)


async def forward_line_operation(request: Request, client=Depends(get_line_operations_client)):
    try:
        response = await client.request(request.method, request.url.path,
                                        content=await request.body(), headers=request.headers,
                                        params=request.query_params.multi_items())
    except LineOperationsUnavailable:
        raise typed_http_error(503, "unavailable", "line_operations_unavailable",
                               "LINE 功能暫時無法連線，請稍後重試", "line-operations", retryable=False) from None
    headers = {key: value for key, value in response.headers.items()
               if key.lower() in {"content-type", "x-correlation-id", "retry-after"}}
    headers["Cache-Control"] = "private, no-store"
    return Response(response.content, status_code=response.status_code, headers=headers)


# This is an explicit selection of the existing LIFF contracts, not a catch-all
# proxy to management URLs. Original handlers enforce LINE identity, current
# binding, capabilities, scope, versions and idempotency inside management-api.
_OPERATIONS = (
    line_candidate_contact.router, line_deposit_payment.router, line_service_help.public_router,
    line_feedback.router, line_mobile_admin.router, line_mobile_staff_leave_coordination.router,
    notification_task_actions.mobile_router,
)
private_router = APIRouter(prefix=PREFIX, include_in_schema=False,
                          dependencies=[Depends(require_private_line_operations)])
public_router = APIRouter()
for original in _OPERATIONS:
    private_router.include_router(original)
    for route in original.routes:
        public_router.add_api_route(route.path, forward_line_operation, methods=sorted(route.methods),
                                    name=route.name, include_in_schema=route.include_in_schema)
for pages in (line_candidate_contact.page_router, line_deposit_payment.page_router,
              line_service_help.page_router, line_mobile_admin.page_router):
    public_router.include_router(pages)
