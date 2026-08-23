"""
File: test_non_line_typed_projection_openapi.py
Description: 驗證四個非 LINE typed GET 的成功、驗證、授權與失敗狀態皆有 OpenAPI 契約。
"""

from api.routes.orders_card_projection import router as orders_card_router
from api.routes.orders_stage_projection import router as orders_stage_router
from api.routes.scheduling_eligibility_collision import router as scheduling_router
from api.routes.staff_qualification_master import router as staff_router


def _get_route(router, path: str):
    return next(route for route in router.routes if route.path == path)


def test_non_line_typed_projection_gets_declare_every_runtime_status() -> None:
    cases = (
        (
            _get_route(orders_stage_router, "/api/orders/operational-timelines"),
            {304, 401, 403, 409, 422, 500, 503},
        ),
        (
            _get_route(orders_card_router, "/api/v1/orders/{case_no}/card-projection"),
            {401, 403, 404, 409, 422, 500, 503},
        ),
        (
            _get_route(scheduling_router, "/api/v1/scheduling/eligibility-collisions"),
            {401, 403, 404, 409, 422, 500, 503},
        ),
        (
            _get_route(staff_router, "/api/v1/staff/{staff_id}/qualification-master"),
            {401, 403, 404, 422, 500, 503},
        ),
    )

    for route, expected_statuses in cases:
        assert route.methods == {"GET"}
        assert expected_statuses <= set(route.responses)
        for status_code in expected_statuses - {304}:
            assert route.responses[status_code].get("model") is not None
