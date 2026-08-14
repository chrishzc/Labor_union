"""
File: test_wp73_dirty_data_characterization.py
Description: 以 synthetic 髒資料鎖定三條歷史匯入 lane 的 validator 與 no-write 缺口。
"""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import pytest

from domains.case_import.client_beclass_validation import validate_client_beclass_row
from domains.case_import.client_import_validation import validate_hcm_row
from domains.case_import.staff_import_validation import validate_staff_row
from scripts.imports import (
    import_client_beclass,
    import_client_hcm,
    import_staff_beclass,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = PROJECT_ROOT / "tests/fixtures/case_import/wp73_dirty_rows_v1.json"
SCENARIO_PATH = (
    PROJECT_ROOT
    / "validation/scenarios/case_import/wp73_phase0_dirty_data_rehearsal_v1.json"
)
VALIDATORS = {
    "hcm": validate_hcm_row,
    "client_beclass": validate_client_beclass_row,
    "staff_beclass": validate_staff_row,
}
IMPORTERS = (
    import_client_hcm,
    import_client_beclass,
    import_staff_beclass,
)
SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"09\d{8}"),
    re.compile(r"\b[A-Z][12]\d{8}\b"),
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _all_text_values(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from _all_text_values(child)
        return
    if isinstance(value, list):
        for child in value:
            yield from _all_text_values(child)
        return
    if isinstance(value, str):
        yield value


def test_dirty_corpus_is_synthetic_and_covers_all_wp73_source_shapes() -> None:
    corpus = _load_json(FIXTURE_PATH)

    assert corpus["synthetic"] is True
    assert corpus["derived_from_real_person_data"] is False
    assert {case["lane"] for case in corpus["cases"]} == {
        "hcm",
        "client_beclass",
        "staff_beclass",
    }


def test_dirty_corpus_contains_no_phone_or_identity_card_shaped_text() -> None:
    corpus = _load_json(FIXTURE_PATH)

    assert all(
        pattern.search(text) is None
        for text in _all_text_values(corpus)
        for pattern in SENSITIVE_VALUE_PATTERNS
    )


@pytest.mark.parametrize(
    "case",
    _load_json(FIXTURE_PATH)["cases"],
    ids=lambda case: case["case_id"],
)
def test_dirty_rows_lock_the_current_validator_characterization(case: dict) -> None:
    actual_errors = VALIDATORS[case["lane"]](case["row"])

    assert sorted(actual_errors) == sorted(case["current_error_fields"])
    assert case["desired_issue_codes"]


def test_phase0_contract_forbids_database_side_effects_during_characterization() -> None:
    scenario = _load_json(SCENARIO_PATH)
    invariant = scenario["no_write_invariant"]

    assert invariant["source_snapshot"] == "read_only"
    assert invariant["candidate_snapshot_before_equals_after"] is True
    assert invariant["database_connections_allowed_during_parser_characterization"] == 0
    assert invariant["commits_allowed_during_parser_characterization"] == 0
    assert invariant["rollbacks_allowed_during_parser_characterization"] == 0


@pytest.mark.xfail(
    strict=True,
    reason="WP73 Phase 0: production importers do not expose true no-write rehearsal yet",
)
@pytest.mark.parametrize("importer", IMPORTERS, ids=lambda module: module.__name__.rsplit(".", 1)[-1])
def test_importers_expose_an_explicit_no_write_mode(importer) -> None:
    parameters = inspect.signature(importer.process_import).parameters

    assert "dry_run" in parameters or "mode" in parameters
