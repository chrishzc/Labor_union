"""
File: historical_order_workbook.py
Description: 依版本化欄位契約解析歷史訂單 workbook、Excel date system 與雙月嫂來源。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from hashlib import sha256
from pathlib import Path
import re
from unicodedata import normalize

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel

from domains.orders.historical_adoption import HistoricalOrderSourceStatus
from domains.orders.terms import ServiceTimeTerms
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.workbook_resource_limits import validate_xlsx_workbook


_FIELD_ALIASES = {
    "client_name": {"client_name", "name", "客戶", "客戶姓名", "姓名"},
    "case_no": {"case_no", "案件編號", "查詢序號", "訂單編號"},
    "start_date": {"start_date", "開始日期", "服務開始", "服務開始日", "實際服務開始日"},
    "end_date": {"end_date", "結束日期", "服務結束", "服務結束日", "實際服務結束日"},
    "start_time": {"service_start_time", "每日服務開始時間", "服務開始時間"},
    "end_time": {"service_end_time", "每日服務結束時間", "服務結束時間"},
    "end_day_offset": {"service_end_day_offset", "跨日標記", "服務結束日偏移"},
    "time_range": {"service_time", "服務時間", "每日服務時間", "服務時段", "每日服務時段", "服務時間(每日時數)"},
    "status": {"status", "狀態", "訂單狀態", "訂單成立狀態"},
}
_STAFF_HEADER = re.compile(r"^(staff_name|服務人員|月嫂|月嫂姓名)$")
_TIME_TEXT_TRANSLATION = str.maketrans("‐‑‒–—―−〜", "-------~", "\u200b\u2060\ufeff")
_CLOCK_TEXT = r"[0-9]{1,2}\s*:\s*[0-9]{2}(?:\s*:\s*[0-9]{2})?"
_TIME_RANGE = re.compile(
    rf"(?P<start>{_CLOCK_TEXT})\s*[-~至到]\s*"
    rf"(?P<overnight>次日|翌日|\+1)?\s*(?P<end>{_CLOCK_TEXT})"
    r"\s*(?:\(\s*[0-9]+(?:\.[0-9]+)?\s*小時(?:整)?\s*\))?"
)
_STATUS_MAP = {
    "0": HistoricalOrderSourceStatus.CANCELLED,
    "1": HistoricalOrderSourceStatus.DEPOSIT_PAID,
    "2": HistoricalOrderSourceStatus.DISCUSSION,
}


@dataclass(frozen=True, slots=True)
class HistoricalCaregiverSource:
    ordinal: int
    name: str | None
    start_date: date | None
    end_date: date | None
    has_individual_interval: bool
    issue_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HistoricalOrderWorkbookRow:
    source_row: int
    source_identity: str
    source_fingerprint: str
    case_no: str | None
    client_name: str | None
    asserted_status: HistoricalOrderSourceStatus | None
    actual_start_date: date | None
    actual_end_date: date | None
    caregivers: tuple[HistoricalCaregiverSource, ...]
    issue_codes: tuple[str, ...]
    service_time: ServiceTimeTerms | None = None
    service_time_columns_present: bool | None = None


class _ServiceTimeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class HistoricalOrderWorkbook:
    content_digest: str
    sheet_identity: str
    sheet_name: str
    rows: tuple[HistoricalOrderWorkbookRow, ...]


def load_historical_order_workbook(path: str | Path, sheet: str | None = None) -> HistoricalOrderWorkbook:
    workbook_path = Path(path)
    validate_xlsx_workbook(workbook_path)
    content_digest = sha256(workbook_path.read_bytes()).hexdigest()
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        selected, header, data_start = _select_sheet(workbook, sheet)
        rows = _parse_rows(selected, header, data_start, workbook.epoch, content_digest)
        sheet_name = str(selected.title)
    finally:
        workbook.close()
    return HistoricalOrderWorkbook(
        content_digest,
        sha256(sheet_name.encode("utf-8")).hexdigest(),
        sheet_name,
        rows,
    )


def parse_historical_status(value) -> HistoricalOrderSourceStatus | None:
    if _blank(value):
        return None
    text = str(value).strip()
    if re.fullmatch(r"[012](?:\.0+)?", text):
        text = text[0]
    return _STATUS_MAP.get(text)


def parse_excel_source_date(value, epoch) -> tuple[date | None, bool]:
    if _blank(value):
        return None, False
    if isinstance(value, datetime):
        return value.date(), False
    if isinstance(value, date):
        return value, False
    if isinstance(value, (int, float)):
        try:
            converted = from_excel(value, epoch=epoch)
            return converted.date() if isinstance(converted, datetime) else converted, False
        except (TypeError, ValueError, OverflowError):
            return None, True
    try:
        return datetime.fromisoformat(str(value).strip().replace("/", "-")).date(), False
    except ValueError:
        return None, True


def _select_sheet(workbook, requested):
    if requested is not None:
        if requested not in workbook.sheetnames:
            raise ValueError("historical_order_sheet_not_found")
        candidate = _sheet_contract(workbook[requested])
        if candidate is None:
            raise ValueError("historical_order_sheet_contract_mismatch")
        return workbook[requested], *candidate
    candidates = [(sheet, _sheet_contract(sheet)) for sheet in workbook.worksheets]
    matches = [(sheet, contract) for sheet, contract in candidates if contract is not None]
    if len(matches) != 1:
        raise ValueError("historical_order_sheet_contract_not_unique")
    selected, contract = matches[0]
    return selected, *contract


def _sheet_contract(sheet):
    first_row = next(
        ((index, tuple(row)) for index, row in enumerate(sheet.iter_rows(values_only=True), start=1)
         if any(not _blank(value) for value in row)),
        None,
    )
    if first_row is None:
        return None
    row_number, first = first_row
    headers = tuple(_header(value) for value in first)
    recognized = {_field_for_header(value) for value in headers}
    if {"client_name", "case_no", "status"}.issubset(recognized):
        return headers, row_number + 1
    if len(first) == 6:
        return ("client_name", "case_no", "start_date", "end_date", "status", "staff_name"), row_number
    return None


def _parse_rows(sheet, headers, data_start, epoch, digest):
    positions = _header_positions(headers)
    rows: list[HistoricalOrderWorkbookRow] = []
    for source_row, values in enumerate(sheet.iter_rows(min_row=data_start, values_only=True), start=data_start):
        if all(_blank(value) for value in values):
            continue
        rows.append(_parse_row(values, positions, source_row, epoch, digest))
    return tuple(rows)


def _parse_row(values, positions, source_row, epoch, digest):
    start, bad_start = parse_excel_source_date(_value(values, positions.get("start_date")), epoch)
    end, bad_end = parse_excel_source_date(_value(values, positions.get("end_date")), epoch)
    issues = _row_issues(values, positions, bad_start, bad_end, start, end)
    caregivers = _caregivers(values, positions, epoch, start, end)
    raw_time = tuple(_value(values, positions.get(key)) for key in (
        "start_time", "end_time", "end_day_offset",
    ))
    try:
        service_time = _read_service_time(raw_time, (_value(values, index) for index in positions["time_range"]))
    except _ServiceTimeError as error:
        service_time = None
        issues += (str(error),)
    payload = {
        "case_no": _text(_value(values, positions.get("case_no"))),
        "client_name": _text(_value(values, positions.get("client_name"))),
        "status": _source_status_token(_value(values, positions.get("status"))),
        "start_date": start.isoformat() if start else None,
        "end_date": end.isoformat() if end else None,
        "caregivers": tuple(
            (
                item.name,
                item.start_date.isoformat() if item.start_date else None,
                item.end_date.isoformat() if item.end_date else None,
            )
            for item in caregivers
        ),
    }
    if service_time is not None:
        payload["service_time"] = service_time.canonical_payload()
    return HistoricalOrderWorkbookRow(
        source_row,
        f"historical-orders:{digest}:row:{source_row}",
        fingerprint_payload(payload).value,
        _case_no(_value(values, positions.get("case_no"))),
        _text(_value(values, positions.get("client_name"))),
        parse_historical_status(_value(values, positions.get("status"))),
        start,
        end,
        caregivers,
        tuple(sorted(set(issues + tuple(code for item in caregivers for code in item.issue_codes)))),
        service_time,
        bool(positions["time_range"] or any(field in positions for field in ("start_time", "end_time"))),
    )


def _read_service_time(raw_time, raw_ranges) -> ServiceTimeTerms | None:
    start, end, offset = raw_time
    try:
        day_offset = None if _blank(offset) else int(_normalize_time_text(offset))
    except ValueError as error:
        raise _ServiceTimeError("historical_service_time_offset_invalid") from error
    if day_offset not in (None, 0, 1):
        raise _ServiceTimeError("historical_service_time_offset_invalid")
    split = (
        _split_clock(start, "start"),
        _split_clock(end, "end"),
        day_offset,
    )
    range_texts = (_normalize_time_text(value) for value in raw_ranges if not _blank(value))
    ranges = {_parse_time_range(text) for text in range_texts if text}
    if len(ranges) > 1:
        raise _ServiceTimeError("historical_service_time_columns_conflict")
    service_time = ranges.pop() if ranges else None
    if service_time is not None:
        expected = (service_time.start_time, service_time.end_time, service_time.end_day_offset)
        if any(value is not None and value != expected_value for value, expected_value in zip(split, expected)):
            raise _ServiceTimeError("historical_service_time_columns_conflict")
    elif any(value is not None for value in split):
        if split[0] is None or split[1] is None:
            raise _ServiceTimeError("historical_service_time_split_incomplete")
        service_time = ServiceTimeTerms(split[0], split[1], split[2] if split[2] is not None else 0)
    if service_time is not None and service_time.service_interval(date(2000, 1, 1)) is None:
        if service_time.end_time < service_time.start_time:
            raise _ServiceTimeError("historical_service_time_overnight_missing")
        raise _ServiceTimeError("historical_service_time_interval_empty")
    return service_time


def _parse_time_range(text: str) -> ServiceTimeTerms:
    match = _TIME_RANGE.fullmatch(text)
    if match is None:
        raise _ServiceTimeError("historical_service_time_range_invalid")
    try:
        return ServiceTimeTerms(
            _clock_time(match["start"]), _clock_time(match["end"]), int(bool(match["overnight"])),
        )
    except ValueError as error:
        raise _ServiceTimeError("historical_service_time_range_invalid") from error


def _split_clock(value, field):
    if _blank(value):
        return None
    try:
        return _clock_time(value)
    except ValueError as error:
        raise _ServiceTimeError(f"historical_service_time_{field}_invalid") from error


def _normalize_time_text(value) -> str:
    return normalize("NFKC", str(value)).translate(_TIME_TEXT_TRANSLATION).strip()


def _clock_time(value):
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, time):
        return value
    text = re.sub(r"\s*:\s*", ":", _normalize_time_text(value))
    if re.fullmatch(r"[0-9]:.*", text):
        text = "0" + text
    return time.fromisoformat(text)


def _header_positions(headers):
    positions: dict[str, object] = {"staff": [], "staff_start": {}, "staff_end": {}, "time_range": []}
    for index, header in enumerate(headers):
        field = _field_for_header(header)
        if field == "time_range":
            positions["time_range"].append(index)
            continue
        if field and field not in positions:
            positions[field] = index
            continue
        staff_match = _STAFF_HEADER.fullmatch(header)
        if staff_match:
            positions["staff"].append(index)
            continue
    return positions


def _caregivers(values, positions, epoch, generic_start, generic_end):
    staff_positions = positions["staff"]
    result: list[HistoricalCaregiverSource] = []
    for ordinal, position in enumerate(staff_positions, start=1):
        own_start_position = positions["staff_start"].get(ordinal)
        own_end_position = positions["staff_end"].get(ordinal)
        has_own = own_start_position is not None or own_end_position is not None
        start, bad_start = parse_excel_source_date(_value(values, own_start_position), epoch) if has_own else (generic_start, False)
        end, bad_end = parse_excel_source_date(_value(values, own_end_position), epoch) if has_own else (generic_end, False)
        eligible_generic = len(staff_positions) == 1
        issues = _interval_issues(bad_start, bad_end, start, end, f"caregiver_{ordinal}")
        result.append(HistoricalCaregiverSource(ordinal, _text(_value(values, position)), start, end, has_own or eligible_generic, issues))
    return tuple(result)


def _row_issues(values, positions, bad_start, bad_end, start, end):
    issues = list(_interval_issues(bad_start, bad_end, start, end, "order"))
    if _blank(_value(values, positions.get("case_no"))):
        issues.append("historical_case_no_missing")
    if _blank(_value(values, positions.get("client_name"))):
        issues.append("historical_client_name_missing")
    status_value = _value(values, positions.get("status"))
    if not _blank(status_value) and parse_historical_status(status_value) is None:
        issues.append("historical_status_invalid")
    return tuple(issues)


def _interval_issues(bad_start, bad_end, start, end, prefix):
    issues = []
    if bad_start:
        issues.append(f"historical_{prefix}_start_date_invalid")
    if bad_end:
        issues.append(f"historical_{prefix}_end_date_invalid")
    if start is not None and end is not None and start > end:
        issues.append(f"historical_{prefix}_date_range_invalid")
    return tuple(issues)


def _field_for_header(header):
    for field, aliases in _FIELD_ALIASES.items():
        candidate = _normalize_time_text(header) if field == "time_range" else header
        if candidate in {_header(alias) for alias in aliases}:
            return field
    return None


def _header(value):
    return re.sub(r"\s+", "", str(value or "").strip().casefold())


def _value(values, position):
    return None if position is None or position >= len(values) else values[position]


def _text(value):
    return None if _blank(value) else str(value).strip()


def _case_no(value):
    text = _text(value)
    return text[:-2] if text and text.endswith(".0") and text[:-2].isdigit() else text


def _source_status_token(value) -> str:
    """Keep numeric zero distinct from an absent source status."""

    return "" if _blank(value) else str(value).strip()


def _blank(value):
    return value is None or (isinstance(value, str) and not value.strip())


__all__ = [
    "HistoricalCaregiverSource",
    "HistoricalOrderWorkbook",
    "HistoricalOrderWorkbookRow",
    "load_historical_order_workbook",
    "parse_excel_source_date",
    "parse_historical_status",
]
