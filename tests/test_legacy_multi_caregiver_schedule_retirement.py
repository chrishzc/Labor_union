"""Retired scheduling endpoints remain mounted only to return typed 410 responses."""

from datetime import date

import pytest
from fastapi import HTTPException

from api.routes import multi_caregiver_schedule


def test_retired_schedule_generation_route_returns_the_canonical_replacement():
    with pytest.raises(HTTPException) as raised:
        multi_caregiver_schedule.generate_assignment_schedule(1)

    assert raised.value.status_code == 410
    assert raised.value.detail["code"] == "legacy_assignment_schedule_writer_retired"


def test_retired_schedule_adjustment_route_returns_the_canonical_replacement():
    with pytest.raises(HTTPException) as raised:
        multi_caregiver_schedule.adjust_assignment_schedule(None, 1, date(2026, 8, 9))

    assert raised.value.status_code == 410
    assert raised.value.detail["replacement"].endswith("/assignment-plan/preview")
