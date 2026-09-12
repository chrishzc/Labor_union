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


def test_stage5_customer_confirmation_preview_exposes_complete_send_readiness(monkeypatch):
    class Notifications:
        def preview_customer_confirmation(self, actor, plan):
            assert actor.actor_id == "admin:7"
            assert plan.case_no == "CASE-001"
            assert plan.plan_id == 51
            assert plan.version == 4
            return SimpleNamespace(
                plan=plan,
                order_information_1_ready=True,
                order_information_2_ready=True,
                weekly_service_ready=True,
                weekly_service_row_count=3,
                caregiver_resumes=(SimpleNamespace(
                    staff_id=12,
                    staff_name="王小美",
                    ready=True,
                    filename="王小美履歷.pdf",
                    version=2,
                    blocker=None,
                ),),
                blockers=(),
                send_allowed=True,
            )

    principal = SimpleNamespace(
        id=7,
        username="operator",
        role="system_admin",
        is_root=True,
        enabled=True,
        effective_capabilities=lambda: frozenset({"line.matching.read"}),
    )
    monkeypatch.setattr(matches, "matching_notifications", Notifications())

    app = FastAPI()
    app.include_router(matches.router)
    app.dependency_overrides[matches.require_line_matching_reader] = lambda: principal
    client = TestClient(app)

    response = client.get(
        "/api/v1/orders/CASE-001/matching-plans/51/customer-confirmation/preview",
        params={"expected_version": 4},
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "case_no": "CASE-001",
        "plan_id": 51,
        "expected_version": 4,
        "order_information_1_ready": True,
        "order_information_2_ready": True,
        "weekly_service_ready": True,
        "weekly_service_row_count": 3,
        "caregiver_resumes": [{
            "staff_id": 12,
            "staff_name": "王小美",
            "ready": True,
            "filename": "王小美履歷.pdf",
            "version": 2,
            "blocker": None,
        }],
        "blockers": [],
        "send_allowed": True,
    }


def test_stage5_willing_candidate_payload_reaches_matching_plan_route(monkeypatch):
    captured = {}
    principal = SimpleNamespace(
        id=7,
        username="operator",
        role="system_admin",
        is_root=True,
        enabled=True,
    )

    def create_matching_plan_version(**kwargs):
        captured.update(kwargs)
        return {
            "plan_id": 51,
            "case_no": kwargs["case_no"],
            "version": 1,
            "status": "proposed",
            "result": "created",
            "segments": [
                {
                    "segment_order": 1,
                    "staff_id": 1,
                    "assigned_start_date": "2026-12-01",
                    "assigned_end_date": "2026-12-20",
                }
            ],
            "actor": kwargs["created_by"],
            "as_of": kwargs["as_of"],
            "event_key": kwargs["event_key"],
            "command_fingerprint": "a" * 64,
            "replayed": False,
        }

    monkeypatch.setattr(matches, "create_matching_plan_version", create_matching_plan_version)
    app = FastAPI()
    app.include_router(matches.router)
    app.dependency_overrides[matches.require_system_admin] = lambda: principal
    client = TestClient(app)

    response = client.post(
        "/api/v1/orders/CASE-2026-S05/matching-plans",
        json={
            "segments": [
                {
                    "staff_id": 1,
                    "start_date": "2026-12-01",
                    "end_date": "2026-12-20",
                }
            ],
            "created_by": "operator",
            "as_of": "2026-09-11",
            "event_key": "matching-plan:CASE-2026-S05:create",
        },
    )

    assert response.status_code == 200, response.text
    assert captured["case_no"] == "CASE-2026-S05"
    assert captured["segments"] == [
        {"staff_id": 1, "start_date": "2026-12-01", "end_date": "2026-12-20"}
    ]
    assert captured["created_by"] == "operator"
    assert captured["as_of"] == "2026-09-11"
    assert captured["require_willing_candidate"] is True


def test_stage5_stale_candidate_is_a_typed_conflict_not_request_validation(monkeypatch):
    principal = SimpleNamespace(
        id=7,
        username="operator",
        role="system_admin",
        is_root=True,
        enabled=True,
    )
    monkeypatch.setattr(
        matches,
        "create_matching_plan_version",
        lambda **_kwargs: (_ for _ in ()).throw(
            ValueError("current willing candidate is required")
        ),
    )
    app = FastAPI()
    app.include_router(matches.router)
    app.dependency_overrides[matches.require_system_admin] = lambda: principal
    client = TestClient(app)

    response = client.post(
        "/api/v1/orders/CASE-2026-S05/matching-plans",
        json={
            "segments": [
                {
                    "staff_id": 1,
                    "start_date": "2026-12-01",
                    "end_date": "2026-12-20",
                }
            ],
            "created_by": "operator",
            "as_of": "2026-09-11",
            "event_key": "matching-plan:CASE-2026-S05:stale",
        },
    )

    assert response.status_code == 409, response.text
    error = response.json()["detail"]["error"]
    assert error["category"] == "conflict"
    assert error["code"] == "matching_candidate_no_longer_available"
