"""Keep retired rest-date mutation routes closed to the legacy writer."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from api.routes import assignment_schedule_rest_dates


@pytest.mark.parametrize(
    ("endpoint", "arguments"),
    (
        (
            assignment_schedule_rest_dates.preview_assignment_leave_resolution_batch_route,
            (None, 1, None),
        ),
        (
            assignment_schedule_rest_dates.apply_assignment_leave_resolution_batch_route,
            (None, 1, None),
        ),
        (assignment_schedule_rest_dates.save_assignment_rest_dates, (None, 1)),
        (
            assignment_schedule_rest_dates.preview_assignment_leave_resolution_route,
            (None, 1, None),
        ),
        (
            assignment_schedule_rest_dates.apply_assignment_leave_resolution_route,
            (None, 1, None),
        ),
    ),
)
def test_retired_rest_date_mutation_route_returns_gone(endpoint, arguments):
    with pytest.raises(HTTPException) as raised:
        endpoint(*arguments)

    assert raised.value.status_code == 410
    assert raised.value.detail["code"] == "legacy_leave_schedule_writer_retired"
