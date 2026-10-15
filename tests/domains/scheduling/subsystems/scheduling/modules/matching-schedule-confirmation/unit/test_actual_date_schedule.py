import json
from datetime import date
from types import SimpleNamespace
import pytest

from domains.scheduling.assignment_plan import AssignmentPlanIntent, AssignmentPlanSegmentIntent
from infrastructure.mysql.assignment_plan_repository import _matching_schedule_segments
from infrastructure.mysql.assignment_plan_repository import _current_confirmed_execution, _require_exact_commitment_days
from domains.scheduling.commitment_execution import CommitmentServiceDay, ExecutionServiceDay, CommitmentExecutionMismatch, require_exact_commitment_execution
from infrastructure.mysql.automatic_service_arrangement_repository import MySqlAutomaticServiceArrangementSource
from infrastructure.mysql.matching_schedule_confirmation_repository import MySqlMatchingScheduleConfirmationRepository, _schedule_payload


class Cursor:
    def __init__(self, *, one=(), many=()):
        self.one, self.many = iter(one), iter(many)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def execute(self, *_):
        pass

    def fetchone(self):
        return next(self.one)

    def fetchall(self):
        return next(self.many)


def connection(cursor):
    return SimpleNamespace(cursor=lambda: cursor)


def test_single_caregiver_receives_all_current_dates_after_actual_start_changes():
    cursor = Cursor(one=[{'line_user_id': None}], many=[
        [{'service_date': date(2026, 9, 14)}, {'service_date': date(2026, 9, 15)}],
        [{'id': 4, 'assigned_start_date': date(2026, 10, 26), 'assigned_end_date': date(2026, 11, 5), 'line_user_id': None}],
    ])
    payloads = MySqlMatchingScheduleConfirmationRepository._payloads(cursor, 'CASE', 4, 3)
    assert payloads[1]['total_service_days'] == 2
    assert payloads[1]['weeks'] == payloads[0]['weeks']


def test_old_empty_child_confirmation_cannot_satisfy_corrected_date_table():
    fresh = [_schedule_payload('customer', 'customer', None, None, ['2026-09-14']), _schedule_payload('caregiver', 'caregiver:4', 4, None, ['2026-09-14'])]
    old = [fresh[0], _schedule_payload('caregiver', 'caregiver:4', 4, None, [])]
    cursor = Cursor(one=[{'id': 3, 'version': 3}, {'id': 4, 'confirmed_version_id': 3, 'current_marker': 1, 'status': 'draft'}])
    repository = MySqlMatchingScheduleConfirmationRepository(connection(cursor))
    repository._payloads = lambda *_: fresh
    repository._snapshot_payloads = lambda *_: old
    result = repository.query('CASE', 4)
    assert result['snapshot_status'] == 'sent_outdated'
    assert result['recipients'] == []
    assert result['gate_passed'] is False
    assert result['outdated_schedule_preview']['recipient_schedules'][1]['total_service_days'] == 0


def test_manual_audit_metadata_does_not_invalidate_unchanged_schedule_payload():
    payload = _schedule_payload('customer', 'customer', None, None, ['2026-09-14'])
    stored = {**payload, 'manual_preparation': {'actor': 'test-admin', 'reason': 'test confirmation'}}
    cursor = Cursor(many=[[{'payload_snapshot': json.dumps(stored)}]])
    assert MySqlMatchingScheduleConfirmationRepository._snapshot_payloads(cursor, 4) == [payload]


def test_assignment_requires_exact_confirmed_child_dates_instead_of_old_proposed_period():
    payload = _schedule_payload('caregiver', 'caregiver:4', 4, None, ['2026-09-14', '2026-09-15'])
    row = {'segment_id': 4, 'staff_id': 1, 'assigned_start_date': date(2026, 10, 26), 'assigned_end_date': date(2026, 11, 5), 'actual_start_date': date(2026, 9, 14), 'payload_snapshot': json.dumps(payload)}
    def resolve(days):
        intent = AssignmentPlanIntent((AssignmentPlanSegmentIntent(1, date(2026, 9, 14), date(2026, 9, 15), days),))
        return _matching_schedule_segments(Cursor(many=[[row]]), 4, intent)
    assert resolve((date(2026, 9, 14), date(2026, 9, 15))) == (4,)
    assert resolve((date(2026, 9, 14),)) is None


def test_automatic_assignment_uses_confirmed_actual_period_for_single_caregiver():
    row = {'id': 4, 'staff_id': 1, 'assigned_start_date': date(2026, 10, 26), 'assigned_end_date': date(2026, 11, 5), 'actual_start_date': date(2026, 9, 13)}
    source = MySqlAutomaticServiceArrangementSource(connection(Cursor(many=[[row]])), SimpleNamespace(query=lambda _: SimpleNamespace(assignment_plan=SimpleNamespace(effective_assignments=()))))
    source.schedules = SimpleNamespace(query=lambda *_: {'gate_passed': True, 'confirmed_service_date_version': 3, 'schedule_preview': {'recipient_schedules': [{'audience_type': 'caregiver', 'segment_id': 4, 'weeks': [{'service_dates': ['2026-09-14', '2026-09-15']}]}]}})
    intent = source.proposal('CASE', 4).intent.segments[0]
    assert intent.assigned_start_date == date(2026, 9, 13)
    assert intent.assigned_end_date == date(2026, 9, 15)
    assert intent.official_service_dates == (date(2026, 9, 14), date(2026, 9, 15))


def test_actual_start_shift_preserves_signed_people_and_volume_without_resigning():
    signed = (CommitmentServiceDay(1, date(2026, 10, 26)),)
    current = (ExecutionServiceDay(1, date(2027, 1, 4)),)
    require_exact_commitment_execution(4, (4,), signed, current, confirmed_days=current)
    assert signed[0].service_date == date(2026, 10, 26)


@pytest.mark.parametrize('plan,staff,days,confirmed', [
    (5, 1, (4,), (4,)),       # different plan
    (4, 2, (4,), (4,)),       # different caregiver
    (4, 1, (4, 5), (4, 5)), # changed service volume
    (4, 1, (4,), (5,)),      # current confirmations cover another date
    (4, 1, (4, 4), (4, 4)), # duplicate dates
    (4, 1, (4,), ()),        # no current confirmed dates
])
def test_confirmed_date_shift_cannot_bypass_signed_identity_volume_or_confirmation(plan, staff, days, confirmed):
    signed = (CommitmentServiceDay(1, date(2026, 10, 26)),)
    execution = tuple(ExecutionServiceDay(staff, date(2027, 1, day)) for day in days)
    confirmed_days = tuple(ExecutionServiceDay(staff, date(2027, 1, day)) for day in confirmed)
    with pytest.raises(CommitmentExecutionMismatch):
        require_exact_commitment_execution(4, (plan,), signed, execution, confirmed_days=confirmed_days)


def test_conversion_reads_current_confirmed_snapshot_instead_of_trusting_intent_dates():
    cursor = Cursor(one=[{'id': 11, 'matching_plan_id': 4, 'terminal_event_id': None}, {'id': 8, 'confirmed_version_id': 6}, {'total': 2, 'confirmed': 2}], many=[
        [{'staff_id': 1, 'service_date': date(2026, 10, 26)}],
        [{'plan_id': 4}],
        [{'segment_id': 4, 'staff_id': 1, 'payload_snapshot': {'weeks': [{'service_dates': ['2027-01-04']}]}}],
    ])
    assert _require_exact_commitment_days(cursor, 'CASE', (ExecutionServiceDay(1, date(2027, 1, 4)),), (17,), lock=True) == 11


@pytest.mark.parametrize('snapshot,counts', [(None, None), ({'id': 8}, {'total': 2, 'confirmed': 1})])
def test_shift_cannot_use_obsolete_or_only_partially_confirmed_snapshot(snapshot, counts):
    cursor = Cursor(one=[snapshot, counts], many=[[{'segment_id': 4}]])
    with pytest.raises(CommitmentExecutionMismatch):
        _current_confirmed_execution(cursor, 'CASE', 4, lock=True)
