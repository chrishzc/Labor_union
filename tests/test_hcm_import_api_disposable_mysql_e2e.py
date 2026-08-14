"""
File: tests/test_hcm_import_api_disposable_mysql_e2e.py
Description: 以 disposable MySQL 驗證 HCM multipart API 的 Preview、Apply、replay 與 conflict。
"""

from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.hcm_import import router


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(
    not DATABASE or os.getenv("DB_DATABASE") != DATABASE,
    reason="requires an explicitly configured disposable lu_test_* MySQL database",
)


def test_hcm_multipart_api_writes_once_replays_and_rejects_changed_payload(
    tmp_path, monkeypatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "false")
    case_no = f"HCM-API-{uuid4().hex[:14]}"
    valid_path = _write_hcm_workbook(tmp_path / "valid.xlsx", case_no, "0912345678")
    changed_path = _write_hcm_workbook(tmp_path / "changed.xlsx", case_no, "0923456789")
    client = _client()
    command_headers = {
        "Idempotency-Key": f"hcm-api:{case_no}",
        "X-Correlation-ID": f"hcm-api:{case_no}",
    }

    preview = _upload(client, "/workbooks/preview", valid_path)
    fingerprint = preview.json()["data"]["preview_fingerprint"]
    applied = _upload(
        client,
        "/workbooks/apply",
        valid_path,
        headers={**command_headers, "X-Preview-Fingerprint": fingerprint},
    )
    replay = _upload(
        client,
        "/workbooks/apply",
        valid_path,
        headers={**command_headers, "X-Preview-Fingerprint": fingerprint},
    )
    conflict = _upload(
        client,
        "/workbooks/apply",
        changed_path,
        headers={**command_headers, "X-Preview-Fingerprint": _preview_fingerprint(client, changed_path)},
    )

    assert preview.status_code == 200
    assert preview.json()["data"]["ready_count"] == 1
    assert applied.status_code == 200
    assert applied.json()["data"]["inserted_count"] == 1
    assert replay.status_code == 200
    assert replay.json()["data"]["replayed_workbook"] is True
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "hcm_workbook_idempotency_conflict"
    _assert_formal_case(case_no)


def test_historical_hcm_api_overwrites_fields_without_overwriting_order_status(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ENABLE_ADMIN_AUTH", "false")
    case_no = f"HCM-HISTORY-API-{uuid4().hex[:10]}"
    initial_path = _write_hcm_workbook(tmp_path / "initial.xlsx", case_no, "0912345678")
    newer = _hcm_row(case_no, "0923456789")
    newer.update({"報名時間(建檔)": "2026/01/01", "姓名": "歷史 API 新姓名", "希望服務天數": 12})
    older = _hcm_row(case_no, "0912345678")
    older.update({"報名時間(建檔)": "2025/01/01", "姓名": "歷史 API 舊姓名", "希望服務天數": 8})
    history_path = tmp_path / "history.xlsx"
    pd.DataFrame([newer, older]).to_excel(history_path, sheet_name="任意資料頁", index=False)
    client = _client()
    initial_preview = _upload(client, "/workbooks/preview", initial_path)
    initial_applied = _upload(
        client, "/workbooks/apply", initial_path,
        headers={
            "Idempotency-Key": f"hcm-history-api-initial:{case_no}",
            "X-Correlation-ID": f"hcm-history-api-initial:{case_no}",
            "X-Preview-Fingerprint": initial_preview.json()["data"]["preview_fingerprint"],
        },
    )
    preview = _upload(client, "/historical-workbooks/preview", history_path)
    applied = _upload(
        client, "/historical-workbooks/apply", history_path,
        headers={
            "Idempotency-Key": f"hcm-history-api:{case_no}",
            "X-Correlation-ID": f"hcm-history-api:{case_no}",
            "X-Preview-Fingerprint": preview.json()["data"]["preview_fingerprint"],
        },
    )

    assert initial_applied.status_code == 200
    assert preview.status_code == 200
    assert applied.status_code == 200
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM clients WHERE case_no=%s", (case_no,))
            assert cursor.fetchone() == {"name": "歷史 API 新姓名"}
            cursor.execute("SELECT status,service_days FROM orders WHERE case_no=%s", (case_no,))
            assert cursor.fetchone() == {"status": "洽談中", "service_days": 12}
    finally:
        connection.close()


def _client() -> TestClient:
    application = FastAPI()
    application.include_router(router)
    return TestClient(application)


def _upload(
    client: TestClient,
    path: str,
    workbook_path: Path,
    headers: dict[str, str] | None = None,
):
    with open(workbook_path, "rb") as workbook:
        return client.post(
            f"/api/v1/case-import/hcm{path}",
            headers=headers,
            files={
                "workbook": (
                    workbook_path.name,
                    workbook.read(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )


def _preview_fingerprint(client: TestClient, workbook_path: Path) -> str:
    response = _upload(client, "/workbooks/preview", workbook_path)
    assert response.status_code == 200
    return str(response.json()["data"]["preview_fingerprint"])


def _write_hcm_workbook(path: Path, case_no: str, phone: str) -> Path:
    pd.DataFrame([_hcm_row(case_no, phone)]).to_excel(path, sheet_name="任意資料頁", index=False)
    return path


def _hcm_row(case_no: str, phone: str) -> dict[str, object]:
    return {
        "案件狀態": "洽談中",
        "查詢序號(案件編號)": case_no,
        "報名時間(建檔)": "2026/08/14",
        "IP位址": "192.0.2.60",
        "姓名": f"合成 API 客戶 {case_no}",
        "性別": "女",
        "行動電話": phone,
        "縣市": "新竹市",
        "身分資格": "一般市民",
        "服務時間": "8 小時 09:00 17:00",
        "預產期/預計服務開始月份": "2026/09/01",
        "預計服務日期": "2026/09/10",
        "希望服務天數": 5,
        "居住型態": "大樓",
        "生產方式": "自然產",
        "服務方式": "週休2日",
        "寶寶資訊": "合成資料",
    }


def _assert_formal_case(case_no: str) -> None:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT status FROM orders WHERE case_no=%s", (case_no,))
            assert cursor.fetchone() == {"status": "洽談中"}
    finally:
        connection.close()
