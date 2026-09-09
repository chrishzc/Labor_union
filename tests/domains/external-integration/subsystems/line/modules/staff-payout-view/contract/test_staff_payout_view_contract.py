"""Contract tests for the verified staff payout LIFF view."""

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from api.routes import line_staff_self_service
from api.schemas.line_staff_self_service import StaffLiffRequest
from domains.line.identities import LineUserId
from subsystems.staff_payables.staff_payout_self_service_query import StaffPayoutItemView


ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if (parent / "requirements.txt").is_file() and (parent / "subsystems").is_dir()
)


def test_staff_payout_query_uses_verified_binding_and_due_month(monkeypatch) -> None:
    recorded = {}
    payment = StaffPayoutItemView(
        assignment_id=17,
        case_no="CASE-7",
        staff_id=3,
        total_payable=Decimal("3000"),
        amount_paid=Decimal("3000"),
        due_date=date(2026, 8, 15),
        paid_at=date(2026, 8, 14),
        payment_status="completed",
    )

    class PaymentQueries:
        def query_by_staff_and_payment_month(self, staff_id, year, month):
            recorded["query"] = (staff_id, year, month)
            return (payment,)

    class UnitOfWork:
        customer_service = SimpleNamespace(
            staff_subject=lambda line_user_id: {
                "staff_id": 3,
                "staff_name": "測試月嫂",
            }
        )
        staff_payout_self_service = PaymentQueries()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(
        line_staff_self_service,
        "_verified_line_user_id",
        lambda _: LineUserId("U-staff"),
    )
    monkeypatch.setattr(
        line_staff_self_service,
        "open_line_unit_of_work",
        lambda: UnitOfWork(),
    )

    response = line_staff_self_service.monthly_payouts(
        StaffLiffRequest(line_id_token="signed-token"), year=2026, month=8
    )

    assert recorded["query"] == (3, 2026, 8)
    assert response.data.staff_id == 3
    assert response.data.items[0].case_no == "CASE-7"


def test_staff_payout_page_is_safe_and_shows_required_payment_fields() -> None:
    source = (ROOT / "line" / "static" / "staff_payout.html").read_text(encoding="utf-8")

    assert "/api/v1/line/staff-self-service/payouts" in source
    assert "目標付款月份" in source
    assert "目標付款日" in source
    assert "實際付款日" in source
    assert "已付金額" in source
    assert "payment_status" in source
    assert "replaceChildren" in source
    assert ".innerHTML" not in source
    assert 'development_line_user_id: ""' in source
    assert 'get("userId")' not in source
