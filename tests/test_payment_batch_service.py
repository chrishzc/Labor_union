import datetime
from unittest.mock import patch, MagicMock
from services.payment_batch_service import prepare_monthly_payments


@patch('services.payment_batch_service.get_connection')
def test_prepare_monthly_payments(mock_get_connection):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_get_connection.return_value = mock_conn
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    
    mock_cursor.fetchall.return_value = [
        {
            "id": 1,
            "case_no": "115000001",
            "staff_id": 10,
            "due_date": datetime.date(2026, 7, 15),
            "total_payable": 16000.0,
            "amount_paid": 0.0,
            "payment_status": "pending"
        },
        {
            "id": 2,
            "case_no": "115000002",
            "staff_id": 11,
            "due_date": datetime.date(2026, 7, 15),
            "total_payable": 20000.0,
            "amount_paid": 5000.0,
            "payment_status": "partially_paid"
        }
    ]
    
    results = prepare_monthly_payments("2026-07")
    assert len(results) == 2
    assert results[0]["staff_payment_id"] == 1
    assert results[0]["remaining_amount"] == 16000.0
    assert results[1]["staff_payment_id"] == 2
    assert results[1]["remaining_amount"] == 15000.0
