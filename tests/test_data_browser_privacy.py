"""Regression coverage for canonical Data Browser projections after issue #101."""

from __future__ import annotations

import json

from api.schemas.data_browser import DataBrowserPageView
from infrastructure.mysql.data_browser_query_repository import DataBrowserQueryRepository


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, _sql, _params):
        return None

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.rows = rows

    def cursor(self):
        return _Cursor(self.rows)


def _render(source_id, row):
    page = DataBrowserQueryRepository(_Connection([row])).query_page(
        source_id,
        limit=25,
        after=None,
        query=None,
    )
    return json.dumps(
        DataBrowserPageView.model_validate(page).model_dump(mode="json"),
        ensure_ascii=False,
    )


def test_client_and_staff_rows_preserve_canonical_names_without_expanding_projection():
    client = _render(
        "clients",
        {
            "id": 7,
            "name": "林佩萱",
            "city": "台北市",
            "identity_status": "一般市民",
            "db_created_at": "2026-08-01T00:00:00",
            "db_updated_at": "2026-08-02T00:00:00",
            "phone": "OUTSIDE_PROJECTION_PHONE",
            "address": "OUTSIDE_PROJECTION_ADDRESS",
        },
    )
    staff = _render(
        "staff",
        {
            "id": 9,
            "name": "王美惠",
            "city": "新竹市",
            "status": "active",
            "created_at": "2026-08-01T00:00:00",
            "updated_at": "2026-08-02T00:00:00",
            "identity_card": "OUTSIDE_PROJECTION_ID",
            "bank_account": "OUTSIDE_PROJECTION_ACCOUNT",
        },
    )

    assert "林佩萱" in client
    assert "王美惠" in staff
    assert "OUTSIDE_PROJECTION_PHONE" not in client
    assert "OUTSIDE_PROJECTION_ADDRESS" not in client
    assert "OUTSIDE_PROJECTION_ID" not in staff
    assert "OUTSIDE_PROJECTION_ACCOUNT" not in staff


def test_bank_row_exposes_canonical_amount_without_expanding_projection():
    rendered = _render(
        "bank_facts",
        {
            "id": 12,
            "dedup_fingerprint": "a" * 64,
            "transaction_date": "2026-08-17",
            "direction": "incoming",
            "classification_type": "pending",
            "reconciliation_status": "pending",
            "credit": 78000,
            "debit": None,
            "created_at": "2026-08-17T00:00:00",
            "source_bank_account": "OUTSIDE_PROJECTION_ACCOUNT",
            "counterparty_name": "OUTSIDE_PROJECTION_COUNTERPARTY",
            "raw_payload": {"secret": "raw"},
        },
    )

    assert "78000" in rendered
    assert "OUTSIDE_PROJECTION_ACCOUNT" not in rendered
    assert "OUTSIDE_PROJECTION_COUNTERPARTY" not in rendered
    assert "raw_payload" not in rendered
