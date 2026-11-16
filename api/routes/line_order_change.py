"""Retired LINE order-change endpoint."""

from fastapi import APIRouter

from api.error_contracts import typed_http_error


router = APIRouter(prefix="/api/v1/line/order-change")


@router.post("/apply", include_in_schema=False)
def retired_order_change_ticket_apply():
    raise typed_http_error(
        410,
        "validation",
        "order_change_ticket_apply_retired",
        "如需變更訂單，請在 LINE 官方帳號聊天室留言，由工會專員協助。",
        "line-order-change:retired-apply",
    )
