"""
File: test_government_subsidy_overpayment_query.py
Description: 驗證政府補助溢撥 owner Query 的根事實、資格與唯讀去敏契約。
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from api.dependencies.admin_auth import require_system_admin
from api.dependencies.government_subsidy import get_government_subsidy_application
from api.main import app
from infrastructure.mysql.government_subsidy_repository import (
    MySqlGovernmentSubsidyRepository,
)
from shared_kernel.identities import CorrelationId
from subsystems.government_subsidy.overpayment_query import (
    GovernmentSubsidyOverpaymentQueryError,
    GovernmentSubsidyOverpaymentQueryWorkflow,
    GovernmentSubsidyOffsetTargetQueryView,
    GovernmentSubsidyOverpaymentQueryView,
    GovernmentSubsidyReturnRecipientQueryView,
)


class _Cursor:
    def __init__(self, *, payer="hccg", recipient=True):
        self.payer = payer
        self.recipient = recipient
        self.statements = []
        self._result = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, _params=()):
        self.statements.append(statement)
        assert statement.lstrip().upper().startswith("SELECT")
        if "FROM government_subsidy_overpayments" in statement:
            self._result = {
                "overpayment_identity": "government-overpayment:bank-1",
                "source_finance_import_row_id": 11,
                "source_transaction_id": 21,
                "payer_identity": self.payer,
                "remaining_amount_ntd": 700,
                "status": "pending_review",
                "projection_version": 3,
            }
        elif "FROM subsidy_claim_batch_items" in statement:
            self._result = [
                {
                    "claim_item_id": 31,
                    "batch_id": 41,
                    "aggregate_version": 8,
                    "approved_amount": 1000,
                    "receipt_amount": 100,
                    "offset_amount": 200,
                    "submitted_at": date(2026, 1, 2),
                    "approved_at": date(2026, 1, 3),
                },
                {
                    "claim_item_id": 32,
                    "batch_id": 42,
                    "aggregate_version": 2,
                    "approved_amount": 100,
                    "receipt_amount": 100,
                    "offset_amount": 0,
                    "submitted_at": date(2026, 1, 2),
                    "approved_at": date(2026, 1, 3),
                },
            ]
        elif "FROM government_payer_receiving_accounts" in statement:
            self._result = (
                [
                    {
                        "bank_code": "004",
                        "account_number": "123456789012",
                        "account_name": "新竹市政府",
                        "effective_from": date(2026, 1, 1),
                    }
                ]
                if self.recipient
                else []
            )
        elif "FROM government_overpayment_return_excess_recoveries" in statement:
            self._result = None

    def fetchone(self):
        if isinstance(self._result, list):
            return self._result[0] if self._result else None
        return self._result

    def fetchall(self):
        return self._result if isinstance(self._result, list) else []


class _Connection:
    def __init__(self, **kwargs):
        self.cursor_value = _Cursor(**kwargs)

    def cursor(self):
        return self.cursor_value


def test_query_uses_owner_root_and_returns_only_eligible_targets_without_writes():
    connection = _Connection()
    result = MySqlGovernmentSubsidyRepository(connection).query_overpayment(
        "government-overpayment:bank-1"
    )

    assert result.remaining_amount_ntd == 700
    assert result.payer_identity == "hccg"
    assert result.offset_targets[0].outstanding_amount_ntd == 700
    assert result.offset_targets[0].batch_version == 8
    assert result.return_recipient.ready is True
    assert result.return_recipient.account_display.endswith("9012")
    assert result.return_recipient.account_display != "123456789012"
    assert result.available_actions == ("offset", "return")
    assert result.blockers == ()
    assert result.source_bank_fact_reference.startswith("redacted:")
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in connection.cursor_value.statements)


def test_query_reports_typed_recipient_blocker_and_keeps_offset_action():
    result = MySqlGovernmentSubsidyRepository(_Connection(recipient=False)).query_overpayment(
        "government-overpayment:bank-1"
    )

    assert result.return_recipient.ready is False
    assert result.return_recipient.blockers == (
        "government_subsidy_recipient_account_missing",
    )
    assert result.available_actions == ("offset",)
    assert result.blockers == ("government_subsidy_recipient_account_missing",)


def test_query_rejects_wrong_government_payer_fail_closed():
    with pytest.raises(ValueError, match="government_subsidy_overpayment_cross_payer"):
        MySqlGovernmentSubsidyRepository(_Connection(payer="other-government")).query_overpayment(
            "government-overpayment:bank-1"
        )


def test_query_workflow_maps_missing_root_to_typed_error():
    class _Missing:
        def query_overpayment(self, _identity):
            return None

    with pytest.raises(GovernmentSubsidyOverpaymentQueryError) as raised:
        GovernmentSubsidyOverpaymentQueryWorkflow(_Missing()).query(
            "government-overpayment:missing", CorrelationId("query")
        )
    assert raised.value.error.code == "government_subsidy_overpayment_not_found"


def test_query_route_returns_strict_owner_view():
    class _Application:
        def query_overpayment(self, identity, _correlation):
            return GovernmentSubsidyOverpaymentQueryView(
                identity,
                "hccg",
                700,
                "pending_review",
                3,
                "redacted:bank",
                "redacted:transaction",
                (
                    GovernmentSubsidyOffsetTargetQueryView(31, 41, 8, 700, "hccg"),
                ),
                GovernmentSubsidyReturnRecipientQueryView(
                    True,
                    (),
                    "hccg",
                    "新竹市政府",
                    "004",
                    "********9012",
                    "a" * 64,
                    "2026-01-01",
                ),
                (),
                ("offset", "return"),
            )

    app.dependency_overrides[require_system_admin] = lambda: object()
    app.dependency_overrides[get_government_subsidy_application] = lambda: _Application()
    try:
        response = TestClient(app).get(
            "/api/v1/government-subsidy/overpayments/government-overpayment:bank-1"
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["payer_identity"] == "hccg"
    assert payload["offset_targets"][0]["outstanding_amount_ntd"] == 700
