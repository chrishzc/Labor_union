"""Normalize Taishin transaction-detail worksheets without classifying events."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import unicodedata
from typing import Any

import pandas as pd


TAISHIN_HEADERS = (
    "序號",
    "交易日期",
    "交易時間",
    "帳務日期",
    "摘要",
    "支出金額",
    "存入金額",
    "帳戶餘額",
    "備註",
)

_ACCOUNT_PATTERN = re.compile(r"(?<![0-9])([0-9]{16})(?![0-9])")


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _header(value: Any) -> str:
    if _is_missing(value):
        return ""
    return unicodedata.normalize("NFKC", str(value)).strip()


def _text(value: Any) -> str | None:
    if _is_missing(value):
        return None
    text = str(value).strip()
    return text or None


def _identifier(value: Any) -> str | None:
    if _is_missing(value):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip() or None


def _decimal(value: Any, field: str, warnings: list[str]) -> Decimal | None:
    if _is_missing(value) or (isinstance(value, str) and not value.strip()):
        return None
    text = unicodedata.normalize("NFKC", str(value)).strip().replace(",", "")
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        warnings.append(f"{field}_invalid")
        return None


def _iso_date(value: Any, field: str, warnings: list[str]) -> str | None:
    if _is_missing(value) or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()

    text = unicodedata.normalize("NFKC", str(value)).strip()
    for pattern in ("%Y/%m/%d", "%Y-%m-%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            pass
    for pattern in ("%y/%m/%d", "%y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            pass
    warnings.append(f"{field}_invalid")
    return None


def _iso_time(value: Any, warnings: list[str]) -> str | None:
    if _is_missing(value) or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, datetime):
        return value.time().replace(microsecond=0).isoformat()
    if isinstance(value, time):
        return value.replace(microsecond=0).isoformat()

    text = unicodedata.normalize("NFKC", str(value)).strip()
    for pattern in ("%H:%M:%S", "%H:%M", "%H%M%S", "%H%M"):
        try:
            return datetime.strptime(text, pattern).time().isoformat()
        except ValueError:
            pass
    warnings.append("transaction_time_invalid")
    return None


def _account_from_memo(memo: str | None, warnings: list[str]) -> str | None:
    candidates = list(dict.fromkeys(_ACCOUNT_PATTERN.findall(memo or "")))
    if len(candidates) == 1:
        return candidates[0]
    warnings.append("account_not_found" if not candidates else "account_ambiguous")
    return None


def _direction(debit: Decimal | None, credit: Decimal | None, warnings: list[str]) -> str:
    debit_positive = debit is not None and debit > 0
    credit_positive = credit is not None and credit > 0
    if debit_positive and not credit_positive:
        return "outgoing"
    if credit_positive and not debit_positive:
        return "incoming"
    warnings.append("direction_ambiguous" if debit_positive and credit_positive else "direction_missing")
    return "unknown"


def _json_scalar(value: Any) -> str | int | float | bool | None:
    if _is_missing(value):
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (date, time)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)):
        return value
    item = getattr(value, "item", None)
    if callable(item):
        converted = item()
        if isinstance(converted, (str, int, float, bool)) or converted is None:
            return converted
    return str(value)


def _validated(row: dict[str, Any]) -> dict[str, Any]:
    from scripts.imports.finance_normalized_row import validate_normalized_row

    return validate_normalized_row(row)


def normalize_taishin_rows(
    excel_path: str | Path,
    sheet_name: str,
    header_row: int,
) -> list[dict[str, Any]]:
    """Return normalized Taishin rows using the detector's 1-based header row."""
    assert len(TAISHIN_HEADERS) == 9
    if not isinstance(header_row, int) or isinstance(header_row, bool) or header_row < 1:
        raise ValueError("header_row must be a positive 1-based integer")

    frame = pd.read_excel(excel_path, sheet_name=sheet_name, header=None, dtype=object)
    if header_row > len(frame):
        raise ValueError("header_row is outside the worksheet")

    header_values = frame.iloc[header_row - 1].tolist()
    positions: dict[str, int] = {}
    for index, value in enumerate(header_values):
        name = _header(value)
        if name in TAISHIN_HEADERS:
            if name in positions:
                raise ValueError(f"duplicate Taishin header: {name}")
            positions[name] = index
    missing = [name for name in TAISHIN_HEADERS if name not in positions]
    if missing:
        raise ValueError(f"missing Taishin headers: {', '.join(missing)}")

    normalized_rows = []
    for zero_based_row in range(header_row, len(frame)):
        source_values = {
            name: frame.iat[zero_based_row, positions[name]]
            for name in TAISHIN_HEADERS
        }
        transaction_values = (source_values[name] for name in TAISHIN_HEADERS[1:])
        if all(
            _is_missing(value) or (isinstance(value, str) and not value.strip())
            for value in transaction_values
        ):
            continue

        warnings: list[str] = []
        debit = _decimal(source_values["支出金額"], "debit", warnings)
        credit = _decimal(source_values["存入金額"], "credit", warnings)
        memo = _text(source_values["備註"])
        row = {
            "format_id": "taishin",
            "source_file": str(Path(excel_path)),
            "source_bank_account": None,
            "sheet_name": sheet_name,
            "source_row": zero_based_row + 1,
            "source_reference": None,
            "transaction_date": _iso_date(source_values["交易日期"], "transaction_date", warnings),
            "transaction_time": _iso_time(source_values["交易時間"], warnings),
            "posting_date": _iso_date(source_values["帳務日期"], "posting_date", warnings),
            "value_date": None,
            "debit": debit,
            "credit": credit,
            "direction": _direction(debit, credit, warnings),
            "balance": _decimal(source_values["帳戶餘額"], "balance", warnings),
            "currency": None,
            "summary": _text(source_values["摘要"]),
            "memo": memo,
            "counterparty_name": None,
            "counterparty_account": _account_from_memo(memo, warnings),
            "cancellation_code": None,
            "bank_references": {"sequence": _identifier(source_values["序號"])},
            "warnings": list(dict.fromkeys(warnings)),
            "raw_payload": {
                name: _json_scalar(source_values[name])
                for name in TAISHIN_HEADERS
            },
        }
        normalized_rows.append(_validated(row))

    return normalized_rows
