"""Regression contract for durable Staff Payout Apply delivery."""

from datetime import date

from api.routes.staff_payout import _staff_payout_command
from domains.staff_payables.reconciliation import StaffPayoutEventType
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.jobs.durable_job_worker import (
    default_job_handlers,
    staff_payout_apply_handler,
)
from subsystems.staff_payables.payout_reconciliation import (
    StaffPayoutApplyRequest,
    StaffPayoutSelection,
)


def _request(event_type, bank_fact_identities, reopen_fact_identity=None):
    return StaffPayoutApplyRequest(
        StaffPayoutSelection(event_type, bank_fact_identities, ("obligation-1",), reopen_fact_identity),
        ExpectedVersion(3), ExpectedVersion(4), PreviewFingerprint("a" * 64),
        IdempotencyKey(f"staff-payout-{event_type.value}"), ActorContext("payroll-admin"),
        "record canonical staff payment", CorrelationId("staff-payout-correlation"),
    )


def test_staff_payout_command_preserves_all_three_event_identities():
    payout = _staff_payout_command("job-payout", _request(StaffPayoutEventType.PAYOUT, ("bank-1",)))
    returned = _staff_payout_command("job-return", _request(StaffPayoutEventType.RETURN, (), "return-1"))
    reversal = _staff_payout_command("job-reversal", _request(StaffPayoutEventType.REVERSAL, (), "reversal-1"))

    assert payout.command_type == returned.command_type == reversal.command_type == "staff_payout_apply"
    assert payout.payload["selection"] == {
        "event_type": "payout", "bank_fact_identities": ["bank-1"],
        "obligation_identities": ["obligation-1"], "reopen_fact_identity": None,
    }
    assert returned.payload["selection"]["reopen_fact_identity"] == "return-1"
    assert reversal.payload["selection"]["reopen_fact_identity"] == "reversal-1"


def test_staff_payout_handler_reconstructs_existing_apply_request(monkeypatch):
    captured = {}

    class _Connection:
        def close(self):
            captured["closed"] = True

    class _Application:
        def apply(self, request):
            captured["request"] = request
            return _Receipt()

    class _Receipt:
        event_type = StaffPayoutEventType.PAYOUT
        staff_id = 1
        staff_payables_version = 4
        bank_facts_version = 4
        resulting_status = "paid"
        event_count = 1
        obligation_link_count = 1
        preview_fingerprint = PreviewFingerprint("b" * 64)

    import api.dependencies.staff_payout as dependency
    import infrastructure.mysql.mysql_adapter as mysql_adapter

    monkeypatch.setattr(mysql_adapter, "get_connection", _Connection)
    monkeypatch.setattr(dependency, "build_staff_payout_application", lambda _connection: _Application())

    receipt, reference = staff_payout_apply_handler(
        _staff_payout_command("job-payout", _request(StaffPayoutEventType.PAYOUT, ("bank-1",))).payload
    )

    assert receipt["event_type"] == "payout"
    assert reference == "staff_payout:1"
    assert captured["request"].selection.bank_fact_identities == ("bank-1",)
    assert captured["closed"] is True


def test_default_durable_worker_registry_includes_staff_payout_handler():
    assert default_job_handlers()["staff_payout_apply"] is staff_payout_apply_handler
