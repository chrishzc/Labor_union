from datetime import date

import pytest

from domains.case_import.beclass_import_review import BeClassImportSourceKind
from subsystems.case_import.beclass_review_intake import (
    _canonical_value,
    _source_event_identity,
    masked_review_identifier,
)


def test_masks_the_stable_identifier_without_exposing_it() -> None:
    assert masked_review_identifier(BeClassImportSourceKind.CLIENT, "ABC1234", None) == "client-***-1234"


def test_masks_a_missing_identifier_with_a_fixed_safe_value() -> None:
    assert masked_review_identifier(BeClassImportSourceKind.CLIENT, None, None) == "client-***-none"


def test_builds_a_durable_lowercase_digest_identity() -> None:
    digest = "a" * 64
    assert _source_event_identity(digest, 7) == f"beclass-workbook:{digest}:row:7"


@pytest.mark.parametrize("digest", ["A" * 64, "a" * 63, "g" * 64])
def test_rejects_noncanonical_digest(digest: str) -> None:
    with pytest.raises(ValueError, match="lowercase SHA-256"):
        _source_event_identity(digest, 1)


def test_canonicalizes_dates_integral_floats_and_nan() -> None:
    assert _canonical_value(date(2026, 8, 3)) == "2026-08-03"
    assert _canonical_value(3.0) == 3
    assert _canonical_value(float("nan")) is None
