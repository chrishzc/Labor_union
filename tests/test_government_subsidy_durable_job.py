"""
File: test_government_subsidy_durable_job.py
Description: 驗證 Government Subsidy 全 action canonical payload、worker重建與handler registry。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from api.dependencies.durable_job_handlers import (
    _government_subsidy_request,
    default_job_handlers,
    government_subsidy_apply_handler,
)


def _payload(action: str, intent: dict) -> dict:
    return {
        "action": action,
        "intent": intent,
        "expected_batch_version": 3,
        "preview_fingerprint": "a" * 64,
        "idempotency_key": f"government-{action}",
        "actor": "admin_user_id:1",
        "reason": "durable command contract",
        "correlation_id": f"government-{action}",
    }


def test_reconstructs_all_government_subsidy_apply_requests():
    requests = (
        _government_subsidy_request(_payload("claim_plan", {
            "application_year": 2026, "quarter": 3, "revision": 1,
        })),
        _government_subsidy_request(_payload("claim_submission", {"batch_id": 7})),
        _government_subsidy_request(_payload("claim_approval", {
            "batch_id": 7, "item_approvals": [{"item_id": 11, "approved_amount_ntd": 300}],
        })),
        _government_subsidy_request(_payload("receipt", {
            "finance_import_row_id": 21, "batch_id": 7,
            "allocations": [{"target_identity": 11, "amount_ntd": 300}],
        })),
        _government_subsidy_request(_payload("reversal", {
            "finance_import_row_id": 22, "source_receipt_id": 31,
            "allocations": [{"target_identity": 11, "amount_ntd": 300}],
        })),
    )

    assert [request.intent.__class__.__name__ for request in requests] == [
        "ClaimPlanningIntent", "ClaimSubmissionIntent", "ClaimApprovalIntent",
        "ReceiptIntent", "ReversalIntent",
    ]
    assert [request.expected_batch_version.value for request in requests] == [3] * 5


def test_route_command_contains_the_full_durable_envelope():
    from api.routes.government_subsidy import _government_subsidy_command

    request = _government_subsidy_request(_payload("claim_submission", {"batch_id": 7}))
    command = _government_subsidy_command(
        "claim_submission", {"batch_id": 7}, request
    )("job-1")

    assert command.job_id == "job-1"
    assert command.command_identity == "government-claim_submission"
    assert command.command_type == "government_subsidy_apply"
    assert command.submitted_by == "admin_user_id:1"
    assert command.payload["intent"] == {"batch_id": 7}


def test_government_subsidy_handler_is_registered_and_routes_do_not_use_background_tasks():
    source = Path("api/routes/government_subsidy.py").read_text(encoding="utf-8")

    assert "government_subsidy_apply" in default_job_handlers()
    assert "BackgroundTasks" not in source
    assert "background_tasks" not in source
    assert "_call_apply_async" not in source


def test_handler_rebuilds_claim_plan_with_a_fresh_connection(monkeypatch):
    import api.dependencies.government_subsidy as dependency
    import infrastructure.mysql.mysql_adapter as mysql_adapter

    @dataclass(frozen=True)
    class Receipt:
        batch_id: int
        batch_version: int

    class Application:
        def apply_claim_plan(self, request):
            assert request.intent.identity.application_year == 2026
            return Receipt(7, 4)

    class Connection:
        closed = False

        def close(self):
            self.closed = True

    connection = Connection()
    monkeypatch.setattr(mysql_adapter, "get_connection", lambda: connection)
    monkeypatch.setattr(dependency, "build_government_subsidy_application", lambda _: Application())

    receipt, reference = government_subsidy_apply_handler(_payload("claim_plan", {
        "application_year": 2026, "quarter": 3, "revision": 1,
    }))

    assert receipt == {"batch_id": 7, "batch_version": 4}
    assert reference == "government_subsidy:7"
    assert connection.closed is True
