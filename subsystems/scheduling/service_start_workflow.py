"""Coordinate explicit service-start results and the exceptional substitute worklist."""

from dataclasses import dataclass
from datetime import date
from typing import Callable, Protocol

from domains.scheduling.service_start import ServiceStartConflict, ServiceStartSubmission
from shared_kernel.fingerprints import fingerprint_payload


@dataclass(frozen=True, slots=True)
class ServiceStartView:
    request_id: int
    case_no: str
    staff_id: int
    staff_name: str
    segment_id: int | None
    order_version: int
    version: int
    status: str
    requested_start_date: str | None
    selected_staff_id: int | None = None
    selected_staff_name: str | None = None
    willingness: str | None = None
    invitation_status: str | None = None
    joined: bool = False
    result: dict | None = None
    proposed_start_date: str | None = None
    proposed_end_date: str | None = None
    workflow_kind: str = 'service_start'
    leave_dates: tuple[dict, ...] = ()
    conflict_message: str | None = None
    handover_dates: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HandoverContext:
    case_no: str
    assignment_id: int
    staff_id: int
    staff_name: str
    order_version: int
    scheduling_version: int
    service_dates: tuple[str, ...]
    request: ServiceStartView | None = None


@dataclass(frozen=True, slots=True)
class ServiceStartCase:
    case_no: str
    staff_id: int
    staff_name: str
    segment_id: int | None
    order_version: int
    service_days: int
    planned_start_date: str
    assignment_id: int | None = None
    segment_start_date: str | None = None
    segment_end_date: str | None = None


@dataclass(frozen=True, slots=True)
class LeaveCase:
    case_no: str
    assignment_id: int
    order_version: int
    scheduling_version: int
    service_dates: tuple[str, ...]


class ServiceStartRepository(Protocol):
    def staff_cases(self, staff_id: int) -> tuple[ServiceStartCase, ...]: ...
    def replay_submission(self, submission: ServiceStartSubmission) -> ServiceStartView | None: ...
    def lock_subject(self, submission: ServiceStartSubmission): ...
    def create_submission(self, submission: ServiceStartSubmission, subject): ...
    def view(self, request_id: int, *, staff_id: int | None = None) -> ServiceStartView: ...


class ServiceStartWorkflow:
    def __init__(self, repository, arrangement, unit_of_work_factory: Callable):
        self.repository, self.arrangement, self.units = repository, arrangement, unit_of_work_factory

    def staff_cases(self, staff_id):
        return self.repository.staff_cases(staff_id)

    def submit(self, submission: ServiceStartSubmission):
        with self.units() as unit:
            replay = self.repository.replay_submission(submission)
            if replay is not None:
                return replay
            self.repository.lock_submission(submission)
            replay=self.repository.replay_submission(submission,lock=True)
            if replay is not None:
                return replay
            subject = self.repository.lock_subject(submission)
            request_id = self.repository.create_submission(submission, subject)
            if submission.decision.value == 'accepted':
                self._arrange(request_id, submission.start_date, f'staff:{submission.staff_id}', submission.key)
            unit.commit()
            return self.repository.view(request_id, staff_id=submission.staff_id)

    def leave_cases(self, staff_id):
        return self.repository.leave_cases(staff_id)

    def submit_leave(self, submission):
        with self.units() as unit:
            self.repository.lock_case(submission.case_no, (submission.staff_id,))
            replay = self.repository.replay_leave(submission)
            if replay is not None:
                return replay
            request_id = self.repository.create_leave(submission)
            if submission.decision == 'defer':
                self._arrange(request_id, submission.dates[0].new_date,
                              f'staff:{submission.staff_id}', submission.key)
            unit.commit()
            return self.repository.view(request_id, staff_id=submission.staff_id)

    def todos(self, page=1, page_size=25, case_no=None):
        return self.repository.todos(page, page_size, case_no)

    def handover_context(self, case_no, assignment_id=None):
        return self.repository.handover_context(case_no, assignment_id)

    def inquire_handover(self, case_no, assignment_id, staff_id, order_version, scheduling_version, actor, key):
        payload = (case_no, assignment_id, staff_id, order_version, scheduling_version, actor)
        with self.units() as unit:
            self.repository.lock_case(case_no, (staff_id,))
            replay = self.repository.command_replay('handover', key, payload)
            if replay is not None:
                return self.repository.view(replay,lock=True)
            request_id, dates = self.repository.create_handover(case_no, assignment_id,
                order_version, scheduling_version, key, payload)
            self.repository.inquire(request_id, staff_id, date.fromisoformat(dates[0]),
                date.fromisoformat(dates[-1]), 1, actor, key)
            self.repository.save_command('handover', key, request_id, payload)
            result = self.repository.view(request_id,lock=True)
            unit.commit()
            return result

    def inquire(self, request_id, staff_id, start_date, end_date, version, actor, key):
        with self.units() as unit:
            self.repository.lock_command(request_id, (staff_id,))
            replay = self.repository.command_replay('inquire', key, (request_id, staff_id, str(start_date), str(end_date), version, actor))
            if replay is None:
                self.repository.inquire(request_id, staff_id, start_date, end_date, version, actor, key)
                self.repository.save_command('inquire', key, request_id, (request_id, staff_id, str(start_date), str(end_date), version, actor))
            result = self.repository.view(request_id,lock=True)
            if replay is None:
                unit.commit()
            return result

    def invite(self, request_id, version, actor, key):
        with self.units() as unit:
            self.repository.lock_command(request_id)
            replay = self.repository.command_replay('invite', key, (request_id, version, actor))
            if replay is None:
                self.repository.invite(request_id, version, actor, key)
                self.repository.save_command('invite', key, request_id, (request_id, version, actor))
            result = self.repository.view(request_id,lock=True)
            if replay is None:
                unit.commit()
            return result

    def save_dates(self, request_id, start_date, version, actor, key, date_changes=None):
        payload = (request_id, str(start_date), version, actor)
        if date_changes is not None:
            payload = (request_id, str(start_date), version,
                       tuple((str(d.original_date), str(d.new_date)) for d in date_changes), actor)
        with self.units() as unit:
            self.repository.lock_command(request_id)
            replay = self.repository.command_replay('dates', key, payload)
            if replay is None:
                self.repository.require_joined_candidate(request_id, version)
                self.repository.record_leave_dates(request_id, date_changes)
                self.repository.record_candidate_date(request_id,start_date)
                self._arrange(request_id, start_date, actor, key)
                self.repository.save_command('dates', key, request_id, payload)
            result = self.repository.view(request_id,lock=True)
            if replay is None:
                unit.commit()
            return result

    def save_defer_dates(self, request_id, dates, version, actor, key):
        payload = (request_id, tuple((str(d.original_date), str(d.new_date)) for d in dates), version, actor)
        with self.units() as unit:
            self.repository.lock_command(request_id)
            replay = self.repository.command_replay('defer', key, payload)
            if replay is None:
                self.repository.require_pending(request_id, version)
                self.repository.record_leave_dates(request_id, dates, defer=True)
                self._arrange(request_id, dates[0].new_date, actor, key)
                self.repository.save_command('defer', key, request_id, payload)
            result = self.repository.view(request_id,lock=True)
            if replay is None:
                unit.commit()
            return result

    def record_willingness_in_current_unit_of_work(self, token, line_user_id, willingness, event_key):
        return self.repository.record_willingness(token, line_user_id, willingness, event_key)

    def _arrange(self, request_id, start_date, actor, key):
        # A canonical business occupancy conflict becomes an exception work item.
        # Infrastructure and stale errors still abort the complete transaction.
        self.repository.arrangement_savepoint()
        try:
            result = self.arrangement.apply(request_id, start_date, actor, key)
        except Exception as error:
            if not self.arrangement.is_occupancy_conflict(error):
                raise
            self.repository.rollback_arrangement()
            self.repository.mark_substitute_required(request_id, error)
            return
        if result is not None:
            self.repository.complete(request_id, result, actor, key)
