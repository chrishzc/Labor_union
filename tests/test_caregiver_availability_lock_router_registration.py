from api.main import app


EXPECTED_LOCK_POST_PATHS = {
    "/api/v1/orders/{case_no}/matching-plans/{plan_id}/availability-lock/acquire",
    "/api/v1/orders/{case_no}/matching-plans/{plan_id}/availability-locks/{lock_id}/release",
    "/api/v1/orders/{case_no}/availability-locks/{lock_id}/convert",
}


def test_caregiver_availability_lock_routes_are_registered_once():
    openapi_paths = app.openapi()["paths"]
    runtime_routes = []
    for registered in app.routes:
        original_router = getattr(registered, "original_router", None)
        runtime_routes.extend(
            original_router.routes if original_router is not None else [registered]
        )

    for path in EXPECTED_LOCK_POST_PATHS:
        assert path in openapi_paths
        assert "post" in openapi_paths[path]

        matching_routes = [
            route
            for route in runtime_routes
            if getattr(route, "path_format", None) == path
            and "POST" in getattr(route, "methods", set())
        ]
        assert len(matching_routes) == 1


def test_caregiver_availability_lock_router_does_not_register_cancellation():
    lock_paths = {
        path
        for path in app.openapi()["paths"]
        if "availability-lock" in path
    }

    assert all("cancel" not in path for path in lock_paths)
