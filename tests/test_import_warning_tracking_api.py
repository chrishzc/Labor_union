"""
File: test_import_warning_tracking_api.py
Description: 驗證匯入警示 API 查詢契約、TaskView 結構、分頁參數、權限防護與 Preview／Apply 邊界。
契約依據: 00_Global_共同契約.md, 22_銀行流水匯入與帳務異常處理正式規格.md, PROV-20260816 Phase 2D 規格。
變更範圍: 擴充 tasks 查詢契約測試，涵蓋 ImportWarningTaskView 欄位、分頁參數邊界、401/403 認證與零副作用。
驗證依據: pytest tests/test_import_warning_tracking_api.py 執行全數通過。
無副作用宣告: 純唯讀契約測試，無狀態變更或資料庫副作用。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
import pytest

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.import_warning_tracking import get_import_warning_tracking_application
from api.routes.import_warning_tracking import router
from api.schemas.import_warning_tracking import (
    ImportWarningTaskView,
    WarningTransitionBody,
)
from domains.anomalies.import_warning_tracking import ImportWarningTrackingStatus
from subsystems.anomalies.import_warning_tracking_workflow import (
    ImportWarningTask,
    WarningReferralDescriptor,
    WarningTransitionPreview,
)


class _Application:
    def __init__(self, tasks: tuple[ImportWarningTask, ...] | None = None) -> None:
        self.applied = False
        self.last_query_params: dict[str, Any] | None = None
        self.task = ImportWarningTask(
            "warning-1", "hcm", "HCM-FIELD-001", "身分證字號", "masked",
            ("hcm_field_missing:身分證字號",), ImportWarningTrackingStatus.OPEN,
            1, None, "hcm_import_center", "缺少身分證",
        )
        self.tasks = tasks if tasks is not None else (self.task,)

    def query_tasks(
        self,
        *,
        active_only: bool = True,
        limit: int = 100,
        offset: int = 0,
        **_,
    ) -> tuple[ImportWarningTask, ...]:
        self.last_query_params = {
            "active_only": active_only,
            "limit": limit,
            "offset": offset,
        }
        filtered = [
            t for t in self.tasks
            if not active_only or t.tracking_status not in {
                ImportWarningTrackingStatus.CLOSED,
                ImportWarningTrackingStatus.AUTO_RESOLVED,
            }
        ]
        return tuple(filtered[offset : offset + limit])

    def preview(self, request):
        return WarningTransitionPreview(request.occurrence_identity, 1, ImportWarningTrackingStatus.AWAITING_EXTERNAL_CONFIRMATION, 2)

    def apply(self, request):
        self.applied = True
        return WarningTransitionPreview(request.occurrence_identity, 1, ImportWarningTrackingStatus.AWAITING_EXTERNAL_CONFIRMATION, 2)

    def query_referral(self, occurrence_identity, *, expected_version):
        assert occurrence_identity == "warning-1"
        assert expected_version == 1
        return WarningReferralDescriptor(
            occurrence_identity="warning-1",
            expected_version=1,
            owning_lane="hcm",
            logical_code="HCM-FIELD-001",
            field_path="身分證字號",
            masked_subject="masked",
            display_message="缺少身分證",
            navigation_action="hcm_import_center",
            action_kind="owner_preview_apply",
            target_command="preview_hcm_resubmission",
        )


def _client(application: _Application, authenticate: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(router)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request, exc: RequestValidationError):
        errors = []
        for err in exc.errors():
            clean_err = dict(err)
            if clean_err.get("input") is Ellipsis:
                clean_err["input"] = None
            if "ctx" in clean_err and isinstance(clean_err["ctx"], dict):
                clean_err["ctx"] = {
                    k: str(v) if isinstance(v, Exception) else v
                    for k, v in clean_err["ctx"].items()
                }
            errors.append(clean_err)
        return JSONResponse(status_code=422, content={"detail": errors})

    if authenticate:
        app.dependency_overrides[require_system_admin] = lambda: SimpleNamespace(username="operator-1")
    app.dependency_overrides[get_import_warning_tracking_application] = lambda: application
    return TestClient(app)


def _headers() -> dict[str, str]:
    return {"Idempotency-Key": "warning-apply-1", "X-Correlation-ID": "warning-correlation-1"}


def test_preview_is_typed_and_does_not_apply() -> None:
    application = _Application()

    response = _client(application).post("/api/v1/import-warning-tracking/tasks/warning-1/preview", headers=_headers(), json={"expected_version": 1, "target_status": "awaiting_external_confirmation", "reason_code": "contact_started"})

    assert response.status_code == 200
    assert response.json()["data"]["resulting_version"] == 2
    assert application.applied is False


def test_task_query_exposes_business_message_and_ui_neutral_navigation_action() -> None:
    application = _Application()

    response = _client(application).get("/api/v1/import-warning-tracking/tasks")

    assert response.status_code == 200
    task = response.json()["data"][0]
    assert task["display_message"] == "缺少身分證"
    assert task["navigation_action"] == "hcm_import_center"
    assert "url" not in task
    assert "corrected_fields" not in task


def test_apply_rejects_corrected_payload_before_application() -> None:
    application = _Application()

    response = _client(application).post("/api/v1/import-warning-tracking/tasks/warning-1/apply", headers=_headers(), json={"expected_version": 1, "target_status": "awaiting_external_confirmation", "reason_code": "contact_started", "corrected_fields": {"phone": "123"}})

    assert response.status_code == 422
    assert application.applied is False


def test_hcm_referral_is_read_only_typed_owner_context_without_corrected_payload() -> None:
    application = _Application()

    response = _client(application).get(
        "/api/v1/import-warning-tracking/tasks/warning-1/referral",
        params={"expected_version": 1},
    )

    assert response.status_code == 200
    referral = response.json()["data"]
    assert referral == {
        "occurrence_identity": "warning-1",
        "expected_version": 1,
        "owning_lane": "hcm",
        "logical_code": "HCM-FIELD-001",
        "field_path": "身分證字號",
        "masked_subject": "masked",
        "display_message": "缺少身分證",
        "navigation_action": "hcm_import_center",
        "action_kind": "owner_preview_apply",
        "target_command": "preview_hcm_resubmission",
    }
    assert "corrected_fields" not in referral
    assert "source_snapshot" not in referral


# =============================================================================
# Lane B Augmented Query Contract Tests for GET /api/v1/import-warning-tracking/tasks
# =============================================================================


def test_task_query_structure_and_pydantic_contract_conformance() -> None:
    task1 = ImportWarningTask(
        occurrence_identity="import-warning:3a7e4f9b8c0d1e2f3a4b5c6d7e8f9012",
        owning_lane="hcm",
        logical_code="HCM-FIELD-001",
        field_path="身分證字號",
        masked_subject="A12****789",
        issue_codes=("hcm_field_missing:身分證字號",),
        tracking_status=ImportWarningTrackingStatus.OPEN,
        tracking_version=1,
        evidence_reference="batch-20260816-01",
        navigation_action="hcm_import_center",
        display_message="缺少身分證字號",
    )
    task2 = ImportWarningTask(
        occurrence_identity="import-warning:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        owning_lane="finance",
        logical_code="FIN-IMPORT-002",
        field_path="amount",
        masked_subject="TX-9988",
        issue_codes=("finance_amount_negative", "finance_format_invalid"),
        tracking_status=ImportWarningTrackingStatus.AWAITING_EXTERNAL_CONFIRMATION,
        tracking_version=2,
        evidence_reference=None,
        navigation_action="finance_import_recovery_center",
        display_message="金額欄位不得為負數",
    )
    application = _Application(tasks=(task1, task2))
    client = _client(application)

    response = client.get("/api/v1/import-warning-tracking/tasks")
    assert response.status_code == 200

    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "成功取得匯入警示追蹤清單"
    assert payload["error"] is None
    assert isinstance(payload["data"], list)
    assert len(payload["data"]) == 2

    # Validate against Pydantic schema
    for item in payload["data"]:
        view = ImportWarningTaskView.model_validate(item)
        assert view.tracking_version >= 1
        assert len(view.display_message) >= 1
        assert len(view.display_message) <= 200

    # Field-level verification for item 0
    t0 = payload["data"][0]
    assert t0["occurrence_identity"] == "import-warning:3a7e4f9b8c0d1e2f3a4b5c6d7e8f9012"
    assert t0["owning_lane"] == "hcm"
    assert t0["logical_code"] == "HCM-FIELD-001"
    assert t0["field_path"] == "身分證字號"
    assert t0["masked_subject"] == "A12****789"
    assert t0["issue_codes"] == ["hcm_field_missing:身分證字號"]
    assert t0["tracking_status"] == "open"
    assert t0["tracking_version"] == 1
    assert t0["evidence_reference"] == "batch-20260816-01"
    assert t0["display_message"] == "缺少身分證字號"
    assert t0["navigation_action"] == "hcm_import_center"

    # Field-level verification for item 1
    t1 = payload["data"][1]
    assert t1["owning_lane"] == "finance"
    assert t1["evidence_reference"] is None
    assert t1["navigation_action"] == "finance_import_recovery_center"
    assert t1["tracking_status"] == "awaiting_external_confirmation"
    assert t1["tracking_version"] == 2


def test_task_query_parameter_filtering_and_pagination() -> None:
    tasks = tuple(
        ImportWarningTask(
            f"warning-{i}",
            "historical_order",
            f"HIST-00{i}",
            "order_date",
            f"ORD-{i}",
            (f"issue_{i}",),
            ImportWarningTrackingStatus.CLOSED if i == 3 else ImportWarningTrackingStatus.OPEN,
            1,
            None,
            "historical_order_import_center",
            f"訊息 {i}",
        )
        for i in range(1, 5)
    )
    application = _Application(tasks=tasks)
    client = _client(application)

    # Test active_only=false, limit=2, offset=1
    response = client.get("/api/v1/import-warning-tracking/tasks?active_only=false&limit=2&offset=1")
    assert response.status_code == 200
    assert application.last_query_params == {
        "active_only": False,
        "limit": 2,
        "offset": 1,
    }

    data = response.json()["data"]
    assert len(data) == 2
    assert data[0]["occurrence_identity"] == "warning-2"
    assert data[1]["occurrence_identity"] == "warning-3"
    assert data[1]["tracking_status"] == "closed"


def test_task_query_parameter_validation_boundaries() -> None:
    application = _Application()
    client = _client(application)

    # limit bounds: ge=1, le=200
    assert client.get("/api/v1/import-warning-tracking/tasks?limit=1").status_code == 200
    assert client.get("/api/v1/import-warning-tracking/tasks?limit=200").status_code == 200

    # limit violations -> 422
    assert client.get("/api/v1/import-warning-tracking/tasks?limit=0").status_code == 422
    assert client.get("/api/v1/import-warning-tracking/tasks?limit=-1").status_code == 422
    assert client.get("/api/v1/import-warning-tracking/tasks?limit=201").status_code == 422
    assert client.get("/api/v1/import-warning-tracking/tasks?limit=not_an_int").status_code == 422

    # offset bounds: ge=0
    assert client.get("/api/v1/import-warning-tracking/tasks?offset=0").status_code == 200
    assert client.get("/api/v1/import-warning-tracking/tasks?offset=10").status_code == 200
    assert client.get("/api/v1/import-warning-tracking/tasks?offset=-1").status_code == 422
    assert client.get("/api/v1/import-warning-tracking/tasks?offset=not_an_int").status_code == 422

    # active_only boolean validation
    assert client.get("/api/v1/import-warning-tracking/tasks?active_only=true").status_code == 200
    assert client.get("/api/v1/import-warning-tracking/tasks?active_only=false").status_code == 200
    assert client.get("/api/v1/import-warning-tracking/tasks?active_only=not_a_bool").status_code == 422


def test_task_query_authentication_required() -> None:
    application = _Application()
    client = _client(application, authenticate=False)

    response = client.get("/api/v1/import-warning-tracking/tasks")
    assert response.status_code in {401, 403}


def test_task_query_zero_mutation_guarantee() -> None:
    application = _Application()
    client = _client(application)

    assert application.applied is False

    res1 = client.get("/api/v1/import-warning-tracking/tasks")
    res2 = client.get("/api/v1/import-warning-tracking/tasks?active_only=false")
    res3 = client.get("/api/v1/import-warning-tracking/tasks?limit=50&offset=0")

    assert res1.status_code == 200
    assert res2.status_code == 200
    assert res3.status_code == 200
    assert application.applied is False


def test_task_query_all_navigation_action_variants() -> None:
    actions = [
        "hcm_import_center",
        "historical_order_import_center",
        "client_beclass_import_center",
        "staff_beclass_import_center",
        "finance_import_recovery_center",
        None,
    ]
    tasks = tuple(
        ImportWarningTask(
            f"warn-nav-{i}",
            "lane",
            f"CODE-{i}",
            "field",
            "subj",
            ("issue",),
            ImportWarningTrackingStatus.OPEN,
            1,
            None,
            act,
            f"訊息 {act}",
        )
        for i, act in enumerate(actions)
    )
    application = _Application(tasks=tasks)
    client = _client(application)

    response = client.get("/api/v1/import-warning-tracking/tasks?limit=10")
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 6
    for i, act in enumerate(actions):
        assert data[i]["navigation_action"] == act
        ImportWarningTaskView.model_validate(data[i])


def test_task_query_all_tracking_status_enums() -> None:
    statuses = [
        ImportWarningTrackingStatus.OPEN,
        ImportWarningTrackingStatus.AWAITING_EXTERNAL_CONFIRMATION,
        ImportWarningTrackingStatus.RESPONSE_RECORDED,
        ImportWarningTrackingStatus.REIMPORT_REQUESTED,
        ImportWarningTrackingStatus.CLOSED,
        ImportWarningTrackingStatus.AUTO_RESOLVED,
    ]
    tasks = tuple(
        ImportWarningTask(
            f"warn-st-{i}",
            "lane",
            f"CODE-{i}",
            "field",
            "subj",
            ("issue",),
            st,
            1,
            None,
            "hcm_import_center",
            f"狀態 {st.value}",
        )
        for i, st in enumerate(statuses)
    )
    application = _Application(tasks=tasks)
    client = _client(application)

    # With active_only=false to retrieve closed & auto_resolved
    response = client.get("/api/v1/import-warning-tracking/tasks?active_only=false&limit=10")
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 6
    for i, st in enumerate(statuses):
        assert data[i]["tracking_status"] == st.value
        ImportWarningTaskView.model_validate(data[i])


def test_task_query_empty_list() -> None:
    application = _Application(tasks=())
    client = _client(application)

    response = client.get("/api/v1/import-warning-tracking/tasks")
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"] == []
    assert payload["error"] is None


def test_task_public_contract_rejects_unknown_tracking_status() -> None:
    payload = {
        "occurrence_identity": "warning-1",
        "owning_lane": "hcm",
        "logical_code": "HCM-FIELD-001",
        "field_path": "身分證字號",
        "masked_subject": "masked",
        "issue_codes": ["missing"],
        "tracking_status": "unknown",
        "tracking_version": 1,
        "evidence_reference": None,
        "display_message": "缺少身分證",
        "navigation_action": "hcm_import_center",
    }

    with pytest.raises(ValueError):
        ImportWarningTaskView.model_validate(payload)


def test_import_warning_public_json_schema_exposes_all_tracking_statuses() -> None:
    schema = ImportWarningTaskView.model_json_schema()

    assert schema["$defs"]["ImportWarningTrackingStatus"]["enum"] == [
        "open",
        "awaiting_external_confirmation",
        "response_recorded",
        "reimport_requested",
        "closed",
        "auto_resolved",
    ]

    transition_schema = WarningTransitionBody.model_json_schema()
    assert transition_schema["properties"]["target_status"]["enum"] == [
        "awaiting_external_confirmation",
        "response_recorded",
        "reimport_requested",
        "closed",
    ]

    for forbidden_target in ("open", "auto_resolved", "unknown", ""):
        with pytest.raises(ValueError):
            WarningTransitionBody.model_validate(
                {
                    "expected_version": 1,
                    "target_status": forbidden_target,
                    "reason_code": "operator-review",
                }
            )
