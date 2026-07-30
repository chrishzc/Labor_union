from datetime import date, datetime

import pytest

from services import multi_caregiver_schedule_read as service


def test_validate_assignment_id_rejects_invalid_inputs():
    invalid_ids = [0, -1, "21", True, None]
    for value in invalid_ids:
        with pytest.raises(ValueError, match="assignment_id must be a positive integer"):
            service._validate_assignment_id(value)

    assert service._validate_assignment_id(21) == 21


def test_validate_case_no_rejects_invalid_inputs_and_trims():
    invalid_case_nos = [None, "", "   ", 115000001]
    for case_no in invalid_case_nos:
        with pytest.raises(ValueError, match="case_no must be a non-empty string"):
            service._validate_case_no(case_no)

    assert service._validate_case_no("  115000001  ") == "115000001"


@pytest.mark.parametrize(
    "value,expected",
    [
        (date(2026, 7, 10), date(2026, 7, 10)),
        (datetime(2026, 7, 10, 7, 30, 0), date(2026, 7, 10)),
        ("2026-07-10", date(2026, 7, 10)),
    ],
)
def test_as_date_accepts_supported_types(value, expected):
    assert service._as_date(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "",
        "2026/07/10",
        "2026-7-10",
        "not-a-date",
        "20260710",
        "2026-W27-1",
        "２０２６-０７-１０",
        "２０26-07-10",
        "2026-０7-10",
        " 2026-07-10",
        "2026-07-10 ",
        "2026-07-10T08:00:00",
        "2026-07-10 08:00:00",
        1,
        1.23,
        None,
    ],
)
def test_as_date_rejects_invalid_types_and_formats(value):
    with pytest.raises(ValueError, match="invalid date value"):
        service._as_date(value)


def test_validate_case_assignment_rejects_non_dict():
    with pytest.raises(ValueError, match="assignment must be a dict"):
        service._validate_case_assignment("not-a-dict", "115000001")


def test_validate_case_assignment_rejects_invalid_ownership_and_status_and_ranges():
    base = {
        "id": 21,
        "case_no": "115000001",
        "staff_id": 8,
        "status": "active",
        "assigned_start_date": date(2026, 6, 1),
        "assigned_end_date": date(2026, 6, 3),
        "planned_hours": 18,
        "actual_hours": 18,
    }

    invalid_rows = [
        ({**base, "id": 0}, "assignment_id must be a positive integer"),
        ({**base, "id": True}, "assignment_id must be a positive integer"),
        ({**base, "staff_id": 0}, "staff_id must be a positive integer"),
        ({**base, "staff_id": True}, "staff_id must be a positive integer"),
        ({**base, "case_no": "WRONG"}, "assignment case_no mismatch"),
        ({**base, "status": "cancelled"}, "cancelled assignment should not be returned"),
        ({**base, "assigned_start_date": None}, "assignment date range is incomplete"),
        ({**base, "assigned_end_date": None}, "assignment date range is incomplete"),
        (
            {**base, "assigned_start_date": date(2026, 6, 10), "assigned_end_date": date(2026, 6, 1)},
            "assignment assigned_start_date cannot be after assigned_end_date",
        ),
    ]

    for row, match in invalid_rows:
        with pytest.raises(ValueError, match=match):
            service._validate_case_assignment(row, "115000001")

    missing_planned_hours = dict(base)
    missing_planned_hours.pop("planned_hours")
    with pytest.raises(ValueError, match="planned_hours is required"):
        service._validate_case_assignment(missing_planned_hours, "115000001")

    missing_actual_hours = dict(base)
    missing_actual_hours.pop("actual_hours")
    with pytest.raises(ValueError, match="actual_hours is required"):
        service._validate_case_assignment(missing_actual_hours, "115000001")


def test_validate_case_assignment_normalizes_dates_and_returns_row(monkeypatch):
    monkeypatch.setattr(
        service,
        "get_connection",
        lambda: (_ for _ in ()).throw(AssertionError("helper should not touch db")),
    )

    row = {
        "id": 21,
        "case_no": "115000001",
        "staff_id": 8,
        "status": "active",
        "assigned_start_date": "2026-06-01",
        "assigned_end_date": datetime(2026, 6, 3, 12, 0),
        "planned_hours": 18,
        "actual_hours": 18,
    }

    normalized = service._validate_case_assignment(row, "115000001")
    assert normalized["assigned_start_date"] == date(2026, 6, 1)
    assert normalized["assigned_end_date"] == date(2026, 6, 3)
