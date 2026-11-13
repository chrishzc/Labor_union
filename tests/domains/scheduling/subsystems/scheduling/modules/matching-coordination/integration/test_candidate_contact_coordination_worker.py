"""Retired coordination effects are cancelled without creating outbound messages."""
import pytest
from subsystems.line.candidate_contact_coordination_worker import CandidateContactCoordinationWorker


class Connection:
    committed = False
    rolled_back = False
    rowcount = 1
    def __init__(self, fail=False):
        self.statements = []
        self.fail = fail
    def cursor(self):
        return self
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def execute(self, sql, args):
        self.statements.append((sql, args))
        if self.fail:
            raise RuntimeError('storage unavailable')
    def commit(self):
        self.committed = True
    def rollback(self):
        self.rolled_back = True
    def close(self):
        pass


def test_worker_cancels_all_pending_retired_coordination_sources():
    connection = Connection()
    assert CandidateContactCoordinationWorker(lambda: connection, lambda: None).run_once() == 1
    assert connection.committed
    [(sql, params)] = connection.statements
    assert sql.startswith('UPDATE line_delivery_tasks')
    assert "processing_status IN ('pending','retryable_failed')" in sql
    assert set(params) == {
        'candidate_contact_adjustment', 'candidate_contact_answer',
        'candidate_contact_manual_followup', 'candidate_contact_question',
        'candidate_contact_staff_review', 'matching_plan_decision',
        'mobile-matching-followup:%',
    }


def test_worker_storage_failure_is_rolled_back():
    connection = Connection(fail=True)
    with pytest.raises(RuntimeError, match='storage unavailable'):
        CandidateContactCoordinationWorker(lambda: connection, lambda: None).run_once()
    assert connection.rolled_back and not connection.committed
