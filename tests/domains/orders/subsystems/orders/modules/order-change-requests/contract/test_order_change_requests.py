"""Orders-owned application handling through the authenticated admin router."""

from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api.dependencies.admin_auth import require_persisted_admin, require_system_admin
from api.routes.line_order_change import (
    admin_router,
    complete_order_change_request,
    list_order_change_requests,
    retired_order_change_ticket_apply,
)
from api.schemas.line_order_change import OrderChangeRequestCompletionBody
from domains.orders.order_change_request import (
    CustomerOrderChangeKind,
    OrderChangeCompletion,
    OrderChangeRequest,
)
from subsystems.orders.order_change_requests import OrderChangeRequestsApplication


_STAMP = datetime(2026, 11, 15, tzinfo=timezone.utc)
_REQUEST = OrderChangeRequest(
    31, "CASE-001", CustomerOrderChangeKind.OTHER, {}, {"details": "調整服務"},
    _STAMP, "fingerprint", None,
)


class _Fixtures:
    def __init__(self):
        self.requests = {31: _REQUEST}
        self.customer_order_changes = self
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        self.commits += 1

    def list_requests(self, *, case_no, pending_only, before_id, limit):
        return tuple(item for item in self.requests.values()
                     if (case_no is None or item.case_no == case_no)
                     and (not pending_only or item.completion is None)
                     and (before_id is None or item.request_id < before_id))[:limit]

    def load_request(self, request_id, *, lock):
        assert lock
        return self.requests.get(request_id)

    def complete_request(self, request_id, *, actor_id, actor_name, result):
        updated = replace(
            self.requests[request_id], completion=OrderChangeCompletion(result, actor_id, actor_name, _STAMP),
        )
        self.requests[request_id] = updated
        return updated


def test_admin_completion_is_read_back_once_and_remains_in_case_history():
    fixtures = _Fixtures()
    application = OrderChangeRequestsApplication(lambda: fixtures)
    complete_route = next(route for route in admin_router.routes if route.endpoint is complete_order_change_request)
    assert {dep.call for dep in complete_route.dependant.dependencies} >= {require_system_admin, require_persisted_admin}

    principal = SimpleNamespace(id=5, username="operator")
    first_page = list_order_change_requests(application=application).data
    assert first_page["items"][0]["status"] == "pending"

    body = OrderChangeRequestCompletionBody(expected_version=0, result="已和客戶確認")
    observed = complete_order_change_request(31, body, principal, application).data
    assert observed["completion"]["result"] == body.result
    assert observed["completion"]["actor_name"] == "operator"
    assert observed["completion"]["completed_at"] == _STAMP
    assert observed["version"] == 1
    assert complete_order_change_request(31, body, principal, application).data == observed

    with pytest.raises(HTTPException) as conflict:
        complete_order_change_request(31, body.model_copy(update={"result": "其他結果"}), principal, application)
    assert conflict.value.status_code == 409
    assert list_order_change_requests(application=application).data["items"] == []
    assert list_order_change_requests(case_no="CASE-001", application=application).data["items"] == [observed]
    assert list_order_change_requests(case_no="OTHER", application=application).data["items"] == []
    assert fixtures.commits == 1


def test_legacy_liff_apply_is_gone_before_any_dependencies_or_writes():
    with pytest.raises(HTTPException) as response:
        retired_order_change_ticket_apply()
    assert response.value.status_code == 410
    assert response.value.detail["error"]["code"] == "order_change_ticket_apply_retired"
