"""
File: test_data_browser_privacy.py
Description: 驗證 Data Browser masked rows 不輸出 PII 或 raw payload。
"""

from __future__ import annotations

import json

from api.schemas.data_browser import DataBrowserMaskedPageView
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
    page = DataBrowserQueryRepository(_Connection([row])).query_masked_page(
        source_id,
        limit=25,
        after=None,
        query=None,
    )
    return json.dumps(
        DataBrowserMaskedPageView.model_validate(page).model_dump(mode="json"),
        ensure_ascii=False,
    )


def test_client_and_staff_rows_mask_names_and_omit_contact_fields():
    client = _render(
        "clients",
        {
            "id": 7,
            "name": "林佩萱",
            "city": "台北市",
            "identity_status": "一般市民",
            "db_created_at": "2026-08-01T00:00:00",
            "db_updated_at": "2026-08-02T00:00:00",
            "phone": "SENSITIVE_PHONE_SENTINEL",
            "address": "完整地址不得出現",
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
            "identity_card": "A123456789",
            "bank_account": "1234567890",
        },
    )

    assert "林佩萱" not in client and "林○○" in client
    assert "SENSITIVE_PHONE_SENTINEL" not in client and "完整地址不得出現" not in client
    assert "王美惠" not in staff and "王○○" in staff
    assert "A123456789" not in staff and "1234567890" not in staff


def test_bank_row_never_exposes_amount_or_account_details():
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
            "source_bank_account": "完整銀行帳號",
            "counterparty_name": "完整交易人",
            "raw_payload": {"secret": "raw"},
        },
    )

    assert "78000" not in rendered
    assert "完整銀行帳號" not in rendered
    assert "完整交易人" not in rendered
    assert "raw_payload" not in rendered
    assert "NT$ ****" in rendered
