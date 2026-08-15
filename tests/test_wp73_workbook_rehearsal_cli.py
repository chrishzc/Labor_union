"""
File: test_wp73_workbook_rehearsal_cli.py
Description: 驗證 WP73 活頁簿演練唯讀去識別化，並正確處理替代欄位與選表歧義。
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pandas as pd
import pymysql

from scripts.imports import rehearse_case_import_workbook as rehearsal
from scripts.imports import import_client_beclass, import_staff_beclass


def _write_workbook(path: Path, sheets: dict[str, list[dict]]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, rows in sheets.items():
            pd.DataFrame(rows).to_excel(writer, sheet_name=sheet_name, index=False)


def _client_valid_row() -> dict:
    return {
        "查詢序號": "CASE-001",
        "姓名": "僅供測試姓名",
        "報名時間": "2026/08/13",
        "行動電話": 912345678,
        "Email": "safe@example.invalid",
        "縣市": "台北市",
        "出生年": 1990,
        "月": 1,
        "日": 2,
        "補助款退款:銀行代號+分行代號": "",
        "銀行帳號": "",
    }


def _profile_row(lane: str) -> dict:
    row = {header: "" for header in rehearsal.LANE_POLICIES[lane].required_headers}
    row["項次"] = 1
    return row


def test_rehearsal_reports_safe_counts_without_database_access(tmp_path, monkeypatch, capsys) -> None:
    workbook = tmp_path / "real-shape-client.xlsx"
    invalid = {**_client_valid_row(), "查詢序號": "", "姓名": "不可外洩姓名"}
    _write_workbook(workbook, {"真實來源工作表": [_client_valid_row(), invalid]})

    def fail_if_connected(*args, **kwargs):
        raise AssertionError("rehearsal must not connect to MySQL")

    monkeypatch.setattr(pymysql, "connect", fail_if_connected)
    assert rehearsal.main(["--lane", "client-beclass", "--workbook", str(workbook)]) == 0
    output = capsys.readouterr().out
    receipt = json.loads(output)

    assert receipt["source_rows"] == 2
    assert receipt["valid_rows"] == 1
    assert receipt["review_required_rows"] == 1
    assert receipt["issue_counts_by_field"] == {"查詢序號": 1}
    assert receipt["database_connections"] == 0
    assert receipt["writes_performed"] == 0
    assert "不可外洩姓名" not in output
    assert "真實來源工作表" not in output
    assert str(workbook) not in output


def test_rehearsal_blocks_ambiguous_sheet_selection(tmp_path, capsys) -> None:
    workbook = tmp_path / "ambiguous.xlsx"
    _write_workbook(workbook, {"資料一": [_client_valid_row()], "資料二": [_client_valid_row()]})

    assert rehearsal.main(["--lane", "client-beclass", "--workbook", str(workbook)]) == 2
    receipt = json.loads(capsys.readouterr().out)

    assert receipt["status"] == "blocked"
    assert receipt["error_code"] == "ambiguous_sheet_selection"


def test_source_profiles_ignore_file_and_sheet_names(tmp_path, capsys) -> None:
    cases = (
        ("hcm", "完全任意檔名.xlsx", "工作表1"),
        ("client-beclass", "不是client名稱.xlsx", "Worksheet"),
        ("staff-beclass", "不是staff名稱.xlsx", "Worksheet"),
    )
    for lane, file_name, sheet_name in cases:
        workbook = tmp_path / file_name
        _write_workbook(workbook, {sheet_name: [_profile_row(lane)]})

        assert rehearsal.main(["--lane", lane, "--workbook", str(workbook)]) == 0
        receipt = json.loads(capsys.readouterr().out)

        assert receipt["source_rows"] == 1
        assert receipt["matched_required_headers"] == receipt["required_header_count"]


def test_client_importer_selects_arbitrary_sheet_name_by_headers(tmp_path) -> None:
    workbook = tmp_path / "client.xlsx"
    _write_workbook(workbook, {"工作表1": [_profile_row("client-beclass")]})

    selected = import_client_beclass._load_client_beclass_frame(workbook)

    assert selected is not None
    assert selected[0] == "工作表1"


def test_staff_importer_selects_arbitrary_sheet_name_by_headers(tmp_path) -> None:
    workbook = tmp_path / "staff.xlsx"
    _write_workbook(workbook, {"任意名稱": [_profile_row("staff-beclass")]})

    selected = import_staff_beclass._load_staff_beclass_frame(workbook)

    assert selected is not None
    assert selected[0] == "任意名稱"


def test_staff_profile_accepts_real_history_bank_header_alias(tmp_path, capsys) -> None:
    row = _profile_row("staff-beclass")
    row.pop("民國出生年月日")
    row["銀行代號+分行代號"] = "7001001"
    row["銀行帳號"] = "12345678"
    row.pop("銀行代3碼+分行代號4碼")
    workbook = tmp_path / "staff-history.xlsx"
    _write_workbook(workbook, {"任意名稱": [row]})

    selected = import_staff_beclass._load_staff_beclass_frame(workbook)
    assert selected is not None
    assert import_staff_beclass._historical_bank_accounts(row, {}) == (
        ("700", "1001", "12345678", True),
    )
    capsys.readouterr()

    assert rehearsal.main([
        "--lane", "staff-beclass", "--workbook", str(workbook),
    ]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["source_rows"] == 1


def test_staff_blank_ip_is_nullable_and_does_not_require_review() -> None:
    row = _profile_row("staff-beclass")
    row["IP位址"] = ""

    errors = rehearsal.LANE_POLICIES["staff-beclass"].validator(row)

    assert "IP位址" not in errors


def test_beclass_importers_block_ambiguous_header_matches(tmp_path) -> None:
    client_workbook = tmp_path / "client-ambiguous.xlsx"
    staff_workbook = tmp_path / "staff-ambiguous.xlsx"
    _write_workbook(client_workbook, {
        "資料一": [_profile_row("client-beclass")],
        "資料二": [_profile_row("client-beclass")],
    })
    _write_workbook(staff_workbook, {
        "資料一": [_profile_row("staff-beclass")],
        "資料二": [_profile_row("staff-beclass")],
    })

    assert import_client_beclass._load_client_beclass_frame(client_workbook) is None
    assert import_staff_beclass._load_staff_beclass_frame(staff_workbook) is None


def test_explicit_sheet_must_match_lane_profile(tmp_path, capsys) -> None:
    workbook = tmp_path / "wrong-profile.xlsx"
    _write_workbook(workbook, {"HCM資料": [_profile_row("hcm")]})

    assert rehearsal.main([
        "--lane", "client-beclass", "--workbook", str(workbook), "--sheet", "HCM資料",
    ]) == 2
    receipt = json.loads(capsys.readouterr().out)

    assert receipt["error_code"] == "sheet_schema_mismatch"


def test_explicit_sheet_resolves_ambiguity_without_echoing_name(tmp_path, capsys) -> None:
    workbook = tmp_path / "explicit.xlsx"
    _write_workbook(workbook, {"不要輸出此名稱": [_client_valid_row()], "其他": [_client_valid_row()]})

    assert rehearsal.main([
        "--lane", "client-beclass", "--workbook", str(workbook), "--sheet", "不要輸出此名稱",
    ]) == 0
    output = capsys.readouterr().out

    assert "不要輸出此名稱" not in output
    assert json.loads(output)["selected_sheet_index"] == 0


def test_rehearsal_rejects_non_xlsx_before_parsing(tmp_path, capsys) -> None:
    workbook = tmp_path / "history.xls"
    workbook.write_bytes(b"not-an-excel-file")

    assert rehearsal.main(["--lane", "hcm", "--workbook", str(workbook)]) == 2
    receipt = json.loads(capsys.readouterr().out)

    assert receipt["error_code"] == "unsupported_extension"


def test_rehearsal_module_has_no_database_or_importer_dependency() -> None:
    source = inspect.getsource(rehearsal)

    assert "pymysql" not in source
    assert "infrastructure.mysql" not in source
    assert "scripts.imports.import_" not in source
