"""Issue #337 HTTP input contract for an explicit empty service-time tuple."""

import pytest
from pydantic import ValidationError

from api.routes.order_terms import OrderTermsInput


def _payload(service_time):
    return {
        "planned_start_date": "2026-10-02",
        "service_days": 5,
        "service_hours_per_day": 8,
        "requires_cooking": None,
        "floor_fee_ntd": 0,
        "service_time": service_time,
    }


def test_empty_time_survives_http_model_and_domain_conversion():
    empty = {"start_time": None, "end_time": None, "end_day_offset": None}

    model = OrderTermsInput.model_validate(_payload(empty))

    assert model.to_domain().canonical_payload() == _payload(empty)


@pytest.mark.parametrize(
    "values",
    [
        {"start_time": "09:00:00", "end_time": "13:30:00", "end_day_offset": 0},
        {"start_time": "21:00:00", "end_time": "05:00:00", "end_day_offset": 1},
    ],
)
def test_complete_time_survives_http_model_and_domain_conversion(values):
    payload = _payload(values)
    payload["service_hours_per_day"] = 4.5

    assert OrderTermsInput.model_validate(payload).to_domain().canonical_payload() == payload


@pytest.mark.parametrize(
    "values",
    [
        {"start_time": None, "end_time": "17:00:00", "end_day_offset": 0},
        {"start_time": "09:00:00", "end_time": None, "end_day_offset": 0},
        {"start_time": "09:00:00", "end_time": "17:00:00", "end_day_offset": None},
        {"start_time": None, "end_time": None, "end_day_offset": 0},
    ],
)
def test_partial_time_is_rejected_before_workflow(values):
    with pytest.raises(ValueError, match="all empty or all present"):
        OrderTermsInput.model_validate(_payload(values)).to_domain()


@pytest.mark.parametrize("missing", ["start_time", "end_time", "end_day_offset"])
def test_nullable_fields_remain_explicit_not_omitted(missing):
    empty = {"start_time": None, "end_time": None, "end_day_offset": None}
    del empty[missing]

    with pytest.raises(ValidationError):
        OrderTermsInput.model_validate(_payload(empty))
