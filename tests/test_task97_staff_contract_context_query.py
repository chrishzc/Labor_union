"""Focused Task 97 checks for the typed staff contract context query."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from api.routes import contracts
from api.schemas.base import BaseResponse
from api.schemas.contract_context import ContractContextView
from subsystems.contract_integration.contract_context import (
    ContractContextQueryService,
    ContractContextView as ContractContextProjection,
)


ROOT = Path(__file__).resolve().parents[1]


CASE_FACTS = {
    "case_no": "115000001",
    "status": "服務中",
    "contract_identity": "contract-1",
    "service_days": 20,
    "service_hours_per_day": 9,
    "floor_fee": 500,
    "start_date": "2026-06-01",
    "end_date": "2026-06-20",
    "actual_start_date": None,
    "actual_end_date": None,
    "client_id": 4,
    "client_name": "王小明",
    "client_phone": "0912",
    "client_city": "台北市",
    "client_address": "中正區",
    "client_identity_status": "一般市民",
    "service_type": "週休一日",
    "service_time": "09:00",
    "baby_info": "單胞胎",
    "client_notes": "",
    "beclass_query_no": "115000001",
    "survey_details": {"飲食": "素食"},
    "beclass_admin_notes": "",
}


ASSIGNMENT = {
    "assignment_id": 1,
    "case_no": "115000001",
    "staff_id": 11,
    "assignment_sequence": 1,
    "assigned_start_date": "2026-06-01",
    "assigned_end_date": "2026-06-20",
    "planned_hours": 180,
    "actual_hours": None,
    "hourly_rate": 350,
    "floor_fee_allocated": 500,
    "status": "active",
    "replacement_reason": None,
    "staff_name": "月嫂1",
    "staff_identity_card": "A123456789",
    "staff_phone": "0988",
    "staff_email": "staff@example.com",
    "staff_city": "台北市",
    "staff_address": "大安區",
}


class _Repository:
    def load_case_facts(self, case_no):
        assert case_no == CASE_FACTS["case_no"]
        return CASE_FACTS

    def load_assignments(self, case_no):
        assert case_no == ASSIGNMENT["case_no"]
        return (ASSIGNMENT,)


def test_staff_contract_query_returns_typed_owner_projection():
    result = ContractContextQueryService(_Repository()).query("115000001")

    assert isinstance(result, ContractContextProjection)
    assert result.order.case_no == "115000001"
    assert result.client.id == 4
    assert result.assignment.assignment_id == 1
    assert result.client.identity_status == "一般市民"
    assert result.staff.name == "月嫂1"


def test_staff_contract_route_declares_closed_typed_response_and_projects_result():
    projection = ContractContextQueryService(_Repository()).query("115000001")
    response = contracts.get_staff_contract_by_case_no(
        case_no="115000001",
        service=SimpleNamespace(query=lambda case_no, assignment_id: projection),
    )

    assert contracts.router.routes[0].response_model == BaseResponse[ContractContextView]
    assert isinstance(response.data, ContractContextView)
    assert response.data.assignment.assignment_id == 1
    assert response.data.model_dump()["unmapped_template_fields"] is None


def test_staff_contract_route_has_no_sql_or_transaction_ownership():
    source = (ROOT / "api/routes/contracts.py").read_text(encoding="utf-8")

    assert ".cursor(" not in source
    assert ".execute(" not in source
    assert ".commit(" not in source
    assert ".rollback(" not in source
