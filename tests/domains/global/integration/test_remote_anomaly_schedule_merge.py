"""
File: test_remote_anomaly_schedule_merge.py
Description: 驗證遠端異常、排程與 HCM durable review 相容邊界。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.routes import anomaly_registry, staff
from infrastructure.mysql import anomaly_registry_repository
from infrastructure.mysql.staff_summary_query_repository import (
    MySqlStaffSummaryQueryRepository,
)
from scripts.imports import import_client_hcm
from subsystems.staff.summary_query import (
    StaffSummaryQueryApplication,
    StaffSummaryQueryService,
)
from subsystems.access.authentication_session import AdminPrincipal


class _Cursor:
    def __init__(self, rows=()):
        self.rows = list(rows)
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        return False

    def execute(self, query, parameters=None):
        self.executed.append((query, parameters))

    def fetchall(self):
        return list(self.rows)


class _Connection:
    def __init__(self, rows=()):
        self.cursor_instance = _Cursor(rows)
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


def test_projector_idempotency_key_is_fixed_length_and_semantic():
    request = SimpleNamespace(
        consumer_identity="consumer" * 40,
        partition_identity="partition" * 40,
        source_event_identity="event" * 100,
    )

    first = anomaly_registry_repository._projector_key(request, "reopen")
    second = anomaly_registry_repository._projector_key(request, "reopen")
    different = anomaly_registry_repository._projector_key(request, "auto_resolve")

    assert first == second
    assert first != different
    assert len(first) == len("anomaly-projector:") + 64


def test_schedule_navigation_is_typed_by_api_adapter():
    schedule_001 = anomaly_registry._staff_calendar_navigation(
        "SCHEDULE-001",
        {"staff_id": 7, "holiday_date": "2026-10-10"},
    )
    schedule_003 = anomaly_registry._staff_calendar_navigation(
        "SCHEDULE-003",
        {"staff_id": 8, "assignment_a": {"start": "2026-09-03"}},
    )

    assert schedule_001 == {"staff_id": 7, "target_date": "2026-10-10"}
    assert schedule_003 == {"staff_id": 8, "target_date": "2026-09-03"}
    assert anomaly_registry._staff_calendar_navigation(
        "SCHEDULE-005",
        {"staff_id": 9, "work_date": "not-a-date"},
    ) is None


def test_staff_summary_supports_exact_typed_lookup():
    connection = _Connection(
        [{"id": 7, "name": "王小美", "phone": "0900", "education": None}]
    )

    response = staff.get_staff_summaries(
        page_size=1,
        after_id=None,
        staff_id=7,
        principal=AdminPrincipal(7, "staff-reader", "Staff Reader", "admin"),
        application=StaffSummaryQueryApplication(
            StaffSummaryQueryService(MySqlStaffSummaryQueryRepository(connection))
        ),
    )
    connection.close()

    assert response.data.items[0].id == 7
    assert response.data.next_cursor is None
    assert connection.cursor_instance.executed[0][1] == (7,)
    assert connection.closed is True


def test_existing_hcm_case_with_invalid_source_persists_owned_review(monkeypatch):
    recorded = []
    monkeypatch.setattr(
        import_client_hcm,
        "_normalized_record",
        lambda row: {"case_no": "CASE-7", "created_at": object()},
    )
    monkeypatch.setattr(
        import_client_hcm,
        "validate_hcm_row",
        lambda row: {"服務天數": "invalid"},
    )
    monkeypatch.setattr(
        import_client_hcm,
        "record_hcm_import_review",
        lambda connection, **kwargs: recorded.append(kwargs) or "hcm-review:test",
    )
    application = SimpleNamespace(
        resolve_hcm_identity=lambda *_: import_client_hcm.HcmIdentityResolution.EXISTING_MATCH,
        find_receipt=lambda *_: None,
    )

    result = import_client_hcm._import_row(
        SimpleNamespace(to_dict=lambda: {"查詢序號(案件編號)": "CASE-7"}),
        3,
        object(),
        application,
        "hcm.xlsx",
        connection=object(),
        source_digest="a" * 64,
        source_sheet="來源",
    )

    assert result == "review_required"
    assert recorded[0]["case_identity"] == "CASE-7"
    assert recorded[0]["source_row"] == 3


def test_hcm_review_persistence_failure_is_not_reported_as_reviewable(monkeypatch):
    monkeypatch.setattr(
        import_client_hcm,
        "record_hcm_import_review",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("DB unavailable")),
    )

    with pytest.raises(RuntimeError, match="DB unavailable"):
        import_client_hcm._persist_hcm_review(
            object(), "a" * 64, "來源", 3, {}, "CASE-7", {"服務天數": "invalid"}
        )
