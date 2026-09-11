from datetime import date

from subsystems.government_subsidy import reconciliation_register_query as register


class FakeCursor:
    def __init__(self):
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params):
        self.executed.append((" ".join(sql.split()), params))

    def fetchall(self):
        return []


class FakeConnection:
    def __init__(self):
        self.cursor_instance = FakeCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


def test_established_case_staff_falls_back_to_latest_effective_assignment():
    connection = FakeConnection()

    register._fetch_established_cases(
        date(2026, 1, 1),
        date(2027, 1, 1),
        lambda: connection,
    )

    sql, _params = connection.cursor_instance.executed[0]
    assert "LEFT JOIN staff s ON s.id = o.staff_id" in sql
    assert "SELECT assigned_staff.name FROM case_staff_assignments csa" in sql
    assert "JOIN staff assigned_staff ON assigned_staff.id = csa.staff_id" in sql
    assert "csa.case_no = o.case_no" in sql
    assert "csa.status IN ('planned', 'active', 'completed')" in sql
    assert "ORDER BY csa.assignment_sequence DESC LIMIT 1" in sql
    assert connection.closed is True
