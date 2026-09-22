"""Contract tests for typed tpl_info_01/tpl_info_02 projections."""

from __future__ import annotations

from datetime import date, timedelta
import json

import pytest

from subsystems.orders.order_information import (
    build_candidate_information,
    OrderInformationOwnerSnapshot,
    OrderInformationQueryService,
    OrderInformationTemplate,
)


def test_candidate_information_works_without_assignment_or_beclass_and_binds_content():
    facts = {"case_no": "INQUIRY-1", "staff_name": "測試月嫂", "assigned_start_date": date(2026, 10, 1),
             "assigned_end_date": date(2026, 10, 5), "service_hours_per_day": 8,
             "requires_cooking": False, "service_time": "09:00–17:00", "total_salary": None,
             "deposit_amount": 12000, "deposit_due_date": date(2026, 9, 20),
             "first_payment_amount": 36000, "first_payment_due_date": date(2026, 10, 1),
             "second_payment_amount": 0, "second_payment_due_date": None,
             "floor_fee": 0, "floor_fee_due_date": None,
             "total_employer_self_pay_payable": 48000}
    first = build_candidate_information("INQUIRY-1", 9, 1, facts, {}, "recipient-a")
    second = build_candidate_information("INQUIRY-1", 9, 2, facts, {}, "recipient-a")
    assert "預計服務開始日期：2026-10-01" in first.text
    assert "總薪資" not in first.text
    assert "預計發薪日" not in first.text
    assert "每日服務時數：8" in first.text
    assert "服務是否需要下廚：不需要下廚" in first.text
    assert "樓層費：NT$ 0" in first.text
    assert "食材準備參考" in second.text
    sections = {section.title: dict(section.rows) for section in first.line_sections}
    first_rows = sections["服務約定"]
    assert [label for label, _ in first.line_sections[0].rows[:8]] == [
        "預計服務開始日",
        "預計服務結束日",
        "每日服務時段",
        "每日服務時數",
        "服務方式",
        "希望服務天數",
        "下廚需求",
        "寶寶資訊",
    ]
    assert first_rows["每日服務時數"] == "8"
    assert first_rows["下廚需求"] == "不需要下廚"
    assert sections["客戶付款約定"]["訂金金額"] == "NT$ 12,000"
    assert sections["客戶付款約定"]["預計訂金繳款日"] == "2026-09-20"
    assert sections["客戶付款約定"]["第一期金額"] == "NT$ 36,000"
    assert sections["客戶付款約定"]["預計第一期繳款日"] == "2026-10-01"
    assert sections["客戶付款約定"]["第二期金額"] == "NT$ 0"
    assert sections["客戶付款約定"]["預計第二期繳款日"] == "不適用"
    assert all(label not in {"客戶名稱", "聯絡電話", "服務地址"} for section in second.line_sections for label, _ in section.rows)
    assert first.preview_fingerprint != second.preview_fingerprint
    assert first.preview_fingerprint != build_candidate_information("INQUIRY-1", 10, 1, facts, {}, "recipient-a").preview_fingerprint
    assert first.preview_fingerprint != build_candidate_information("INQUIRY-1", 9, 1, facts, {}, "recipient-b").preview_fingerprint
    assert first.preview_fingerprint == build_candidate_information("INQUIRY-1", 9, 1, {**facts, "total_salary": 48000}, {}, "recipient-a").preview_fingerprint
from infrastructure.mysql.order_information_repository import (
    MySqlOrderInformationRepository,
)
from domains.case_import.order_information import project_order_information


class _Repository:
    def __init__(self, snapshot=None):
        self.snapshot = snapshot
        self.calls = []

    def load_owner_snapshot(self, case_no, assignment_id=None):
        self.calls.append((case_no, assignment_id))
        if self.snapshot is None or self.snapshot.case_no != case_no:
            return None
        if assignment_id is not None and self.snapshot.assignment_id != assignment_id:
            return None
        return self.snapshot


def _snapshot():
    return OrderInformationOwnerSnapshot(
        case_no="CASE-1",
        assignment_id=7,
        facts={
            "case_no": "CASE-1",
            "staff_name": "月嫂甲",
            "client_name": "客戶甲",
            "assigned_start_date": date(2026, 9, 1),
            "assigned_end_date": date(2026, 9, 20),
            "service_days": 20,
            "service_hours_per_day": 10,
            "requires_cooking": True,
            "service_time": "08:00–18:00",
            "address": "新竹市",
            "phone": "0900000000",
            "total_salary": 48000,
            "salary_payment_date": date(2026, 10, 5),
            "special_holidays": "2026-09-07、2026-09-14",
            "notes": "請注意寶寶作息",
            "dietary_habits": "葷食",
            "vegetarian_preference": "可以",
            "alcohol_ratio": "半酒",
            "cooking_oil_type": "苦茶油",
            "maternal_allergy": "無",
            "special_care_notes": "依需求照顧",
            "meal_preferences": "清淡",
            "cooking_tools": "電鍋",
            "bath_water_prep": "中藥包煮沸",
            "breastfeeding_method": "母乳",
            "holiday_pricing_terms": "依合約",
            "multi_birth_count": "單胞胎",
            "stair_floor_fee_mode": "電梯",
            "parking_space_provided": "有",
            "other_babies_present": "無",
        },
        owner_fingerprints={"orders": "a" * 64, "scheduling": "b" * 64},
    )


def test_info_01_uses_exact_typed_owner_values_and_no_legacy_execution_dates():
    repository = _Repository(_snapshot())
    result = OrderInformationQueryService(repository).preview(
        OrderInformationTemplate.INFO_01, "CASE-1", 7
    )

    assert result.can_render is True
    assert result.blockers == ()
    assert result.warnings == ()
    values = {field.field_id: field.value for field in result.fields}
    assert values["f_104_c4"] == date(2026, 9, 1)
    assert values["f_105_c5"] == date(2026, 9, 20)
    assert "f_110_ca" not in values
    assert "f_111_cb" not in values
    assert values["f_114_ce"] == "2026-09-07、2026-09-14"
    assert repository.calls == [("CASE-1", 7)]


def test_info_02_uses_case_import_typed_projection_without_raw_passthrough():
    result = OrderInformationQueryService(_Repository(_snapshot())).query(
        "tpl_info_02", "CASE-1", 7
    )

    assert result.can_render is True
    assert result.blockers == ()
    assert result.warnings == ()
    assert all("survey_details" not in blocker for blocker in result.blockers)
    field = next(item for item in result.fields if item.field_id == "f_206_e6")
    assert field.owner == "case_import"
    assert field.source == "case_import.order_information.dietary_habits"
    assert field.value == "葷食"


def test_info_02_warns_only_for_missing_case_import_field_without_blocking_render():
    snapshot = _snapshot()
    facts = dict(snapshot.facts)
    facts["cooking_tools"] = None
    missing = OrderInformationOwnerSnapshot(
        snapshot.case_no,
        snapshot.assignment_id,
        facts,
        snapshot.owner_fingerprints,
    )
    result = OrderInformationQueryService(_Repository(missing)).query(
        "tpl_info_02", "CASE-1", 7
    )
    assert result.can_render is True
    assert result.blockers == ()
    assert "order_information_required_field_missing:f_213_ed" in result.warnings
    assert all("f_206_e6" not in warning for warning in result.warnings)


def test_staff_projection_requires_exact_assignment_target():
    repository = _Repository(_snapshot())
    service = OrderInformationQueryService(repository)

    with pytest.raises(ValueError) as error:
        service.query("tpl_info_01", "CASE-1", 8)

    assert str(error.value) == "找不到指定案件或服務人員指派。"


@pytest.mark.parametrize("template_id", ["tpl_info_01", "tpl_info_02"])
def test_templates_declare_typed_owner_and_requiredness_metadata(template_id):
    import json
    from pathlib import Path

    template = json.loads(
        (Path("db/templates") / f"{template_id}.json").read_text(encoding="utf-8")
    )
    assert template["fields"]
    for field in template["fields"]:
        assert field["owner"]
        assert field["requiredness"] in {"required", "conditional", "optional"}
        assert field["status"] in {"resolved", "unresolved"}
    assert all(
        "survey_details" not in str(field).lower() for field in template["fields"]
    )
    if template_id == "tpl_info_01":
        by_id = {field["id"]: field for field in template["fields"]}
        assert "f_110_ca" not in by_id
        assert "f_111_cb" not in by_id
        assert by_id["f_106_c6"]["source"] == "order.service_hours_per_day"
        assert by_id["f_109_c9"]["source"] == "order.requires_cooking"
        assert by_id["f_112_cc"]["db_key"] == "deposit_amount"
        assert by_id["f_113_cd"]["db_key"] == "deposit_due_date"
        assert by_id["f_116_cg"]["db_key"] == "first_payment_amount"
        assert by_id["f_117_ch"]["db_key"] == "first_payment_due_date"
        assert by_id["f_114_ce"]["source"] == "order.custom_rest_dates"
        assert by_id["f_115_cf"]["label"] == "注意事項備註"
    else:
        assert "f_204_e4" not in {field["id"] for field in template["fields"]}


class _Cursor:
    def __init__(self):
        self.rows = []
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, params):
        self.executed.append((statement, params))
        if "FROM orders" in statement:
            self.rows = [
                {
                    "case_no": "CASE-1",
                    "service_days": 20,
                    "service_hours_per_day": 10,
                    "requires_cooking": 1,
                    "service_start_time": timedelta(hours=8),
                    "service_end_time": timedelta(hours=18),
                    "service_end_day_offset": 0,
                    "floor_fee": 0,
                    "custom_rest_dates": '["2026-09-07"]',
                    "client_identity_status": "一般市民",
                    "client_hourly_rate_ntd": 300,
                    "payroll_hourly_rate_ntd": 300,
                    "client_name": "客戶甲",
                    "client_phone": "0900000000",
                    "client_address": "新竹市",
                    "client_notes": None,
                    "_case_import_payload": json.dumps(
                        {"月子餐點調理喜好/飲食習慣：": "葷食"},
                        ensure_ascii=False,
                    ),
                }
            ]
        elif "FROM caregiver_matching_plans plan" in statement:
            self.rows = [
                {
                    "assignment_id": 17,
                    "staff_id": 9,
                    "assigned_start_date": date(2026, 9, 1),
                    "assigned_end_date": date(2026, 9, 20),
                    "staff_name": "月嫂甲",
                }
            ]
        elif "FROM caregiver_candidate_contact_entries" in statement:
            self.rows = [
                {
                    "staff_name": "月嫂甲",
                    "line_user_id": "U" + "a" * 32,
                    "assigned_start_date": date(2026, 9, 1),
                    "assigned_end_date": date(2026, 9, 20),
                }
            ]
        elif "FROM case_staff_assignments" in statement:
            self.rows = [
                {
                    "assignment_id": 7,
                    "case_no": "CASE-1",
                    "staff_id": 9,
                    "assigned_start_date": date(2026, 9, 1),
                    "assigned_end_date": date(2026, 9, 20),
                    "hourly_rate": 2400,
                    "status": "active",
                    "staff_name": "月嫂甲",
                }
            ]
        else:
            self.rows = []

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self):
        self.cursor_instance = _Cursor()

    def cursor(self):
        return self.cursor_instance


def test_mysql_adapter_projects_case_import_source_before_returning_owner_snapshot():
    snapshot = MySqlOrderInformationRepository(_Connection()).load_owner_snapshot(
        "CASE-1", 7
    )

    assert snapshot is not None
    assert snapshot.facts["dietary_habits"] == "葷食"
    assert snapshot.facts["requires_cooking"] is True
    assert snapshot.facts["service_time"] == "08:00–18:00"
    assert "_case_import_payload" not in snapshot.facts
    assert snapshot.field_issues == {}
    assert "case_import" in snapshot.owner_fingerprints


def test_formal_plan_information_one_excludes_staff_payroll_terms():
    rows = MySqlOrderInformationRepository(_Connection()).preview_matching_plan_information(
        "CASE-1", 51, 1
    )

    assert len(rows) == 1
    assert "總薪資" not in rows[0]["text"]
    assert "預計發薪日" not in rows[0]["text"]


def test_candidate_information_one_excludes_staff_payroll_terms():
    preview = MySqlOrderInformationRepository(_Connection()).preview_candidate_information(
        "CASE-1", 91, 1
    )

    assert all(section.title != "月嫂報酬" for section in preview.line_sections)
    assert "總薪資" not in preview.text
    assert "預計發薪日" not in preview.text


def test_case_import_projection_keeps_missing_and_ambiguous_answers_field_local():
    result = project_order_information(
        {
            "月子餐點調理喜好/飲食習慣:": "葷食",
            "月子餐點調理喜好/飲食習慣：": "素食",
            "餐點喜忌備註": "清淡",
        }
    )

    assert result.values["dietary_habits"] is None
    assert result.issues["dietary_habits"] == "ambiguous"
    assert result.values["meal_preferences"] == "清淡"
    assert result.values["cooking_tools"] is None
