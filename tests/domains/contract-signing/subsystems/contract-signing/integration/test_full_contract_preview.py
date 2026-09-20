"""Contract tests for the exact-target Full Contract Query/Preview boundary."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from openpyxl import Workbook, load_workbook

from subsystems.contract_signing.contract_renderer import render_contract_template
from subsystems.contract_signing.full_contract_preview import (
    ContractPreviewScope,
    FullContractOwnerProjection,
    FullContractPreviewApplication,
    FullContractPreviewError,
    _mapping_blockers,
    _mapping_validation,
)
from shared_kernel.clock import FixedBusinessClock
from infrastructure.mysql.contract_full_preview_repository import (
    _canonical_service_mode,
    _assignment_service_day_count,
    _assignment_staff_summary,
    _due_date_from_due_month,
    _load_client_email,
    _load_approved_subsidy_claim,
    _load_precontract_plan,
    _extend_precontract_staff_payroll,
    _project_subsidy_coverage,
    _special_holidays_text,
)
from subsystems.contract_signing.staff_contract_application import _rest_weekdays


class _Repository:
    def __init__(self, projection):
        self.projection = projection

    def load_client_projection(self, case_no):
        return self.projection if self.projection and case_no == self.projection.case_no else None

    def load_staff_projection(self, case_no, assignment_id):
        return (
            self.projection
            if self.projection
            and case_no == self.projection.case_no
            and assignment_id == self.projection.assignment_id
            else None
        )

    def load_staff_projection_for_segment(self, case_no, matching_segment_id):
        return (
            self.projection
            if self.projection
            and case_no == self.projection.case_no
            and matching_segment_id == 41
            else None
        )


def _projection(scope=ContractPreviewScope.CLIENT, assignment_id=None):
    return FullContractOwnerProjection(
        case_no="CASE-1",
        scope=scope,
        assignment_id=assignment_id,
        facts={"case_no": "CASE-1", "typed_owner_fact": "value"},
        owner_fingerprints={"orders": "a" * 64},
    )


def _approved_mapping(tmp_path: Path):
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "id": "contract_client_copy",
                "param_mappings": {
                    "A1": {
                        "db_key": "typed_owner_fact",
                        "requiredness": "required",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    template = tmp_path / "contract.xlsx"
    Workbook().save(template)
    return mapping, template


def test_client_preview_uses_exact_target_and_returns_typed_cell_values(monkeypatch, tmp_path):
    mapping, template = _approved_mapping(tmp_path)
    monkeypatch.setattr(
        "subsystems.contract_signing.full_contract_preview.load_approved_template",
        lambda key: SimpleNamespace(
            template_key=key,
            mapping_sha256="b" * 64,
            template_sha256="c" * 64,
            template_filename=template.name,
        ),
    )
    monkeypatch.setattr(
        "subsystems.contract_signing.full_contract_preview.approved_template_mapping_path",
        lambda key: mapping,
    )
    result = FullContractPreviewApplication(
        _Repository(_projection()),
        FixedBusinessClock(datetime(2026, 9, 2, 9, 0, 0, tzinfo=UTC)),
    ).preview_client("CASE-1")

    assert result.scope is ContractPreviewScope.CLIENT
    assert result.assignment_id is None
    assert result.blockers == ()
    assert result.ready_to_print is True
    assert result.field_values == {"A1": "value"}


def test_staff_segment_preview_uses_resolved_assignment_identity(monkeypatch, tmp_path):
    mapping, template = _approved_mapping(tmp_path)
    monkeypatch.setattr(
        "subsystems.contract_signing.full_contract_preview.load_approved_template",
        lambda key: SimpleNamespace(
            template_key=key,
            mapping_sha256="b" * 64,
            template_sha256="c" * 64,
            template_filename=template.name,
        ),
    )
    monkeypatch.setattr(
        "subsystems.contract_signing.full_contract_preview.approved_template_mapping_path",
        lambda key: mapping,
    )
    projection = _projection(ContractPreviewScope.STAFF, assignment_id=171)

    result = FullContractPreviewApplication(_Repository(projection)).preview_staff_segment(
        "CASE-1", 41
    )

    assert result.assignment_id == 171
    assert result.ready_to_print is True


def test_preview_reports_null_required_owner_fact_without_blocking(monkeypatch, tmp_path):
    mapping, template = _approved_mapping(tmp_path)
    mapping.write_text(
        json.dumps(
            {
                "id": "contract_client_copy",
                "param_mappings": {
                    "A1": {"db_key": "typed_owner_fact", "requiredness": "required"}
                },
            }
        ),
        encoding="utf-8",
    )
    import subsystems.contract_signing.full_contract_preview as module

    monkeypatch.setattr(module, "load_approved_template", lambda key: SimpleNamespace(
        template_key=key,
        mapping_sha256="b" * 64,
        template_sha256="c" * 64,
        template_filename=template.name,
    ))
    monkeypatch.setattr(module, "approved_template_mapping_path", lambda key: mapping)
    projection = FullContractOwnerProjection(
        case_no="CASE-1", scope=ContractPreviewScope.CLIENT, assignment_id=None,
        facts={"case_no": "CASE-1", "typed_owner_fact": None},
        owner_fingerprints={"orders": "a" * 64},
    )
    result = FullContractPreviewApplication(_Repository(projection)).preview_client("CASE-1")
    assert result.ready_to_print is True
    assert result.blockers == ()
    assert result.warnings == ("contract_pdf_field_missing:A1",)
    assert result.field_states["A1"] == "missing"


def test_client_preview_fingerprint_canonicalizes_native_owner_dates_and_amounts(
    monkeypatch, tmp_path,
):
    mapping, template = _approved_mapping(tmp_path)
    mapping.write_text(
        json.dumps(
            {
                "id": "contract_client_copy",
                "param_mappings": {
                    "A1": {"db_key": "service_date", "requiredness": "required"},
                    "A2": {"db_key": "amount", "requiredness": "required"},
                    "A3": {"db_key": "total_hours", "requiredness": "required"},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "subsystems.contract_signing.full_contract_preview.load_approved_template",
        lambda key: SimpleNamespace(
            template_key=key,
            mapping_sha256="b" * 64,
            template_sha256="c" * 64,
            template_filename=template.name,
        ),
    )
    monkeypatch.setattr(
        "subsystems.contract_signing.full_contract_preview.approved_template_mapping_path",
        lambda key: mapping,
    )
    projection = FullContractOwnerProjection(
        case_no="CASE-1",
        scope=ContractPreviewScope.CLIENT,
        assignment_id=None,
        facts={
            "service_date": date(2026, 3, 2),
            "amount": Decimal("12000.00"),
            "total_hours": 25.5,
        },
        owner_fingerprints={"orders": "a" * 64},
    )

    result = FullContractPreviewApplication(_Repository(projection)).preview_client("CASE-1")

    assert result.ready_to_print is True
    assert len(result.preview_fingerprint.value) == 64
    assert result.field_values == {
        "A1": date(2026, 3, 2),
        "A2": Decimal("12000.00"),
        "A3": 25.5,
    }


@pytest.mark.parametrize("value", ["休周六", "休周日", "週休2日", "連續服務"])
def test_client_service_type_is_an_exact_canonical_rest_mode(value):
    assert _canonical_service_mode(value) == value


@pytest.mark.parametrize("value", [None, "care", "居家"])
def test_ambiguous_service_type_is_not_reinterpreted(value):
    assert _canonical_service_mode(value) is None


@pytest.mark.parametrize("value", ["週休1日", "週休一日"])
def test_legacy_weekly_one_is_canonicalized_to_rest_sunday(value):
    assert _canonical_service_mode(value) == "休周日"


def test_staff_contract_allocation_preserves_selected_single_rest_weekday():
    assert _rest_weekdays("休周六") == frozenset({5})
    assert _rest_weekdays("休周日") == frozenset({6})


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('["2026-09-07", "2026-09-14"]', "2026-09-07、2026-09-14"),
        (["2026-09-07"], "2026-09-07"),
        (None, None),
        ("not-json", None),
        ('{"date":"2026-09-07"}', None),
    ],
)
def test_orders_custom_rest_dates_are_projected_as_typed_text(value, expected):
    assert _special_holidays_text(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026/09/15", "2026-09-15"),
        ("2026-09-15", "2026-09-15"),
        (date(2026, 9, 15), "2026-09-15"),
        ("2026/02/30", None),
        ("2026/09", None),
        (None, None),
    ],
)
def test_legacy_due_month_only_projects_explicit_full_dates(value, expected):
    result = _due_date_from_due_month(value)
    assert (result.isoformat() if result else None) == expected


def test_contract_case_context_selects_due_month_for_template_projection():
    from infrastructure.mysql.contract_context_repository import _CASE_FACTS_SQL

    assert "c.due_month" in _CASE_FACTS_SQL


def test_conditional_unresolved_mapping_is_skipped_when_owner_says_not_applicable(tmp_path):
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "id": "contract_client_copy",
                "param_mappings": {
                    "C37": {
                        "db_key": "deposit_date",
                        "requiredness": "conditional",
                        "status": "unresolved",
                        "applicability": "floor_fee_positive",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    assert _mapping_blockers("contract_client_copy", mapping, {"floor_fee": 0}) == ()
    assert _mapping_blockers("contract_client_copy", mapping, {"floor_fee": 100}) == (
        "contract_pdf_required_mapping_unresolved",
    )


def test_absent_zero_amount_payment_stages_and_blank_notes_do_not_block_client_contract(tmp_path):
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "id": "contract_client_copy",
                "param_mappings": {
                    "F1": {
                        "db_key": "case_no",
                        "requiredness": "required",
                    },
                    "F41": {
                        "db_key": "notes",
                        "requiredness": "conditional",
                    },
                    "C34": {
                        "db_key": "deposit_due_date",
                        "requiredness": "conditional",
                        "applicability": "deposit_payment_positive",
                    },
                    "C35": {
                        "db_key": "first_payment_due_date",
                        "requiredness": "conditional",
                        "applicability": "first_payment_positive",
                    },
                    "C36": {
                        "db_key": "second_payment_due_date",
                        "requiredness": "conditional",
                        "applicability": "second_payment_positive",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    assert _mapping_blockers(
        "contract_client_copy",
        mapping,
        {
            "case_no": "CASE-1",
            "notes": None,
            "deposit_amount": 0,
            "first_payment_amount": 0,
            "second_payment_amount": 0,
        },
    ) == ()

    for amount_key in ("deposit_amount", "first_payment_amount", "second_payment_amount"):
        facts = {
            "case_no": "CASE-1",
            "notes": None,
            "deposit_amount": 0,
            "first_payment_amount": 0,
            "second_payment_amount": 0,
            amount_key: 1,
        }
        blockers, warnings, states = _mapping_validation(
            "contract_client_copy", mapping, facts
        )
        assert blockers == ()
        missing_cell = {
            "deposit_amount": "C34",
            "first_payment_amount": "C35",
            "second_payment_amount": "C36",
        }[amount_key]
        assert warnings == (f"contract_pdf_field_missing:{missing_cell}",)
        assert states[missing_cell] == "missing"


def test_subsidy_unresolved_mapping_blocks_only_for_typed_eligible_identity(tmp_path):
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "id": "contract_client_copy",
                "param_mappings": {
                    "B28": {
                        "db_key": "subsidy_hours",
                        "requiredness": "conditional",
                        "status": "unresolved",
                        "applicability": "subsidy_eligible",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    assert _mapping_blockers("contract_client_copy", mapping, {"identity_status": "待確認"}) == ()
    assert _mapping_blockers("contract_client_copy", mapping, {"identity_status": "補助市民"}) == (
        "contract_pdf_required_mapping_unresolved",
    )


def test_staff_legacy_funding_split_cells_stay_blank_and_whole_obligation_populates_totals(
    tmp_path,
):
    canonical_path = Path(__file__).resolve().parents[6] / "db/templates/contracts/contract_staff_service.json"
    canonical = json.loads(canonical_path.read_text(encoding="utf-8"))
    mapping = tmp_path / "mapping.json"
    split_cells = {}
    for cell in ("C13", "B15", "C15"):
        descriptor = canonical["param_mappings"][cell]
        assert descriptor["status"] == "not_applicable"
        assert descriptor["db_key"] == ""
        split_cells[cell] = descriptor
    split_cells.update(
        {
            "B13": canonical["param_mappings"]["B13"],
            "F10": {"db_key": "staff_payable_total", "requiredness": "required"},
            "B19": {"db_key": "staff_payable_total", "requiredness": "required"},
        }
    )
    mapping.write_text(
        json.dumps({"id": "contract_staff_service", "param_mappings": split_cells}),
        encoding="utf-8",
    )
    template = tmp_path / "contract.xlsx"
    Workbook().save(template)
    facts = {"staff_payable_total": 42000}

    assert _mapping_blockers("contract_staff_service", mapping, facts) == ()
    rendered = render_contract_template(
        template_path=template,
        mapping_path=mapping,
        facts=facts,
    )
    worksheet = load_workbook(BytesIO(rendered), data_only=False).active
    for cell in ("C13", "B15", "C15"):
        assert worksheet[cell].value is None
    assert worksheet["B13"].value == 42000
    assert worksheet["F10"].value == 42000
    assert worksheet["B19"].value == 42000


def test_real_staff_template_clears_legacy_funding_placeholders():
    root = Path(__file__).resolve().parents[6]
    template = root / "db/templates/contracts/staff_service_contract.xlsx"
    mapping = root / "db/templates/contracts/contract_staff_service.json"
    descriptors = json.loads(mapping.read_text(encoding="utf-8"))["param_mappings"]
    facts = {
        descriptor["db_key"]: "測試值"
        for descriptor in descriptors.values()
        if descriptor.get("db_key") and descriptor.get("requiredness") == "required"
    }
    facts.update(
        {
            "case_no": "CASE-1", "staff_name": "服務人員", "client_name": "客戶",
            "assigned_start_date": "2026-09-01", "assigned_end_date": "2026-09-10",
            "service_days": 10, "assignment_service_days": 10, "service_time": "09:00-17:00",
            "service_type": "週休1日", "service_unit_price": 300,
            "staff_payable_total": 24000, "payroll_payment_date": "2026-09-15",
            "client_city": "新竹市", "client_address": "測試地址", "staff_phone": "0900000000",
            "contract_signed_date": "2026-09-01", "__today__": "2026-09-01",
        }
    )

    rendered = render_contract_template(
        template_path=template,
        mapping_path=mapping,
        facts=facts,
    )
    worksheet = load_workbook(BytesIO(rendered), data_only=False).active
    assert [worksheet[cell].value for cell in ("B13", "C13", "B15", "C15")] == [24000, None, None, None]


def test_real_templates_render_multi_staff_summary_and_personal_service_days():
    root = Path(__file__).resolve().parents[6]
    assignments = (
        {"staff_name": "月嫂甲", "assigned_start_date": date(2026, 9, 1),
         "assigned_end_date": date(2026, 9, 12), "planned_hours": 80},
        {"staff_name": "月嫂乙", "assigned_start_date": date(2026, 9, 13),
         "assigned_end_date": date(2026, 10, 8), "planned_hours": 160},
    )
    summary = _assignment_staff_summary(assignments, 8)

    client_content = render_contract_template(
        template_path=root / "db/templates/contracts/contract_client_copy.xlsx",
        mapping_path=root / "db/templates/contracts/contract_client_copy.json",
        facts={
            "staff_name": summary,
            "service_days": 30,
            "total_hours": 240,
            "service_time": "08:00-16:00",
            "total_employer_self_pay_payable": 120000,
            "email": "corrected@example.test",
        },
    )
    client_sheet = load_workbook(BytesIO(client_content), data_only=False).active
    assert client_sheet["C10"].value == summary
    merged_ranges = {str(item) for item in client_sheet.merged_cells.ranges}
    assert client_sheet["C10"].alignment.wrap_text is True
    assert "C10:E10" in merged_ranges
    assert "F10:G10" in merged_ranges
    assert "E34:G34" in merged_ranges
    assert "B181:D181" in merged_ranges
    assert "E181:G181" in merged_ranges
    assert all(
        getattr(side, "style", None) is None
        for side in (
            client_sheet["E34"].border.left,
            client_sheet["E34"].border.right,
            client_sheet["E34"].border.top,
            client_sheet["E34"].border.bottom,
        )
    )
    assert client_sheet["B181"].alignment.wrap_text is True
    assert client_sheet["F24"].value == 30
    assert client_sheet["F25"].value == 240
    assert client_sheet["E28"].value == "08:00-16:00"
    assert client_sheet["F30"].value == 120000
    assert client_sheet["B38"].value == 120000
    assert client_sheet["E34"].value == "corrected@example.test"

    staff_content = render_contract_template(
        template_path=root / "db/templates/contracts/staff_service_contract.xlsx",
        mapping_path=root / "db/templates/contracts/contract_staff_service.json",
        facts={
            "staff_name": "月嫂甲",
            "service_days": 30,
            "assignment_service_days": 5,
            "service_time": "08:00-16:00",
            "service_unit_price": 500,
            "staff_payable_total": 20000,
        },
    )
    staff_sheet = load_workbook(BytesIO(staff_content), data_only=False).active
    assert staff_sheet["C4"].value == "月嫂甲"
    assert staff_sheet["D6"].value == 30
    assert staff_sheet["G7"].value == 5
    assert staff_sheet["B8"].value == "08:00-16:00"
    assert staff_sheet["B10"].value == 500
    assert [staff_sheet[cell].value for cell in ("F10", "B13", "B19")] == [20000, 20000, 20000]


def test_client_contract_uses_planned_due_dates_and_per_case_virtual_account():
    root = Path(__file__).resolve().parents[6]
    mapping = json.loads((root / "db/templates/contracts/contract_client_copy.json").read_text(encoding="utf-8"))
    assert mapping["param_mappings"]["D36"] == {
        "label": "本案專屬虛擬帳號 (D36)",
        "db_table": "Client Finance per-case virtual account projection",
        "db_key": "client_virtual_account",
        "requiredness": "required",
        "status": "approved",
    }
    assert {
        cell: mapping["param_mappings"][cell]["db_key"]
        for cell in ("C34", "C35", "C36", "C37")
    } == {
        "C34": "deposit_due_date",
        "C35": "first_payment_due_date",
        "C36": "second_payment_due_date",
        "C37": "deposit_due_date",
    }


@pytest.mark.parametrize(
    ("filename", "print_area"),
    [("staff_service_contract.xlsx", "'工作表1'!$A$1:$H$97"), ("contract_client_copy.xlsx", "'客戶契約'!$A$1:$G$185")],
)
def test_contract_templates_print_one_page_wide_without_horizontal_fragment_pages(filename, print_area):
    root = Path(__file__).resolve().parents[6]
    worksheet = load_workbook(root / "db/templates/contracts" / filename).active
    assert str(worksheet.print_area) == print_area
    assert worksheet.page_setup.fitToWidth == 1
    assert worksheet.page_setup.fitToHeight == 0
    assert worksheet.page_setup.scale is None
    assert worksheet.sheet_properties.pageSetUpPr.fitToPage is True


def test_client_finance_coverage_projection_uses_exact_planned_hours():
    facts = {
        "identity_status": "補助市民",
        "total_hours": 80,
        "floor_fee": 0,
    }
    owners = {"client_finance": "a" * 64}
    _project_subsidy_coverage(facts, owners)
    assert facts["subsidy_hours"] == 80
    assert facts["projected_subsidy_amount"] == 28000
    assert owners["client_finance"] != "a" * 64


class _PayrollPolicyCursor:
    def execute(self, statement, _parameters=None):
        assert "FROM case_payroll_rate_policy_snapshots" in statement

    def fetchone(self):
        return {
            "policy_version": "approved-rates-v1",
            "policy_kind": "citizen",
            "hourly_rate_ntd": 300,
        }


class _PayrollPolicyConnection:
    class _Context:
        def __enter__(self):
            return _PayrollPolicyCursor()

        def __exit__(self, *_args):
            return False

    def cursor(self):
        return self._Context()


def test_precontract_staff_preview_projects_whole_payable_and_due_date():
    segment = {"id": 71, "staff_id": 8892}
    service_dates = tuple(date(2026, 9, day) for day in range(1, 6))
    plan = {
        "id": 51,
        "segments": (segment,),
        "allocations": tuple((segment, day) for day in service_dates),
    }
    facts = {
        "service_days": 5,
        "service_hours_per_day": Decimal("8.0"),
        "floor_fee": 0,
        "identity_status": "一般市民",
        "total_hours": 40,
        "total_employer_self_pay_payable": 12000,
    }
    owners = {}

    _extend_precontract_staff_payroll(
        _PayrollPolicyConnection(),
        "CASE-1",
        facts,
        owners,
        plan,
        71,
    )

    assert facts["service_unit_price"] == 300
    assert facts["staff_payable_total"] == 12000
    assert facts["staff_payable_due_date"] == date(2026, 10, 15)
    assert facts["payroll_payment_date"] == date(2026, 10, 15)
    assert "payroll" in owners


def test_client_finance_coverage_does_not_invent_subsidy_for_noneligible_identity():
    facts = {"identity_status": "非市民", "total_hours": 80, "floor_fee": 0}
    owners = {"client_finance": "a" * 64}
    _project_subsidy_coverage(facts, owners)
    assert "subsidy_hours" not in facts


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, *_args):
        return None

    def fetchall(self):
        return self.rows


def test_effective_beclass_email_overrides_original_import_value():
    cursor = _Cursor([{
        "email": "old@example.test",
        "effective_values_json": json.dumps({"email": "new@example.test"}),
    }])

    assert _load_client_email(cursor, "CASE-1") == "new@example.test"


def test_effective_beclass_email_can_remain_missing_without_old_value_fallback():
    cursor = _Cursor([{
        "email": "old@example.test",
        "effective_values_json": json.dumps({"email": None}),
    }])

    assert _load_client_email(cursor, "CASE-1") is None


def test_assignment_service_days_use_planned_service_volume_not_calendar_span():
    assignment = {
        "assigned_start_date": date(2026, 9, 1),
        "assigned_end_date": date(2026, 9, 7),
        "planned_hours": Decimal("40"),
    }

    assert _assignment_service_day_count(assignment, Decimal("8")) == 5


def test_multi_staff_client_summary_keeps_each_segment_and_service_volume():
    assignments = (
        {"staff_name": "月嫂甲", "assigned_start_date": date(2026, 9, 1),
         "assigned_end_date": date(2026, 9, 12), "planned_hours": 80},
        {"staff_name": "月嫂乙", "assigned_start_date": date(2026, 9, 13),
         "assigned_end_date": date(2026, 10, 8), "planned_hours": 160},
    )

    assert _assignment_staff_summary(assignments, 8) == (
        "月嫂甲（2026-09-01～2026-09-12，10天）\n"
        "月嫂乙（2026-09-13～2026-10-08，20天）"
    )


class _PrecontractCursor:
    def __init__(self, segment_end=date(2026, 9, 7)):
        self.rows = ()
        self.segment_end = segment_end

    def execute(self, statement, _parameters=None):
        if "FROM caregiver_matching_plans plan" in statement:
            assert "plan.status IN ('proposed','accepted')" in statement
            assert "matching_response_events" not in statement
            self.rows = ({"id": 51},)
        elif "FROM caregiver_matching_plan_segments segment" in statement:
            self.rows = ({
                "id": 71,
                "staff_id": 8892,
                "assigned_start_date": date(2026, 9, 1),
                "assigned_end_date": self.segment_end,
                "staff_name": "月嫂甲",
                "staff_phone": "0900000000",
            },)
        else:
            raise AssertionError(statement)

    def fetchall(self):
        return self.rows


class _PrecontractConnection:
    def __init__(self, segment_end=date(2026, 9, 7)):
        self.cursor_instance = _PrecontractCursor(segment_end)

    class _Context:
        def __init__(self, cursor):
            self.cursor = cursor

        def __enter__(self):
            return self.cursor

        def __exit__(self, *_args):
            return False

    def cursor(self):
        return self._Context(self.cursor_instance)


def test_precontract_preview_projects_expected_dates_without_formal_confirmation():
    result = _load_precontract_plan(
        _PrecontractConnection(),
        "CASE-1",
        {"start_date": date(2026, 9, 1), "service_days": 5, "service_type": "週休2日"},
    )

    assert result["id"] == 51
    assert tuple(day for _, day in result["allocations"]) == tuple(
        date(2026, 9, day) for day in (1, 2, 3, 4, 7)
    )


def test_precontract_preview_rejects_expected_dates_outside_current_segments():
    with pytest.raises(FullContractPreviewError) as captured:
        _load_precontract_plan(
            _PrecontractConnection(date(2026, 9, 4)),
            "CASE-1",
            {"start_date": date(2026, 9, 1), "service_days": 5, "service_type": "連續服務"},
        )

    assert captured.value.code == "contract_preview_service_dates_stale"


def test_precontract_preview_keeps_current_plan_when_date_inputs_are_missing():
    result = _load_precontract_plan(
        _PrecontractConnection(),
        "CASE-1",
        {"start_date": None, "service_days": 5, "service_type": "連續服務"},
    )

    assert result["id"] == 51
    assert result["allocations"] == ()


def test_government_claim_item_projection_requires_one_exact_approved_item():
    cursor = _Cursor(
        [
            {
                "id": 7,
                "batch_id": 9,
                "assignment_id": 11,
                "staff_id": 13,
                "claimed_hours": 40,
                "unit_price": 300,
                "requested_amount": 12000,
                "approved_amount": 11800,
                "aggregate_version": 2,
            }
        ]
    )
    result = _load_approved_subsidy_claim(cursor, "CASE-1", 11)
    assert result["claimed_hours"] == 40
    assert result["approved_amount"] == 11800
    assert _load_approved_subsidy_claim(_Cursor(cursor.rows * 2), "CASE-1", 11) is None


def test_case_import_named_projection_is_the_only_multi_birth_source():
    from infrastructure.mysql.contract_full_preview_repository import _common_facts

    facts = _common_facts(
        {
            "case_no": "CASE-1",
            "survey_details": '{"特殊計費:胎數":"雙胞胎"}',
        }
    )
    assert facts["multi_birth_count"] == "雙胞胎"
    assert "survey_details" not in facts


def test_common_facts_projects_the_same_per_case_virtual_account_used_by_reconciliation():
    from infrastructure.mysql.contract_full_preview_repository import _common_facts

    facts = _common_facts({"case_no": "115000157", "survey_details": None})

    assert facts["client_virtual_account"] == "99781699115157"


def test_staff_preview_requires_exact_assignment_and_uses_no_client_fallback():
    application = FullContractPreviewApplication(
        _Repository(_projection(ContractPreviewScope.STAFF, 7)),
    )

    with pytest.raises(FullContractPreviewError) as captured:
        application.preview_staff("CASE-1", 8)

    assert captured.value.code == "contract_preview_target_not_found"


def test_preview_exposes_mapping_blocker(tmp_path):
    mapping, template = _approved_mapping(tmp_path)
    mapping.write_text(
        json.dumps(
            {
                "id": "contract_client_copy",
                "param_mappings": {
                    "A1": {"db_key": "typed_owner_fact"}
                },
            }
        ),
        encoding="utf-8",
    )
    import subsystems.contract_signing.full_contract_preview as module

    original_loader = module.load_approved_template
    original_mapping = module.approved_template_mapping_path
    module.load_approved_template = lambda key: SimpleNamespace(
        template_key=key,
        mapping_sha256="b" * 64,
        template_sha256="c" * 64,
        template_filename=template.name,
    )
    module.approved_template_mapping_path = lambda key: mapping
    try:
        result = FullContractPreviewApplication(_Repository(_projection())).preview_client("CASE-1")
    finally:
        module.load_approved_template = original_loader
        module.approved_template_mapping_path = original_mapping
    assert result.ready_to_print is False
    assert result.blockers == ("contract_pdf_required_mapping_unresolved",)
