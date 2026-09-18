from datetime import date

import pytest

from infrastructure.mysql.staff_leave_intake_repository import MySqlStaffLeaveIntakeRepository


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.sql = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params):
        self.sql = sql
        self.connection.calls.append((sql, params))

    def fetchone(self):
        return self.connection.request_row

    def fetchall(self):
        return self.connection.target_rows


class _Connection:
    def __init__(self, request_row, target_rows=()):
        self.request_row = request_row
        self.target_rows = target_rows
        self.calls = []

    def cursor(self):
        return _Cursor(self)


def _request_row(*, status="accepted_for_processing", version=3):
    return {
        "id": 17,
        "staff_id": 9,
        "line_user_id": "Ustaff",
        "leave_start_date": date(2026, 9, 20),
        "leave_end_date": date(2026, 9, 22),
        "request_reason": "leave",
        "request_status": status,
        "aggregate_version": version,
        "request_fingerprint": "fp",
    }


def test_coordination_context_projects_current_case_and_customer_recipient():
    connection = _Connection(
        _request_row(),
        (
            {"case_no": "CASE-001", "client_line_user_id": " Uclient "},
            {"case_no": "CASE-002", "client_line_user_id": None},
        ),
    )

    result = MySqlStaffLeaveIntakeRepository(connection).coordination_context(17, 3)

    assert result == {
        "request_id": 17,
        "request_version": 3,
        "leave_start_date": date(2026, 9, 20),
        "leave_end_date": date(2026, 9, 22),
        "targets": [
            {"case_no": "CASE-001", "client_line_user_id": "Uclient"},
            {"case_no": "CASE-002", "client_line_user_id": None},
        ],
    }
    target_sql, target_args = connection.calls[-1]
    assert "case_staff_assignments" in target_sql
    assert "g.effective_generation_id" in target_sql
    assert target_args == (9, date(2026, 9, 22), date(2026, 9, 20))


def test_coordination_context_rejects_stale_leave_version_before_case_projection():
    connection = _Connection(_request_row(version=4))

    with pytest.raises(ValueError, match="leave_request_stale"):
        MySqlStaffLeaveIntakeRepository(connection).coordination_context(17, 3)

    assert len(connection.calls) == 1


def test_coordination_context_requires_union_accepted_leave():
    connection = _Connection(_request_row(status="pending"))

    with pytest.raises(ValueError, match="leave_request_not_accepted"):
        MySqlStaffLeaveIntakeRepository(connection).coordination_context(17, 3)

    assert len(connection.calls) == 1


class _SqlCursor:
    """Execute production SELECTs; only DB-API placeholders/date values differ.

    This exercises relational filtering, not MySQL locking or collation rules.
    No repository method or query result is mocked in the SQL tests below.
    """

    def __init__(self, connection):
        self.cursor = connection.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.cursor.close()
        return False

    def execute(self, sql, params):
        values = tuple(value.isoformat() if isinstance(value, date) else value for value in params)
        self.cursor.execute(sql.replace("%s", "?"), values)

    @staticmethod
    def _row(row):
        if row is None:
            return None
        result = dict(row)
        for key in ("leave_start_date", "leave_end_date"):
            if isinstance(result.get(key), str):
                result[key] = date.fromisoformat(result[key])
        return result

    def fetchone(self):
        return self._row(self.cursor.fetchone())

    def fetchall(self):
        return [self._row(row) for row in self.cursor.fetchall()]


class _SqlConnection:
    def __init__(self, connection):
        self.connection = connection

    def cursor(self):
        return _SqlCursor(self.connection)


@pytest.fixture
def sql_context():
    import sqlite3

    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE scheduling_staff_leave_request_aggregates (
            id INTEGER PRIMARY KEY, staff_id INTEGER, line_user_id TEXT,
            leave_start_date TEXT, leave_end_date TEXT, request_reason TEXT,
            request_status TEXT, aggregate_version INTEGER, request_fingerprint TEXT);
        CREATE TABLE scheduling_aggregates (case_no TEXT PRIMARY KEY, effective_generation_id INTEGER);
        CREATE TABLE case_staff_assignments (
            id INTEGER PRIMARY KEY, case_no TEXT, staff_id INTEGER, generation_id INTEGER,
            status TEXT, assigned_start_date TEXT, assigned_end_date TEXT);
        CREATE TABLE staff_schedule (
            id INTEGER PRIMARY KEY, assignment_id INTEGER, staff_id INTEGER,
            work_date TEXT, is_work_day INTEGER);
        CREATE TABLE orders (case_no TEXT PRIMARY KEY, client_id INTEGER);
        CREATE TABLE clients (id INTEGER PRIMARY KEY, case_no TEXT, line_user_id TEXT);
        CREATE TABLE line_identity_role_bindings (
            line_user_id TEXT, subject_type TEXT, subject_reference TEXT, binding_status TEXT,
            PRIMARY KEY (line_user_id, subject_type));
        CREATE TABLE line_order_group_participants (
            id INTEGER PRIMARY KEY, case_no TEXT, participant_type TEXT,
            invitation_status TEXT, line_user_id TEXT);
        INSERT INTO scheduling_staff_leave_request_aggregates VALUES (
            17,9,'Ustaff','2026-09-20','2026-09-22','leave','accepted_for_processing',3,'fp');
        INSERT INTO scheduling_aggregates VALUES ('CASE-001',20);
        INSERT INTO case_staff_assignments VALUES (
            1,'CASE-001',9,20,'active','2026-09-19','2026-09-25');
        INSERT INTO staff_schedule VALUES (1,1,9,'2026-09-20',1);
        INSERT INTO orders VALUES ('CASE-001',41);
        INSERT INTO clients VALUES (41,'CASE-001','Uclient');
        INSERT INTO line_identity_role_bindings VALUES ('Uclient','customer','41','bound');
    """)
    db.commit()
    try:
        yield MySqlStaffLeaveIntakeRepository(_SqlConnection(db)), db
    finally:
        db.close()


def _targets(sql_context):
    return sql_context[0].coordination_context(17, 3)["targets"]


def test_sql_current_service_day_and_customer_binding_are_read_only(sql_context):
    repository, db = sql_context
    db.execute("PRAGMA query_only=ON")
    result = repository.coordination_context(17, 3)
    assert result["leave_start_date"] == date(2026, 9, 20)
    assert result["targets"] == [{"case_no": "CASE-001", "client_line_user_id": "Uclient"}]
    assert not db.in_transaction


def test_sql_assignment_range_does_not_make_a_rest_day_a_service_day(sql_context):
    sql_context[1].execute("UPDATE staff_schedule SET is_work_day=0")
    assert _targets(sql_context) == []


def test_sql_no_official_service_day_does_not_create_a_coordination_target(sql_context):
    sql_context[1].execute("DELETE FROM staff_schedule")
    assert _targets(sql_context) == []


@pytest.mark.parametrize("work_date", ["2026-09-19", "2026-09-23"])
def test_sql_official_day_outside_leave_window_is_not_affected(sql_context, work_date):
    sql_context[1].execute("UPDATE staff_schedule SET work_date=?", (work_date,))
    assert _targets(sql_context) == []


@pytest.mark.parametrize("work_date", ["2026-09-20", "2026-09-22"])
def test_sql_leave_window_includes_both_boundary_days(sql_context, work_date):
    sql_context[1].execute("UPDATE staff_schedule SET work_date=?", (work_date,))
    assert len(_targets(sql_context)) == 1


def test_sql_wrong_staff_daily_row_is_not_used(sql_context):
    sql_context[1].execute("UPDATE staff_schedule SET staff_id=10")
    assert _targets(sql_context) == []


def test_sql_unlinked_daily_row_is_not_used(sql_context):
    sql_context[1].execute("UPDATE staff_schedule SET assignment_id=NULL")
    assert _targets(sql_context) == []


def test_sql_previous_generation_is_not_used(sql_context):
    sql_context[1].execute("UPDATE scheduling_aggregates SET effective_generation_id=21")
    assert _targets(sql_context) == []


@pytest.mark.parametrize("status", ["cancelled", "replaced"])
def test_sql_inactive_assignment_is_not_used(sql_context, status):
    sql_context[1].execute("UPDATE case_staff_assignments SET status=?", (status,))
    assert _targets(sql_context) == []


def test_sql_multiple_affected_days_only_project_one_case(sql_context):
    sql_context[1].execute("INSERT INTO staff_schedule VALUES (2,1,9,'2026-09-22',1)")
    assert _targets(sql_context) == [{"case_no": "CASE-001", "client_line_user_id": "Uclient"}]


def test_sql_stale_joined_group_member_does_not_override_current_binding(sql_context):
    db = sql_context[1]
    db.execute("INSERT INTO line_order_group_participants VALUES (1,'CASE-001','customer','joined','Uold')")
    assert _targets(sql_context) == [{"case_no": "CASE-001", "client_line_user_id": "Uclient"}]


def test_sql_recipient_comes_from_order_client_id_not_legacy_case_lookup(sql_context):
    db = sql_context[1]
    db.execute("UPDATE orders SET client_id=42")
    db.execute("INSERT INTO clients VALUES (42,'OTHER-REFERENCE','Ucorrect')")
    db.execute("INSERT INTO line_identity_role_bindings VALUES ('Ucorrect','customer','42','bound')")
    assert _targets(sql_context) == [{"case_no": "CASE-001", "client_line_user_id": "Ucorrect"}]


@pytest.mark.parametrize("status", ["pending_review", "revocation_pending", "revoked"])
def test_sql_non_bound_recipient_remains_missing_despite_legacy_data(sql_context, status):
    sql_context[1].execute("UPDATE line_identity_role_bindings SET binding_status=?", (status,))
    assert _targets(sql_context) == [{"case_no": "CASE-001", "client_line_user_id": None}]


def test_sql_missing_binding_does_not_hide_affected_case_or_restore_legacy_recipient(sql_context):
    sql_context[1].execute("DELETE FROM line_identity_role_bindings")
    assert _targets(sql_context) == [{"case_no": "CASE-001", "client_line_user_id": None}]


@pytest.mark.parametrize("role", ["staff", "admin"])
def test_sql_non_customer_binding_does_not_authorize_recipient(sql_context, role):
    sql_context[1].execute("UPDATE line_identity_role_bindings SET subject_type=?", (role,))
    assert _targets(sql_context) == [{"case_no": "CASE-001", "client_line_user_id": None}]


def test_sql_rebinding_uses_only_the_new_current_customer_binding(sql_context):
    db = sql_context[1]
    db.execute("UPDATE line_identity_role_bindings SET binding_status='revoked'")
    db.execute("INSERT INTO line_identity_role_bindings VALUES ('Unew','customer','41','bound')")
    assert _targets(sql_context) == [{"case_no": "CASE-001", "client_line_user_id": "Unew"}]
