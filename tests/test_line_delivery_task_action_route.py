"""Focused contract checks for typed LINE delivery task control responses."""

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.dependencies.admin_auth import require_line_task_controller
from api.routes import line_tasks
from api.schemas.line_tasks import LineDeliveryTaskActionResultView, LineTaskActionRequest
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import (
    LineDeliveryRequest,
    LineDeliveryStatus,
    LineDeliveryTaskSnapshot,
    LineMessageKind,
    LineRecipient,
    LineRecipientType,
)
from domains.line.identities import LineDeliveryTaskId, LineUserId
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.line.delivery_admin_application import LineDeliveryTaskStateConflictError


def _principal() -> AdminPrincipal:
    return AdminPrincipal(1, "admin", "管理員", "system_admin")


def _task() -> LineDeliveryTaskSnapshot:
    return LineDeliveryTaskSnapshot(
        task_id=LineDeliveryTaskId(7),
        request=LineDeliveryRequest(
            recipient=LineRecipient(LineRecipientType.USER, LineUserId("U-action")),
            message_kind=LineMessageKind.TEXT,
            payload_json=canonical_line_payload_json({"type": "text", "text": "action"}),
            scheduled_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
            idempotency_key=IdempotencyKey("line-action-task"),
            correlation_id=CorrelationId("line-action-task"),
            source_aggregate_type="customer_service_ticket",
            source_aggregate_identity="CASE-action",
        ),
        status=LineDeliveryStatus.PENDING,
        completed_attempts=0,
    )


class _Application:
    def __init__(self, task: LineDeliveryTaskSnapshot) -> None:
        self.task = task
        self.calls: list[str] = []

    def cancel(self, _command):
        self.calls.append("cancel")
        self.task = LineDeliveryTaskSnapshot(
            self.task.task_id, self.task.request, LineDeliveryStatus.CANCELLED, 0
        )
        return self.task

    def run_now(self, _command):
        self.calls.append("run_now")
        return self.task

    def retry(self, _command):
        self.calls.append("retry")
        return self.task


def _client(monkeypatch, application: _Application) -> TestClient:
    app = FastAPI()
    app.include_router(line_tasks.router)
    app.dependency_overrides[require_line_task_controller] = _principal
    monkeypatch.setattr(line_tasks, "get_line_delivery_task_admin_application", lambda: application)
    return TestClient(app)


@pytest.mark.parametrize(
    ("action", "method_name"),
    (("cancel", "cancel"), ("run-now", "run_now"), ("retry", "retry")),
)
def test_task_actions_return_closed_typed_result_and_keep_application_dispatch(
    monkeypatch, action: str, method_name: str
) -> None:
    application = _Application(_task())
    client = _client(monkeypatch, application)

    response = client.post(
        f"/api/v1/line/tasks/7/{action}",
        json={"reason": "人工確認", "idempotency_key": "action-key", "correlation_id": "action-correlation"},
    )

    assert response.status_code == 200
    assert application.calls == [method_name]
    data = response.json()["data"]
    assert set(data) == {
        "id", "task_id", "task_type", "message_kind", "scheduled_at",
        "status", "completed_attempts",
    }
    assert data["task_id"] == 7
    assert response.json()["data"]["status"] == (
        "cancelled" if action == "cancel" else "pending"
    )
    for denied in ("U-action", "CASE-action", "action"):
        assert denied not in response.text
    assert isinstance(
        line_tasks._task_snapshot(application.task), LineDeliveryTaskActionResultView
    )


def test_task_action_preserves_conflict_error_status(monkeypatch) -> None:
    class _ConflictingApplication(_Application):
        def retry(self, _command):
            raise LineDeliveryTaskStateConflictError("conflict")

    client = _client(monkeypatch, _ConflictingApplication(_task()))

    response = client.post("/api/v1/line/tasks/7/retry", json={})

    assert response.status_code == 409
    assert response.json()["detail"] == "conflict"
