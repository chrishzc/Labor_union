from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from api.schemas.line_identity import (
    ProvisionalRegistrationPreviewRequest,
    ProvisionalRegistrationRequest,
)


REQUEST_MODELS = (ProvisionalRegistrationPreviewRequest, ProvisionalRegistrationRequest)


def _payload(request_model, **overrides):
    payload = {
        "name": "王小明",
        "phone": "0912345678",
        "expected_date": (date.today() + timedelta(days=800)).isoformat(),
        "service_days": 61,
        "address": "台北市測試路 1 號",
    }
    if request_model is ProvisionalRegistrationRequest:
        payload.update(
            expected_binding_version=0,
            preview_fingerprint="a" * 64,
        )
    payload.update(overrides)
    return payload


@pytest.mark.parametrize("request_model", REQUEST_MODELS)
def test_canonical_registration_accepts_confirmed_valid_formats_without_business_limits(request_model):
    request_model(
        **_payload(request_model),
        id_number="A123456789",
        email="user@example.com",
        birth_date="2000-01-02",
    )


@pytest.mark.parametrize("request_model", REQUEST_MODELS)
@pytest.mark.parametrize("blank", [None, ""])
def test_canonical_registration_accepts_blank_optional_fixed_format_fields(request_model, blank):
    request_model(
        **_payload(request_model),
        id_number=blank,
        email=blank,
        birth_date=blank,
    )


@pytest.mark.parametrize("request_model", REQUEST_MODELS)
@pytest.mark.parametrize("id_number", ["A12345678", "A123456788"])
def test_canonical_registration_rejects_invalid_taiwan_id(request_model, id_number):
    with pytest.raises(ValidationError):
        request_model(**_payload(request_model), id_number=id_number)


@pytest.mark.parametrize("request_model", REQUEST_MODELS)
def test_canonical_registration_rejects_invalid_email(request_model):
    with pytest.raises(ValidationError):
        request_model(**_payload(request_model), email="not-an-email")


@pytest.mark.parametrize("request_model", REQUEST_MODELS)
@pytest.mark.parametrize(
    "birth_date",
    ["2026-02-30", (date.today() + timedelta(days=1)).isoformat()],
)
def test_canonical_registration_rejects_invalid_or_future_birth_date(request_model, birth_date):
    with pytest.raises(ValidationError):
        request_model(**_payload(request_model), birth_date=birth_date)


@pytest.mark.parametrize("request_model", REQUEST_MODELS)
def test_canonical_registration_rejects_invalid_expected_date(request_model):
    with pytest.raises(ValidationError):
        request_model(**_payload(request_model, expected_date="2026-02-30"))


@pytest.mark.parametrize("request_model", REQUEST_MODELS)
def test_canonical_registration_keeps_service_days_positive_only(request_model):
    request_model(**_payload(request_model, service_days=61))

    with pytest.raises(ValidationError):
        request_model(**_payload(request_model, service_days=0))
