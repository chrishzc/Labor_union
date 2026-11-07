"""Pure text checks for candidate rendering; never execute project SQL."""
from copy import deepcopy
from pathlib import Path
import re

import pytest

from scripts.build_validation_schema_release import (
    _source_section, _trim_normal_sql_line_tails, build_release_text,
    verify_release, write_release,
)
from scripts.sql_statements import split_sql
from scripts.verify_validation_schema_manifest import (
    BOOTSTRAP_PREFIX_SELECTION_V1, TRIM_NORMAL_SQL_LINE_TAILS_V1,
    load_manifest, selected_schema_parts, verify_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
STAFF_MANIFEST = ROOT / "db/cutover_releases/labor_union_validation_schema_staff_payout_payment_sources_v1.json"


def _tokens(text):
    # The original splitter preserves quoted SQL and delimiter semantics. Keep
    # quoted tokens exact while ignoring whitespace only between SQL tokens.
    token = r"'(?:\\.|''|[^'\\])*'|\"(?:\\.|\"\"|[^\"\\])*\"|`(?:\\.|``|[^`\\])*`|[^\s'\"`]+"
    return tuple(tuple(re.findall(token, statement, re.S)) for statement in split_sql(text))


@pytest.mark.parametrize("protected", [
    "'first  \nsecond'", '"first\t \nsecond"', "`first  \nsecond`",
    "'first''quoted  \nsecond'", '"first""quoted\t \nsecond"', "`first``quoted  \nsecond`",
    "'escaped\\'quote  \nsecond'", '"escaped\\"quote  \nsecond"', "'slash\\\\  \nsecond'",
    "-- comment  \t\n", "# comment  \t\n", "/* block  \t\ncomment */",
    "/*!80000 executable  \t\ncomment */", "/*+ hint  \t\ncomment */",
])
def test_only_normal_ascii_line_tails_change(protected):
    text = "SELECT 1; \t\r\n" + protected + "\nSELECT 2;\t \n"
    expected = "SELECT 1;\r\n" + protected + "\nSELECT 2;\n"
    assert _trim_normal_sql_line_tails(text) == expected
    assert _trim_normal_sql_line_tails(protected) == protected
    assert _tokens(text) == _tokens(expected)


def test_delimiters_non_ascii_and_legacy_section_bytes_are_preserved():
    text = "DELIMITER $$ \t\nCREATE PROCEDURE p() BEGIN SELECT 'a;  \nb'; END$$ \t\nDELIMITER ; \n"
    expected = "DELIMITER $$\nCREATE PROCEDURE p() BEGIN SELECT 'a;  \nb'; END$$\nDELIMITER ;\n"
    assert _trim_normal_sql_line_tails(text) == expected
    assert split_sql(text) == split_sql(expected)
    assert _trim_normal_sql_line_tails("SELECT 1;\u00a0 \t\n") == "SELECT 1;\u00a0\n"
    assert _trim_normal_sql_line_tails("SELECT 1--2;  \n") == "SELECT 1--2;\n"
    for source in (text, "SELECT 'quote  \nvalue'; \t\n", "-- old EOF rule  \t\n"):
        assert _source_section("source.sql", source) == (
            "-- BEGIN SOURCE: source.sql\n" + source.rstrip() + "\n-- END SOURCE: source.sql\n"
        )


def test_both_candidate_manifests_rebuild_with_only_86_normal_line_changes(tmp_path):
    for manifest in (load_manifest(), load_manifest(STAFF_MANIFEST)):
        assert verify_manifest(manifest) == []
        assert manifest["full_release"]["source_line_whitespace"] == TRIM_NORMAL_SQL_LINE_TAILS_V1
        legacy = deepcopy(manifest)
        legacy["full_release"].pop("source_line_whitespace")
        original = build_release_text(legacy)
        current = build_release_text(manifest)
        assert sum(line.rstrip(" \t") != line for line in original.splitlines()) == 86
        assert all(line.rstrip(" \t") == line for line in current.splitlines())
        assert _trim_normal_sql_line_tails(original) == current
        assert _tokens(original) == _tokens(current)
        assert verify_release(manifest) == []
        target = tmp_path / Path(manifest["full_release"]["path"]).name
        assert write_release(manifest, target) == target
        assert target.read_text() == current


@pytest.mark.parametrize("change, error", [
    ("missing_terminal", "prefix terminal"),
    ("inactive_terminal", "prefix terminal"),
    ("beyond_bound", "schema part count"),
    ("wrong_count", "schema part count"),
    ("wrong_order_hash", "ordered schema part digest"),
    ("wrong_assembly_hash", "schema assembly digest"),
    ("unknown_selection", "unsupported schema part selection"),
    ("unknown_whitespace", "unsupported full release source whitespace"),
])
def test_candidate_prefix_and_policy_fail_closed(change, error):
    manifest = load_manifest(STAFF_MANIFEST)
    assert manifest["schema_parts"]["selection"] == BOOTSTRAP_PREFIX_SELECTION_V1
    assert selected_schema_parts(manifest)[-1].name == "1070_staff_payout_payment_sources.sql"
    if change == "missing_terminal":
        manifest["schema_parts"].pop("terminal_artifact")
    elif change == "inactive_terminal":
        manifest["schema_parts"]["terminal_artifact"] = "153_retire_empty_legacy_field_inventory.sql"
    elif change == "beyond_bound":
        manifest["schema_parts"]["terminal_artifact"] = "1071_controlled_signed_staff_agreement.sql"
    elif change == "wrong_count":
        manifest["schema_parts"]["expected_count"] += 1
    elif change == "wrong_order_hash":
        manifest["schema_parts"]["ordered_digest_sha256"] = "0" * 64
    elif change == "wrong_assembly_hash":
        manifest["schema_assembly"]["sha256"] = "0" * 64
    elif change == "unknown_selection":
        manifest["schema_parts"]["selection"] = "arbitrary-prefix"
    else:
        manifest["full_release"]["source_line_whitespace"] = "rstrip-everything"
    assert any(error in item for item in verify_manifest(manifest))
    with pytest.raises(RuntimeError, match=error):
        build_release_text(manifest)
