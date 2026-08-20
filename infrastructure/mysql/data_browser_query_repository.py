"""
File: data_browser_query_repository.py
Description: 查詢六個 allowlisted source 並在 repository 邊界產生 masked rows。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
import hashlib
import json
from typing import Literal


SourceId = Literal[
    "orders",
    "clients",
    "staff",
    "beclass_intake",
    "hcm_review",
    "bank_facts",
]
Presentation = Literal[
    "text",
    "date",
    "datetime",
    "integer",
    "decimal",
    "status",
    "masked",
]


@dataclass(frozen=True, slots=True)
class MaskedCell:
    field_id: str
    label: str
    value: str | int | bool | float | None
    presentation: Presentation


@dataclass(frozen=True, slots=True)
class MaskedRow:
    source_id: SourceId
    row_identity: str
    display_title: str
    summary_cells: tuple[MaskedCell, ...]
    detail_cells: tuple[MaskedCell, ...]
    recorded_at: str | None
    source_actor_label: str | None
    version_identity: str


@dataclass(frozen=True, slots=True)
class MaskedPage:
    source_id: SourceId
    items: tuple[MaskedRow, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class _SourceSpec:
    table: str
    primary_key: str
    columns: tuple[str, ...]
    search_columns: tuple[str, ...]
    integer_cursor: bool


_SOURCE_SPECS: dict[str, _SourceSpec] = {
    "orders": _SourceSpec(
        "orders",
        "case_no",
        ("case_no", "status", "start_date", "end_date", "created_at", "updated_at"),
        ("case_no", "status"),
        False,
    ),
    "clients": _SourceSpec(
        "clients",
        "id",
        ("id", "name", "city", "identity_status", "db_created_at", "db_updated_at"),
        ("id", "city", "identity_status"),
        True,
    ),
    "staff": _SourceSpec(
        "staff",
        "id",
        ("id", "name", "city", "status", "created_at", "updated_at"),
        ("id", "city", "status"),
        True,
    ),
    "beclass_intake": _SourceSpec(
        "beclass_records",
        "id",
        ("id", "query_no", "name", "created_at", "db_created_at", "db_updated_at"),
        ("id", "query_no"),
        True,
    ),
    "hcm_review": _SourceSpec(
        "case_import_hcm_review_rows",
        "id",
        ("id", "review_identity", "masked_case_identity", "issue_codes", "created_at"),
        ("id", "masked_case_identity"),
        True,
    ),
    "bank_facts": _SourceSpec(
        "finance_import_rows",
        "id",
        (
            "id",
            "dedup_fingerprint",
            "transaction_date",
            "direction",
            "classification_type",
            "reconciliation_status",
            "credit",
            "debit",
            "created_at",
        ),
        ("id", "dedup_fingerprint", "direction", "classification_type", "reconciliation_status"),
        True,
    ),
}


class DataBrowserSourceNotFound(ValueError):
    """The public source identity is not in the fixed allowlist."""


class DataBrowserQueryRepository:
    def __init__(self, connection) -> None:
        self._connection = connection

    def query_masked_page(
        self,
        source_id: str,
        *,
        limit: int,
        after: str | None,
        query: str | None,
    ) -> MaskedPage:
        spec = _SOURCE_SPECS.get(source_id)
        if spec is None:
            raise DataBrowserSourceNotFound("source_not_found")
        cursor_value = _cursor_value(spec, after)
        query_value = _query_value(query)
        where: list[str] = []
        params: list[object] = []
        if cursor_value is not None:
            where.append(f"`{spec.primary_key}` > %s")
            params.append(cursor_value)
        if query_value is not None:
            searchable = ", ".join(
                f"COALESCE(CAST(`{column}` AS CHAR), '')"
                for column in spec.search_columns
            )
            where.append(f"CONCAT_WS(' ', {searchable}) LIKE %s")
            params.append(f"%{query_value}%")
        predicate = f" WHERE {' AND '.join(where)}" if where else ""
        selected = ", ".join(f"`{column}`" for column in spec.columns)
        sql = (
            f"SELECT {selected} FROM `{spec.table}`{predicate} "
            f"ORDER BY `{spec.primary_key}` ASC LIMIT %s"
        )
        params.append(limit + 1)
        with self._connection.cursor() as cursor:
            cursor.execute(sql, tuple(params))
            rows = tuple(cursor.fetchall())
        visible = rows[:limit]
        items = tuple(_masked_row(source_id, row) for row in visible)
        next_cursor = items[-1].row_identity if len(rows) > limit and items else None
        return MaskedPage(source_id, items, next_cursor)


def canonical_source_ids() -> tuple[str, ...]:
    return tuple(_SOURCE_SPECS)


def _cursor_value(spec: _SourceSpec, after: str | None) -> int | str | None:
    if after is None:
        return None
    value = after.strip()
    if not value or len(value) > 191:
        raise ValueError("cursor_invalid")
    if spec.integer_cursor:
        if not value.isascii() or not value.isdigit() or int(value) < 1:
            raise ValueError("cursor_invalid")
        return int(value)
    return value


def _query_value(query: str | None) -> str | None:
    if query is None:
        return None
    value = query.strip()
    if not value:
        return None
    if len(value) > 100:
        raise ValueError("query_too_long")
    return value


def _masked_row(source_id: str, row: dict[str, object]) -> MaskedRow:
    builders = {
        "orders": _orders_row,
        "clients": _clients_row,
        "staff": _staff_row,
        "beclass_intake": _beclass_row,
        "hcm_review": _hcm_row,
        "bank_facts": _bank_row,
    }
    return builders[source_id](row)


def _orders_row(row):
    identity = _required_text(row.get("case_no"), "row_identity_invalid")
    cells = (
        _cell("status", "訂單狀態", row.get("status"), "status"),
        _cell("start_date", "服務開始", row.get("start_date"), "date"),
        _cell("end_date", "服務結束", row.get("end_date"), "date"),
        _cell("updated_at", "更新時間", row.get("updated_at"), "datetime"),
    )
    return _row("orders", identity, f"訂單 {identity}", cells[:3], cells, row.get("updated_at"))


def _clients_row(row):
    identity = _positive_identity(row.get("id"))
    name = _mask_name(row.get("name"))
    cells = (
        _cell("name", "客戶姓名", name, "masked"),
        _cell("city", "縣市", row.get("city"), "text"),
        _cell("identity_status", "身分資格", row.get("identity_status"), "status"),
        _cell("updated_at", "更新時間", row.get("db_updated_at"), "datetime"),
    )
    return _row("clients", identity, f"客戶 #{identity} · {name}", cells[:3], cells, row.get("db_updated_at"))


def _staff_row(row):
    identity = _positive_identity(row.get("id"))
    name = _mask_name(row.get("name"))
    cells = (
        _cell("name", "服務人員姓名", name, "masked"),
        _cell("city", "縣市", row.get("city"), "text"),
        _cell("status", "主檔狀態", row.get("status"), "status"),
        _cell("updated_at", "更新時間", row.get("updated_at"), "datetime"),
    )
    return _row("staff", identity, f"服務人員 #{identity} · {name}", cells[:3], cells, row.get("updated_at"))


def _beclass_row(row):
    identity = _positive_identity(row.get("id"))
    query_no = _safe_text(row.get("query_no"))
    name = _mask_name(row.get("name"))
    cells = (
        _cell("query_no", "查詢序號", query_no, "text"),
        _cell("name", "報名者", name, "masked"),
        _cell("received_at", "報名時間", row.get("created_at"), "datetime"),
        _cell("updated_at", "更新時間", row.get("db_updated_at"), "datetime"),
    )
    title_identity = query_no or f"#{identity}"
    return _row("beclass_intake", identity, f"BeClass {title_identity} · {name}", cells[:3], cells, row.get("db_updated_at"))


def _hcm_row(row):
    identity = _positive_identity(row.get("id"))
    masked_case = _required_text(row.get("masked_case_identity"), "masked_case_identity_invalid")
    cells = (
        _cell("masked_case_identity", "遮罩案件", masked_case, "masked"),
        _cell("issue_codes", "問題代碼", _issue_code_text(row.get("issue_codes")), "text"),
        _cell("created_at", "建立時間", row.get("created_at"), "datetime"),
    )
    return _row("hcm_review", identity, f"HCM review {masked_case}", cells, cells, row.get("created_at"))


def _bank_row(row):
    identity = _positive_identity(row.get("id"))
    amount_present = row.get("credit") is not None or row.get("debit") is not None
    cells = (
        _cell("transaction_date", "交易日期", row.get("transaction_date"), "date"),
        _cell("direction", "流向", row.get("direction"), "status"),
        _cell("classification_type", "分類", row.get("classification_type"), "status"),
        _cell("reconciliation_status", "核銷狀態", row.get("reconciliation_status"), "status"),
        _cell("amount", "金額", "NT$ ****" if amount_present else None, "masked"),
        _cell("created_at", "建立時間", row.get("created_at"), "datetime"),
    )
    return _row("bank_facts", identity, f"銀行根事實 #{identity}", cells[:4], cells, row.get("created_at"))


def _cell(field_id, label, value, presentation):
    return MaskedCell(field_id, label, _scalar(value), presentation)


def _row(source_id, identity, title, summary, detail, recorded_at):
    payload = {
        "source_id": source_id,
        "row_identity": identity,
        "summary": [(cell.field_id, cell.value) for cell in summary],
        "detail": [(cell.field_id, cell.value) for cell in detail],
    }
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return MaskedRow(
        source_id,
        identity,
        title,
        tuple(summary),
        tuple(detail),
        _datetime_text(recorded_at),
        None,
        digest,
    )


def _positive_identity(value) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("row_identity_invalid")
    return str(value)


def _required_text(value, code) -> str:
    text = _safe_text(value)
    if not text:
        raise ValueError(code)
    return text


def _safe_text(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:191] if text else None


def _mask_name(value) -> str:
    text = _safe_text(value)
    if not text:
        return "未提供"
    return text[0] + "○" * max(1, len(text) - 1)


def _issue_code_text(value) -> str | None:
    parsed = json.loads(value) if isinstance(value, str) else value
    if not isinstance(parsed, (list, tuple)):
        raise ValueError("issue_codes_invalid")
    codes: list[str] = []
    for item in parsed:
        text = _safe_text(item)
        if text is None:
            raise ValueError("issue_codes_invalid")
        codes.append(text)
    return ", ".join(codes)[:500]


def _scalar(value):
    if value is None or isinstance(value, (str, int, bool, float)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    raise ValueError("masked_cell_value_invalid")


def _datetime_text(value) -> str | None:
    scalar = _scalar(value)
    return None if scalar is None else str(scalar)
