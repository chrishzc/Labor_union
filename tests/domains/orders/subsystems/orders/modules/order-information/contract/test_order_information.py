"""Contract tests for typed tpl_info_01/tpl_info_02 projections."""

from __future__ import annotations

from datetime import date
import json

import pytest

from subsystems.orders.order_information import (
    OrderInformationOwnerSnapshot,
    OrderInformationQueryService,
    OrderInformationTemplate,
)
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
            "service_hours_per_day": 10,
            "service_days": 20,
            "address": "新竹市",
            "phone": "0900000000",
            "caregiver_rate": 2400,
            "service_salary": 48000,
            "salary_payment_date_1": date(2026, 10, 5),
            "floor_fee": 0,
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
    values = {field.field_id: field.value for field in result.fields}
    assert values["f_104_c4"] == date(2026, 9, 1)
    assert values["f_105_c5"] == date(2026, 9, 20)
    assert values["f_110_ca"] == 48000
    assert values["f_109_c9"] == 2400
    assert values["f_114_ce"] == "2026-09-07、2026-09-14"
    assert repository.calls == [("CASE-1", 7)]


def test_info_02_uses_case_import_typed_projection_without_raw_passthrough():
    result = OrderInformationQueryService(_Repository(_snapshot())).query(
        "tpl_info_02", "CASE-1", 7
    )

    assert result.can_render is True
    assert result.blockers == ()
    assert all("survey_details" not in blocker for blocker in result.blockers)
    field = next(item for item in result.fields if item.field_id == "f_206_e6")
    assert field.owner == "case_import"
    assert field.source == "case_import.order_information.dietary_habits"
    assert field.value == "葷食"


def test_info_02_blocks_only_missing_case_import_field():
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
    assert "order_information_required_field_missing:f_213_ed" in result.blockers
    assert all("f_206_e6" not in blocker for blocker in result.blockers)


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
        assert by_id["f_109_c9"]["label"] == "服務單價（時薪）"
        assert by_id["f_114_ce"]["source"] == "order.custom_rest_dates"
        assert by_id["f_115_cf"]["label"] == "注意事項備註"


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
                    "floor_fee": 0,
                    "custom_rest_dates": '["2026-09-07"]',
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
    assert "_case_import_payload" not in snapshot.facts
    assert snapshot.field_issues == {}
    assert "case_import" in snapshot.owner_fingerprints


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
