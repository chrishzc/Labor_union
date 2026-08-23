"""
File: test_matching_coordination_schema_contract.py
Description: 驗證 M3 matching coordination additive schema 與 descriptor 完整契約。
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "db/schema_parts/1003_matching_coordination_successor.sql"
DESCRIPTOR_PATH = (
    ROOT
    / "db/migration_releases/"
    / "labor_union_2026_08_22_matching_coordination_successor_v1.descriptors.json"
)
ARTIFACT_NAME = "1003_matching_coordination_successor.sql"
TABLES = (
    "matching_coordination_criteria_snapshots",
    "matching_coordination_package_lineage",
    "matching_coordination_events",
    "matching_coordination_apply_receipts",
    "matching_coordination_outbox",
)


def _read_utf8(path: Path) -> str:
    raw = path.read_bytes()
    assert raw.decode("utf-8").encode("utf-8") == raw
    return raw.decode("utf-8")


def _parenthesized(text: str, opening: int) -> str:
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return text[opening + 1 : index]
    raise AssertionError("unclosed SQL parenthesis")


def _split_top_level(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    for index, character in enumerate(text):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == "," and depth == 0:
            parts.append(text[start:index].strip())
            start = index + 1
    parts.append(text[start:].strip())
    return parts


def _table_body(sql: str, table: str) -> str:
    match = re.search(
        rf"CREATE TABLE IF NOT EXISTS\s+{re.escape(table)}\s*\(",
        sql,
        flags=re.IGNORECASE,
    )
    assert match is not None, table
    return _parenthesized(sql, match.end() - 1)


def _sql_columns(sql: str, table: str) -> list[str]:
    columns: list[str] = []
    for definition in _split_top_level(_table_body(sql, table)):
        match = re.match(r"([A-Za-z0-9_]+)\s+", definition)
        if match and not definition.upper().startswith(
            ("CONSTRAINT ", "PRIMARY ", "UNIQUE ", "INDEX ", "KEY ")
        ):
            columns.append(match.group(1))
    return columns


def _load_descriptor() -> dict[str, object]:
    payload = json.loads(_read_utf8(DESCRIPTOR_PATH))
    assert payload["contract"] == "migration-owned-object-descriptors/v1"
    return payload["descriptors"][ARTIFACT_NAME]


def test_matching_coordination_schema_has_five_immutable_owned_tables() -> None:
    sql = _read_utf8(SQL_PATH)
    descriptor = _load_descriptor()

    assert tuple(re.findall(r"CREATE TABLE IF NOT EXISTS\s+([A-Za-z0-9_]+)", sql)) == TABLES
    assert tuple(descriptor["tables"]) == TABLES
    assert sql.count("case_no VARCHAR(50) NOT NULL") == 5
    assert "case_no VARCHAR(191)" not in sql

    expected_triggers = {
        f"trg_{suffix}_before_{event}"
        for suffix in (
            "matching_criteria_snapshots",
            "matching_package_lineage",
            "matching_coordination_events",
            "matching_apply_receipts",
            "matching_outbox",
        )
        for event in ("update", "delete")
    }
    actual_triggers = set(re.findall(r"CREATE TRIGGER\s+([A-Za-z0-9_]+)", sql))
    assert actual_triggers == expected_triggers
    assert set(descriptor["triggers"]) == expected_triggers
    for table in TABLES:
        assert f"BEFORE UPDATE ON {table}" in sql
        assert f"BEFORE DELETE ON {table}" in sql


def test_matching_coordination_descriptor_is_exact_for_sql_contract() -> None:
    sql = _read_utf8(SQL_PATH)
    descriptor = _load_descriptor()

    for table in TABLES:
        assert descriptor["tables"][table] == _sql_columns(sql, table)

    index_names: set[str] = set()
    for table in TABLES:
        body = _table_body(sql, table)
        index_names.add(f"{table}.PRIMARY")
        index_names.update(
            f"{table}.{name}"
            for name in re.findall(
                r"(?:UNIQUE KEY|INDEX)\s+([A-Za-z0-9_]+)\s*\(", body,
                flags=re.IGNORECASE,
            )
        )
    assert set(descriptor["indexes"]) == index_names
    assert len(index_names) == 31

    sql_foreign_key_names = set(
        re.findall(
            r"CONSTRAINT\s+(fk_[A-Za-z0-9_]+)\s+FOREIGN KEY",
            sql,
            flags=re.IGNORECASE,
        )
    )
    descriptor_foreign_key_names = {
        key.split(".", 1)[1] for key in descriptor["foreign_keys"]
    }
    assert descriptor_foreign_key_names == sql_foreign_key_names
    assert len(descriptor["foreign_keys"]) == 9
    assert len(descriptor["checks"]) == 26


def test_matching_coordination_schema_is_additive_and_outbox_pairs_are_closed() -> None:
    sql = _read_utf8(SQL_PATH)
    descriptor = _load_descriptor()

    assert not re.search(
        r"(?im)^\s*(ALTER TABLE|DROP TABLE|TRUNCATE|INSERT INTO|UPDATE\s+[A-Za-z_]|DELETE FROM|LOAD DATA)\b",
        sql,
    )
    assert "dispatch_state" not in sql
    assert "idx_matching_outbox_dispatch" not in descriptor["indexes"]
    assert any(
        key.endswith(".idx_matching_outbox_created_time")
        for key in descriptor["indexes"]
    )

    assert "orders_terms_update_requested" in sql
    assert "target_owner ENUM('line_integration','assignment_workflow','orders_workflow')" in sql
    for pair in (
        "intent_type IN ('line_matching_interaction','line_criteria_diff_resend')",
        "target_owner = 'line_integration'",
        "intent_type IN ('assignment_conversion_requested','rematch_requested')",
        "target_owner = 'assignment_workflow'",
        "intent_type = 'orders_terms_update_requested'",
        "target_owner = 'orders_workflow'",
    ):
        assert pair in sql
    assert "scheduling_workflow" not in sql
    assert "scheduling_terms_update_requested" not in sql

    outbox_check = descriptor["checks"][
        "matching_coordination_outbox.chk_matching_outbox_target"
    ]
    assert "orders_terms_update_requested" in outbox_check
    assert "orders_workflow" in outbox_check
