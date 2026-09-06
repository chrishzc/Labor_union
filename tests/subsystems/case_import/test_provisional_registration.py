"""Focused coverage for the shared provisional registration ID owner."""

from __future__ import annotations

import pytest

from domains.case_import.provisional_registration import (
    ProvisionalRegistrationDomainError,
    ProvisionalRegistrationIntent,
    build_provisional_registration_candidate,
)


def _intent(*, id_number: str | None) -> ProvisionalRegistrationIntent:
    return ProvisionalRegistrationIntent(
        line_user_id="U-id-format-smoke",
        name="測試申請人",
        phone="0912345678",
        expected_date="2026-10-01",
        service_days=1,
        address="測試地址",
        gender=None,
        email=None,
        birth_date=None,
        tel=None,
        ext=None,
        city=None,
        zip_code=None,
        id_number=id_number,
        liff_config_revision=None,
        survey_details={},
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" o123456782 ", "O123456782"),
        ("ｏ１２３４５６７８２", "O123456782"),
        (None, None),
        ("   ", None),
    ],
)
def test_shared_candidate_normalizes_nonempty_ids_and_keeps_optional_empty_values(
    value: str | None,
    expected: str | None,
) -> None:
    candidate = build_provisional_registration_candidate(_intent(id_number=value))

    assert candidate.beclass_payload["survey_details"]["身分證字號"] == expected


def test_shared_candidate_does_not_add_checksum_or_second_digit_limits() -> None:
    candidate = build_provisional_registration_candidate(_intent(id_number="O000000000"))

    assert candidate.beclass_payload["survey_details"]["身分證字號"] == "O000000000"


@pytest.mark.parametrize("value", ["O12345678", "O12345678X", "1234567890"])
def test_shared_candidate_rejects_nonempty_ids_outside_database_shape(value: str) -> None:
    with pytest.raises(ProvisionalRegistrationDomainError, match="id_number is invalid"):
        build_provisional_registration_candidate(_intent(id_number=value))
