from infrastructure.mysql.order_detail_query_repository import _ORDER_DETAIL_SQL
from infrastructure.mysql.order_summary_query_repository import _ORDER_SUMMARY_PAGE_SQL


def _assert_historical_staff_fallback(sql: str) -> None:
    assert "historical_order_pairing_evidence historical_pairing" in sql
    assert "historical_order_adoption_receipts historical_receipt" in sql
    assert "latest_historical_receipt.outcome = 'adopted'" in sql
    assert "historical_pairing.staff_id IS NOT NULL" in sql
    assert "'evidence_only', 'assignment_candidate', 'assignment_reused'" in sql
    assert "'歷史訂單－未服務'" in sql
    assert "'歷史訂單－服務中'" in sql
    assert "'歷史訂單－服務完成'" in sql
    assert "'歷史訂單－帳務完成'" in sql


def test_order_summary_prefers_formal_assignment_with_historical_pairing_fallback() -> None:
    assert "assignment.status <> 'cancelled'" in _ORDER_SUMMARY_PAGE_SQL
    assert _ORDER_SUMMARY_PAGE_SQL.index("case_staff_assignments assignment") < _ORDER_SUMMARY_PAGE_SQL.index(
        "historical_order_pairing_evidence historical_pairing"
    )
    _assert_historical_staff_fallback(_ORDER_SUMMARY_PAGE_SQL)


def test_order_detail_uses_legacy_staff_then_historical_pairing_fallback() -> None:
    assert "COALESCE(" in _ORDER_DETAIL_SQL
    assert "s.name" in _ORDER_DETAIL_SQL
    assert _ORDER_DETAIL_SQL.index("s.name") < _ORDER_DETAIL_SQL.index(
        "historical_order_pairing_evidence historical_pairing"
    )
    _assert_historical_staff_fallback(_ORDER_DETAIL_SQL)
