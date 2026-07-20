"""Normalize Sinopac's fifteen-column statement without classifying payments."""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd


SINOPAC_HEADERS = (
    "帳號",
    "交易日",
    "計息日",
    "入帳日",
    "摘要",
    "幣別",
    "支出",
    "存入",
    "餘額",
    "票據號碼",
    "銷帳編號",
    "交易參考編號",
    "備註",
    "更正註記",
    "存摺備註",
)


def _canonical_header(value: Any) -> str:
    if pd.isna(value):
        return ""
    return "".join(unicodedata.normalize("NFKC", str(value)).split())


def _is_missing(value: Any) -> bool:
    try:
        missing = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return bool(missing) if not hasattr(missing, "__len__") else False


def _identifier(value: Any) -> str | None:
    """Return a lossless textual identifier without adding a trailing .0."""

    if _is_missing(value):
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    return text or None


def _verbatim_text(value: Any) -> str | None:
    """Preserve non-empty bank note text without account-like interpretation."""
    if _is_missing(value):
        return None
    if isinstance(value, str):
        return value if value.strip() else None
    return _identifier(value)


def _decimal(value: Any) -> Decimal | None:
    if _is_missing(value) or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"無法解析永豐金額：{value!r}") from exc


def _timestamp(value: Any) -> pd.Timestamp | None:
    if _is_missing(value) or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, (bool, int, float, Decimal)):
        return None
    if isinstance(value, str) and not re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}", value.strip()):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed


def _iso_date(value: Any) -> str | None:
    parsed = _timestamp(value)
    return parsed.strftime("%Y-%m-%d") if parsed is not None else None


def _iso_time(value: Any) -> str | None:
    parsed = _timestamp(value)
    return parsed.strftime("%H:%M:%S") if parsed is not None else None


def _json_scalar(value: Any) -> str | int | float | bool | None:
    if _is_missing(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, (date, time)):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _direction(debit: Decimal | None, credit: Decimal | None) -> tuple[str, list[str]]:
    if debit is None and credit is None:
        return "unknown", ["direction_missing"]

    debit_positive = debit is not None and debit > 0
    credit_positive = credit is not None and credit > 0
    if debit_positive and not credit_positive:
        return "outgoing", []
    if credit_positive and not debit_positive:
        return "incoming", []
    return "unknown", ["direction_ambiguous"]


def normalize_sinopac_rows(
    excel_path: str | Path,
    sheet_name: str,
    header_row: int,
) -> list[dict[str, Any]]:
    """Return normalized Sinopac transaction rows from a detected worksheet."""

    assert len(SINOPAC_HEADERS) == 15
    if not isinstance(header_row, int) or header_row < 1:
        raise ValueError("header_row 必須是 Excel 一基底正整數")

    path = Path(excel_path)
    frame = pd.read_excel(path, sheet_name=sheet_name, header=None, dtype=object)
    header_index = header_row - 1
    if header_index >= len(frame):
        raise ValueError("header_row 超出工作表範圍")

    source_headers = [
        "" if _is_missing(value) else str(value)
        for value in frame.iloc[header_index].tolist()
    ]
    canonical_headers = [_canonical_header(value) for value in source_headers]
    nonempty_headers = [value for value in canonical_headers if value]
    if (
        len(source_headers) != len(SINOPAC_HEADERS)
        or len(nonempty_headers) != len(set(nonempty_headers))
        or set(nonempty_headers) != set(SINOPAC_HEADERS)
    ):
        raise ValueError("永豐對帳單必須包含唯一且完整的十五個指定表頭")

    column_index = {name: index for index, name in enumerate(canonical_headers)}
    normalized_rows: list[dict[str, Any]] = []
    for row_index in range(header_index + 1, len(frame)):
        values = frame.iloc[row_index].tolist()
        transaction_timestamp = _timestamp(values[column_index["交易日"]])
        if transaction_timestamp is None:
            # Blank rows and the report's totals footer are not bank events.
            continue

        debit = _decimal(values[column_index["支出"]])
        credit = _decimal(values[column_index["存入"]])
        direction, direction_warnings = _direction(debit, credit)
        warnings = list(dict.fromkeys(direction_warnings))

        raw_payload = {
            source_header: _json_scalar(values[index])
            for index, source_header in enumerate(source_headers)
        }
        json.dumps(raw_payload, ensure_ascii=False)

        normalized_rows.append(
            {
                "format_id": "sinopac",
                "source_file": str(path),
                "source_bank_account": _identifier(values[column_index["帳號"]]),
                "sheet_name": sheet_name,
                "source_row": row_index + 1,
                "source_reference": None,
                "transaction_date": transaction_timestamp.strftime("%Y-%m-%d"),
                "transaction_time": transaction_timestamp.strftime("%H:%M:%S"),
                "posting_date": _iso_date(values[column_index["入帳日"]]),
                "value_date": _iso_date(values[column_index["計息日"]]),
                "debit": debit,
                "credit": credit,
                "direction": direction,
                "balance": _decimal(values[column_index["餘額"]]),
                "currency": _identifier(values[column_index["幣別"]]),
                "summary": _identifier(values[column_index["摘要"]]),
                "memo": _verbatim_text(values[column_index["備註"]]),
                "counterparty_name": None,
                "counterparty_account": None,
                "cancellation_code": _identifier(values[column_index["更正註記"]]),
                "bank_references": {
                    "票據號碼": _identifier(values[column_index["票據號碼"]]),
                    "銷帳編號": _identifier(values[column_index["銷帳編號"]]),
                    "交易參考編號": _identifier(values[column_index["交易參考編號"]]),
                    "存摺備註": _verbatim_text(values[column_index["存摺備註"]]),
                },
                "warnings": warnings,
                "raw_payload": raw_payload,
            }
        )

    return normalized_rows
