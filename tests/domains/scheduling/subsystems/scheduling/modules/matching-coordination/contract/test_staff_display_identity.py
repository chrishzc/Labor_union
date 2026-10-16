"""Candidate identity labels borrow the current Staff-owned union number."""
from datetime import date, datetime

import pytest

from api.schemas.candidate_contact_pool import CandidateContactPoolView
from subsystems.scheduling.candidate_contact_pool_workflow import query_pool
from infrastructure.mysql.matching_notification_repository import _segment_contact
from api.routes.matches import _segment_state_data
from api.schemas.matches import ContactMatchingSegmentView


@pytest.mark.parametrize("union_no", ["A002", "0007", None])
def test_candidate_pool_query_preserves_union_number_without_writes(union_no):
    class Cursor:
        def __init__(self):
            self.rows = []
            self.statements = []

        def execute(self, sql, params):
            assert sql.startswith("SELECT ")
            self.statements.append(sql)
            if "FROM caregiver_candidate_contact_pools" in sql:
                self.rows = [{"id": 1, "case_no": "DISPLAY-1"}]
            elif "FROM caregiver_candidate_contact_entries" in sql:
                assert "s.union_no AS staff_union_no" in sql
                self.rows = [{"id": 5, "staff_id": 17, "staff_name": "測試月嫂", "staff_union_no": union_no,
                              "service_start_date": date(2026, 11, 1), "service_end_date": date(2026, 11, 2),
                              "status": "active", "created_at": datetime(2026, 10, 16)}]
            else:
                self.rows = []

        def fetchone(self):
            return self.rows[0]

        def fetchall(self):
            return self.rows

        def close(self):
            pass

    class Connection:
        def __init__(self):
            self.reader = Cursor()

        def cursor(self):
            return self.reader

    connection = Connection()
    state = query_pool("DISPLAY-1", connection=connection)
    view = CandidateContactPoolView.model_validate(state).model_dump()
    assert view["candidates"][0]["staff_id"] == 17
    assert view["candidates"][0]["staff_name"] == "測試月嫂"
    assert view["candidates"][0]["staff_union_no"] == union_no
    assert len(connection.reader.statements) == 3


def test_existing_recommendation_projects_union_number_in_its_current_query():
    segment = _segment_contact({
        "segment_id": 5, "segment_order": 1, "staff_id": 17, "staff_name": "測試月嫂",
        "staff_union_no": "0007", "assigned_start_date": "2026-11-01", "assigned_end_date": "2026-11-02",
    }, {}, {})
    view = ContactMatchingSegmentView.model_validate(_segment_state_data(segment))
    assert view.staff_union_no == "0007"
    assert view.staff_name == "測試月嫂"
    assert view.staff_id == 17


def test_weekly_preview_keeps_exact_staff_identity_without_changing_delivery_rows():
    from infrastructure.mysql.matching_notification_repository import _proposed_weekly_rows

    segments = [
        {"segment_id": 5, "staff_id": 17, "staff_name": "同名月嫂", "client_name": "測試客戶", "case_no": "DISPLAY-1", "assigned_start_date": "2026-11-02", "assigned_end_date": "2026-11-03", "service_hours_per_day": 8},
        {"segment_id": 6, "staff_id": 18, "staff_name": "同名月嫂", "client_name": "測試客戶", "case_no": "DISPLAY-1", "assigned_start_date": "2026-11-04", "assigned_end_date": "2026-11-05", "service_hours_per_day": 8},
    ]
    delivery = _proposed_weekly_rows(segments)
    preview = _proposed_weekly_rows(segments, include_staff_identity=True)
    assert [row["staff_id"] for row in preview] == [17, 18]
    assert tuple({key: value for key, value in row.items() if key != "staff_id"} for row in preview) == delivery
    assert all("staff_id" not in row for row in delivery)
