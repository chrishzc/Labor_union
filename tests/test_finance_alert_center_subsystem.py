from __future__ import annotations

import json

from fastapi import HTTPException
import pytest

from api.routes import system_alerts
from api.schemas.finance_alert_center import (
    AlertFamily,
    AlertQuery,
    ImportReviewBatchViewModel,
    ScanAlertsCommand,
    TypedErrorCode,
    system_alert_detail_from_record,
)
from ui.api_clients.finance_alert_center_client import (
    FinanceAlertCenterApiClient,
    FinanceAlertCenterApiError,
)


def _system_record():
    return {
        "id": 6,
        "alert_code": "IMPORT-006",
        "source_domain": "finance_import",
        "case_key": "finance-import-batch:1",
        "reason": "銀行對帳匯入待人工分類",
        "status": "open",
        "details": json.dumps(
            {
                "batch_id": 1,
                "format_id": "legacy",
                "source_file": r"C:\imports\history.xlsx",
                "batch_status": "completed",
                "row_count": 2659,
                "occurrence_count": 2659,
                "distinct_count": 2655,
                "remaining_count": 2376,
                "direction_counts": {"incoming": 1779, "outgoing": 597},
                "reason_counts": {
                    "sinopac_invalid_or_missing_virtual_account": 1779,
                    "sinopac_staff_account_no_match": 597,
                },
                "sample_row_ids": list(range(1, 30)),
                "last_reprocess": {
                    "run_id": 2,
                    "status": "completed",
                    "selected_count": 2655,
                    "changed_count": 279,
                },
            },
            ensure_ascii=False,
        ),
    }


def test_import_006_maps_to_bounded_typed_batch_view() -> None:
    detail = system_alert_detail_from_record(_system_record())

    assert isinstance(detail, ImportReviewBatchViewModel)
    assert detail.occurrence_count == 2659
    assert detail.distinct_count == 2655
    assert detail.remaining_count == 2376
    assert len(detail.sample_row_ids) == 20
    assert detail.source_file_label == "history.xlsx"
    assert detail.last_reprocess.changed_count == 279
    assert {item.key: item.count for item in detail.direction_counts} == {
        "incoming": 1779,
        "outgoing": 597,
    }


class _Response:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._body


class _Session:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response


def test_api_client_preserves_typed_conflict_and_never_falls_back() -> None:
    session = _Session(
        _Response(
            409,
            {
                "detail": {
                    "code": "conflict",
                    "message": "stale alert",
                    "retryable": False,
                }
            },
        )
    )
    client = FinanceAlertCenterApiClient(
        base_url="http://admin.test",
        headers={"X-Internal-API-Key": "test"},
        session=session,
    )

    with pytest.raises(FinanceAlertCenterApiError) as exc_info:
        client.list_alerts(AlertQuery(family=AlertFamily.SYSTEM))

    assert exc_info.value.status_code == 409
    assert exc_info.value.error.code == TypedErrorCode.CONFLICT
    assert len(session.calls) == 1


class _Cursor:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Connection:
    def __init__(self):
        self.cursor_value = _Cursor()
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed += 1


def test_system_scan_requires_import_006_and_commits_once(monkeypatch) -> None:
    connection = _Connection()
    monkeypatch.setattr(system_alerts, "get_connection", lambda: connection)
    monkeypatch.setattr(
        system_alerts,
        "run_process_alert_scan",
        lambda cursor: {
            "IMPORT-006": {
                "created": 1,
                "updated": 0,
                "reopened": 0,
                "resolved": 0,
                "unchanged": 0,
            }
        },
    )

    result = system_alerts.scan_alerts()

    assert result.data.items[0].alert_code == "IMPORT-006"
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert connection.closed == 1


def test_system_scan_missing_import_006_rolls_back(monkeypatch) -> None:
    connection = _Connection()
    monkeypatch.setattr(system_alerts, "get_connection", lambda: connection)
    monkeypatch.setattr(
        system_alerts,
        "run_process_alert_scan",
        lambda cursor: {"PROCESS-001": {"unchanged": 1}},
    )

    with pytest.raises(HTTPException) as exc_info:
        system_alerts.scan_alerts()

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail["code"] == "internal_error"
    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.closed == 1


def test_scan_command_only_targets_system_family() -> None:
    assert ScanAlertsCommand().family == AlertFamily.SYSTEM
