"""
File: test_hcm_resubmission_workbook.py
Description: 驗證 HCM 修正版工作簿僅能為已綁定案件建立單欄 owner source。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pytest

from domains.case_import.hcm_resubmission import HcmResubmissionFacts
from subsystems.case_import.hcm_resubmission_workbook import HcmResubmissionWorkbookService


@dataclass
class _Workflow:
    facts_value: HcmResubmissionFacts
    source: object | None = None

    def facts(self, occurrence_identity):
        assert occurrence_identity == self.facts_value.occurrence_identity
        return self.facts_value

    def preview(self, occurrence_identity, source):
        self.source = source
        return source


class _Loader:
    def __init__(self, frame):
        self._frame = frame

    def load_frame(self, source_path):
        return self._frame


def _facts():
    return HcmResubmissionFacts(
        "warning-1", 1, "HCM-FIELD-001", "身分資格", "CASE-1", 5, 7,
        "prior-source", 2, "a" * 64,
    )


def _row(**changes):
    row = {
        "案件狀態": "洽談中", "查詢序號(案件編號)": "CASE-1", "報名時間(建檔)": "2026/08/01",
        "IP位址": "127.0.0.1", "姓名": "去敏測試", "性別": "女", "行動電話": "0912345678",
        "縣市": "台北市", "身分資格": "一般市民", "服務時間": "8小時 09:00-17:00",
        "預產期/預計服務開始月份": "2026/09/01", "預計服務日期": "2026/09/10",
        "希望服務天數": 26, "居住型態": "公寓", "生產方式": "自然產",
        "服務方式": "連續服務", "寶寶資訊": "單胞胎",
    }
    row.update(changes)
    return row


def test_full_valid_workbook_row_derives_only_warning_target(tmp_path):
    path = tmp_path / "resubmission.xlsx"
    path.write_bytes(b"workbook")
    workflow = _Workflow(_facts())
    service = HcmResubmissionWorkbookService(
        workflow, _Loader(pd.DataFrame([_row()])), lambda: set(), _normalizer,
    )

    source = service.preview(str(path), "warning-1")

    assert source.target_values == {"clients.identity_status": "一般市民"}
    assert source.source_event_identity.startswith("hcm-resubmission:")


def test_resubmission_rejects_wrong_or_multiple_case_rows(tmp_path):
    path = tmp_path / "resubmission.xlsx"
    path.write_bytes(b"workbook")
    workflow = _Workflow(_facts())
    service = HcmResubmissionWorkbookService(
        workflow, _Loader(pd.DataFrame([_row(), _row()])), lambda: set(), _normalizer,
    )

    with pytest.raises(ValueError, match="hcm_resubmission_case_row_not_unique"):
        service.preview(str(path), "warning-1")


def test_resubmission_requires_whole_source_row_to_pass_validator(tmp_path):
    path = tmp_path / "resubmission.xlsx"
    path.write_bytes(b"workbook")
    workflow = _Workflow(_facts())
    service = HcmResubmissionWorkbookService(
        workflow, _Loader(pd.DataFrame([_row(**{"姓名": ""})])), lambda: set(), _normalizer,
    )

    with pytest.raises(ValueError, match="hcm_resubmission_workbook_still_invalid"):
        service.preview(str(path), "warning-1")


def _normalizer(row):
    return {"case_no": row.get("查詢序號(案件編號)"), "identity_status": row.get("身分資格")}
