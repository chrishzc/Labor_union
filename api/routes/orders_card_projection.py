"""
File: orders_card_projection.py
Description: 提供案件範圍的 Orders 卡片 composite GET endpoint。
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, Depends, Path
from pymysql.err import OperationalError, ProgrammingError

from api.dependencies.admin_auth import require_system_admin
from api.error_contracts import internal_query_error, typed_http_error
from api.schemas.base import BaseResponse
from api.schemas.errors import GlobalTypedErrorResponseView
from api.schemas.orders_card_projection import OrdersCardProjectionView
from infrastructure.mysql.mysql_adapter import get_connection
from infrastructure.mysql.orders_card_projection_repository import (
    MySqlOrdersCardProjectionRepository,
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.card_projection_query import (
    OrdersCardProjectionContractError,
    OrdersCardProjectionNotFoundError,
    OrdersCardProjectionQueryService,
)


router = APIRouter(prefix="/api/v1/orders", tags=["Orders Card Projection"])


@dataclass(slots=True)
class OrdersCardProjectionApplication:
    service: OrdersCardProjectionQueryService

    def query(self, case_no: str):
        return self.service.query(case_no)


def get_orders_card_projection_application():
    """Construct one connection-scoped read application for FastAPI Depends."""
    connection = get_connection()
    try:
        yield OrdersCardProjectionApplication(
            OrdersCardProjectionQueryService(
                MySqlOrdersCardProjectionRepository(connection)
            )
        )
    finally:
        connection.close()


@router.get(
    "/{case_no}/card-projection",
    response_model=BaseResponse[OrdersCardProjectionView],
    responses={
        401: {"model": GlobalTypedErrorResponseView, "description": "需要有效的管理員驗證"},
        403: {"model": GlobalTypedErrorResponseView, "description": "目前身分無權查詢訂單卡片"},
        404: {"model": GlobalTypedErrorResponseView, "description": "訂單不存在"},
        409: {"model": GlobalTypedErrorResponseView, "description": "訂單卡片根事實不一致"},
        422: {"model": GlobalTypedErrorResponseView, "description": "查詢條件不符合公開契約"},
        500: {"model": GlobalTypedErrorResponseView, "description": "訂單卡片查詢失敗"},
        503: {"model": GlobalTypedErrorResponseView, "description": "訂單卡片資料暫時無法使用"},
    },
)
def get_orders_card_projection(
    case_no: str = Path(..., min_length=1, max_length=50),
    principal: AdminPrincipal = Depends(require_system_admin),
    application: OrdersCardProjectionApplication = Depends(
        get_orders_card_projection_application
    ),
):
    del principal
    try:
        result = application.query(case_no)
        return BaseResponse(
            data=OrdersCardProjectionView.model_validate(
                _materialize(result), from_attributes=True
            ),
            message="成功取得訂單卡片資料",
        )
    except OrdersCardProjectionNotFoundError as error:
        raise typed_http_error(
            404,
            "not_found",
            "orders_card_projection_not_found",
            "找不到指定案件的訂單卡片資料。",
            "orders-card-projection",
        ) from error
    except OrdersCardProjectionContractError as error:
        raise typed_http_error(
            409,
            "conflict",
            "orders_card_projection_invalid",
            "訂單卡片根事實無法產生一致投影。",
            "orders-card-projection",
        ) from error
    except (OperationalError, ProgrammingError) as error:
        mysql_code = int(error.args[0]) if error.args else 0
        retryable = mysql_code in {1205, 1213}
        raise typed_http_error(
            503 if retryable else 500,
            "unavailable" if retryable else "internal",
            (
                "orders_card_projection_temporarily_unavailable"
                if retryable
                else "orders_card_projection_database_error"
            ),
            "訂單卡片查詢暫時無法完成。" if retryable else "訂單卡片查詢資料庫錯誤。",
            "orders-card-projection",
            retryable=retryable,
        ) from error
    except ValueError as error:
        raise typed_http_error(
            422,
            "validation",
            "orders_card_projection_query_invalid",
            "訂單卡片查詢條件不正確。",
            "orders-card-projection",
        ) from error
    except Exception as error:
        raise internal_query_error(
            "orders_card_projection_internal_error",
            "訂單卡片查詢失敗。",
            "orders-card-projection",
        ) from error


def _materialize(result):
    """Convert the domain tuple to JSON-compatible list values without raw dicts."""
    payload = {
        "case_no": result.case_no,
        "contact_phone": result.contact_phone,
        "contact_address": result.contact_address,
        "requires_cooking": result.requires_cooking,
        "floor_fee_ntd": result.floor_fee_ntd,
        "deposit_amount_ntd": result.deposit_amount_ntd,
        "deposit_settlement_state": result.deposit_settlement_state,
        "deposit_settled_on": result.deposit_settled_on,
        "actual_start_date": result.actual_start_date,
        "actual_end_date": result.actual_end_date,
        "historical_source_start_date": result.historical_source_start_date,
        "historical_source_end_date": result.historical_source_end_date,
        "historical_paired_staff_name": result.historical_paired_staff_name,
        "assignment_segments": {
            **_field_payload(result.assignment_segments),
            "value": [
                {
                    field_name: _field_payload(getattr(segment, field_name))
                    for field_name in (
                        "assignment_id",
                        "staff_id",
                        "staff_name",
                        "sequence",
                        "assigned_start_date",
                        "assigned_end_date",
                        "status",
                    )
                }
                for segment in (result.assignment_segments.value or ())
            ]
            if result.assignment_segments.value is not None
            else None,
        },
    }
    for field_name in (
        "contact_phone",
        "contact_address",
        "requires_cooking",
        "floor_fee_ntd",
        "deposit_amount_ntd",
        "deposit_settlement_state",
        "deposit_settled_on",
        "actual_start_date",
        "actual_end_date",
        "historical_source_start_date",
        "historical_source_end_date",
        "historical_paired_staff_name",
    ):
        payload[field_name] = _field_payload(getattr(result, field_name))
    return payload


def _field_payload(field):
    return {
        "value": field.value,
        "owner": field.owner,
        "source_identity": field.source_identity,
        "source_version": field.source_version,
        "availability": field.availability,
        "availability_reason": field.availability_reason,
    }


__all__ = [
    "OrdersCardProjectionApplication",
    "get_orders_card_projection",
    "get_orders_card_projection_application",
    "router",
]
