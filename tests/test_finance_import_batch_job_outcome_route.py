"""
File: test_finance_import_batch_job_outcome_route.py
Description: 驗證 Finance Import durable Apply 只透過 canonical receipt table 公開 terminal receipt。
"""

from types import SimpleNamespace

import pytest

from api.routes.finance_import import query_finance_import_batch_job_outcome
from api.routes.finance_import import query_finance_import_correction_job_outcome
from subsystems.finance_import.query import (
    FinanceImportBatchApplyReceipt,
    FinanceImportCorrectionApplyReceipt,
)


def _job(status="succeeded"):
    return SimpleNamespace(
        job_id="finance-job-1",
        command_identity="finance-apply-key",
        command_type="finance_import_batch_apply",
        status=status,
        receipt_payload={"kind": "success", "schema_version": 1, "result_reference": "finance_import_batch:finance-import-batch:9"},
        error_payload=None,
        attempt_count=1,
        max_attempts=3,
    )


def test_succeeded_batch_job_reads_typed_receipt_not_durable_raw_payload() -> None:
    repository = SimpleNamespace(get_job=lambda _job_id: _job())
    receipt = FinanceImportBatchApplyReceipt("finance-import-batch:9", 2, "a" * 64, 1, 2, 3)
    query = SimpleNamespace(get_batch_apply_receipt=lambda key: receipt if key == "finance-apply-key" else None)

    response = query_finance_import_batch_job_outcome("finance-job-1", None, repository, query)

    assert response.data.status == "succeeded"
    assert response.data.result_reference == "finance_import_batch:finance-import-batch:9"
    assert response.data.receipt is not None
    assert response.data.receipt.reconciled_count == 1


def test_succeeded_batch_job_fails_closed_when_receipt_is_missing() -> None:
    repository = SimpleNamespace(get_job=lambda _job_id: _job())
    query = SimpleNamespace(get_batch_apply_receipt=lambda _key: None)

    with pytest.raises(Exception) as raised:
        query_finance_import_batch_job_outcome("finance-job-1", None, repository, query)

    assert raised.value.status_code == 503
    assert raised.value.detail["error"]["code"] == "finance_import_batch_receipt_unavailable"


def test_succeeded_correction_job_reads_typed_receipt_not_durable_raw_payload() -> None:
    repository = SimpleNamespace(
        get_job=lambda _job_id: SimpleNamespace(
            **{
                **_job().__dict__,
                "command_identity": "finance-correction-key",
                "command_type": "finance_import_correction_apply",
            }
        )
    )
    receipt = FinanceImportCorrectionApplyReceipt(
        "finance-import-row:9", "finance-import-batch:9", 2, 1, 1, 1, 1, 1, "a" * 64
    )
    query = SimpleNamespace(
        get_correction_apply_receipt=lambda key: receipt if key == "finance-correction-key" else None
    )

    response = query_finance_import_correction_job_outcome("finance-job-1", None, repository, query)

    assert response.data.status == "succeeded"
    assert response.data.receipt is not None
    assert response.data.receipt.row_identity == "finance-import-row:9"


def test_succeeded_correction_job_fails_closed_when_receipt_is_missing() -> None:
    repository = SimpleNamespace(
        get_job=lambda _job_id: SimpleNamespace(
            **{
                **_job().__dict__,
                "command_identity": "finance-correction-key",
                "command_type": "finance_import_correction_apply",
            }
        )
    )
    query = SimpleNamespace(get_correction_apply_receipt=lambda _key: None)

    with pytest.raises(Exception) as raised:
        query_finance_import_correction_job_outcome("finance-job-1", None, repository, query)

    assert raised.value.status_code == 503
    assert raised.value.detail["error"]["code"] == "finance_import_correction_receipt_unavailable"
