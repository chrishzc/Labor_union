"""Task 97 regression for bounded public and private health projections."""

import pytest
from pydantic import ValidationError

from api.main import app
from api.schemas.base import BaseResponse
from api.schemas.runtime_health import ApiHealthView, PrivateRuntimeCheckView


def test_public_health_route_uses_a_closed_response_view() -> None:
    health_route = next(
        route for route in app.routes if getattr(route, "path", None) == "/health"
    )

    assert health_route.response_model == BaseResponse[ApiHealthView]
    with pytest.raises(ValidationError):
        ApiHealthView.model_validate(
            {
                "status": "healthy",
                "service": "Labor Union API",
                "unexpected": True,
            }
        )


def test_private_runtime_check_view_rejects_unbounded_fields() -> None:
    with pytest.raises(ValidationError):
        PrivateRuntimeCheckView.model_validate(
            {
                "status": "ready",
                "service": "durable-job-worker",
                "unexpected": True,
            }
        )
