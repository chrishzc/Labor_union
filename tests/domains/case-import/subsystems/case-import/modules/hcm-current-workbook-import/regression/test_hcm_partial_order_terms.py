"""A field warning must not discard other valid HCM intake terms."""

from datetime import date, datetime
import sqlite3

import pytest

from domains.case_import.case_import import CaseImportFacts, build_case_import_candidate
from domains.case_import.hcm_import_review import unresolved_hcm_review_fields
from domains.orders.lifecycle import OrderLifecycleStatus
from infrastructure.mysql.case_import_repository import _insert_order
from scripts.imports import import_client_hcm
from subsystems.orders.order_intake_terms_bootstrap import (
    OrderIntakeTermsBootstrapFacts,
    preview_completion_case,
)


class SqlCursor:
    def __init__(self, connection):
        self.cursor = connection.cursor()

    def execute(self, sql, params):
        values = tuple(value.isoformat() if type(value) is date else value for value in params)
        self.cursor.execute(sql.replace("%s", "?"), values)

    @property
    def rowcount(self):
        return self.cursor.rowcount


@pytest.mark.parametrize(
    "warning_field, expected_start, expected_days",
    [
        ("行動電話", "2026-10-20", 20),
        ("姓名", "2026-10-20", 20),
        ("生產方式", "2026-10-20", 20),
        ("服務時間", "2026-10-20", 20),
        ("預計服務日期", None, 20),
        ("希望服務天數", "2026-10-20", None),
    ],
)
def test_partial_import_persists_each_valid_term_independently(
    monkeypatch, warning_field, expected_start, expected_days,
):
    monkeypatch.setattr(import_client_hcm, "_find_matching_provisional_registration", lambda *_: None)
    intent = import_client_hcm._hcm_import_intent(
        None,
        {
            "case_no": "SYNTH-HCM-PARTIAL",
            "name": "測試客戶",
            "phone": "123",
            "created_at": datetime(2026, 10, 1, 9),
            "service_start_date": date(2026, 10, 20),
            "service_days": 20,
            "service_time": "8小時 09:00-17:00",
        },
        {"身分資格": "不可空值", warning_field: "不可空值"},
    )
    candidate = build_case_import_candidate(CaseImportFacts(False, None), intent)
    assert candidate.order is None and candidate.bootstrap is None

    with sqlite3.connect(":memory:") as connection:
        connection.execute(
            "CREATE TABLE orders (case_no TEXT, client_id INTEGER, status TEXT, "
            "lifecycle_version INTEGER, start_date TEXT, service_days INTEGER, service_hours_per_day REAL)"
        )
        _insert_order(SqlCursor(connection), candidate, 1)
        row = connection.execute(
            "SELECT status,start_date,service_days FROM orders"
        ).fetchone()

    assert row == ("待補件", expected_start, expected_days)
    current_values = {
        "clients.name": "測試客戶",
        "clients.phone": "0912345678",
        "clients.delivery_type": "自然產",
        "orders.start_date": row[1],
        "orders.service_days": row[2],
        "orders.service_hours_per_day": 8,
        "orders.service_start_time": "09:00:00",
        "orders.service_end_time": "17:00:00",
        "orders.service_end_day_offset": 0,
    }
    assert unresolved_hcm_review_fields((warning_field,), current_values) == (
        (warning_field,) if warning_field in {"預計服務日期", "希望服務天數"} else ()
    )

    class CompletionRepository:
        def load_case(self, case_no, *, for_update):
            assert for_update is False
            return OrderIntakeTermsBootstrapFacts(
                case_no, OrderLifecycleStatus.PENDING_COMPLETION, 0,
                date.fromisoformat(row[1]) if row[1] else None, row[2],
                None, False, False, False, False, True, "測試客戶",
            )

    completion = preview_completion_case(CompletionRepository(), intent.case_no, for_update=False)
    expected_missing = (
        ("start_date",) if expected_start is None else
        ("service_days",) if expected_days is None else ()
    )
    assert completion.missing_fields == expected_missing
    assert completion.apply_allowed is (not expected_missing)
