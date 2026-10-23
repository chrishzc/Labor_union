"""Retired automatic effects are cancelled without creating outbound messages."""
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
        self.statements.append(sql)
        if self.fail:
            raise RuntimeError('storage unavailable')
    def commit(self):
        self.committed = True
    def rollback(self):
        self.rolled_back = True
    def close(self):
        pass


def test_worker_only_retires_automatic_effects_and_preserves_staff_authored_questions():
    connection = Connection()
    assert CandidateContactCoordinationWorker(lambda: connection, lambda: None).run_once() == 2
    assert connection.committed
    assert all(sql.startswith('UPDATE line_delivery_tasks') for sql in connection.statements)
    assert "'candidate_contact_adjustment','candidate_contact_manual_followup','candidate_contact_staff_review'" in connection.statements[0]
    assert "'matching_plan_decision'" in connection.statements[0]
    assert "information_question_sent" in connection.statements[1] and "adjustment_question_sent" in connection.statements[1]
    assert all('timed_out' not in sql for sql in connection.statements)


def test_worker_storage_failure_is_rolled_back():
    connection = Connection(fail=True)
    with pytest.raises(RuntimeError, match='storage unavailable'):
        CandidateContactCoordinationWorker(lambda: connection, lambda: None).run_once()
    assert connection.rolled_back and not connection.committed
