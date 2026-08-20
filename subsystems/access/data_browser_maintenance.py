"""
File: data_browser_maintenance.py
Description: 編排 legacy table metadata 與 masked Data Browser query。
"""

from typing import Any, Dict
from infrastructure.mysql import mysql_adapter as db_service

# 白名單資料表
ALLOWED_TABLES = {
    "clients",
    "staff",
    "orders",
    "beclass_records",
    "holidays",
    "matching_records",
    "staff_bank_accounts",
    "line_confirmation_requests",
    "staff_bookings",
    "case_staff_assignments",
    "client_payments",
    "client_payment_transactions",
    "actual_hours_adjustments",
    "staff_payments",
    "staff_payment_transactions",
    "payment_migration_reviews",
    "staff_schedule",
}

# 可編輯欄位白名單
EDITABLE_COLUMNS = {
    "clients": ["name", "gender", "phone", "city", "address", "notes", "admin_notes", "reject_reason"],
    "beclass_records": ["name", "email", "phone", "tel", "ext", "city", "zip_code", "address", "admin_notes"],
    "staff": ["name", "phone", "tel", "tel_ext", "email", "city", "zip_code", "address", "birthday", "has_massage_cert", "weekly_rest_days", "service_regions", "special_skills", "care_babies"],
}

# 唯讀表清單：僅來源主檔可經 source-correction workflow 變更。
READ_ONLY_TABLES = ALLOWED_TABLES - set(EDITABLE_COLUMNS)


# 下拉選單中繼資料 (SSOT)
COLUMN_VALID_OPTIONS = {
    'clients': {
        'gender': ['女', '男'],
        'residence_type': ['電梯大樓', '公寓', '透天', '其他'],
        'delivery_type': ['自然產', '剖腹產', '未定'],
        'service_type': ['24小時', '9小時', '4小時', '其他'],
    },
    'staff': {
        'has_massage_cert': ['有', '無'],
    },
    'matching_records': {
        'caregiver_accepted': ['0', '1'],
    },
}

def get_data_browser_table_schema(table_name: str) -> Dict[str, Any]:
    """
    動態取得資料表之資料列、欄位清單與中繼權限 SSOT。
    關鍵修復：主鍵由 TABLE_PRIMARY_KEYS 動態回傳 (例如 orders 轉為 case_no)。
    """
    if table_name not in ALLOWED_TABLES:
        raise ValueError(f"不允許存取的資料表: {table_name}")

    rows = db_service.get_table_data(table_name)
    cols = db_service.get_table_columns(table_name)
    pk_col = db_service.TABLE_PRIMARY_KEYS.get(table_name, "id")
    is_read_only = table_name in READ_ONLY_TABLES
    editable = [] if is_read_only else EDITABLE_COLUMNS.get(table_name, [])

    return {
        "rows": rows,
        "columns": cols,
        "primary_key": pk_col,
        "editable_columns": editable,
        "valid_options": COLUMN_VALID_OPTIONS.get(table_name, {}),
        "read_only": is_read_only,
    }


def query_masked_data_browser_source(
    repository,
    source_id: str,
    *,
    limit: int,
    after: str | None,
    query: str | None,
):
    """Run one bounded read-only source query without exposing table identifiers."""
    if limit < 1 or limit > 100:
        raise ValueError("limit_invalid")
    return repository.query_masked_page(
        source_id,
        limit=limit,
        after=after,
        query=query,
    )
