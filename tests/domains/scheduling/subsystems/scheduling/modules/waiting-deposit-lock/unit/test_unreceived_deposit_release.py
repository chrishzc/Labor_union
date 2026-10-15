"""Release may use Finance's absence proof but must recheck it before any occupancy mutation."""

from datetime import date, datetime
import json

import pytest

from domains.client_finance.reconciliation import UnreceivedDepositConfirmation
from shared_kernel.fingerprints import PreviewFingerprint
from subsystems.scheduling import availability_lock_release_workflow as workflow
from subsystems.scheduling.availability_lock_helpers import normalize_plan_snapshot


DAY = date(2026, 11, 16)
REQUEST = dict(case_no='CASE', plan_id=10, lock_id=20, event_key='release-1', actor='operator', reason='Customer requested replacement')


class _Cursor:
    rowcount = 1
    def __init__(self): self.writes = []; self.projection = None
    def execute(self, sql, params):
        if not sql.startswith('SELECT '): self.writes.append((sql, params))
    def fetchone(self): return self.projection
    def close(self): pass


class _Connection:
    def __init__(self): self._cursor = _Cursor(); self.commits = 0; self.rollbacks = 0
    def cursor(self): return self._cursor
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1
    def close(self): pass


@pytest.fixture
def setup(monkeypatch):
    connection = _Connection()
    plan = dict(id=10, case_no='CASE', status='accepted', is_active=1, start_date=DAY, end_date=DAY)
    segments = [dict(id=30, plan_id=10, segment_order=1, staff_id=40, assigned_start_date=DAY, assigned_end_date=DAY)]
    snapshot = normalize_plan_snapshot('CASE', 10, plan, segments)
    lock = dict(id=20, plan_id=10, status='active', is_active=1, released_by=None, released_at=None)
    days = [dict(id=50, segment_id=30, staff_id=40, lock_date=DAY, active_marker=1, released_by=None, released_at=None)]
    state = {'confirmation': UnreceivedDepositConfirmation('CASE', 0, (), (), ()), 'event': None}
    monkeypatch.setattr(workflow, 'get_connection', lambda: connection)
    def confirmation(borrowed, case_no):
        assert borrowed is connection and case_no == 'CASE'
        return state['confirmation']
    monkeypatch.setattr(workflow, 'get_unreceived_deposit_confirmation', confirmation)
    monkeypatch.setattr(workflow, '_load_lock_rows_for_update', lambda *args: (lock, days))
    monkeypatch.setattr(workflow, 'lock_staff_occupancy_mutex', lambda cursor, ids: ids)
    monkeypatch.setattr(workflow, '_load_order_snapshot', lambda *args: dict(case_no='CASE', status='洽談中'))
    monkeypatch.setattr(workflow, '_load_plan_snapshot', lambda *args: (plan, segments, snapshot))
    monkeypatch.setattr(workflow, '_load_existing_event', lambda *args: state['event'])
    return connection, state, plan, lock, days


def _preview():
    return workflow.preview_caregiver_availability_lock_release('CASE', 10, 20)


def test_missing_settlement_can_release_with_finance_proof_and_one_outer_commit(setup):
    connection, state, *_ = setup
    preview = _preview()
    assert preview['apply_allowed'] and not connection._cursor.writes and connection.commits == 0
    receipt = workflow.release_caregiver_availability_lock(**REQUEST, expected_preview_fingerprint=preview['preview_fingerprint'])
    assert receipt['lock_status'] == 'released' and connection.commits == 1
    assert len(connection._cursor.writes) == 4
    payload = json.loads(connection._cursor.writes[-1][1][-1])
    assert payload['finance_confirmation'] == workflow._confirmation_payload(state['confirmation'])
    assert not any('client_' in sql for sql, _ in connection._cursor.writes)


def test_finance_version_change_between_preview_and_apply_is_stale_without_writes(setup):
    connection, state, *_ = setup
    preview = _preview()
    state['confirmation'] = UnreceivedDepositConfirmation('CASE', 1, (), (), ())
    with pytest.raises(ValueError, match='stale_preview'):
        workflow.release_caregiver_availability_lock(**REQUEST, expected_preview_fingerprint=preview['preview_fingerprint'])
    assert not connection._cursor.writes and connection.commits == 0 and connection.rollbacks == 1


@pytest.mark.parametrize('root', ['obligation', 'event', 'receipt'])
def test_new_financial_history_after_preview_blocks_release_and_preserves_the_slot(setup, root):
    connection, state, *_ = setup
    preview = _preview()
    state['confirmation'] = UnreceivedDepositConfirmation('CASE', 1, ('deposit:1',) if root == 'obligation' else (), (7,) if root == 'event' else (), (9,) if root == 'receipt' else ())
    with pytest.raises(ValueError, match='unreceived deposit not confirmed'):
        workflow.release_caregiver_availability_lock(**REQUEST, expected_preview_fingerprint=preview['preview_fingerprint'])
    assert not connection._cursor.writes and connection.commits == 0 and connection.rollbacks == 1


def test_confirmation_for_another_case_cannot_release_this_slot(setup):
    connection, state, *_ = setup
    state['confirmation'] = UnreceivedDepositConfirmation('OTHER', 0, (), (), ())
    with pytest.raises(ValueError, match='confirmation case_no mismatch'): _preview()
    assert not connection._cursor.writes


@pytest.mark.parametrize('allocated', [0, 100])
def test_existing_settlement_preserves_the_formal_net_amount_gate(setup, allocated):
    connection, state, *_ = setup
    state['confirmation'] = UnreceivedDepositConfirmation('CASE', 1, ('deposit:1',), (7,), (9,))
    connection._cursor.projection = dict(case_no='CASE', deposit_obligation_identity='deposit:1', settlement_state='unsettled', contracted_amount_ntd=1000, allocated_net_amount_ntd=allocated, settlement_identity=None, source_fingerprint='a'*64, projection_version=1, latest_ledger_entry_id=9)
    preview = _preview()
    assert preview['apply_allowed'] == (allocated == 0)
    assert preview['blockers'] == ([] if allocated == 0 else ['deposit_not_zero'])
    assert not connection._cursor.writes


def test_exact_replay_keeps_original_finance_proof_and_does_not_write_again(setup):
    connection, state, plan, lock, days = setup
    preview = _preview()
    workflow.release_caregiver_availability_lock(**REQUEST, expected_preview_fingerprint=preview['preview_fingerprint'])
    payload = connection._cursor.writes[-1][1][-1]
    state['event'] = dict(id=60, lock_id=20, event_type='lock_released', event_key='release-1', actor='operator', reason=REQUEST['reason'], payload=payload)
    state['confirmation'] = UnreceivedDepositConfirmation('CASE', 1, (), (), ())
    plan.update(status='proposed')
    lock.update(status='released', is_active=None, released_by='operator', released_at=datetime(2026, 10, 14))
    for row in days: row.update(active_marker=None, released_by='operator', released_at=datetime(2026, 10, 14))
    connection._cursor.writes.clear()
    result = workflow.release_caregiver_availability_lock(**REQUEST, expected_preview_fingerprint=PreviewFingerprint(preview['preview_fingerprint']).value)
    assert result['result'] == 'existing'
    assert not connection._cursor.writes and connection.commits == 1 and connection.rollbacks == 1
