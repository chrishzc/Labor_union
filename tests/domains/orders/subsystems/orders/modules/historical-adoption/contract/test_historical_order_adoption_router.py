"""
File: test_historical_order_adoption_router.py
Description: 驗證訂單歷史 workbook HTTP Preview／Apply typed result、conflict 與暫存清理。
"""

from __future__ import annotations

import json
from datetime import date
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook
from pymysql.err import DataError, OperationalError

from api.dependencies.admin_auth import require_admin
from api.dependencies.historical_order_adoption import get_historical_order_workbook_import_service
from api.exception_handlers.typed_errors import CorrelationBoundaryMiddleware, install_typed_error_handlers
from api.routes.historical_order_adoption import router
from domains.orders.historical_adoption import HistoricalOrderOutcome
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.identities import CorrelationId
from subsystems.orders.actual_start_workflow import ActualStartWorkflowError
from subsystems.orders.historical_adoption_workflow import (
    HistoricalOrderAdoptionPreview,
    HistoricalOrderAdoptionReceipt,
    HistoricalPairingCandidate,
    HistoricalPairingResolution,
)
from subsystems.orders.historical_order_workbook_import import (
    HistoricalOrderResultCounts,
    HistoricalOrderStatusCounts,
    HistoricalOrderWorkbookConflict,
    HistoricalOrderWorkbookImportService,
    HistoricalOrderWorkbookPreview,
    HistoricalOrderWorkbookReceipt,
)


class _Service:
    def __init__(
        self,
        conflict: bool = False,
        conflict_code: str = "historical_order_workbook_idempotency_conflict",
    ) -> None:
        self.conflict = conflict
        self.conflict_code = conflict_code
        self.paths: list[Path] = []

    def preview(self, path):
        self.paths.append(Path(path))
        return HistoricalOrderWorkbookPreview(
            "0" * 64, "1" * 64, 1, 1, 0, 0, 0, 0, 0,
            HistoricalOrderStatusCounts(0, 1, 0, 0),
            HistoricalOrderResultCounts(0, 0, 1, 0, 0), "2" * 64,
        )

    def apply(self, path, key, preview, actor, correlation):
        self.paths.append(Path(path))
        if self.conflict:
            raise HistoricalOrderWorkbookConflict(self.conflict_code)
        return HistoricalOrderWorkbookReceipt(
            "0" * 64, 1, 1, 0, 0, 0, 0, 0, False,
            HistoricalOrderStatusCounts(0, 1, 0, 0),
            HistoricalOrderResultCounts(0, 0, 1, 0, 0),
        )


def test_preview_and_apply_remove_server_temporary_workbooks():
    service = _Service()
    client = _client(service)
    preview = client.post("/api/v1/orders/historical-adoption/workbooks/preview", files=_file())
    apply = client.post(
        "/api/v1/orders/historical-adoption/workbooks/apply", headers=_headers(),
        data={"preview_fingerprint": "2" * 64}, files=_file(),
    )

    assert preview.status_code == 200
    assert apply.status_code == 200
    assert all(path.exists() is False for path in service.paths)


def test_apply_conflict_is_typed_and_removes_temporary_workbook():
    service = _Service(conflict=True)
    response = _client(service).post(
        "/api/v1/orders/historical-adoption/workbooks/apply", headers=_headers(),
        data={"preview_fingerprint": "2" * 64}, files=_file(),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "historical_order_workbook_idempotency_conflict"
    assert service.paths[0].exists() is False


def test_apply_stale_preview_is_a_conflict_not_a_validation_error():
    service = _Service(conflict=True, conflict_code="historical_order_preview_stale")
    response = _client(service).post(
        "/api/v1/orders/historical-adoption/workbooks/apply", headers=_headers(),
        data={"preview_fingerprint": "2" * 64}, files=_file(),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "historical_order_preview_stale"


def test_database_dependency_unavailable_is_typed(monkeypatch):
    import api.dependencies.historical_order_adoption as dependency
    import pymysql

    monkeypatch.setattr(dependency, "get_connection", lambda: (_ for _ in ()).throw(pymysql.OperationalError(2003, "offline")))
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[require_admin] = lambda: SimpleNamespace(username="test-admin")

    response = TestClient(application).post("/api/v1/orders/historical-adoption/workbooks/preview", files=_file())

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "historical_order_import_database_unavailable"


def test_apply_reports_pending_status_constraint_as_database_upgrade_required():
    service = _Service()

    def fail_apply(*_args):
        raise OperationalError(
            3819,
            "Check constraint 'chk_order_lifecycle_state_event_before_status' is violated.",
        )

    service.apply = fail_apply
    response = _client(service).post(
        "/api/v1/orders/historical-adoption/workbooks/apply",
        headers=_headers(),
        data={"preview_fingerprint": "2" * 64},
        files=_file(),
    )

    assert response.status_code == 503
    assert response.json()["detail"]["error"]["code"] == (
        "historical_order_database_upgrade_required"
    )


def test_apply_reports_pairing_resolution_enum_drift_as_database_upgrade_required():
    service = _Service()

    def fail_apply(*_args):
        raise DataError(1265, "Data truncated for column 'resolution' at row 1")

    service.apply = fail_apply
    response = _client(service).post(
        "/api/v1/orders/historical-adoption/workbooks/apply",
        headers=_headers(),
        data={"preview_fingerprint": "2" * 64},
        files=_file(),
    )

    assert response.status_code == 503
    assert response.json()["detail"]["error"]["code"] == (
        "historical_order_database_upgrade_required"
    )
    assert response.json()["detail"]["error"]["retryable"] is False


def test_apply_actual_start_idempotency_mismatch_is_a_conflict_not_a_server_error():
    service = _Service()

    def fail_apply(*_args):
        raise ActualStartWorkflowError(
            TypedError(
                ErrorCategory.IDEMPOTENCY_MISMATCH,
                "idempotency_mismatch",
                "Idempotency key was already used with a different command.",
                CorrelationId("historical-order-router-test"),
            )
        )

    service.apply = fail_apply
    response = _client(service).post(
        "/api/v1/orders/historical-adoption/workbooks/apply",
        headers=_headers(),
        data={"preview_fingerprint": "2" * 64},
        files=_file(),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["error"]["code"] == "idempotency_mismatch"


def test_preview_actual_start_blocker_uses_domain_blocked_error_envelope():
    service = _Service()

    def fail_preview(*_args):
        raise ActualStartWorkflowError(
            TypedError(
                ErrorCategory.DOMAIN_BLOCKED,
                "historical_assignment_required_for_actual_start",
                "歷史訂單缺少重建實際開工所需的目前資料。",
                CorrelationId("historical-order-router-test"),
                domain_blockers=("historical_assignment_required_for_actual_start",),
            )
        )

    service.preview = fail_preview
    response = _production_client(service).post(
        "/api/v1/orders/historical-adoption/workbooks/preview",
        headers=_headers(),
        files=_file(),
    )

    assert response.status_code == 409
    error = response.json()["detail"]["error"]
    assert error["category"] == "domain_blocked"
    assert error["code"] == "historical_assignment_required_for_actual_start"
    assert error["domain_blockers"] == ["historical_assignment_required_for_actual_start"]
    assert error["correlation_id"] == "historical-order-router-test"


def test_preview_rejects_source_schedule_overlap_as_a_validation_error():
    service = _Service()

    def fail_preview(*_args):
        raise ValueError("historical_order_source_schedule_conflict")

    service.preview = fail_preview
    response = _client(service).post(
        "/api/v1/orders/historical-adoption/workbooks/preview",
        headers={"X-Correlation-ID": "historical-source-overlap"},
        files=_file(),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["error"]["code"] == (
        "historical_order_source_schedule_conflict"
    )


def test_actual_xlsx_upload_rejects_nonblank_invalid_status_before_apply():
    """A contradictory nonblank source value rejects the whole workbook."""
    repository = _WorkbookRepository()
    service = HistoricalOrderWorkbookImportService(
        repository,
        _PreviewMatrixWorkflow(),
        _UnitOfWork,
    )
    client = _client(service)
    upload = _preview_matrix_workbook()

    preview_response = client.post(
        "/api/v1/orders/historical-adoption/workbooks/preview",
        headers={"X-Correlation-ID": "historical-matrix-preview"},
        files={"workbook": ("historical-preview-matrix.xlsx", upload, _XLSX_MEDIA_TYPE)},
    )

    assert preview_response.status_code == 422
    assert preview_response.json()["detail"]["error"]["code"] == (
        "historical_order_source_status_invalid"
    )
    assert repository.receipts == {}


def _client(service):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(username="test-admin")
    app.dependency_overrides[get_historical_order_workbook_import_service] = lambda: service
    return TestClient(app)


def _production_client(service):
    app = FastAPI()
    app.include_router(router)
    app.add_middleware(CorrelationBoundaryMiddleware)
    install_typed_error_handlers(app)
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(username="test-admin")
    app.dependency_overrides[get_historical_order_workbook_import_service] = lambda: service
    return TestClient(app)


def _headers():
    return {"Idempotency-Key": "historical-order-router-test", "X-Correlation-ID": "historical-order-router-test"}


def _file():
    return {"workbook": ("orders.xlsx", b"test", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}


_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class _UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        return None


class _WorkbookRepository:
    def __init__(self):
        self.claims: dict[str, str] = {}
        self.receipts: dict[str, dict[str, str]] = {}
        self.locked: set[str] = set()

    def acquire_lock(self, key):
        if key in self.locked:
            return False
        self.locked.add(key)
        return True

    def release_lock(self, key):
        self.locked.remove(key)

    def load_receipt(self, key):
        return self.receipts.get(key)

    def find_absent_orders(self, _source_case_nos, *, for_update):
        assert type(for_update) is bool
        return ()

    def cancel_absent_orders(
        self,
        candidates,
        *,
        workbook_key,
        source_content_digest,
        actor,
        correlation_id,
    ):
        del workbook_key, source_content_digest, actor, correlation_id
        assert candidates == ()
        return 0

    def claim(self, key, digest, _correlation_id):
        prior = self.claims.get(key)
        if prior is not None and prior != digest:
            return "conflict"
        self.claims[key] = digest
        return "created"

    def save_receipt(self, key, digest, _preview_fingerprint, _actor, result):
        self.receipts[key] = {
            "request_fingerprint": digest,
            "result_snapshot": json.dumps(result),
        }


class _PreviewMatrixWorkflow:
    _OUTCOMES = {
        "MATRIX-CANCELLED": (HistoricalOrderOutcome.ADOPTED, (), ()),
        "MATRIX-DEPOSIT": (
            HistoricalOrderOutcome.ADOPTED,
            (HistoricalPairingResolution.ASSIGNMENT_CANDIDATE,),
            (),
        ),
        "MATRIX-DISCUSSION": (
            HistoricalOrderOutcome.ADOPTED,
            (HistoricalPairingResolution.EVIDENCE_ONLY,),
            (),
        ),
        "MATRIX-UNMATCHED": (HistoricalOrderOutcome.UNMATCHED_CASE, (), ()),
        "MATRIX-REVIEW": (
            HistoricalOrderOutcome.REVIEW_REQUIRED,
            (),
            ("historical_status_invalid",),
        ),
        "MATRIX-CONFLICT": (HistoricalOrderOutcome.CURRENT_CONFLICT, (), ()),
    }

    def preview(self, row):
        outcome, resolutions, issues = self._OUTCOMES[row.case_no]
        pairings = tuple(
            HistoricalPairingCandidate(
                index,
                "月**",
                100 + index,
                row.actual_start_date,
                row.actual_end_date,
                resolution,
                (),
            )
            for index, resolution in enumerate(resolutions, start=1)
        )
        return HistoricalOrderAdoptionPreview(
            row.source_identity,
            row.source_fingerprint,
            outcome,
            None if outcome is HistoricalOrderOutcome.UNMATCHED_CASE else row.case_no,
            0,
            0,
            "洽談中",
            "洽談中",
            (),
            pairings,
            issues,
            fingerprint_payload({"source_identity": row.source_identity, "outcome": outcome.value}),
        )

    def apply(self, request):
        preview = self.preview(request.row)
        return HistoricalOrderAdoptionReceipt(
            preview.outcome,
            preview.case_no,
            preview.resulting_version,
            sum(
                pairing.resolution is HistoricalPairingResolution.ASSIGNMENT_CANDIDATE
                for pairing in preview.pairings
            ),
            "historical-review" if preview.outcome is HistoricalOrderOutcome.REVIEW_REQUIRED else None,
            False,
            request.preview_fingerprint,
        )

    def preview_in_current_unit_of_work(self, row, *, for_update):
        assert for_update is True
        return self.preview(row)

    def apply_in_current_unit_of_work(self, request):
        return self.apply(request)


def _preview_matrix_workbook() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "歷史訂單預覽矩陣"
    sheet.append(["客戶姓名", "案件編號", "開始日期", "結束日期", "狀態", "月嫂姓名"])
    sheet.append(["客戶甲", "MATRIX-CANCELLED", date(2025, 1, 2), date(2025, 1, 31), 0, None])
    sheet.append(["客戶乙", "MATRIX-DEPOSIT", date(2025, 2, 2), date(2025, 2, 28), 1, "月嫂甲"])
    sheet.append(["客戶丙", "MATRIX-DISCUSSION", date(2025, 3, 3), date(2025, 3, 31), 2, "月嫂乙"])
    sheet.append(["客戶丁", "MATRIX-UNMATCHED", None, None, 1, None])
    sheet.append(["客戶戊", "MATRIX-REVIEW", None, None, "無效狀態", None])
    sheet.append(["客戶己", "MATRIX-CONFLICT", None, None, 1, None])
    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()
