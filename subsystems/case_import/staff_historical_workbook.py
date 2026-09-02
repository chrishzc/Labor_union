"""
File: staff_historical_workbook.py
Description: 解析 Staff 歷史 workbook 並建立不含原始個資的列級採納輸入。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path
import re

import pandas as pd

from domains.case_import.staff_import_validation import (
    EXCEL_TO_DB_COLUMN,
    matches_staff_beclass_headers,
    staff_bank_branch_value,
    validate_staff_row,
)
from shared_kernel.fingerprints import fingerprint_payload


EDUCATION_HEADERS = ("學歷", "教育程度", "最高學歷")
EMERGENCY_CONTACT_NAME_HEADERS = ("緊急聯絡人", "緊急聯絡人姓名", "緊急聯絡姓名")
EMERGENCY_CONTACT_PHONE_HEADERS = ("緊急聯絡電話", "緊急聯絡人電話", "緊急聯絡人手機")
ADMIN_NOTE_HEADERS = ("行政備註", "行政註記", "管理者註記", "管理者註記事項")
CERTIFICATION_HEADER_PATTERN = re.compile(
    r"(證書|證照|證明|良民|警察刑事紀錄|體檢|健檢|CPR|急救|保母|托育|烹飪|廚師)",
    re.IGNORECASE,
)
EXCLUDED_CERTIFICATION_HEADERS = frozenset({"有嬰幼兒按摩證書嗎?"})


@dataclass(frozen=True, slots=True)
class StaffHistoricalWorkbookRow:
    source_row: int
    record: dict[str, object]
    errors: tuple[str, ...]
    bank_accounts: tuple[tuple[object, ...], ...]
    relations: dict[str, tuple[tuple[object, ...], ...]]


@dataclass(frozen=True, slots=True)
class StaffHistoricalWorkbook:
    source_content_digest: str
    sheet_identity: str
    rows: tuple[StaffHistoricalWorkbookRow, ...]


def load_staff_historical_workbook(path: str | Path, source_revision: str | None = None) -> StaffHistoricalWorkbook:
    workbook_path = Path(path)
    with pd.ExcelFile(workbook_path) as workbook:
        matches = _matching_sheets(workbook)
    if len(matches) != 1:
        raise ValueError("staff_historical_sheet_contract_not_unique")
    sheet_name, frame = matches[0]
    digest = _source_digest(workbook_path, source_revision)
    rows = tuple(_row(source_row, series) for source_row, (_, series) in enumerate(frame.iterrows(), start=2))
    return StaffHistoricalWorkbook(digest, sha256(sheet_name.encode("utf-8")).hexdigest(), rows)


def _matching_sheets(workbook) -> list[tuple[str, pd.DataFrame]]:
    result = []
    for sheet_name in workbook.sheet_names:
        frame = workbook.parse(sheet_name=sheet_name, dtype=object)
        headers = {str(column).strip() for column in frame.columns}
        if not frame.dropna(how="all").empty and matches_staff_beclass_headers(headers):
            result.append((str(sheet_name), frame))
    return result


def _row(source_row: int, series) -> StaffHistoricalWorkbookRow:
    raw = series.to_dict()
    errors = validate_staff_row(raw)
    record = _record(raw, errors)
    return StaffHistoricalWorkbookRow(
        source_row,
        record,
        tuple(sorted(errors)),
        _bank_accounts(raw, errors),
        _relations(raw),
    )


def _record(raw: dict[str, object], errors: dict[str, str]) -> dict[str, object]:
    city, address = _city_and_address(raw.get("縣市"), raw.get("地址"))
    record = {
        "registered_at": _registered_at(raw.get("報名時間")),
        "ip_address": _text(raw.get("IP位址")),
        "name": _text(raw.get("姓名")),
        "identity_card": _identity_card(raw.get("身分證字號")),
        "phone": _phone(raw.get("行動電話")),
        "tel": _text(raw.get("市話")),
        "tel_ext": _text(raw.get("分機")),
        "email": _text(raw.get("EMAIL")),
        "birthday": _birthday(raw),
        "city": city,
        "zip_code": _text(raw.get("郵遞區號")),
        "address": address,
        "education": _first_text(raw, EDUCATION_HEADERS),
        "emergency_contact_name": _first_text(raw, EMERGENCY_CONTACT_NAME_HEADERS),
        "emergency_contact_phone": _phone(_first_value(raw, EMERGENCY_CONTACT_PHONE_HEADERS)),
        "admin_notes": _first_text(raw, ADMIN_NOTE_HEADERS),
        "has_massage_cert": _yes(raw.get("有嬰幼兒按摩證書嗎?")),
        "care_babies": _care_babies(raw),
        "status": "active",
    }
    for excel_column, database_column in EXCEL_TO_DB_COLUMN.items():
        if excel_column in errors:
            record[database_column] = None
    return record


def _source_digest(path: Path, source_revision: str | None) -> str:
    digest = sha256(path.read_bytes()).hexdigest()
    if source_revision is None:
        return digest
    revision = str(source_revision).strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", revision):
        raise ValueError("staff_historical_source_revision_invalid")
    return fingerprint_payload({"workbook_digest": digest, "source_revision": revision}).value


def _text(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _first_value(raw: dict[str, object], headers: tuple[str, ...]) -> object | None:
    for header in headers:
        if _text(raw.get(header)) is not None:
            return raw.get(header)
    return None


def _first_text(raw: dict[str, object], headers: tuple[str, ...]) -> str | None:
    return _text(_first_value(raw, headers))


def _identity_card(value: object) -> str | None:
    text = _text(value)
    return None if text is None else text.upper()


def _phone(value: object) -> str | None:
    text = _text(value)
    if text is None:
        return None
    digits = re.sub(r"\D", "", text)
    if digits.startswith("886"):
        digits = "0" + digits[3:]
    return "0" + digits if len(digits) == 9 and digits.startswith("9") else digits


def _registered_at(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(parsed) else parsed.strftime("%Y-%m-%d %H:%M:%S")


def _birthday(raw: dict[str, object]) -> str | None:
    combined = raw.get("民國出生年月日")
    if combined is not None and not pd.isna(combined):
        parsed = pd.to_datetime(combined, errors="coerce")
        if not pd.isna(parsed):
            return parsed.strftime("%Y-%m-%d")
    try:
        year = int(raw.get("出生年"))
        month = int(raw.get("月"))
        day = int(raw.get("日"))
        return date(year + 1911 if year < 1900 else year, month, day).isoformat()
    except (TypeError, ValueError):
        return None


def _city_and_address(city_value: object, address_value: object) -> tuple[str | None, str | None]:
    city = (_text(city_value) or "").replace("台", "臺")
    address = (_text(address_value) or "").replace("台", "臺")
    return city or None, address or None


def _yes(value: object) -> bool:
    return (_text(value) or "").casefold() in {"有", "y", "1", "true"}


def _care_babies(raw: dict[str, object]) -> int:
    values = " ".join(
        _text(raw.get(field)) or ""
        for field in ("可承接的胎數", "雙胞胎", "三胞胎", "[其它].4")
    )
    return 3 if "三胞胎" in values else 2 if "雙胞胎" in values else 1


def _bank_accounts(raw: dict[str, object], errors: dict[str, str]) -> tuple[tuple[object, ...], ...]:
    account = _text(raw.get("銀行帳號"))
    if account is None or "銀行代3碼+分行代號4碼" in errors:
        return ()
    digits = re.sub(r"\D", "", _text(staff_bank_branch_value(raw)) or "")
    accounts = [(digits[:3] or None, digits[3:] or None, account, True)]
    extra = re.sub(r"\D", "", _text(raw.get("若有其它同銀行帳號，請一併提供。(永豐或台新)")) or "")
    if len(extra) >= 8:
        accounts.append((None, None, extra, False))
    return tuple(accounts)


def _certifications(raw: dict[str, object]) -> tuple[tuple[object, ...], ...]:
    values: list[tuple[object, ...]] = []
    for raw_header, raw_value in raw.items():
        header = str(raw_header).strip()
        if header in EXCLUDED_CERTIFICATION_HEADERS:
            continue
        if _text(raw_value) != "Y":
            continue
        if CERTIFICATION_HEADER_PATTERN.search(header) is None:
            continue
        values.append((header,))
    return tuple(values)


def _relations(raw: dict[str, object]) -> dict[str, tuple[tuple[object, ...], ...]]:
    specs = (
        ("staff_regions", ("北區", "東區", "香山區", "新竹縣", "苗栗縣"), "[其它].1"),
        ("staff_time_slots", ("4小時(上午8:30-12:30)", "4小時(下午13:00-17:00)", "8小時", "24小時"), "[其它].2"),
        ("staff_cooking_skills", ("葷食", "素食"), "[其它]"),
        ("staff_transportation", ("機車", "轎車"), None),
        ("staff_holiday_availability", ("年節農曆過年初一", "年節農曆過年初二", "年節農曆過年初三", "端午節", "中秋節", "國定假日必休"), "[其它].5"),
        ("staff_weekly_rest", ("連續服務", "週休1日", "週休2日"), "[其它].3"),
        ("staff_baby_types", ("單胞胎", "雙胞胎"), "[其它].4"),
    )
    result = {}
    for table_name, options, other_column in specs:
        values = [
            (option,) if table_name == "staff_transportation" else (option, None)
            for option in options
            if _text(raw.get(option)) == "Y"
        ]
        other = _text(raw.get(other_column)) if other_column else None
        if other is not None:
            values.append(("其他", other))
        result[table_name] = tuple(values)
    result["staff_certifications"] = _certifications(raw)
    return result


__all__ = ["StaffHistoricalWorkbook", "StaffHistoricalWorkbookRow", "load_staff_historical_workbook"]
