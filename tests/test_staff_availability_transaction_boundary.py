"""
File: test_staff_availability_transaction_boundary.py
Description: 驗證 Availability 使用 canonical occupancy mutex 與唯一 outer UoW。
"""

from pathlib import Path

import pytest

from subsystems.scheduling.occupancy_mutex import lock_staff_occupancy_mutex


ROOT = Path(__file__).resolve().parents[1]


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def execute(self, query, params):
        self.executed.append((query, params))

    def fetchall(self):
        return self.rows


def test_occupancy_mutex_locks_canonical_staff_set_in_order():
    cursor = _Cursor([{"id": 7}, {"id": 12}])

    locked = lock_staff_occupancy_mutex(cursor, [12, 7])

    assert locked == [7, 12]
    query, params = cursor.executed[0]
    assert "SELECT id FROM staff" in query
    assert "ORDER BY id FOR UPDATE" in query
    assert params == (7, 12)


def test_occupancy_mutex_rejects_duplicate_or_partial_lock_set():
    with pytest.raises(ValueError, match="must not contain duplicates"):
        lock_staff_occupancy_mutex(_Cursor([]), [7, 7])

    with pytest.raises(ValueError, match="cannot lock all requested staff"):
        lock_staff_occupancy_mutex(_Cursor([{"id": 7}]), [7, 12])


def test_availability_backend_has_no_repository_commit_owner():
    workflow_source = (
        ROOT / "subsystems/scheduling/staff_availability_workflow.py"
    ).read_text(encoding="utf-8")
    repository_source = (
        ROOT / "infrastructure/mysql/staff_availability_repository.py"
    ).read_text(encoding="utf-8")
    dependency_source = (
        ROOT / "api/dependencies/staff_availability.py"
    ).read_text(encoding="utf-8")

    assert "lock_staff_occupancy_mutex" in workflow_source
    assert "self._repository.commit(" not in workflow_source
    assert "self._repository.rollback(" not in workflow_source
    assert "def commit(" not in repository_source
    assert "def rollback(" not in repository_source
    assert "MySqlUnitOfWork" in dependency_source


def test_fresh_lock_precedes_fresh_facts_and_receipt_reads():
    source = (
        ROOT / "subsystems/scheduling/staff_availability_workflow.py"
    ).read_text(encoding="utf-8")

    lock_position = source.index("lock_staff_occupancy_mutex")
    fresh_facts_position = source.index("load_facts", lock_position)
    receipt_position = source.index("load_receipt", lock_position)
    assert lock_position < fresh_facts_position
    assert lock_position < receipt_position
