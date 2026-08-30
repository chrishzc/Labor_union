from datetime import date, datetime

from subsystems.scheduling import matching_communication_workflow as service


class _Cursor:
    def __init__(self, *, existing_events=None):
        self.calls = []
        self._result = None
        self.rowcount = 1
        self.lastrowid = 100
        self.closed = 0
        self.existing_events = existing_events or []

    def execute(self, sql, params=()):
        self.calls.append((sql, tuple(params)))
        compact = " ".join(sql.split()).lower()
        self._result = None
        self.rowcount = 1
        if compact.startswith("select p.id, p.case_no"):
            self._result = {
                "id": 7,
                "case_no": "CASE-1",
                "version": 1,
                "status": "proposed",
                "is_active": 1,
                "order_status": "洽談中",
                "client_line_user_id": "U-client",
            }
        elif compact.startswith("select id from caregiver_matching_plans"):
            self._result = {"id": 7}
        elif compact.startswith("select s.id as segment_id"):
            self._result = [
                {
                    "segment_id": 71,
                    "segment_order": 1,
                    "staff_id": 101,
                    "assigned_start_date": date(2026, 8, 1),
                    "assigned_end_date": date(2026, 8, 10),
                    "staff_name": "A",
                    "staff_line_user_id": "U-a",
                },
                {
                    "segment_id": 72,
                    "segment_order": 2,
                    "staff_id": 102,
                    "assigned_start_date": date(2026, 8, 11),
                    "assigned_end_date": date(2026, 8, 20),
                    "staff_name": "B",
                    "staff_line_user_id": "U-b",
                },
            ]
        elif compact.startswith("select id, segment_id, event_type"):
            self._result = self.existing_events
        elif compact.startswith("select id, event_key, plan_id"):
            self._result = []
        elif compact.startswith("select id, plan_id, segment_id, event_type"):
            self._result = None
        elif compact.startswith("select id as lock_id"):
            self._result = {
                "lock_id": 77,
                "plan_id": 7,
                "status": "active",
                "created_by": "admin",
                "created_at": datetime(2026, 7, 3),
            }
        elif compact.startswith("select contracted_amount_ntd as deposit_receivable"):
            self._result = {
                "deposit_receivable": 1000,
                "deposit_received": 1000,
                "deposit_received_at": date(2026, 7, 4),
            }
        elif compact.startswith("select p.status, p.is_active"):
            self._result = {
                "status": "proposed",
                "is_active": 1,
                "order_status": "洽談中",
            }
        elif compact.startswith("insert into caregiver_matching_plan_events"):
            self.lastrowid += 1

    def fetchone(self):
        return self._result

    def fetchall(self):
        if self._result is None:
            return []
        return self._result if isinstance(self._result, list) else [self._result]

    def close(self):
        self.closed += 1


class _Connection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.commits = 0
        self.rollbacks = 0
        self.closed = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed += 1


def test_contact_state_derives_latest_per_segment_willingness_and_send_history(
    monkeypatch,
):
    events = [
        {
            "id": 1,
            "segment_id": 71,
            "event_type": "info_1_sent",
            "event_key": "i1",
            "actor": "admin",
            "payload": '{"delivery_status":"queued"}',
            "occurred_at": datetime(2026, 7, 1),
        },
        {
            "id": 2,
            "segment_id": 71,
            "event_type": "willingness_changed",
            "event_key": "w1",
            "actor": "admin",
            "payload": '{"willingness":"willing"}',
            "occurred_at": datetime(2026, 7, 2),
        },
        {
            "id": 3,
            "segment_id": 72,
            "event_type": "willingness_changed",
            "event_key": "w2",
            "actor": "admin",
            "payload": '{"willingness":"pending"}',
            "occurred_at": datetime(2026, 7, 2),
        },
    ]
    cursor = _Cursor(existing_events=events)
    monkeypatch.setattr(service, "get_connection", lambda: _Connection(cursor))

    state = service.get_matching_plan_contact_state("CASE-1", 7)

    assert state["segments"][0]["info_1_sent"] is True
    assert state["segments"][0]["willingness"] == "willing"
    assert state["segments"][1]["willingness"] == "pending"
    assert state["all_willing"] is False


def test_active_matching_plan_state_reloads_lock_and_deposit(monkeypatch):
    cursor = _Cursor()
    monkeypatch.setattr(service, "get_connection", lambda: _Connection(cursor))

    state = service.get_active_matching_plan_state("CASE-1")

    assert state["plan"]["id"] == 7
    assert state["availability_lock"]["lock_id"] == 77
    assert state["deposit"]["deposit_received"] == 1000
    assert [segment["segment_id"] for segment in state["segments"]] == [71, 72]
    assert not any("client_payments" in sql for sql, _ in cursor.calls)
