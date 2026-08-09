import pytest
from fastapi import HTTPException

from api.routes.orders import get_all_orders


def test_full_order_list_is_gone_with_bounded_query_replacement() -> None:
    with pytest.raises(HTTPException) as raised:
        get_all_orders()

    assert raised.value.status_code == 410
    assert raised.value.detail == {
        "code": "legacy_order_full_list_endpoint_retired",
        "replacement": "/api/v1/orders/summaries",
        "message": "Use the bounded cursor-based order summary endpoint.",
    }
