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


def test_sinopac_uses_original_bank_reference_even_when_canonical_differs():
    row = {
        "format_id": "sinopac",
        "cancellation_code": VALID_CANONICAL,
        "bank_references": {"銷帳編號": VALID_FALLBACK},
    }

    assert resolve_finance_cancellation_code(row) == {
        "cancellation_code": VALID_FALLBACK,
        "source": "sinopac_bank_reference",
    }


@pytest.mark.parametrize("canonical", [None, "", "invalid", "9978169912345"])
def test_sinopac_original_bank_reference_does_not_depend_on_canonical(
    canonical,
):
    row = {
        "format_id": "sinopac",
        "cancellation_code": canonical,
        "bank_references": {"銷帳編號": VALID_FALLBACK},
    }

    assert resolve_finance_cancellation_code(row) == {
        "cancellation_code": VALID_FALLBACK,
        "source": "sinopac_bank_reference",
    }


@pytest.mark.parametrize(
    "value,expected",
    [
        ("9978169912345", None),
        ("997816991234567", None),
        (" 99781699123456", VALID_CANONICAL),
        ("99781699123456 ", VALID_CANONICAL),
        ("prefix99781699123456", None),
        ("99781699ABCDEF", None),
        (99781699123456, None),
    ],
)
def test_account_projection_normalizes_outer_space_but_never_repairs_malformed_values(value, expected):
    row = {
        "format_id": "sinopac",
        "cancellation_code": value,
        "bank_references": {"銷帳編號": value},
    }

    assert resolve_finance_cancellation_code(row) == {
        "cancellation_code": expected,
        "source": "sinopac_bank_reference" if expected is not None else "none",
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
        "source": "sinopac_bank_reference",
    }
    assert row == before
