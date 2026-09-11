"""Regression coverage for issue #277 stage-5 customer recommendation routing."""

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import matches


def test_stage5_customer_profiles_payload_reaches_route_without_request_validation(monkeypatch):
    captured = {}

    class Notifications:
        def request_customer_profiles(self, command):
            captured["command"] = command
            return SimpleNamespace(
                intent_id=81,
                line_delivery_task_id=SimpleNamespace(value=901),
                projection_status=SimpleNamespace(value="projected"),
                notification_kind=SimpleNamespace(value="customer_profiles"),
            )

    principal = SimpleNamespace(
        id=7,
        username="operator",
        role="system_admin",
        is_root=True,
        enabled=True,
        effective_capabilities=lambda: frozenset({"line.matching.send"}),
    )
    monkeypatch.setattr(matches, "matching_notifications", Notifications())

    app = FastAPI()
    app.include_router(matches.router)
    app.dependency_overrides[matches.require_line_matching_sender] = lambda: principal
    client = TestClient(app)

    response = client.post(
        "/api/v1/orders/CASE-001/matching-plans/51/resumes",
        json={
            "actor": "operator",
            "event_key": "orders-customer-profiles-51-11111111-2222-4333-8444-555555555555",
            "expected_version": 4,
            "note": "請查收正式推薦月嫂履歷。",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "intent_id": 81,
        "line_delivery_task_id": 901,
        "delivery_status": "projected",
        "notification_kind": "customer_profiles",
    }
    command = captured["command"]
    assert command.plan.case_no == "CASE-001"
    assert command.plan.plan_id == 51
    assert command.plan.version == 4
    assert command.note == "請查收正式推薦月嫂履歷。"
