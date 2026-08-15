"""
File: test_hcm_import_safety_gate.py
Description: 驗證 HCM 匯入目標、選表、異常資料與 durable review 的安全門。
"""

from __future__ import annotations

import pandas as pd
import pytest

from scripts.imports import import_client_hcm


def _hcm_profile_row() -> dict[str, object]:
    return {header: "測試值" for header in import_client_hcm.HCM_REQUIRED_HEADERS}


def _write_workbook(path, sheets) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, rows in sheets.items():
            pd.DataFrame(rows).to_excel(writer, sheet_name=sheet_name, index=False)


def test_hcm_sheet_selection_uses_headers_instead_of_sheet_name(tmp_path):
    workbook_path = tmp_path / "arbitrary.xlsx"
    _write_workbook(workbook_path, {"工作表1": [_hcm_profile_row()]})

    frame = import_client_hcm._load_hcm_frame(workbook_path)

    assert frame is not None
    assert frame.attrs["source_sheet"] == "工作表1"


def test_hcm_sheet_selection_blocks_multiple_matching_sheets(tmp_path, capsys):
    workbook_path = tmp_path / "ambiguous.xlsx"
    row = _hcm_profile_row()
    _write_workbook(workbook_path, {"資料一": [row], "資料二": [row]})

    assert import_client_hcm._load_hcm_frame(workbook_path) is None
    assert "多個工作表符合 HCM 必要欄位契約" in capsys.readouterr().out


class _PartialCaseApplication:
    def __init__(self):
        self.applied = []

    def case_exists(self, case_no):
        return False

    def preview(self, intent, correlation):
        return type("Preview", (), {"import_version": 0, "fingerprint": object()})()

    def apply(self, command):
        self.applied.append(command)

    def resolve_hcm_identity(self, case_no, ip_address, client_name):
        return import_client_hcm.HcmIdentityResolution.NEW


def test_invalid_hcm_row_with_case_number_creates_partial_formal_case(monkeypatch):
    recorded = []
    application = _PartialCaseApplication()
    monkeypatch.setattr(
        import_client_hcm,
        "_normalized_record",
        lambda row: {"case_no": "HCM-001", "created_at": object()},
    )
    monkeypatch.setattr(import_client_hcm, "_apply_command", lambda *args: object())
    monkeypatch.setattr(import_client_hcm, "_reconcile_without_rolling_back_hcm", lambda *args: None)
    monkeypatch.setattr(
        import_client_hcm,
        "validate_hcm_row",
        lambda row: {"服務時間": "invalid service time"},
    )
    monkeypatch.setattr(
        import_client_hcm,
        "record_hcm_import_review",
        lambda connection, **kwargs: recorded.append(kwargs) or "hcm-review:test",
    )

    outcome = import_client_hcm._import_row(
        pd.Series({"查詢序號(案件編號)": "HCM-001"}),
        7,
        object(),
        application,
        "hcm.xlsx",
        connection=object(),
        source_digest="a" * 64,
        source_sheet="HCM資料",
    )

    assert outcome == "inserted_with_warning"
    assert len(application.applied) == 1
    assert recorded[0]["case_identity"] == "HCM-001"
    assert recorded[0]["source_row"] == 7
    assert recorded[0]["issue_codes"] == (
        "hcm_field_invalid:報名時間(建檔)",
        "hcm_field_invalid:服務時間",
    )


def test_partial_hcm_intent_keeps_parseable_values_and_nulls_invalid_fields():
    record = {
        "case_no": "HCM-002",
        "name": "王小明",
        "gender": "未知",
        "phone": "0912345678",
    }

    intent = import_client_hcm._hcm_import_intent(
        object(),
        record,
        {"性別": "值不在允許範圍內", "行動電話": "格式錯誤"},
    )
    attributes = {attribute.name: attribute.value for attribute in intent.client_attributes}

    assert intent.is_complete is False
    assert attributes["case_no"] == "HCM-002"
    assert attributes["name"] == "王小明"
    assert attributes["gender"] is None
    assert attributes["phone"] is None


def test_hcm_database_config_has_no_default_credentials(monkeypatch):
    for setting in (
        "DB_HOST",
        "DB_USER",
        "DB_PASSWORD",
        "DB_DATABASE",
        "IMPORT_ALLOWED_DATABASES",
    ):
        monkeypatch.delenv(setting, raising=False)

    with pytest.raises(RuntimeError, match="hcm_import_database_config_missing"):
        import_client_hcm._database_config()


def test_hcm_database_target_requires_explicit_allowlist(monkeypatch):
    monkeypatch.setenv("DB_HOST", "127.0.0.1")
    monkeypatch.setenv("DB_USER", "operator")
    monkeypatch.setenv("DB_PASSWORD", "secret")
    monkeypatch.setenv("DB_DATABASE", "candidate_import")
    monkeypatch.setenv("IMPORT_ALLOWED_DATABASES", "another_candidate")

    with pytest.raises(RuntimeError, match="hcm_import_database_target_not_allowed"):
        import_client_hcm._database_config()


def test_invalid_hcm_row_persists_review_before_returning(monkeypatch):
    recorded = []
    connection = object()
    monkeypatch.setattr(
        import_client_hcm,
        "record_hcm_import_review",
        lambda connection, **kwargs: recorded.append(kwargs) or "hcm-review:test",
    )

    identity = import_client_hcm._persist_hcm_review(
        connection,
        "a" * 64,
        "HCM資料",
        3,
        {"姓名": "測試"},
        "HCM-003",
        {"服務時間": "invalid"},
    )

    assert identity == "hcm-review:test"
    assert recorded[0]["case_identity"] == "HCM-003"
    assert recorded[0]["issue_codes"] == ("hcm_field_invalid:服務時間",)
    assert recorded[0]["evidence_snapshot"] == {
        "has_case_identity": False,
        "invalid_field_count": 1,
        "source_field_count": 1,
    }


def test_hcm_review_codes_only_describe_hcm_source_validation():
    errors = {"服務時間": "invalid"}

    assert import_client_hcm._hcm_review_issue_codes(errors) == (
        "hcm_field_invalid:服務時間",
    )


@pytest.mark.parametrize("identity_status", ("低收入戶", "中低收入戶"))
def test_hcm_subsidized_identity_statuses_are_accepted(identity_status):
    row = {
        "案件狀態": "洽談中",
        "查詢序號(案件編號)": "HCM-SUBSIDY-001",
        "報名時間(建檔)": "2026/08/14",
        "IP位址": "192.0.2.30",
        "姓名": "合成補助客戶",
        "性別": "女",
        "行動電話": "0912345678",
        "縣市": "新竹市",
        "身分資格": identity_status,
        "服務時間": "8 小時 09:00 17:00",
        "預產期/預計服務開始月份": "2026/09/01",
        "預計服務日期": "2026/09/10",
        "希望服務天數": 5,
        "居住型態": "大樓",
        "生產方式": "自然產",
        "服務方式": "週休2日",
        "寶寶資訊": "合成資料",
    }

    assert import_client_hcm.validate_hcm_row(row) == {}
