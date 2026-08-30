"""
File: test_assignment_plan_durable_job.py
Description: 驗證 Assignment Plan command、Bridge adoption、worker重建與accepted語意。
"""

from datetime import date

from api.routes.assignment_plan import (
    _assignment_plan_command,
    _apply_request,
    apply_assignment_plan,
)
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.jobs.command_application import DurableJobAcceptance
from api.dependencies.durable_job_handlers import (
    assignment_plan_apply_handler,
    default_job_handlers,
)


class _Body:
    expected_order_version = 3
    expected_scheduling_version = 4
    expected_client_finance_version = 5
    expected_payroll_version = 6
    preview_fingerprint = "a" * 64
    reason = "confirmed plan"

    def to_intent(self):
        from domains.scheduling.assignment_plan import AssignmentPlanIntent, AssignmentPlanSegmentIntent
        segment = AssignmentPlanSegmentIntent(9, date(2026, 8, 1), date(2026, 8, 2), (date(2026, 8, 1), date(2026, 8, 2)))
        return AssignmentPlanIntent((segment,))


def _request():
    principal = AdminPrincipal(1, "admin", "Admin", "system_admin")
    return _apply_request("CASE-001", _Body(), "idem-1", "corr-1", principal)


def test_assignment_plan_command_preserves_apply_identity_and_versions():
    command = _assignment_plan_command("job-1", _request())

    assert command.command_type == "assignment_plan_apply"
    assert command.command_identity == "idem-1"
    assert command.payload["segments"][0]["official_service_dates"] == ["2026-08-01", "2026-08-02"]
    assert command.payload["expected_payroll_version"] == 6


def test_assignment_plan_handler_reconstructs_existing_apply_request(monkeypatch):
    captured = {}

    class _Connection:
        def close(self):
            captured["closed"] = True

    class _Application:
        def apply(self, request):
            captured["request"] = request
            return {"case_no": request.case_no, "receipt": "assignment-plan-1"}

    import api.dependencies.assignment_plan as dependency
    import infrastructure.mysql.mysql_adapter as mysql_adapter

    monkeypatch.setattr(mysql_adapter, "get_connection", _Connection)
    monkeypatch.setattr(dependency, "build_assignment_plan_application", lambda _connection: _Application())

    receipt, reference = assignment_plan_apply_handler(_assignment_plan_command("job-1", _request()).payload)

    assert receipt["case_no"] == "CASE-001"
    assert reference == "assignment_plan:CASE-001"
    assert captured["request"].expected_scheduling_version.value == 4
    assert captured["closed"] is True


def test_assignment_plan_apply_route_enqueues_durable_command_only():
    commands = []

    class _JobApplication:
        def enqueue(self, command):
            commands.append(command)
            return DurableJobAcceptance(command.job_id, replayed=False)

    principal = AdminPrincipal(1, "admin", "Admin", "system_admin")
    response = apply_assignment_plan(
        _Body(), "CASE-001", "idem-1", "corr-1", principal, _JobApplication()
    )

    assert commands[0].command_type == "assignment_plan_apply"
    assert commands[0].submitted_by == "admin_user_id:1"
    assert response.data.status_url.endswith(commands[0].job_id)


def test_default_durable_worker_registry_includes_assignment_plan_handler():
    assert default_job_handlers()["assignment_plan_apply"] is assignment_plan_apply_handler
