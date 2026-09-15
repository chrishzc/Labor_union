"""Case-centered Client registry read-composition contract."""

import pytest
from types import SimpleNamespace

from api.routes.client_registry import get_client_registry, list_client_registry
from infrastructure.mysql.client_registry_query_repository import MySqlClientRegistryQueryRepository
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.client_profile.registry_query import (
    ClientRegistryContractError,
    ClientRegistryQueryApplication,
)


class _Repository:
    def list_page(self, *, query, multi_birth_count, order_status, requires_cooking, sort_by, sort_order, limit, after):
        assert (query, multi_birth_count, order_status, requires_cooking, sort_by, sort_order, limit, after) == ("王小明", None, None, None, None, None, 25, None)
        return (({"client_id": 7, "case_no": "CASE-001", "name": "王小明", "phone": "0912345678", "city": "新竹市", "multi_birth_count": "雙胞胎", "service_days": 26, "requires_cooking": True, "planned_start_date": None, "order_status": "洽談中"},), "CASE-001")

    def load_detail(self, case_no):
        return {
            "case_no": case_no, "client_id": 7, "client_profile_version": 2,
            "client_values": {
                "name": "王小明", "gender": None, "phone": "0912345678",
                "city": "新竹市", "address": None, "residence_type": None,
                "delivery_type": None, "baby_info": None, "notes": None,
            },
            "beclass_status": "ready", "beclass_record_id": 12,
            "beclass_source_kind": "imported", "beclass_version": 3,
            "beclass_values": {"name": "王小明", "phone": "0922222222", "multi_birth_count": "雙胞胎"},
            "order_information_values": {
                "multi_birth_count": "雙胞胎", "dietary_habits": "不吃牛肉",
            },
            "order_information_issues": {},
        }


def test_registry_list_and_detail_keep_case_identity_and_owner_versions():
    application = ClientRegistryQueryApplication(_Repository())
    page = application.list(query=" 王小明 ", limit=25, after=None)
    assert page.next_cursor == "CASE-001"
    assert page.items[0].multi_birth_count == "雙胞胎"
    assert page.items[0].service_days == 26
    assert page.items[0].requires_cooking is True
    detail = application.query("CASE-001")
    assert detail.client.version == 2
    assert detail.beclass.version == 3
    assert detail.beclass.source_kind == "imported"
    assert detail.beclass.values["phone"] == "0922222222"
    assert detail.order_information.values["multi_birth_count"] == "雙胞胎"


def test_registry_list_route_preserves_optional_false_and_returns_roster_fields():
    class _RouteRepository:
        captured = None

        def list_page(self, **kwargs):
            self.captured = kwargs
            return (({
                "client_id": 7, "case_no": "115000001", "virtual_account": "99781699115001", "name": "王小明", "phone": "0912345678", "city": "新竹市", "district": "東區",
                "multi_birth_count": None, "service_days": 26, "requires_cooking": False,
                "planned_start_date": None, "order_status": "洽談中",
            },), None)

    repository = _RouteRepository()
    response = list_client_registry(
        query=None, multi_birth_count="雙胞胎", order_status="洽談中", requires_cooking=False,
        sort_by="case_no", sort_order="asc", limit=25, after=None,
        principal=AdminPrincipal(9, "registry-reader", "Registry Reader", "system_admin"),
        application=ClientRegistryQueryApplication(repository),
    )

    assert repository.captured == {
        "query": None, "multi_birth_count": "雙胞胎", "order_status": "洽談中", "requires_cooking": False,
        "sort_by": "case_no", "sort_order": "asc", "limit": 25, "after": None,
    }
    assert response.data.items[0].model_dump() == {
        "client_id": 7, "case_no": "115000001", "virtual_account": "99781699115001", "name": "王小明", "phone": "0912345678", "city": "新竹市", "district": "東區",
        "multi_birth_count": None, "service_days": 26, "requires_cooking": False,
        "planned_start_date": None, "order_status": "洽談中",
    }


def test_registry_rejects_cursor_not_matching_last_visible_case():
    class _BadRepository(_Repository):
        def list_page(self, **_):
            return (({"client_id": 7, "case_no": "CASE-001"},), "CASE-999")

    with pytest.raises(ClientRegistryContractError, match="cursor_invalid"):
        ClientRegistryQueryApplication(_BadRepository()).list(query=None, limit=25, after=None)


def test_registry_passes_combined_filters_and_discards_unsafe_custom_sort_cursor():
    class _CaptureRepository:
        captured = None

        def list_page(self, **kwargs):
            self.captured = kwargs
            return (({
                "client_id": 7, "case_no": "CASE-001", "name": "王小明", "phone": "0912345678", "city": "新竹市",
                "multi_birth_count": "雙胞胎", "service_days": 26, "requires_cooking": True,
                "planned_start_date": None, "order_status": "洽談中",
            },), "CASE-001")

    repository = _CaptureRepository()
    page = ClientRegistryQueryApplication(repository).list(
        query=" 王 ", multi_birth_count="雙胞胎", order_status="洽談中", requires_cooking=True,
        sort_by="service_days", sort_order="desc", limit=25, after=None,
    )

    assert repository.captured == {
        "query": "王", "multi_birth_count": "雙胞胎", "order_status": "洽談中", "requires_cooking": True,
        "sort_by": "service_days", "sort_order": "desc", "limit": 25, "after": None,
    }
    assert page.next_cursor is None


def test_registry_rejects_invalid_sort_before_it_reaches_repository_and_custom_sort_cursor():
    class _NoCallRepository:
        def list_page(self, **_):
            raise AssertionError("repository must not receive invalid sort")

    application = ClientRegistryQueryApplication(_NoCallRepository())
    with pytest.raises(ValueError, match="sort_by_invalid"):
        application.list(query=None, sort_by="not_sql", limit=25, after=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="cursor_sort_unsupported"):
        application.list(query=None, sort_by="service_days", sort_order="desc", limit=25, after="CASE-001")


def test_registry_http_composition_identifies_each_field_owner_and_editability():
    terms = SimpleNamespace(
        order=SimpleNamespace(
            case_no="CASE-001", version=4, service_data_locked=False,
            terms=SimpleNamespace(canonical_payload=lambda: {
                "planned_start_date": "2026-10-01", "service_days": 20,
                "service_hours_per_day": 8, "requires_cooking": None,
                "floor_fee_ntd": 0,
                "service_time": {"start_time": None, "end_time": None, "end_day_offset": None},
            }),
        ),
        scheduling=SimpleNamespace(aggregate_version=5, generation_number=2),
        client_finance=SimpleNamespace(account_version=6),
        payroll=SimpleNamespace(payroll_version=7),
    )
    response = get_client_registry(
        case_no="CASE-001",
        principal=AdminPrincipal(9, "registry-reader", "Registry Reader", "system_admin"),
        application=ClientRegistryQueryApplication(_Repository()),
        order_terms=SimpleNamespace(query=lambda _case_no: terms),
    )
    payload = response.data.model_dump()
    assert payload["client"]["field_capabilities"]["phone"] == {
        "owner": "client_profile", "editable": True, "reason": None, "options": None,
    }
    assert payload["client"]["field_capabilities"]["gender"]["options"] == ("女", "男")
    assert payload["beclass"]["field_capabilities"]["phone"]["owner"] == "client_beclass"
    assert payload["beclass"]["field_capabilities"]["multi_birth_count"]["options"] == ("單胞胎", "雙胞胎")
    assert payload["order_information"]["values"]["multi_birth_count"] == "雙胞胎"
    assert payload["order_terms"]["field_capabilities"]["planned_start_date"]["owner"] == "order_terms"


class _SqlCursor:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.statements = []
        self.current = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters):
        self.statements.append((" ".join(statement.split()), parameters))
        self.current = next(self.responses)

    def fetchone(self):
        return self.current

    def fetchall(self):
        return self.current


class _SqlConnection:
    def __init__(self, responses):
        self.cursor_instance = _SqlCursor(responses)

    def cursor(self):
        return self.cursor_instance


def test_mysql_registry_uses_order_client_owner_and_bound_beclass_case_identity():
    connection = _SqlConnection([
        {
            "client_id": 7, "case_no": "CASE-001", "order_status": "歷史訂單－服務完成", "client_profile_version": 2,
            "name": "王小明", "gender": None, "phone": "0912345678", "city": "新竹市",
            "address": None, "residence_type": None, "delivery_type": None,
            "baby_info": None, "notes": None,
        },
        ({"beclass_record_id": 12, "record_origin": "imported", "survey_details": '{"特殊計費:胎數":"雙胞胎","餐點喜忌備註":"不吃牛肉"}', "name": "原始姓名", "email": None, "phone": "0911111111", "tel": None, "ext": None, "city": None, "zip_code": None, "address": None, "admin_notes": None},),
        {"aggregate_version": 3, "effective_values_json": '{"phone":"0922222222","multi_birth_count":"單胞胎"}'},
    ])

    detail = MySqlClientRegistryQueryRepository(connection).load_detail("CASE-001")

    statements = [statement for statement, _ in connection.cursor_instance.statements]
    assert "JOIN clients c ON c.id=o.client_id" in statements[0]
    assert "WHERE o.case_no=%s" in statements[0]
    assert "WHERE bound_case_no=%s" in statements[1]
    assert "query_no" not in " ".join(statements)
    assert detail["beclass_values"]["phone"] == "0922222222"
    assert detail["beclass_values"]["multi_birth_count"] == "單胞胎"
    assert detail["order_information_values"]["multi_birth_count"] == "單胞胎"
    assert detail["order_information_values"]["meal_preferences"] == "不吃牛肉"


def test_mysql_registry_exposes_blank_editable_values_for_historical_case_without_beclass():
    connection = _SqlConnection([
        {
            "client_id": 7, "case_no": "CASE-HISTORY",
            "order_status": "歷史訂單－帳務完成", "client_profile_version": 0,
            "name": "歷史客戶", "gender": None, "phone": "0912345678",
            "city": None, "address": None, "residence_type": None,
            "delivery_type": None, "baby_info": None, "notes": None,
        },
        (),
    ])

    detail = MySqlClientRegistryQueryRepository(connection).load_detail("CASE-HISTORY")

    assert detail["beclass_status"] == "ready"
    assert detail["beclass_record_id"] is None
    assert detail["beclass_source_kind"] == "admin_manual"
    assert detail["beclass_version"] == 0
    assert detail["beclass_values"]["name"] is None
    assert detail["order_information_issues"] == {}


def test_mysql_registry_list_applies_bound_filters_and_allowlisted_sorting_in_one_query():
    connection = _SqlConnection([(
        {"client_id": 7, "case_no": "115000001", "name": "王小明", "phone": "0912345678", "city": "新竹市", "address": "東區中央路1號", "multi_birth_count": "雙胞胎", "service_days": 26, "requires_cooking": True, "planned_start_date": None, "order_status": "洽談中"},
        {"client_id": 8, "case_no": "115000002", "name": "林小華", "phone": "0922345678", "city": "新竹市", "address": None, "multi_birth_count": None, "service_days": 20, "requires_cooking": False, "planned_start_date": None, "order_status": "洽談中"},
    )])

    rows, next_cursor = MySqlClientRegistryQueryRepository(connection).list_page(
        query="王", multi_birth_count="雙胞胎", order_status="洽談中", requires_cooking=True,
        sort_by="service_days", sort_order="desc", limit=25, after=None,
    )

    statement, parameters = connection.cursor_instance.statements[0]
    assert len(connection.cursor_instance.statements) == 1
    assert "AS multi_birth_count" in statement and "o.service_days,o.requires_cooking" in statement
    assert "c.city,c.address" in statement
    assert "$.multi_birth_count" in statement and "特殊計費:胎數" in statement
    assert "o.status = %s" in statement and "o.requires_cooking = %s" in statement
    assert "ORDER BY o.service_days DESC, o.case_no ASC" in statement
    assert parameters == ("%王%", "雙胞胎", "洽談中", True, 26)
    assert rows[0]["case_no"] == "115000001"
    assert rows[0]["virtual_account"] == "99781699115001"
    assert rows[0]["district"] == "東區"
    assert rows[1]["district"] is None
    assert next_cursor is None


def test_mysql_registry_list_keeps_null_distinct_from_explicit_cooking_filter():
    connection = _SqlConnection([()])

    MySqlClientRegistryQueryRepository(connection).list_page(
        query=None, multi_birth_count=None, order_status=None, requires_cooking=False,
        sort_by="case_no", sort_order="asc", limit=25, after=None,
    )

    statement, parameters = connection.cursor_instance.statements[0]
    assert "o.requires_cooking = %s" in statement
    assert parameters == (False, 26)
