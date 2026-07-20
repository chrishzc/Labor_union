from fastapi import HTTPException
import pytest

from api.routes import finance_alerts


class Cursor:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class Connection:
    def __init__(self):
        self.cursor_value = Cursor()
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def _connection(monkeypatch):
    connection = Connection()
    monkeypatch.setattr(finance_alerts, "get_connection", lambda: connection)
    return connection


def test_list_and_detail_delegate_to_workflow_service(monkeypatch):
    connection = _connection(monkeypatch)
    observed = {}
    alert = {"id": 41, "status": "open", "events": [{"id": 91}]}

    def list_service(cursor, **kwargs):
        observed["list"] = (cursor, kwargs)
        return [alert]

    def detail_service(cursor, alert_id):
        observed["detail"] = (cursor, alert_id)
        return alert

    monkeypatch.setattr(finance_alerts, "list_finance_alerts", list_service)
    monkeypatch.setattr(finance_alerts, "get_finance_alert", detail_service)

    listed = finance_alerts.list_alerts(
        status="open",
        alert_code="staff_transfer_review",
        source_domain="staff_actual_transfer",
        limit=20,
        offset=5,
    )
    detailed = finance_alerts.get_alert(41)

    assert listed.data == [alert]
    assert detailed.data == alert
    assert observed["list"][0] is connection.cursor_value
    assert observed["list"][1] == {
        "status": "open",
        "alert_code": "staff_transfer_review",
        "source_domain": "staff_actual_transfer",
        "limit": 20,
        "offset": 5,
    }
    assert observed["detail"] == (connection.cursor_value, 41)
    assert connection.commits == 0
    assert connection.closed is True


def test_detail_not_found_returns_404(monkeypatch):
    _connection(monkeypatch)
    monkeypatch.setattr(finance_alerts, "get_finance_alert", lambda *_: None)

    with pytest.raises(HTTPException) as exc_info:
        finance_alerts.get_alert(41)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "alert_id does not exist"


def test_claim_and_resolve_delegate_and_commit(monkeypatch):
    connection = _connection(monkeypatch)
    calls = []

    def claim_service(cursor, **kwargs):
        calls.append(("claim", cursor, kwargs))
        return {"result": "claimed", "alert": {"id": 41, "status": "claimed"}}

    def resolve_service(cursor, **kwargs):
        calls.append(("resolve", cursor, kwargs))
        return {"result": "resolved", "alert": {"id": 41, "status": "resolved"}}

    monkeypatch.setattr(finance_alerts, "claim_finance_alert", claim_service)
    monkeypatch.setattr(finance_alerts, "resolve_finance_alert", resolve_service)

    claimed = finance_alerts.claim_alert(
        finance_alerts.ClaimFinanceAlertRequest(operator=" finance-owner "), 41
    )
    resolved = finance_alerts.resolve_alert(
        finance_alerts.ResolveFinanceAlertRequest(
            operator="finance-owner", reason="已完成人工處理"
        ),
        41,
    )

    assert claimed.data["result"] == "claimed"
    assert resolved.data["result"] == "resolved"
    assert calls == [
        ("claim", connection.cursor_value, {"alert_id": 41, "operator": "finance-owner"}),
        (
            "resolve",
            connection.cursor_value,
            {"alert_id": 41, "operator": "finance-owner", "reason": "已完成人工處理"},
        ),
    ]
    assert connection.commits == 2
    assert connection.rollbacks == 0


@pytest.mark.parametrize("action", ["claim", "resolve"])
def test_workflow_conflict_returns_409_and_rolls_back(monkeypatch, action):
    connection = _connection(monkeypatch)
    result = {"result": "conflict", "alert": {"id": 41, "status": "claimed"}}
    monkeypatch.setattr(finance_alerts, "claim_finance_alert", lambda *_args, **_kwargs: result)
    monkeypatch.setattr(finance_alerts, "resolve_finance_alert", lambda *_args, **_kwargs: result)

    with pytest.raises(HTTPException) as exc_info:
        if action == "claim":
            finance_alerts.claim_alert(
                finance_alerts.ClaimFinanceAlertRequest(operator="other-owner"), 41
            )
        else:
            finance_alerts.resolve_alert(
                finance_alerts.ResolveFinanceAlertRequest(
                    operator="other-owner", reason="衝突"
                ),
                41,
            )

    assert exc_info.value.status_code == 409
    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_workflow_value_error_is_explicit_and_rolls_back(monkeypatch):
    connection = _connection(monkeypatch)

    def missing_alert(*_args, **_kwargs):
        raise ValueError("alert_id does not exist")

    monkeypatch.setattr(finance_alerts, "claim_finance_alert", missing_alert)

    with pytest.raises(HTTPException) as exc_info:
        finance_alerts.claim_alert(
            finance_alerts.ClaimFinanceAlertRequest(operator="finance-owner"), 41
        )

    assert exc_info.value.status_code == 404
    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_router_exposes_only_alert_read_and_workflow_action_endpoints():
    methods_and_paths = {
        (method, route.path)
        for route in finance_alerts.router.routes
        for method in route.methods
    }

    assert methods_and_paths == {
        ("GET", "/api/v1/finance-alerts"),
        ("GET", "/api/v1/finance-alerts/{alert_id}"),
        ("POST", "/api/v1/finance-alerts/{alert_id}/claim"),
        ("POST", "/api/v1/finance-alerts/{alert_id}/resolve"),
    }
