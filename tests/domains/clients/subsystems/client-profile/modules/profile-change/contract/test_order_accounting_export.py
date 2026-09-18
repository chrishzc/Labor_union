"""Client registry order-accounting workbook contract."""

from datetime import date
from io import BytesIO

from openpyxl import load_workbook

from api.routes.client_registry import export_client_registry_order_accounting
from infrastructure.mysql.client_registry_query_repository import MySqlClientRegistryQueryRepository
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.client_profile.order_accounting_export import (
    ClientRegistryOrderAccountingExportApplication,
    HEADERS,
    OrderAccountingExportQuery,
    OrderAccountingExportRow,
    XLSX_MEDIA_TYPE,
)


def _row() -> OrderAccountingExportRow:
    return OrderAccountingExportRow(
        seq_num=7,
        case_no="00115000001",
        name="王小明",
        identity_status="一般市民",
        service_time="09:00-17:00 8小時",
        due_month="2026/10",
        hcm_service_start_date="2026/10/01",
        is_twins=True,
        order_status="訂單成立",
        virtual_account="009978160011500001",
        service_days=26,
        service_hours_per_day=8,
        service_hours=208,
        requires_cooking=False,
        floor_fee_ntd=1200,
        service_unit_price_ntd=450,
        customer_payable_total_ntd=93600,
        deposit_amount_ntd=18000,
        first_payment_amount_ntd=75600,
        second_payment_amount_ntd=0,
        received_total_ntd=18000,
        customer_balance_ntd=75600,
        subsidy_return_amount_ntd=36000,
        planned_start_date=date(2026, 10, 1),
        planned_end_date=date(2026, 10, 31),
        actual_start_date=None,
        actual_end_date=None,
        deposit_due_date=date(2026, 9, 20),
        first_payment_due_date=date(2026, 10, 1),
        second_payment_due_date=date(2026, 10, 31),
        deposit_settled_on=date(2026, 9, 18),
        subsidy_return_due_date=date(2026, 12, 15),
        subsidy_return_status="open",
        staff_payment_due_date=date(2026, 11, 10),
        claim_application_year=None,
        claim_application_month=None,
    )


class _Repository:
    selection = None

    def query_order_accounting_rows(self, selection):
        self.selection = selection
        return (_row(),)


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.statement = None
        self.parameters = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, statement, parameters):
        self.statement = " ".join(statement.split())
        self.parameters = parameters

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.cursor_instance = _Cursor(rows)

    def cursor(self):
        return self.cursor_instance


def test_export_keeps_fixed_hcm_columns_and_native_excel_value_types():
    repository = _Repository()
    content = ClientRegistryOrderAccountingExportApplication(repository).export(
        OrderAccountingExportQuery(
            query=" 王 ",
            multi_birth_count="雙胞胎",
            order_status="訂單成立",
            requires_cooking=False,
            sort_by="service_days",
            sort_order="desc",
        )
    )

    assert repository.selection == OrderAccountingExportQuery(
        query="王",
        multi_birth_count="雙胞胎",
        order_status="訂單成立",
        requires_cooking=False,
        sort_by="service_days",
        sort_order="desc",
    )
    worksheet = load_workbook(BytesIO(content))["訂單帳務"]
    assert tuple(cell.value for cell in worksheet[1]) == HEADERS
    assert tuple(cell.value for cell in worksheet[1][:8]) == (
        "項次", "案件編號", "姓名", "身分資格", "服務時間",
        "預產期／預計服務開始月份", "預計服務日期", "雙胞胎",
    )
    assert worksheet["B2"].value == "00115000001"
    assert worksheet["B2"].number_format == "@"
    assert worksheet["H2"].value == "是"
    assert worksheet["N2"].value == "否"
    assert worksheet["Q2"].value == 93600
    assert worksheet["Q2"].data_type == "n"
    assert worksheet["W2"].value == 36000
    assert worksheet["X2"].value.date() == date(2026, 10, 1)
    assert worksheet["AF2"].value.date() == date(2026, 12, 15)
    assert worksheet["AH2"].value.date() == date(2026, 11, 10)
    assert worksheet.auto_filter.ref == "A1:AJ2"
    assert worksheet.freeze_panes == "A2"


def test_export_route_returns_authenticated_xlsx_download():
    response = export_client_registry_order_accounting(
        query=None,
        multi_birth_count=None,
        order_status=None,
        requires_cooking=None,
        sort_by=None,
        sort_order=None,
        principal=AdminPrincipal(9, "registry-reader", "Registry Reader", "system_admin"),
        application=ClientRegistryOrderAccountingExportApplication(_Repository()),
    )

    assert response.media_type == XLSX_MEDIA_TYPE
    assert response.headers["content-disposition"] == 'attachment; filename="client-order-accounting.xlsx"'
    assert bytes(response.body).startswith(b"PK")


def test_mysql_export_uses_one_unbounded_base_join_and_current_finance_projection(monkeypatch):
    connection = _Connection(({
        "seq_num": 7,
        "case_no": "00115000001",
        "name": "王小明",
        "identity_status": "一般市民",
        "service_time": "09:00-17:00 8小時",
        "due_month": "2026/10",
        "service_start_date": "2026/10/01",
        "baby_info": "雙胞胎",
        "order_status": "訂單成立",
        "service_days": 26,
        "service_hours_per_day": 8,
        "requires_cooking": False,
        "floor_fee": 0,
        "planned_start_date": date(2026, 10, 1),
        "planned_end_date": date(2026, 10, 31),
        "actual_start_date": None,
        "actual_end_date": None,
        "staff_payment_due_date": None,
        "deposit_due_date": date(2026, 9, 20),
        "first_payment_due_date": date(2026, 10, 1),
        "second_payment_due_date": date(2026, 10, 31),
        "deposit_settled_on": date(2026, 9, 18),
    },))
    finance = {
        "service_hours": 208,
        "service_unit_price_ntd": 450,
        "customer_payable_total_ntd": 93600,
        "deposit_amount_ntd": 18000,
        "first_payment_amount_ntd": 75600,
        "second_payment_amount_ntd": 0,
        "received_total_ntd": 18000,
        "customer_balance_ntd": 75600,
        "subsidy_return_amount_ntd": None,
        "subsidy_return_due_date": None,
        "subsidy_return_status": None,
    }
    monkeypatch.setattr(
        "infrastructure.mysql.client_registry_query_repository._finance_values",
        lambda _connection, case_no: ("ready", None, finance) if case_no == "00115000001" else None,
    )

    rows = MySqlClientRegistryQueryRepository(
        connection,
        subsidy_projection_loader=lambda case_nos, _connection: {
            "00115000001": {
                "市府訂單號碼": "00115000001",
                "補助款金額": 36000,
                "服務結束": date(2026, 10, 31),
            }
        },
    ).query_order_accounting_rows(
        OrderAccountingExportQuery(
            query="王",
            multi_birth_count="雙胞胎",
            order_status="訂單成立",
            requires_cooking=False,
            sort_by="service_days",
            sort_order="desc",
        )
    )

    statement = connection.cursor_instance.statement
    assert "FROM orders o JOIN clients c ON c.id=o.client_id" in statement
    assert "LEFT JOIN client_payment_terms terms" in statement
    assert "LEFT JOIN client_deposit_settlement_projection deposit_projection" in statement
    assert "client_obligations" not in statement
    assert "staff_obligations" not in statement
    assert "o.staff_payment_due_date" in statement
    assert " LIMIT " not in statement
    assert "ORDER BY o.service_days DESC, o.case_no ASC" in statement
    assert connection.cursor_instance.parameters == ("%王%", "雙胞胎", "訂單成立", False)
    assert len(rows) == 1
    assert rows[0].is_twins is True
    assert rows[0].customer_payable_total_ntd == 93600
    assert rows[0].subsidy_return_amount_ntd == 36000
    assert rows[0].subsidy_return_due_date == date(2026, 12, 15)
    assert rows[0].subsidy_return_status is None
    assert rows[0].staff_payment_due_date == date(2026, 11, 15)
