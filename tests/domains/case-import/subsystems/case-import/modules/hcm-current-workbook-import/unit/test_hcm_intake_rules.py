from datetime import date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from domains.case_import.client_import_validation import SERVICE_TYPE_VALUES
from domains.case_import.client_import_validation import validate_hcm_row
from domains.case_import.hcm_import_review import unresolved_hcm_review_fields
from scripts.imports import import_client_hcm
from subsystems.case_import.hcm_adapter import (
    build_hcm_partial_case_import_intent,
    build_approved_case_architecture_bootstrap_intent,
    calculate_hcm_service_end_date,
)


@pytest.fixture
def valid_hcm_row():
    return {
        "案件狀態": "符合", "查詢序號(案件編號)": "SYNTH-INTAKE",
        "報名時間(建檔)": "2026/10/01", "IP位址": "192.0.2.1", "姓名": "合成測試客戶",
        "性別": "女", "行動電話": "0912345678", "身分資格": "一般市民",
        "服務時間": "8小時 09:00-17:00", "預產期/預計服務開始月份": "2026/11/01",
        "預計服務日期": "2026/11/01", "希望服務天數": 6, "居住型態": "公寓",
        "生產方式": "自然產", "服務方式": "連續服務", "寶寶資訊": "合成資訊",
    }


def _exercise_hcm_row(monkeypatch, row):
    monkeypatch.setattr(import_client_hcm.MySqlClientProfileRepository, "load_email_fill_target",
                        lambda _self, _case_no, **_kwargs: None)
    applied = []
    reviews = []
    reconciled = []

    class Application:
        def resolve_hcm_identity(self, *_args):
            return import_client_hcm.HcmIdentityResolution.NEW

        def preview(self, *_args):
            return object()

        def apply(self, intent):
            applied.append(intent)

    monkeypatch.setattr(import_client_hcm, "_load_holiday_dates", lambda _cursor: set())
    monkeypatch.setattr(import_client_hcm, "_apply_command", lambda intent, *_args: intent)
    monkeypatch.setattr(import_client_hcm, "_reconcile_without_rolling_back_hcm",
                        lambda *_args: reconciled.append(True))
    monkeypatch.setattr(import_client_hcm, "record_hcm_import_review",
                        lambda *_args, **kwargs: reviews.append(kwargs) or "hcm-review:synthetic")
    preview = import_client_hcm.HcmLegacyRowIntake(None).preview_rows(pd.DataFrame([row]), "synthetic.xlsx")
    outcome = import_client_hcm._import_row(
        row, 1, None, Application(), "synthetic.xlsx", connection=object(), source_digest="a" * 64,
    )
    return preview, outcome, applied, reviews, reconciled


@pytest.mark.parametrize(
    ("city_fields", "expected_city"),
    [
        ({}, ""),
        ({"縣市": None}, ""),
        ({"縣市": ""}, ""),
        ({"縣市": "  "}, ""),
        ({"縣市": float("nan")}, ""),
        ({"縣市": "台北市"}, "台北市"),
        ({"縣市": "臺北市"}, "台北市"),
        ({"縣市": "台北"}, "台北市"),
        ({"縣市": "未知縣市"}, "未知縣市"),
    ],
)
def test_city_does_not_warn_or_turn_an_otherwise_complete_import_into_partial(
    monkeypatch, valid_hcm_row, city_fields, expected_city,
):
    row = pd.Series({**valid_hcm_row, **city_fields})
    preview, outcome, applied, reviews, reconciled = _exercise_hcm_row(monkeypatch, row)
    assert preview == {"ready": 1, "ready_with_warning": 0, "review_required": 0, "email_fill": 0}
    assert outcome == "inserted"
    assert reviews == []
    assert len(applied) == 1
    assert applied[0].is_complete
    assert applied[0].bootstrap is not None
    assert {item.name: item.value for item in applied[0].client_attributes}["city"] == expected_city
    assert reconciled == [True]


@pytest.mark.parametrize(
    ("source", "value", "target", "blocking"),
    [
        ("姓名", "", "name", True),
        ("身分資格", "無效身分", "identity_status", True),
        ("報名時間(建檔)", "錯誤日期", "created_at", True),
        ("報名時間(建檔)", "115/2/30", "created_at", True),
        ("預計服務日期", "錯誤日期", "service_start_date", True),
        ("預計服務日期", "2026/2/30", "service_start_date", True),
        ("希望服務天數", 0, "service_days", True),
        ("服務時間", "錯誤時段", "service_time", True),
        ("服務時間", "0小時 09:00-17:00", "service_time", True),
        ("服務時間", "25小時 09:00-17:00", "service_time", True),
        ("服務時間", "8小時 17:00-09:00", "service_time", True),
        ("服務方式", "", "service_type", True),
        ("行動電話", "123", "phone", False),
        ("行動電話", "", "phone", False),
        ("email", "invalid", "email", False),
        ("IP位址", "", "ip_address", False),
        ("性別", "無效", "gender", False),
        ("預產期/預計服務開始月份", "錯誤日期", "due_month", False),
        ("居住型態", "無效", "residence_type", False),
        ("生產方式", "無效", "delivery_type", False),
        ("寶寶資訊", "", "baby_info", False),
        ("案件狀態", "", None, False),
    ],
)
def test_only_critical_field_errors_use_partial_intake(
    monkeypatch, valid_hcm_row, source, value, target, blocking,
):
    row = pd.Series({**valid_hcm_row, source: value})
    preview, outcome, applied, reviews, reconciled = _exercise_hcm_row(monkeypatch, row)
    assert preview == {"ready": 0, "ready_with_warning": 1, "review_required": 0, "email_fill": 0}
    assert outcome == "inserted_with_warning"
    assert len(applied) == 1
    assert applied[0].is_complete is (not blocking)
    assert (applied[0].bootstrap is not None) is (not blocking)
    assert reconciled == ([] if blocking else [True])
    assert len(reviews) == 1
    assert {code.split(":", 1)[1] for code in reviews[0]["issue_codes"]} == {source}
    if target is not None:
        expected = value if target == "service_type" else None
        assert {item.name: item.value for item in applied[0].client_attributes}[target] == expected


def test_multiple_noncritical_warnings_still_build_complete_case(monkeypatch, valid_hcm_row):
    row = pd.Series({**valid_hcm_row, "行動電話": "123", "email": "invalid", "性別": "無效"})
    _, outcome, applied, reviews, reconciled = _exercise_hcm_row(monkeypatch, row)
    assert outcome == "inserted_with_warning"
    assert applied[0].is_complete and applied[0].bootstrap is not None
    assert reconciled == [True]
    assert len(reviews[0]["issue_codes"]) == 3


@pytest.mark.parametrize("phone,expected", [
    ("0912-345-678", "0912345678"),
    ("(02) 2345-6789", "0223456789"),
    ("03-2345678", "032345678"),
    ("037-234567", "037234567"),
    ("049-2345678", "0492345678"),
    ("082-234567", "082234567"),
    ("0836-23456", "083623456"),
    ("+886-2-2345-6789", "0223456789"),
    ("886-3-2345678", "032345678"),
    (912345678.0, "0912345678"),
])
def test_mobile_and_landline_import_without_phone_warning(monkeypatch, valid_hcm_row, phone, expected):
    row = pd.Series({**valid_hcm_row, "行動電話": phone})
    preview, outcome, applied, reviews, _ = _exercise_hcm_row(monkeypatch, row)
    assert preview == {"ready": 1, "ready_with_warning": 0, "review_required": 0, "email_fill": 0}
    assert outcome == "inserted"
    assert applied[0].is_complete
    assert {item.name: item.value for item in applied[0].client_attributes}["phone"] == expected
    assert reviews == []


def test_hcm_email_enters_client_root_and_missing_column_remains_optional():
    row = {"查詢序號(案件編號)": "SYNTH-EMAIL", "email": "  hcm@example.com  "}
    record = import_client_hcm.normalize_hcm_row(row)
    intent = build_hcm_partial_case_import_intent(record)
    assert {item.name: item.value for item in intent.client_attributes}["email"] == "hcm@example.com"
    assert "email" not in validate_hcm_row(row)
    assert "email" not in validate_hcm_row({})
    assert "email" not in import_client_hcm.normalize_hcm_row({})


@pytest.mark.parametrize("anchor", ["管理員註記", "管理者註記事項"])
def test_hcm_workbook_blank_header_after_admin_note_is_email(tmp_path, anchor):
    from openpyxl import Workbook
    headers = sorted(import_client_hcm.HCM_REQUIRED_HEADERS) + [None, anchor, None]
    values = {"查詢序號(案件編號)": "SYNTH-BLANK-EMAIL", "姓名": "合成測試客戶"}
    row = [values.get(header, "test-value") for header in headers[:-3]] + ["other@example.com", "原始註記", "  hcm@example.com  "]
    workbook = Workbook()
    workbook.active.title = "HCM"
    workbook.active.append(headers)
    workbook.active.append(row)
    path = tmp_path / "blank-email-header.xlsx"
    workbook.save(path)
    frame = import_client_hcm._load_hcm_frame(path)
    assert frame.attrs["source_sheet"] == "HCM"
    assert frame.iloc[0][anchor] == "原始註記"
    assert frame.iloc[0]["email"] == "  hcm@example.com  "
    assert import_client_hcm.normalize_hcm_row(frame.iloc[0])["email"] == "hcm@example.com"
    assert any(frame.iloc[0][column] == "other@example.com" for column in frame.columns if str(column).startswith("Unnamed"))


@pytest.mark.parametrize("next_header", ["其他事項", "Unnamed: 1"])
def test_named_column_after_admin_note_is_not_reinterpreted_as_email(next_header):
    frame = pd.DataFrame([["原始註記", "other@example.com"]], columns=["管理員註記", next_header])
    result = import_client_hcm._normalize_hcm_email_column(frame, ["管理員註記", next_header])
    assert "email" not in result.columns


def test_legacy_workbook_without_an_adjacent_email_column_is_unchanged():
    frame = pd.DataFrame([["test@example.com", "原始註記"]], columns=["Unnamed: 0", "管理員註記"])
    result = import_client_hcm._normalize_hcm_email_column(frame, [None, "管理員註記"])
    assert "email" not in result.columns


def test_ambiguous_blank_email_columns_fail_closed():
    frame = pd.DataFrame([["註記", "a@example.com", "註記", "b@example.com"]],
                         columns=["管理員註記", "Unnamed: 1", "管理者註記事項", "Unnamed: 3"])
    with pytest.raises(ValueError, match="hcm_email_column_ambiguous"):
        import_client_hcm._normalize_hcm_email_column(frame, ["管理員註記", None, "管理者註記事項", None])


@pytest.mark.parametrize("email", [None, "", "  ", float("nan")])
def test_empty_hcm_email_is_nullable_without_warning(email):
    assert "email" not in validate_hcm_row({"email": email})
    assert import_client_hcm.normalize_hcm_row({"email": email})["email"] is None


@pytest.mark.parametrize("email", ["invalid", "user@domain", "a b@example.com", "a" * 90 + "@example.com"])
def test_invalid_hcm_email_is_a_redacted_warning_and_can_be_repaired(email):
    errors = validate_hcm_row({"email": email})
    assert email not in errors["email"]
    record = import_client_hcm.normalize_hcm_row({"email": email})
    assert import_client_hcm._partial_hcm_record(record, errors)["email"] is None
    assert "hcm_field_invalid:email" in import_client_hcm._hcm_review_issue_codes(errors)
    assert unresolved_hcm_review_fields(("email",), {"clients.email": email}) == ("email",)
    assert unresolved_hcm_review_fields(("email",), {"clients.email": "corrected@example.com"}) == ()


def test_urgent_case_caps_deposit_due_date_at_planned_start() -> None:
    urgent = build_approved_case_architecture_bootstrap_intent(
        "HCM-URGENT", "一般市民", datetime(2026, 9, 10, 9), date(2026, 9, 11)
    )
    ordinary = build_approved_case_architecture_bootstrap_intent(
        "HCM-NORMAL", "一般市民", datetime(2026, 9, 1, 9), date(2026, 9, 10)
    )

    assert urgent.client_payment_terms.deposit_due_date == date(2026, 9, 11)
    assert ordinary.client_payment_terms.deposit_due_date == date(2026, 9, 4)


def test_hcm_service_type_normalization_preserves_the_rest_weekday() -> None:
    assert import_client_hcm.normalize_hcm_row({"服務方式": "休周六"})["service_type"] == "休周六"
    assert import_client_hcm.normalize_hcm_row({"服務方式": "休周日"})["service_type"] == "休周日"
    assert import_client_hcm.normalize_hcm_row({"服務方式": "週休1日"})["service_type"] == "週休1日"
    assert {"休周六", "休周日"} <= SERVICE_TYPE_VALUES


@pytest.mark.parametrize('source', ['無休', '休五、日', '排班時確認休假', '  客戶另行約定  '])
def test_nonempty_service_type_is_reference_text_without_format_warning(monkeypatch, valid_hcm_row, source):
    expected = source.strip()
    row = pd.Series({**valid_hcm_row, '服務方式': source})
    preview, outcome, applied, reviews, reconciled = _exercise_hcm_row(monkeypatch, row)
    assert preview == {"ready": 1, "ready_with_warning": 0, "review_required": 0, "email_fill": 0}
    assert outcome == "inserted"
    assert applied[0].is_complete and applied[0].bootstrap is not None
    assert {item.name: item.value for item in applied[0].client_attributes}['service_type'] == expected
    assert reviews == []
    assert reconciled == [True]
    assert '服務方式' not in validate_hcm_row({'服務方式': source})
    assert unresolved_hcm_review_fields(('服務方式',), {'clients.service_type': source}) == ()
    assert import_client_hcm._partial_hcm_record({'service_type': source}, {'服務方式': '歷史格式警示'})['service_type'] == source


@pytest.mark.parametrize('source', [None, '', '  ', float('nan')])
def test_only_blank_service_type_requires_supplementation(monkeypatch, valid_hcm_row, source):
    row = pd.Series({**valid_hcm_row, '服務方式': source})
    preview, outcome, applied, reviews, reconciled = _exercise_hcm_row(monkeypatch, row)
    assert preview == {"ready": 0, "ready_with_warning": 1, "review_required": 0, "email_fill": 0}
    assert outcome == "inserted_with_warning"
    assert not applied[0].is_complete and applied[0].bootstrap is None
    assert reconciled == []
    assert reviews[0]['issue_codes'] == ('hcm_field_missing:服務方式',)
    assert '服務方式' in validate_hcm_row({'服務方式': source})


@pytest.mark.parametrize('source', ['周休二日', '週休1日', '週休一日'])
def test_hcm_service_type_text_is_preserved_without_alias_rewriting(source):
    assert import_client_hcm.normalize_hcm_row({'服務方式': source})['service_type'] == source


@pytest.mark.parametrize('source', ['周休二日', '週休1日', '週休一日'])
def test_direct_repair_does_not_change_existing_hcm_service_type_validation(source):
    assert '服務方式' not in validate_hcm_row({'服務方式': source})
    assert unresolved_hcm_review_fields(('服務方式',), {'clients.service_type': source}) == ()


def test_hcm_end_date_uses_the_selected_single_rest_weekday() -> None:
    start = date(2026, 3, 2)  # Monday

    assert calculate_hcm_service_end_date(start, 6, "休周日", set()) == date(2026, 3, 7)
    assert calculate_hcm_service_end_date(start, 6, "休周六", set()) == date(2026, 3, 8)


def test_ambiguous_name_or_ip_is_a_nonblocking_warning(monkeypatch) -> None:
    applied = []
    recorded = []

    class Application:
        def resolve_hcm_identity(self, *_args):
            return import_client_hcm.HcmIdentityResolution.AMBIGUOUS

        def preview(self, *_args):
            return type("Preview", (), {"import_version": 0, "fingerprint": object()})()

        def apply(self, command):
            applied.append(command)

    monkeypatch.setattr(
        import_client_hcm,
        "_normalized_record",
        lambda _row: {
            "case_no": "HCM-NEW",
            "created_at": datetime(2026, 9, 1, 9),
            "name": "同名申請人",
            "ip_address": "192.0.2.1",
        },
    )
    monkeypatch.setattr(import_client_hcm, "validate_hcm_row", lambda _row: {})
    monkeypatch.setattr(
        import_client_hcm,
        "_hcm_import_intent",
        lambda *_args: SimpleNamespace(case_no="HCM-NEW", is_complete=True),
    )
    monkeypatch.setattr(import_client_hcm, "_apply_command", lambda *_args: object())
    monkeypatch.setattr(import_client_hcm, "_reconcile_without_rolling_back_hcm", lambda *_args: None)
    monkeypatch.setattr(
        import_client_hcm,
        "record_hcm_import_review",
        lambda _connection, **kwargs: recorded.append(kwargs) or "hcm-review:ambiguous",
    )

    outcome = import_client_hcm._import_row(
        pd.Series({"查詢序號(案件編號)": "HCM-NEW"}),
        2,
        object(),
        Application(),
        "hcm.xlsx",
        connection=object(),
        source_digest="a" * 64,
    )

    assert outcome == "inserted_with_warning"
    assert len(applied) == 1
    assert recorded[0]["issue_codes"] == ("hcm_identity:hcm_identity_ambiguous",)
