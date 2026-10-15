import pytest

from subsystems.scheduling.matching_communication_workflow import _cancel_matching_plan_in_transaction


class Cursor:
    def __init__(self, *, assigned=False, locked=False, version=4):
        self.assigned, self.locked, self.version = assigned, locked, version
        self.row = None
        self.rowcount = 1
        self.lastrowid = 19
        self.writes = []

    def execute(self, sql, args):
        if 'SELECT p.status' in sql:
            self.row = {'status': 'proposed', 'is_active': 1, 'communication_version': self.version, 'order_status': '訂單成立'}
        elif 'FROM caregiver_matching_plan_events' in sql:
            self.row = None
        elif 'SELECT assignment.id' in sql:
            self.row = {'id': 1} if self.assigned else None
        elif 'SELECT id FROM caregiver_availability_locks' in sql:
            self.row = {'id': 1} if self.locked else None
        else:
            self.writes.append((sql, args))

    def fetchone(self):
        return self.row


@pytest.mark.parametrize('values,code', [
    ({'assigned': True}, 'recommendation_has_assignment'),
    ({'locked': True}, 'recommendation_lock_release_required'),
    ({'version': 5}, 'recommendation_stale'),
])
def test_recommendation_cancellation_rejects_fresh_assignment_lock_or_version_change(values, code):
    cursor = Cursor(**values)
    with pytest.raises(ValueError, match=code):
        _cancel_matching_plan_in_transaction(object(), cursor, 'CASE-UI', 8, 'original-key', 'operator', '客戶要求換人', 4)
    assert cursor.writes == []


def test_unassigned_restarted_order_can_cancel_recommendation_with_original_reason():
    cursor = Cursor()
    result = _cancel_matching_plan_in_transaction(object(), cursor, 'CASE-UI', 8, 'original-key', 'operator', '客戶要求換人', 4)
    assert result == {'status': 'cancelled', 'event_id': 19}
    assert len(cursor.writes) == 2
    assert cursor.writes[1][1][2] == 'operator'
    assert '客戶要求換人' in cursor.writes[1][1][3]
