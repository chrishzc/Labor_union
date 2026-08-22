"""
File: test_payroll_rebuild_durable_job.py
Description: 驗證 Payroll Rebuild command、Bridge adoption、worker重建與accepted語意。
"""

from dataclasses import dataclass, field

from api.routes.payroll_rebuild import (
    _payroll_rebuild_command,
    apply_payroll_rebuild,
)
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.jobs.command_application import DurableJobAcceptance
from subsystems.jobs.durable_job_worker import (
    default_job_handlers,
    payroll_rebuild_apply_handler,
)
from subsystems.payroll.rebuild_workflow import PayrollRebuildRequest


class _Body:
    expected_payroll_version = 6
    preview_fingerprint = "a" * 64
    reason = "rebuild payroll from canonical service facts"


def _request() -> PayrollRebuildRequest:
    return PayrollRebuildRequest(
        "CASE-001",
        ExpectedVersion(6),
        PreviewFingerprint("a" * 64),
        IdempotencyKey("payroll-rebuild-idempotency"),
        ActorContext("admin_user_id:1"),
        "rebuild payroll from canonical service facts",
        CorrelationId("payroll-rebuild-correlation"),
    )


def test_payroll_rebuild_command_preserves_apply_identity_and_freshness_guard():
    command = _payroll_rebuild_command("job-1", _request())

    assert command.command_type == "payroll_rebuild_apply"
    assert command.command_identity == "payroll-rebuild-idempotency"
    assert command.payload == {
        "actor": "admin_user_id:1",
        "case_no": "CASE-001",
        "correlation_id": "payroll-rebuild-correlation",
        "expected_payroll_version": 6,
        "idempotency_key": "payroll-rebuild-idempotency",
        "preview_fingerprint": "a" * 64,
        "reason": "rebuild payroll from canonical service facts",
    }


def test_payroll_rebuild_handler_reconstructs_existing_apply_request(monkeypatch):
    captured = {}

    class _Connection:
        def close(self):
            captured["closed"] = True

    class _Application:
        def apply(self, request):
            captured["request"] = request
            return _Receipt(request.case_no)

    @dataclass
    class _Amount:
        amount: int = 1200

    @dataclass
    class _Fingerprint:
        value: str = "b" * 64

    @dataclass
    class _Receipt:
        case_no: str
        payroll_version: int = 7
        action_count: int = 1
        total_payable: _Amount = field(default_factory=_Amount)
        preview_fingerprint: _Fingerprint = field(default_factory=_Fingerprint)

    import api.dependencies.payroll_rebuild as dependency
    import infrastructure.mysql.mysql_adapter as mysql_adapter

    monkeypatch.setattr(mysql_adapter, "get_connection", _Connection)
    monkeypatch.setattr(
        dependency,
        "build_payroll_rebuild_application",
        lambda _connection: _Application(),
    )

    receipt, reference = payroll_rebuild_apply_handler(
        _payroll_rebuild_command("job-1", _request()).payload
    )

    assert receipt["case_no"] == "CASE-001"
    assert reference == "payroll_rebuild:CASE-001"
    assert captured["request"].expected_payroll_version.value == 6
    assert captured["closed"] is True


def test_payroll_rebuild_apply_route_enqueues_durable_command_only():
    commands = []

    class _JobApplication:
        def enqueue(self, command):
            commands.append(command)
            return DurableJobAcceptance(command.job_id, replayed=False)

    response = apply_payroll_rebuild(
        _Body(),
        "CASE-001",
        "payroll-rebuild-idempotency",
        "payroll-rebuild-correlation",
        AdminPrincipal(1, "payroll-admin", "Payroll Admin", "system_admin"),
        _JobApplication(),
    )

    assert commands[0].command_type == "payroll_rebuild_apply"
    assert commands[0].submitted_by == "admin_user_id:1"
    assert response.data.status_url.endswith(commands[0].job_id)


def test_default_durable_worker_registry_includes_payroll_rebuild_handler():
    assert default_job_handlers()["payroll_rebuild_apply"] is payroll_rebuild_apply_handler
