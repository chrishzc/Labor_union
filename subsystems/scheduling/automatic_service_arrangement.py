"""Dispatch confirmed service arrangements through the existing canonical job writer."""

from dataclasses import dataclass
from hashlib import sha256
from typing import Literal, Protocol
from uuid import uuid4

from domains.scheduling.assignment_plan import AssignmentPlanIntent
from shared_kernel.durable_job_queue import DurableJobCommand
from shared_kernel.errors import ErrorCategory
from shared_kernel.identities import CorrelationId
from subsystems.jobs.command_application import DurableJobAcceptance
from subsystems.scheduling.assignment_plan_workflow import (
    AssignmentPlanPreview, AssignmentPlanPreviewRequest, AssignmentPlanWorkflowError,
)


@dataclass(frozen=True, slots=True)
class AutomaticArrangementProposal:
    case_no: str
    plan_id: int
    confirmed_version: int
    confirmed: bool
    assignment_count: int
    intent: AssignmentPlanIntent | None


@dataclass(frozen=True, slots=True)
class AutomaticArrangementStatus:
    case_no: str
    plan_id: int
    state: Literal['awaiting_confirmations', 'awaiting_conditions', 'ready', 'queued', 'running', 'effective', 'failed']
    blockers: tuple[str, ...] = ()
    job_id: str | None = None
    assignment_count: int = 0


class AutomaticArrangementSource(Protocol):
    def reserve_waiting_deposit(self, case_no: str) -> None: ...
    def proposal(self, case_no: str, plan_id: int) -> AutomaticArrangementProposal: ...
    def pending(self, after_case_no: str, limit: int) -> tuple[tuple[str, int], ...]: ...
    def job_state(self, identity: str) -> tuple[str, str] | None: ...


class AssignmentPreviewPort(Protocol):
    def preview(self, request: AssignmentPlanPreviewRequest) -> AssignmentPlanPreview: ...


class ArrangementJobEnqueuer(Protocol):
    def enqueue(self, command: DurableJobCommand) -> DurableJobAcceptance: ...


class AutomaticServiceArrangement:
    def __init__(self, source: AutomaticArrangementSource, assignments: AssignmentPreviewPort, jobs: ArrangementJobEnqueuer):
        self.source, self.assignments, self.jobs = source, assignments, jobs

    def query(self, case_no: str, plan_id: int) -> AutomaticArrangementStatus:
        status, _ = self._candidate(case_no, plan_id)
        return status

    def dispatch_case(self, case_no: str, plan_id: int) -> AutomaticArrangementStatus:
        try:
            self.source.reserve_waiting_deposit(case_no)
        except ValueError as error:
            return AutomaticArrangementStatus(case_no, plan_id, 'awaiting_conditions', (str(error),))
        status, command = self._candidate(case_no, plan_id)
        if command is None or status.state != 'ready':
            return status
        accepted = self.jobs.enqueue(command)
        return AutomaticArrangementStatus(case_no, plan_id, 'queued', job_id=accepted.job_id)

    def dispatch_pending(self, page_size: int = 100) -> int:
        after = ''
        queued = 0
        while True:
            page = self.source.pending(after, page_size)
            if not page:
                return queued
            for case_no, plan_id in page:
                if self.dispatch_case(case_no, plan_id).state == 'queued':
                    queued += 1
            after = page[-1][0]

    def _candidate(self, case_no: str, plan_id: int):
        try:
            proposal = self.source.proposal(case_no, plan_id)
            if proposal.assignment_count:
                return AutomaticArrangementStatus(case_no, plan_id, 'effective', assignment_count=proposal.assignment_count), None
            if not proposal.confirmed:
                return AutomaticArrangementStatus(case_no, plan_id, 'awaiting_confirmations'), None
            if proposal.intent is None:
                raise ValueError('matching_schedule_confirmation_required_for_target_segments')
            preview = self.assignments.preview(AssignmentPlanPreviewRequest(case_no, proposal.intent, CorrelationId('automatic-service-arrangement-query')))
        except AssignmentPlanWorkflowError as error:
            if error.error.category not in {ErrorCategory.DOMAIN_BLOCKED, ErrorCategory.CONFLICT, ErrorCategory.VALIDATION}:
                raise
            return AutomaticArrangementStatus(case_no, plan_id, 'awaiting_conditions', error.error.domain_blockers or (error.error.code,)), None
        except ValueError as error:
            return AutomaticArrangementStatus(case_no, plan_id, 'awaiting_conditions', (str(error),)), None
        command = build_automatic_arrangement_command(proposal, preview)
        job = self.source.job_state(command.command_identity)
        if job:
            job_id, job_status = job
            state = 'queued' if job_status == 'queued' else 'running' if job_status == 'running' else 'failed'
            # A succeeded job is not considered effective until the owner query sees assignments.
            return AutomaticArrangementStatus(case_no, plan_id, state, () if state != 'failed' else ('automatic_arrangement_result_requires_readback',), job_id), None
        return AutomaticArrangementStatus(case_no, plan_id, 'ready'), command


def build_automatic_arrangement_command(proposal: AutomaticArrangementProposal, preview: AssignmentPlanPreview) -> DurableJobCommand:
    identity = 'auto-assignment:' + sha256(f'{proposal.case_no}:{proposal.plan_id}:{proposal.confirmed_version}:{preview.fingerprint.value}'.encode('utf-8')).hexdigest()
    actor = 'system:automatic-service-arrangement'
    payload = {
        'case_no': proposal.case_no,
        'segments': [{'staff_id': s.staff_id, 'assigned_start_date': s.assigned_start_date.isoformat(), 'assigned_end_date': s.assigned_end_date.isoformat(), 'official_service_dates': [d.isoformat() for d in s.official_service_dates]} for s in proposal.intent.segments],
        'expected_order_version': preview.order_version,
        'expected_scheduling_version': preview.scheduling_version,
        'expected_client_finance_version': preview.client_finance_version,
        'expected_payroll_version': preview.payroll_version,
        'preview_fingerprint': preview.fingerprint.value,
        'idempotency_key': identity,
        'actor': actor,
        'reason': '客戶與所有月嫂已確認同一份日期表，條件齊備後自動排班',
        'correlation_id': identity,
    }
    return DurableJobCommand(str(uuid4()), identity, 'assignment_plan_apply', 1, payload, actor, identity)
