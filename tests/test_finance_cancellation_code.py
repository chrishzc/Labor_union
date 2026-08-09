from copy import deepcopy

import pytest

from domains.finance_import.cancellation_code import resolve_finance_cancellation_code


VALID_CANONICAL = "99781699123456"
VALID_FALLBACK = "99781699654321"


def test_legacy_reads_only_canonical_cancellation_code():
    row = {
        "format_id": "legacy",
        "cancellation_code": VALID_CANONICAL,
        "bank_references": {"銷帳編號": VALID_FALLBACK},
    }

    assert resolve_finance_cancellation_code(row) == {
        "cancellation_code": VALID_CANONICAL,
        "source": "canonical",
    }


@pytest.mark.parametrize(
    "other_field",
    ["bank_references", "counterparty_name", "memo", "correction_note", "match_field"],
)
def test_legacy_never_falls_back_to_other_fields(other_field):
    row = {
        "format_id": "legacy",
        "cancellation_code": None,
        "bank_references": {},
        other_field: (
            {"銷帳編號": VALID_FALLBACK}
            if other_field == "bank_references"
            else VALID_FALLBACK
        ),
    }

    assert resolve_finance_cancellation_code(row) == {
        "cancellation_code": None,
        "source": "none",
    }


def test_sinopac_prefers_valid_canonical_over_raw_fallback():
    row = {
        "format_id": "sinopac",
        "cancellation_code": VALID_CANONICAL,
        "bank_references": {"銷帳編號": VALID_FALLBACK},
    }

    assert resolve_finance_cancellation_code(row) == {
        "cancellation_code": VALID_CANONICAL,
        "source": "canonical",
    }


@pytest.mark.parametrize("canonical", [None, "", "invalid", "9978169912345"])
def test_sinopac_uses_exact_raw_fallback_when_canonical_is_missing_or_invalid(
    canonical,
):
    row = {
        "format_id": "sinopac",
        "cancellation_code": canonical,
        "bank_references": {"銷帳編號": VALID_FALLBACK},
    }

    assert resolve_finance_cancellation_code(row) == {
        "cancellation_code": VALID_FALLBACK,
        "source": "sinopac_raw_fallback",
    }


@pytest.mark.parametrize(
    "invalid_value",
    [
        "9978169912345",
        "997816991234567",
        " 99781699123456",
        "99781699123456 ",
        "prefix99781699123456",
        "99781699ABCDEF",
        99781699123456,
    ],
)
def test_values_must_be_an_exact_complete_virtual_account(invalid_value):
    row = {
        "format_id": "sinopac",
        "cancellation_code": invalid_value,
        "bank_references": {"銷帳編號": invalid_value},
    }

    assert resolve_finance_cancellation_code(row) == {
        "cancellation_code": None,
        "source": "none",
    }


def test_projection_does_not_mutate_row_or_fingerprint_fields():
    row = {
        "format_id": "sinopac",
        "cancellation_code": None,
        "bank_references": {"銷帳編號": VALID_FALLBACK},
        "raw_payload": {"銷帳編號": VALID_FALLBACK},
        "dedup_fingerprint": "existing-fingerprint",
    }
    before = deepcopy(row)

    result = resolve_finance_cancellation_code(row)

    assert result == {
        "cancellation_code": VALID_FALLBACK,
        "source": "sinopac_raw_fallback",
    }
    assert row == before
