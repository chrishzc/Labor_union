from pymysql.err import OperationalError

from api.routes.order_auto_completion import _mysql_http_error, _typed_http_error
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import CorrelationId


def test_auto_completion_mysql_contention_is_retryable_unavailable():
    response = _mysql_http_error(
        OperationalError(1213, "deadlock"),
        CorrelationId("g05-api-contention"),
    )
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"


def test_auto_completion_conflict_maps_to_http_conflict():
    response = _typed_http_error(
        TypedError(
            ErrorCategory.CONFLICT,
            "order_version_conflict",
            "stale",
            CorrelationId("g05-api-conflict"),
        )
    )
    assert response.status_code == 409
