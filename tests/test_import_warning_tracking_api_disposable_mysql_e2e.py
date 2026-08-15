"""
File: test_import_warning_tracking_api_disposable_mysql_e2e.py
Description: 驗證匯入警示 HTTP API 透過真實隔離 MySQL 執行 Preview、Apply 與 Query。
"""

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_system_admin
from api.routes.import_warning_tracking import router
from infrastructure.mysql.mysql_adapter import get_connection


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(not DATABASE or os.getenv("DB_DATABASE") != DATABASE, reason="requires an explicitly configured disposable lu_test_* MySQL database")


def test_http_apply_then_query_uses_real_tracking_tables() -> None:
    identity = f"wp94-api-{uuid4().hex}"
    _seed(identity)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_system_admin] = lambda: SimpleNamespace(username="operator-wp94")
    client = TestClient(app)
    headers = {"Idempotency-Key": f"wp94-api-{uuid4().hex}", "X-Correlation-ID": f"wp94-api-{uuid4().hex}"}

    preview = client.post(f"/api/v1/import-warning-tracking/tasks/{identity}/preview", headers=headers, json={"expected_version": 1, "target_status": "awaiting_external_confirmation", "reason_code": "contact_started"})
    applied = client.post(f"/api/v1/import-warning-tracking/tasks/{identity}/apply", headers=headers, json={"expected_version": 1, "target_status": "awaiting_external_confirmation", "reason_code": "contact_started"})
    queried = client.get("/api/v1/import-warning-tracking/tasks")

    assert preview.status_code == 200
    assert applied.status_code == 200
    assert any(item["occurrence_identity"] == identity and item["tracking_version"] == 2 for item in queried.json()["data"])


def _seed(identity: str) -> None:
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO import_warning_occurrences (occurrence_identity,owning_lane,source_kind,source_event_identity,logical_code,field_path,masked_subject,issue_codes,evidence_snapshot) VALUES (%s,'hcm','workbook',%s,'IMPORT-004','phone','masked',JSON_ARRAY('invalid_phone'),JSON_OBJECT())", (identity, f"source-{identity}"))
            occurrence_id = cursor.lastrowid
            cursor.execute("INSERT INTO import_warning_tracking_events (event_identity,occurrence_id,action,before_status,after_status,expected_version,resulting_version,actor_kind,actor_identity,reason_code,command_fingerprint,idempotency_key,correlation_id) VALUES (%s,%s,'opened',NULL,'open',0,1,'system','system','opened',%s,%s,%s)", (f"seed-{identity}", occurrence_id, "0" * 64, f"seed-key-{identity}", f"seed-correlation-{identity}"))
            cursor.execute("INSERT INTO import_warning_current_tasks (occurrence_id,tracking_status,tracking_version,last_event_id) VALUES (%s,'open',1,%s)", (occurrence_id, cursor.lastrowid))
        connection.commit()
    finally:
        connection.close()
