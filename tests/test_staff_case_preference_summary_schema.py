import pytest
from pydantic import ValidationError

from api.schemas.staff_case_preference_summary import StaffCasePreferenceSummaryView


def topic(status="not_recorded", detail=None, values=None):
    return {
        "values": values or [],
        "other_detail": detail,
        "other_detail_status": status,
    }


def test_http_schema_is_strict_and_preserves_transport_source_not_ready():
    payload = {
        "staff_id": 11,
        "service_regions": topic("ready", "新竹市", ["北區"]),
        "service_periods": topic(),
        "rest_schedule": topic(),
        "baby_counts": topic(),
        "holiday_availability": topic(),
        "transportation": topic("source_not_ready", None, ["機車"]),
    }
    model = StaffCasePreferenceSummaryView.model_validate(payload)
    assert model.transportation.other_detail_status == "source_not_ready"
    assert model.transportation.other_detail is None

    with pytest.raises(ValidationError):
        StaffCasePreferenceSummaryView.model_validate({**payload, "raw_json": {}})
