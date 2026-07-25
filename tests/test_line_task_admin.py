import uuid
import os
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from api.main import app
from line.worker import _finish_task_attempt, _start_task_attempt
from services.db_service import get_connection
from services.line_task_admin_service import (
    cancel_line_task,
    get_line_task,
    list_line_tasks,
    retry_line_task,
    run_line_task_now,
)
from ui.components.line_schedule_manager import _build_schedule_payload, _preview_rows


ROOT = Path(__file__).resolve().parents[1]


def _insert_task(status: str) -> int:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO line_tasks (
                    to_user_id, task_type, message_content, status,
                    scheduled_at, idempotency_key, line_request_id
                ) VALUES ('U-stage-5-3-test','line_push','test',%s,
                          DATE_ADD(UTC_TIMESTAMP(),INTERVAL 1 DAY),%s,%s)
                """,
                (status, f"stage-5-3:{uuid.uuid4()}", str(uuid.uuid4())),
            )
            task_id = int(cursor.lastrowid)
        conn.commit()
        return task_id
    finally:
        conn.close()


def _delete_tasks(task_ids: list[int]) -> None:
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            placeholders = ",".join(["%s"] * len(task_ids))
            cursor.execute(f"DELETE FROM line_tasks WHERE id IN ({placeholders})", task_ids)
        conn.commit()
    finally:
        conn.close()


def test_task_admin_transitions_and_attempt_history():
    cancel_id = _insert_task("pending")
    run_id = _insert_task("pending")
    retry_id = _insert_task("failed")
    task_ids = [cancel_id, run_id, retry_id]
    try:
        assert cancel_line_task(cancel_id)["status"] == "cancelled"
        assert run_line_task_now(run_id)["status"] == "pending"
        assert retry_line_task(retry_id)["status"] == "pending"

        task = get_line_task(run_id)["task"]
        attempt_id = _start_task_attempt(task)
        _finish_task_attempt(attempt_id, (True, False, "", ""), "sent")
        detail = get_line_task(run_id)
        assert detail["attempts"][0]["outcome"] == "sent"

        listed = list_line_tasks(user_id="U-stage-5-3-test", page_size=10)
        assert listed["total"] >= 3
    finally:
        _delete_tasks(task_ids)


def test_schedule_builder_sorts_steps_and_previews_dates():
    config = {
        "version": 1,
        "timezone": "Asia/Taipei",
        "schedules": [
            {
                "id": "new_user_onboarding",
                "name": "三日引導",
                "enabled": True,
                "trigger": "follow",
                "restart_on_refollow": False,
                "steps": [{"day": 1, "send_time": "10:00", "template_id": "d1"}],
            }
        ],
    }
    rows = pd.DataFrame(
        [
            {"day": 3, "send_time": "10:00", "template_id": "d3"},
            {"day": 1, "send_time": "09:30", "template_id": "d1"},
        ]
    )
    payload = _build_schedule_payload(
        config=config,
        schedule_id="new_user_onboarding",
        timezone_name="Asia/Taipei",
        name="三日引導",
        enabled=True,
        restart_on_refollow=True,
        rows=rows,
    )

    assert [step["day"] for step in payload["schedules"][0]["steps"]] == [1, 3]
    assert payload["schedules"][0]["restart_on_refollow"] is True
    assert len(_preview_rows(payload, "new_user_onboarding")) == 2


def test_task_ui_does_not_add_fixed_polling():
    source = (ROOT / "ui/components/line_task_manager.py").read_text(encoding="utf-8")

    assert "time.sleep" not in source
    assert "autorefresh" not in source.lower()
    assert "st.rerun" in source


def test_schema_contains_task_attempt_history():
    schema = (ROOT / "db/schema.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS line_task_attempts" in schema
    assert "UNIQUE KEY uk_line_task_attempt_no" in schema


def test_task_admin_api_in_development_bypass():
    pending_id = _insert_task("pending")
    failed_id = _insert_task("failed")
    old_values = {
        name: os.environ.get(name)
        for name in ("APP_ENV", "ENABLE_ADMIN_AUTH", "INTERNAL_API_KEY")
    }
    os.environ["APP_ENV"] = "development"
    os.environ["ENABLE_ADMIN_AUTH"] = "false"
    os.environ["INTERNAL_API_KEY"] = "stage-5-3-api-test-key"
    headers = {"X-Internal-API-Key": "stage-5-3-api-test-key"}
    client = TestClient(app)
    try:
        assert client.get("/api/v1/line/tasks/summary", headers=headers).status_code == 200
        listed = client.get(
            "/api/v1/line/tasks",
            headers=headers,
            params={"user_id": "U-stage-5-3-test"},
        )
        assert listed.status_code == 200
        assert client.get(f"/api/v1/line/tasks/{pending_id}", headers=headers).status_code == 200
        assert client.post(
            f"/api/v1/line/tasks/{pending_id}/run-now",
            headers=headers,
            json={"reason": "integration test"},
        ).status_code == 200
        assert client.post(
            f"/api/v1/line/tasks/{pending_id}/cancel",
            headers=headers,
            json={"reason": "integration test cleanup"},
        ).status_code == 200
        assert client.post(
            f"/api/v1/line/tasks/{failed_id}/retry",
            headers=headers,
            json={"reason": "integration test"},
        ).status_code == 200
    finally:
        _delete_tasks([pending_id, failed_id])
        for name, value in old_values.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_schedule_api_rejects_stale_revision_without_writing():
    old_values = {
        name: os.environ.get(name)
        for name in ("APP_ENV", "ENABLE_ADMIN_AUTH", "INTERNAL_API_KEY")
    }
    os.environ["APP_ENV"] = "development"
    os.environ["ENABLE_ADMIN_AUTH"] = "false"
    os.environ["INTERNAL_API_KEY"] = "stage-5-3-schedule-test-key"
    headers = {"X-Internal-API-Key": "stage-5-3-schedule-test-key"}
    client = TestClient(app)
    try:
        state_response = client.get(
            "/api/config/message-schedules/state", headers=headers
        )
        assert state_response.status_code == 200
        config = state_response.json()["config"]
        stale_response = client.put(
            "/api/config/message-schedules",
            headers={**headers, "If-Match": "stale-revision"},
            json=config,
        )
        assert stale_response.status_code == 409
    finally:
        for name, value in old_values.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_task_manager_hides_internal_identifiers_from_service_staff():
    source = (ROOT / "ui/components/line_task_manager.py").read_text(encoding="utf-8")

    assert "LINE User ID 包含" not in source
    assert "st.json(task)" not in source
    assert "重新整理任務" not in source
