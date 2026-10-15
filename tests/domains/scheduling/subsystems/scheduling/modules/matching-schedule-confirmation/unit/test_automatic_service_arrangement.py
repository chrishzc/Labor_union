from datetime import date
from types import SimpleNamespace

from domains.scheduling.assignment_plan import AssignmentPlanIntent, AssignmentPlanSegmentIntent
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId
from subsystems.jobs.command_application import DurableJobAcceptance
from subsystems.scheduling.assignment_plan_workflow import AssignmentPlanWorkflowError
from subsystems.scheduling.automatic_service_arrangement import AutomaticArrangementProposal, AutomaticServiceArrangement


class Source:
    def __init__(self, confirmed=True, assignments=0):
        intent = AssignmentPlanIntent((AssignmentPlanSegmentIntent(9, date(2026, 11, 1), date(2026, 11, 2), (date(2026, 11, 1), date(2026, 11, 2))),))
        self.proposal_value = AutomaticArrangementProposal('CASE-1', 7, 3, confirmed, assignments, intent)
        self.jobs = {}

    def proposal(self, *_args):
        return self.proposal_value

    def job_state(self, identity):
        return self.jobs.get(identity)

    def pending(self, after, limit):
        return (('CASE-1', 7),) if not after else ()


class Preview:
    def __init__(self):
        self.calls = 0
        self.blocked = False

    def preview(self, request):
        self.calls += 1
        if self.blocked:
            raise AssignmentPlanWorkflowError(TypedError(ErrorCategory.DOMAIN_BLOCKED, 'waiting_lock_conversion_blocked', 'blocked', CorrelationId('test'), domain_blockers=('waiting_lock_conversion.deposit_required',)))
        return SimpleNamespace(order_version=4, scheduling_version=2, client_finance_version=3, payroll_version=1, fingerprint=PreviewFingerprint('a' * 64))


class Jobs:
    def __init__(self, source):
        self.source = source
        self.commands = []

    def enqueue(self, command):
        self.commands.append(command)
        self.source.jobs[command.command_identity] = (command.job_id, 'queued')
        return DurableJobAcceptance(command.job_id, False)


def ports(**kwargs):
    source, preview = Source(**kwargs), Preview()
    jobs = Jobs(source)
    return AutomaticServiceArrangement(source, preview, jobs), source, preview, jobs


def test_query_never_enqueues_even_when_ready():
    app, _, preview, jobs = ports()
    assert app.query('CASE-1', 7).state == 'ready'
    assert preview.calls == 1
    assert jobs.commands == []


def test_incomplete_confirmations_do_not_preview_or_dispatch():
    app, _, preview, jobs = ports(confirmed=False)
    assert app.dispatch_case('CASE-1', 7).state == 'awaiting_confirmations'
    assert preview.calls == 0
    assert jobs.commands == []


def test_financial_gate_preserves_confirmation_and_resumes_on_fresh_facts():
    app, _, preview, jobs = ports()
    preview.blocked = True
    status = app.dispatch_case('CASE-1', 7)
    assert status.state == 'awaiting_conditions'
    assert status.blockers == ('waiting_lock_conversion.deposit_required',)
    assert jobs.commands == []
    preview.blocked = False
    assert app.dispatch_case('CASE-1', 7).state == 'queued'
    assert len(jobs.commands) == 1


def test_repeated_discovery_keeps_one_canonical_identity_and_actor():
    app, _, _, jobs = ports()
    first = app.dispatch_case('CASE-1', 7)
    second = app.dispatch_case('CASE-1', 7)
    assert first.job_id == second.job_id
    assert len(jobs.commands) == 1
    command = jobs.commands[0]
    assert command.command_type == 'assignment_plan_apply'
    assert command.submitted_by == 'system:automatic-service-arrangement'
    assert command.payload['idempotency_key'] == command.command_identity
    assert command.payload['expected_scheduling_version'] == 2
    assert command.payload['segments'][0]['official_service_dates'] == ['2026-11-01', '2026-11-02']


def test_existing_owner_assignments_are_effective_without_reapplication():
    app, _, preview, jobs = ports(assignments=1)
    assert app.dispatch_case('CASE-1', 7).state == 'effective'
    assert preview.calls == 0
    assert jobs.commands == []


def test_failed_command_is_not_blindly_reenqueued():
    app, source, _, jobs = ports()
    status = app.dispatch_case('CASE-1', 7)
    identity = jobs.commands[0].command_identity
    source.jobs[identity] = (status.job_id, 'failed')
    assert app.dispatch_case('CASE-1', 7).state == 'failed'
    assert len(jobs.commands) == 1
