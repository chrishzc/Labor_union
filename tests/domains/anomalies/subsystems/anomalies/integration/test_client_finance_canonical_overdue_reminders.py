"""
File: test_client_finance_canonical_overdue_reminders.py
Description: 驗證 Client Finance 逾期提醒依 canonical obligation remaining 判定。
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from api.routes.anomaly_registry import _safe_display_snapshot
from domains.anomalies.registry import default_anomaly_registry
from infrastructure.mysql.process_reminder_anomaly_source import (
    _CLIENT_FINANCE_ACCOUNT_LOCK_SQL,
    _CLIENT_OBLIGATION_CANDIDATE_CASES_SQL,
    _CLIENT_OBLIGATION_REMINDER_SQL,
    _prepare_locked_client_obligation_rows,
)
from subsystems.anomalies.process_reminder_anomaly_source import (
    build_client_payable_requests,
    build_client_receivable_requests,
    build_subsidy_advance_due_requests,
    build_subsidy_return_requests,
)
from subsystems.anomalies.alert_workflow import _detail_actions
from subsystems.anomalies.source_version import daily_root_source_version


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
        "義務 obligation:C-1:deposit｜訂金｜到期 2026-08-01｜未收 NT$ 1,200",
        "義務 obligation:C-1:first｜第一期｜到期 2026-08-03｜未收 NT$ 800",
    ]
    assert active["C-1"].display_snapshot["account_version"] == 0
    assert active["C-1"].desired.source_version == daily_root_source_version(
        as_of=date(2026, 8, 8), root_version=0
    )
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
    assert active["C-3"].display_snapshot["action"] == (
        "以客戶補助退還 Query／Preview／Apply 核銷；不得當一般退款"
    )
    assert active["C-4"].desired.active is False


def test_client_reminder_preserves_mysql_decimal_account_version() -> None:
    request = build_subsidy_return_requests(
        [
            {
                **_obligation(
                    "C-DECIMAL",
                    "subsidy_return",
                    "payable_to_client",
                    900,
                    date(2026, 8, 1),
                ),
                "account_version": Decimal("2"),
            }
        ],
        as_of=date(2026, 8, 27),
    )[0]

    assert request.display_snapshot["account_version"] == 2
    assert request.desired.source_version == daily_root_source_version(
        as_of=date(2026, 8, 27), root_version=2
    )


def test_client_reminder_source_version_advances_for_same_day_owner_change() -> None:
    first = build_client_receivable_requests(
        [_obligation("C-SAME-DAY", "deposit", "receivable_from_client", 900, date(2026, 8, 1))],
        as_of=date(2026, 8, 27),
    )[0]
    second = build_client_receivable_requests(
        [
            {
                **_obligation("C-SAME-DAY", "deposit", "receivable_from_client", 900, date(2026, 8, 1)),
                "account_version": 1,
            }
        ],
        as_of=date(2026, 8, 27),
    )[0]

    assert second.desired.source_version > first.desired.source_version


def test_client_reminder_missing_account_version_fails_closed() -> None:
    with pytest.raises(ValueError, match="client_finance_account_version_missing"):
        build_client_receivable_requests(
            [
                {
                    **_obligation("C-MISSING-VERSION", "deposit", "receivable_from_client", 900, date(2026, 8, 1)),
                    "account_version": None,
                }
            ],
            as_of=date(2026, 8, 27),
        )


def test_client_refund_overdue_is_separate_from_subsidy_return() -> None:
    requests = build_client_payable_requests(
        [_obligation("C-5", "refund", "payable_to_client", 2600, date(2026, 8, 1))],
        as_of=date(2026, 8, 8),
    )

    assert requests[0].desired.definition_code == "CLIENTPAYABLE-001"
    assert requests[0].desired.active is True
    assert requests[0].display_snapshot["overdue_obligations"] == [
        "義務 obligation:C-5:refund｜一般客戶退款｜到期 2026-08-01｜未付 NT$ 2,600"
    ]


def test_positive_remaining_amount_cannot_be_hidden_by_settled_status() -> None:
    request = build_client_receivable_requests(
        [
            _obligation(
                "C-DRIFT",
                "deposit",
                "receivable_from_client",
                1200,
                date(2026, 8, 1),
                "settled",
            )
        ],
        as_of=date(2026, 8, 8),
    )[0]

    assert request.desired.active is True


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
        "action", "case_no", "overdue_obligations", "resolution_condition"
    )
    assert registry.require("RETURN-001").display_fields == (
        "action", "case_no", "overdue_obligations", "resolution_condition"
    )
    assert registry.require("CLIENTPAYABLE-001").display_fields == (
        "action", "case_no", "overdue_obligations", "resolution_condition"
    )


def test_overdue_alert_detail_is_specific_and_binds_owner_actions() -> None:
    registry = default_anomaly_registry()
    for code in ("RECEIVABLE-001", "CLIENTPAYABLE-001", "RETURN-001"):
        definition = registry.require(code)
        snapshot = {
            "action": "依 owner 正式流程處理",
            "case_no": "C-7",
            "overdue_obligations": [
                "義務 obligation:C-7:1｜第一期｜到期 2026-08-01｜未收 NT$ 1,200"
            ],
            "resolution_condition": "所有本碼逾期義務餘額歸零才解除",
            "account_version": 3,
        }
        public = _safe_display_snapshot(code, definition.display_fields, snapshot)
        assert [item.kind for item in public.fields] == [
            "code",
            "identity",
            "detail_list",
            "code",
        ]
        actions = _detail_actions(
            definition.available_actions,
            SimpleNamespace(
                projection=SimpleNamespace(
                    definition_code=code,
                    source_identity="C-7",
                ),
                display_snapshot=snapshot,
            ),
        )
        assert len(actions) == 1
        assert actions[0].source_bindings == {
            "account_version": 3,
            "case_no": "C-7",
        }
        assert actions[0].owning_domain == "client_finance"


def test_overdue_alert_action_binding_fails_closed_on_owner_version_drift() -> None:
    definition = default_anomaly_registry().require("RECEIVABLE-001")
    actions = _detail_actions(
        definition.available_actions,
        SimpleNamespace(
            projection=SimpleNamespace(
                definition_code="RECEIVABLE-001",
                source_identity="C-8",
            ),
            display_snapshot={"case_no": "C-8", "account_version": -1},
        ),
    )
    assert actions == ()


def test_reminder_loader_reads_canonical_obligations_not_legacy_payment_columns() -> None:
    assert "UNION" in _CLIENT_OBLIGATION_CANDIDATE_CASES_SQL
    assert "FOR UPDATE" in _CLIENT_FINANCE_ACCOUNT_LOCK_SQL
    assert "FROM client_obligations" in _CLIENT_OBLIGATION_REMINDER_SQL
    assert "obligation.obligation_identity" in _CLIENT_OBLIGATION_REMINDER_SQL
    assert "FOR UPDATE" in _CLIENT_OBLIGATION_REMINDER_SQL
    assert "client_payments" not in _CLIENT_OBLIGATION_REMINDER_SQL


def test_locked_reminder_rows_require_account_and_complete_obligation_root() -> None:
    candidate = [{"case_no": "C-LOCKED"}]
    with pytest.raises(ValueError, match="client_finance_account_missing"):
        _prepare_locked_client_obligation_rows(candidate, [], [])

    with pytest.raises(ValueError, match="client_finance_obligation_root_missing"):
        _prepare_locked_client_obligation_rows(
            candidate,
            [{"case_no": "C-LOCKED", "aggregate_version": 1}],
            [],
        )


def test_locked_reminder_rows_replace_legacy_account_version_with_locked_root() -> None:
    rows = _prepare_locked_client_obligation_rows(
        [{"case_no": "C-LOCKED"}],
        [{"case_no": "C-LOCKED", "aggregate_version": Decimal("4")}],
        [
            {
                **_obligation("C-LOCKED", "deposit", "receivable_from_client", 900, date(2026, 8, 1)),
                "account_version": 0,
            }
        ],
    )

    assert rows[0]["account_version"] == Decimal("4")


def _obligation(case_no, obligation_type, direction, amount_due_ntd, due_date, status="open"):
    return {
        "case_no": case_no,
        "obligation_identity": f"obligation:{case_no}:{obligation_type}",
        "obligation_type": obligation_type,
        "direction": direction,
        "amount_due_ntd": amount_due_ntd,
        "due_date": due_date,
        "status": status,
        "account_version": 0,
    }
