import pytest
from fastapi import HTTPException

from api.routes.orders import update_order_full_details


def test_full_details_entry_is_a_typed_gone_boundary_with_replacements():
    with pytest.raises(HTTPException) as raised:
        update_order_full_details("CASE-001")

    assert raised.value.status_code == 410
    assert raised.value.detail == {
        "code": "legacy_order_full_details_endpoint_retired",
        "preview_path": "/api/v1/orders/CASE-001/client-name/preview",
        "apply_path": "/api/v1/orders/CASE-001/client-name/apply",
    }
