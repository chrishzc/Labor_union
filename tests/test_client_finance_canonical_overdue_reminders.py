from datetime import date

from domains.anomalies.registry import default_anomaly_registry
from infrastructure.mysql.process_reminder_anomaly_source import (
    _CLIENT_OBLIGATION_REMINDER_SQL,
)
from subsystems.anomalies.process_reminder_anomaly_source import (
    build_client_payable_requests,
    build_client_receivable_requests,
    build_subsidy_advance_due_requests,
    build_subsidy_return_requests,
)


def test_receivable_reminder_uses_only_open_canonical_obligations() -> None:
    requests = build_client_receivable_requests(
        [
            _obligation("C-1", "deposit", "receivable_from_client", 1200, date(2026, 8, 1)),
            _obligation("C-1", "first", "receivable_from_client", 800, date(2026, 8, 3)),
            _obligation("C-1", "adjustment", "payable_to_client", 400, date(2026, 8, 1)),
            _obligation("C-2", "second", "receivable_from_client", 0, date(2026, 8, 1), "settled"),
        ],
        as_of=date(2026, 8, 8),
    )

    active = {request.desired.source_identity: request for request in requests}

    assert active["C-1"].desired.active is True
    assert active["C-1"].display_snapshot["overdue_obligations"] == [
        {"階段": "訂金", "到期日": "2026-08-01", "未收": "1200"},
        {"階段": "第一期", "到期日": "2026-08-03", "未收": "800"},
    ]
    assert active["C-2"].desired.active is False


def test_subsidy_return_reminder_is_a_bank_statement_review_only() -> None:
    requests = build_subsidy_return_requests(
        [
            _obligation("C-3", "subsidy_return", "payable_to_client", 3000, date(2026, 8, 1)),
            _obligation("C-4", "subsidy_return", "payable_to_client", 3000, date(2026, 8, 9)),
        ],
        as_of=date(2026, 8, 8),
    )

    active = {request.desired.source_identity: request for request in requests}

    assert active["C-3"].desired.active is True
    assert active["C-3"].display_snapshot["action"] == "核對應付資料、銀行對帳單與匯入結果"
    assert active["C-4"].desired.active is False


def test_client_refund_overdue_is_separate_from_subsidy_return() -> None:
    requests = build_client_payable_requests(
        [_obligation("C-5", "refund", "payable_to_client", 2600, date(2026, 8, 1))],
        as_of=date(2026, 8, 8),
    )

    assert requests[0].desired.definition_code == "CLIENTPAYABLE-001"
    assert requests[0].desired.active is True
    assert requests[0].display_snapshot["overdue_obligations"] == [
        {"階段": "一般客戶退款", "到期日": "2026-08-01", "未付": "2600"}
    ]


def test_union_advance_due_is_a_read_only_reminder_until_bank_import() -> None:
    requests = build_subsidy_advance_due_requests(
        [
            {
                "case_no": "C-6",
                "actual_end_date": date(2026, 1, 31),
                "entitled_amount_ntd": 3200,
                "allocated_amount_ntd": 0,
            }
        ],
        as_of=date(2026, 3, 15),
    )

    assert requests[0].desired.definition_code == "SUBSIDYADVANCE-001"
    assert requests[0].desired.active is True
    assert requests[0].display_snapshot["action"] == "核對補助撥款、應付資料、銀行對帳單與匯入結果"


def test_overdue_alert_definitions_show_the_manual_review_details() -> None:
    registry = default_anomaly_registry()

    assert registry.require("RECEIVABLE-001").display_fields == (
        "action", "case_no", "overdue_obligations"
    )
    assert registry.require("RETURN-001").display_fields == (
        "action", "case_no", "overdue_obligations"
    )
    assert registry.require("CLIENTPAYABLE-001").display_fields == (
        "action", "case_no", "overdue_obligations"
    )


def test_reminder_loader_reads_canonical_obligations_not_legacy_payment_columns() -> None:
    assert "FROM client_obligations" in _CLIENT_OBLIGATION_REMINDER_SQL
    assert "client_payments" not in _CLIENT_OBLIGATION_REMINDER_SQL


def _obligation(case_no, obligation_type, direction, amount_due_ntd, due_date, status="open"):
    return {
        "case_no": case_no,
        "obligation_type": obligation_type,
        "direction": direction,
        "amount_due_ntd": amount_due_ntd,
        "due_date": due_date,
        "status": status,
    }
