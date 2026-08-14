"""
File: rehearse_case_import_workbook.py
Description: 依各來源欄位契約唯讀檢查 Case Import 活頁簿並輸出去識別化統計。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from domains.case_import.client_beclass_validation import (
    CLIENT_BECLASS_REQUIRED_HEADERS,
    validate_client_beclass_row,
)
from domains.case_import.client_import_validation import HCM_REQUIRED_HEADERS, validate_hcm_row
from domains.case_import.staff_import_validation import (
    STAFF_BECLASS_REQUIRED_HEADERS,
    matches_staff_beclass_headers,
    validate_staff_row,
)

MAX_WORKBOOK_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class LanePolicy:
    validator: Callable[[dict[str, Any]], dict[str, str]]
    identity_field: str
    required_headers: frozenset[str]
    header_matcher: Callable[[set[str]], bool] | None = None


LANE_POLICIES = {
    "hcm": LanePolicy(
        validate_hcm_row,
        "查詢序號(案件編號)",
        HCM_REQUIRED_HEADERS,
    ),
    "client-beclass": LanePolicy(
        validate_client_beclass_row,
        "查詢序號",
        CLIENT_BECLASS_REQUIRED_HEADERS,
    ),
    "staff-beclass": LanePolicy(
        validate_staff_row,
        "身分證字號",
        STAFF_BECLASS_REQUIRED_HEADERS,
        matches_staff_beclass_headers,
    ),
}


class RehearsalBlocked(RuntimeError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as workbook:
        for chunk in iter(lambda: workbook.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_workbook_path(path: Path) -> None:
    if path.suffix.casefold() != ".xlsx":
        raise RehearsalBlocked("unsupported_extension", "目前只接受 .xlsx 活頁簿。")
    if not path.is_file():
        raise RehearsalBlocked("workbook_not_found", "找不到指定的活頁簿。")
    size = path.stat().st_size
    if size == 0:
        raise RehearsalBlocked("empty_workbook", "活頁簿不可為空檔。")
    if size > MAX_WORKBOOK_BYTES:
        raise RehearsalBlocked("workbook_too_large", "活頁簿超過 20 MiB 上限。")


def _read_nonempty_sheets(workbook: pd.ExcelFile) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for sheet_name in workbook.sheet_names:
        frame = workbook.parse(sheet_name=sheet_name, dtype=object)
        if not frame.dropna(how="all").empty:
            frames[sheet_name] = frame
    return frames


def _choose_sheet(
    frames: dict[str, pd.DataFrame],
    policy: LanePolicy,
    requested_sheet: str | None,
) -> tuple[str, pd.DataFrame]:
    if requested_sheet is not None:
        if requested_sheet not in frames:
            raise RehearsalBlocked("sheet_not_found_or_empty", "指定工作表不存在或沒有資料。")
        if not _matches_source_profile(frames[requested_sheet], policy):
            raise RehearsalBlocked("sheet_schema_mismatch", "指定工作表不符合此匯入來源的欄位契約。")
        return requested_sheet, frames[requested_sheet]
    candidates = _automatic_candidates(frames, policy)
    if not candidates:
        raise RehearsalBlocked("source_schema_not_found", "沒有工作表符合此匯入來源的欄位契約。")
    if len(candidates) > 1:
        raise RehearsalBlocked("ambiguous_sheet_selection", "無法唯一判定資料工作表，請使用 --sheet 指定。")
    sheet_name = candidates[0]
    return sheet_name, frames[sheet_name]


def _automatic_candidates(frames: dict[str, pd.DataFrame], policy: LanePolicy) -> list[str]:
    return [name for name, frame in frames.items() if _matches_source_profile(frame, policy)]


def _matches_source_profile(frame: pd.DataFrame, policy: LanePolicy) -> bool:
    actual_headers = {str(column).strip() for column in frame.columns}
    if policy.header_matcher is not None:
        return policy.header_matcher(actual_headers)
    return policy.required_headers <= actual_headers


def _is_blank_row(row: dict[str, Any]) -> bool:
    return all(pd.isna(value) or str(value).strip() == "" for value in row.values())


def _identity_distribution(rows: list[dict[str, Any]], field: str) -> tuple[int, int]:
    identities = [str(row[field]).strip() for row in rows if not pd.isna(row.get(field))]
    counts = Counter(identity for identity in identities if identity)
    repeated = [count for count in counts.values() if count > 1]
    return len(repeated), sum(count - 1 for count in repeated)


def _validation_counts(
    rows: list[dict[str, Any]],
    validator: Callable[[dict[str, Any]], dict[str, str]],
) -> tuple[int, Counter[str]]:
    valid_rows = 0
    issue_counts: Counter[str] = Counter()
    for row in rows:
        errors = validator(row)
        if not errors:
            valid_rows += 1
        issue_counts.update(errors.keys())
    return valid_rows, issue_counts


def _header_fingerprint(frame: pd.DataFrame) -> str:
    canonical_headers = json.dumps(
        sorted(str(column).strip() for column in frame.columns),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return _sha256_text(canonical_headers)


def rehearse_workbook(lane: str, workbook_path: Path, sheet: str | None = None) -> dict[str, Any]:
    _validate_workbook_path(workbook_path)
    policy = LANE_POLICIES[lane]
    with pd.ExcelFile(workbook_path, engine="openpyxl") as workbook:
        frames = _read_nonempty_sheets(workbook)
        sheet_name, frame = _choose_sheet(frames, policy, sheet)
        sheet_index = workbook.sheet_names.index(sheet_name)
    raw_rows = frame.to_dict(orient="records")
    rows = [row for row in raw_rows if not _is_blank_row(row)]
    valid_rows, issue_counts = _validation_counts(rows, policy.validator)
    duplicate_groups, duplicate_rows = _identity_distribution(rows, policy.identity_field)
    return _build_receipt(
        lane, workbook_path, frame, sheet_name, sheet_index, raw_rows, rows,
        valid_rows, issue_counts, duplicate_groups, duplicate_rows,
    )


# Receipt 欄位集中組裝，避免任何原始列、路徑、工作表名稱或驗證訊息外洩。
def _build_receipt(
    lane: str,
    workbook_path: Path,
    frame: pd.DataFrame,
    sheet_name: str,
    sheet_index: int,
    raw_rows: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    valid_rows: int,
    issue_counts: Counter[str],
    duplicate_groups: int,
    duplicate_rows: int,
) -> dict[str, Any]:
    review_rows = len(rows) - valid_rows
    return {
        "status": "review_required" if review_rows else "ready_for_candidate_rehearsal",
        "lane": lane,
        "workbook_sha256": _sha256_file(workbook_path),
        "selected_sheet_index": sheet_index,
        "selected_sheet_fingerprint": _sha256_text(sheet_name),
        "header_count": len(frame.columns),
        "header_fingerprint": _header_fingerprint(frame),
        "required_header_count": len(LANE_POLICIES[lane].required_headers),
        "matched_required_headers": len(LANE_POLICIES[lane].required_headers),
        "source_rows": len(rows),
        "ignored_blank_rows": len(raw_rows) - len(rows),
        "valid_rows": valid_rows,
        "review_required_rows": review_rows,
        "duplicate_identity_groups": duplicate_groups,
        "duplicate_identity_rows": duplicate_rows,
        "issue_counts_by_field": dict(sorted(issue_counts.items())),
        "database_connections": 0,
        "writes_performed": 0,
    }


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="唯讀檢查 Case Import 活頁簿，不連線或寫入資料庫。")
    parser.add_argument("--lane", choices=sorted(LANE_POLICIES), required=True)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--sheet", help="多張工作表都符合欄位契約時明確指定；名稱不會出現在輸出。")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        receipt = rehearse_workbook(args.lane, args.workbook, args.sheet)
    except RehearsalBlocked as exc:
        print(json.dumps({"status": "blocked", "error_code": exc.error_code, "message": str(exc)}, ensure_ascii=False))
        return 2
    except Exception:
        print(json.dumps({"status": "blocked", "error_code": "workbook_unreadable", "message": "活頁簿無法安全解析。"}, ensure_ascii=False))
        return 2
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
