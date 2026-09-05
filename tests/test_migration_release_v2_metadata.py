"""Immutable metadata checks for the post-foundation additive release."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RELEASE_DIRECTORY = PROJECT_ROOT / "db" / "migration_releases"
V1_MANIFEST = RELEASE_DIRECTORY / "labor_union_2026_08_02_v1.json"
V2_MANIFEST = RELEASE_DIRECTORY / "labor_union_2026_08_08_v2.json"
V2_DESCRIPTORS = RELEASE_DIRECTORY / "labor_union_2026_08_08_v2.descriptors.json"
V1_MANIFEST_SHA256 = "6cc2bde9c7be442f8edb04b207be2543d2e60e874810202daa00475b50394815"
V2_ARTIFACT_NAMES = tuple(
    f"{number}_{suffix}.sql"
    for number, suffix in (
        (137, "background_jobs"),
        (138, "client_subsidy_advance_settlement"),
        (139, "finance_import_historical_reprocess"),
        (140, "client_refund_return"),
        (141, "durable_background_job_queue"),
        (142, "client_deposit_reversal"),
        (143, "client_refund_return_review"),
        (144, "order_auto_completion_workflow"),
    )
)


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _release_artifacts(manifest: dict[str, object]) -> list[dict[str, object]]:
    return list(manifest["artifacts"])


def _sql_created_tables(sql: str) -> set[str]:
    return set(re.findall(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?([A-Za-z0-9_]+)`?",
        sql,
        flags=re.IGNORECASE,
    ))


def _sql_altered_tables(sql: str) -> set[str]:
    return set(re.findall(
        r"ALTER\s+TABLE\s+`?([A-Za-z0-9_]+)`?",
        sql,
        flags=re.IGNORECASE,
    ))


def _sql_trigger_names(sql: str) -> set[str]:
    return set(re.findall(
        r"CREATE\s+TRIGGER\s+`?([A-Za-z0-9_]+)`?",
        sql,
        flags=re.IGNORECASE,
    ))


def _parenthesized_content(text: str, opening_index: int) -> str:
    depth = 0
    for index in range(opening_index, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return text[opening_index + 1:index]
    raise AssertionError("unclosed SQL parenthesis")


def _sql_created_columns(sql: str, table: str) -> set[str]:
    match = re.search(
        rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?{re.escape(table)}`?\s*\(",
        sql,
        flags=re.IGNORECASE,
    )
    assert match is not None, table
    body = _parenthesized_content(sql, match.end() - 1)
    candidates = re.findall(
        r"^\s*`?([A-Za-z0-9_]+)`?\s+", body, re.MULTILINE
    )
    return set(candidates).difference({
        "AND", "CHECK", "CONSTRAINT", "FOREIGN", "INDEX", "KEY", "ON",
        "PRIMARY", "REFERENCES", "UNIQUE",
    })


def _sql_altered_columns(sql: str) -> set[str]:
    return set(re.findall(
        r"(?:ADD|MODIFY)\s+COLUMN\s+`?([A-Za-z0-9_]+)`?",
        sql,
        flags=re.IGNORECASE,
    ))


def test_historical_v1_manifest_is_byte_stable() -> None:
    manifest = _load_json(V1_MANIFEST)

    assert _sha256(V1_MANIFEST) == V1_MANIFEST_SHA256
    descriptor = manifest["descriptor_artifact"]
    descriptor_path = PROJECT_ROOT / descriptor["relative_path"]
    assert _sha256(descriptor_path) == descriptor["sha256"]


def test_v2_release_has_live_hashes_and_complete_additive_coverage() -> None:
    manifest = _load_json(V2_MANIFEST)
    artifacts = _release_artifacts(manifest)

    assert manifest["release_id"] == "labor-union-2026-08-08-v2"
    assert manifest["predecessor_release_id"] == "labor-union-2026-08-02-v1"
    assert tuple(artifact["name"] for artifact in artifacts) == V2_ARTIFACT_NAMES
    assert all(artifact["data_effect"] == "schema_only" for artifact in artifacts)
    for artifact in artifacts:
        artifact_path = PROJECT_ROOT / artifact["relative_path"]
        assert artifact_path.name == artifact["name"]
        assert _sha256(artifact_path) == artifact["sha256"]

    descriptor = manifest["descriptor_artifact"]
    assert descriptor["name"].startswith("labor_union_2026_08_08_v2.")
    assert _sha256(PROJECT_ROOT / descriptor["relative_path"]) == descriptor["sha256"]


def test_v2_dependencies_resolve_against_v1_or_prior_v2_artifacts() -> None:
    v1_names = {
        artifact["name"] for artifact in _release_artifacts(_load_json(V1_MANIFEST))
    }
    v2_artifacts = _release_artifacts(_load_json(V2_MANIFEST))
    v2_names = [artifact["name"] for artifact in v2_artifacts]
    v2_index = {name: index for index, name in enumerate(v2_names)}

    assert not set(v1_names).intersection(v2_names)
    assert len(v2_names) == len(set(v2_names))
    for artifact in v2_artifacts:
        for dependency in artifact["dependencies"]:
            assert dependency in v1_names or dependency in v2_index
            if dependency in v2_index:
                assert v2_index[dependency] < v2_index[artifact["name"]]

    dependencies = {artifact["name"]: artifact["dependencies"] for artifact in v2_artifacts}
    assert dependencies["141_durable_background_job_queue.sql"] == ["137_background_jobs.sql"]
    assert dependencies["144_order_auto_completion_workflow.sql"] == [
        "104_order_lifecycle_state_history.sql"
    ]


def test_v2_descriptor_covers_all_live_schema_tables_triggers_and_column_changes() -> None:
    manifest = _load_json(V2_MANIFEST)
    descriptors = _load_json(V2_DESCRIPTORS)

    assert descriptors["contract"] == "migration-owned-object-descriptors/v1"
    assert set(descriptors["descriptors"]) == set(V2_ARTIFACT_NAMES)

    for artifact in _release_artifacts(manifest):
        name = artifact["name"]
        descriptor = descriptors["descriptors"][name]
        sql = (PROJECT_ROOT / artifact["relative_path"]).read_text(encoding="utf-8")
        expected_created_tables = set(descriptor.get("created_tables", []))
        expected_altered_tables = set(descriptor.get("altered_tables", []))
        expected_triggers = set(descriptor.get("triggers", []))
        expected_columns = set(descriptor.get("columns", []))

        assert _sql_created_tables(sql) == expected_created_tables
        assert _sql_altered_tables(sql) == expected_altered_tables
        assert _sql_trigger_names(sql) == expected_triggers
        actual_columns = _sql_altered_columns(sql)
        for table in expected_created_tables:
            actual_columns.update(_sql_created_columns(sql, table))
        assert actual_columns == expected_columns
