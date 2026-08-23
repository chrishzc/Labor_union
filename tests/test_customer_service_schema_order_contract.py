"""
File: test_customer_service_schema_order_contract.py
Description: 驗證客服 schema 順序、父表契約與 Stage11 發布雜湊。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from scripts.schema_assembly import load_schema_assembly


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PART_98 = PROJECT_ROOT / "db/schema_parts/98_customer_service_tickets.sql"
PART_185 = PROJECT_ROOT / "db/schema_parts/185_customer_service_runtime.sql"
STAGE11_MANIFEST = (
    PROJECT_ROOT / "db/migration_releases/labor_union_2026_08_11_line_stage11_v1.json"
)

_TICKET_CREATE = re.compile(
    r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+customer_service_tickets\s*\(.*?"
    r"\)\s*ENGINE\s*=\s*InnoDB\s+DEFAULT\s+CHARSET\s*=\s*utf8mb4\s+"
    r"COLLATE\s*=\s*utf8mb4_unicode_ci\s*;",
    re.IGNORECASE | re.DOTALL,
)
def _normalized_ticket_create(sql: str) -> str:
    match = _TICKET_CREATE.search(sql)
    assert match, "customer_service_tickets must use the canonical IF NOT EXISTS CREATE"
    return " ".join(match.group(0).split()).lower()


def _table_offset(sql: str, table: str) -> int:
    match = re.search(
        rf"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{re.escape(table)}\s*\(",
        sql,
        re.IGNORECASE,
    )
    assert match, f"missing CREATE for {table}"
    return match.start()


def _assert_order_contract(assembly_paths: list[Path], sql_98: str, sql_185: str) -> None:
    names = [path.name for path in assembly_paths]
    index_98 = names.index(PART_98.name)
    index_185 = names.index(PART_185.name)
    assert index_98 < index_185, "98 must precede 185 in canonical fresh assembly"

    parent_98 = _table_offset(sql_98, "customer_service_tickets")
    child_98 = _table_offset(sql_98, "client_profile_change_requests")
    ticket_fk = re.search(
        r"FOREIGN\s+KEY\s*\(\s*ticket_id\s*\)\s*REFERENCES\s+"
        r"customer_service_tickets\s*\(\s*id\s*\)",
        sql_98,
        re.IGNORECASE,
    )
    assert ticket_fk, "profile-change request must retain its ticket FK"
    assert parent_98 < child_98 < ticket_fk.start()

    parent_185 = _table_offset(sql_185, "customer_service_tickets")
    events_185 = _table_offset(sql_185, "customer_service_ticket_events")
    event_fk = re.search(
        r"FOREIGN\s+KEY\s*\(\s*ticket_id\s*\)\s*REFERENCES\s+"
        r"customer_service_tickets\s*\(\s*id\s*\)",
        sql_185,
        re.IGNORECASE,
    )
    assert event_fk, "ticket events must retain their ticket FK"
    assert parent_185 < events_185 < event_fk.start()


def _assert_ticket_definition_contract(sql_98: str, sql_185: str) -> None:
    assert "CREATE TABLE IF NOT EXISTS customer_service_tickets".lower() in sql_98.lower()
    assert "CREATE TABLE IF NOT EXISTS customer_service_tickets".lower() in sql_185.lower()
    assert _normalized_ticket_create(sql_98) == _normalized_ticket_create(sql_185)


def test_customer_service_parts_preserve_canonical_order_and_fk_parents() -> None:
    assembly = load_schema_assembly()
    _assert_order_contract(
        list(assembly.active_artifact_paths),
        PART_98.read_text(encoding="utf-8"),
        PART_185.read_text(encoding="utf-8"),
    )


def test_customer_service_duplicate_parent_definitions_are_exact_and_idempotent() -> None:
    sql_98 = PART_98.read_text(encoding="utf-8")
    sql_185 = PART_185.read_text(encoding="utf-8")
    _assert_ticket_definition_contract(sql_98, sql_185)


def test_stage11_manifest_pins_current_185_sql_bytes() -> None:
    manifest = json.loads(STAGE11_MANIFEST.read_text(encoding="utf-8"))
    artifact = next(
        item for item in manifest["artifacts"] if item["name"] == PART_185.name
    )
    actual_hash = hashlib.sha256(PART_185.read_bytes()).hexdigest()
    assert artifact["relative_path"] == "db/schema_parts/185_customer_service_runtime.sql"
    assert artifact["sha256"] == actual_hash


def test_negative_control_swapped_assembly_order_fails() -> None:
    assembly = list(load_schema_assembly().active_artifact_paths)
    index_98 = assembly.index(PART_98)
    index_185 = assembly.index(PART_185)
    assembly[index_98], assembly[index_185] = assembly[index_185], assembly[index_98]

    with pytest.raises(AssertionError):
        _assert_order_contract(
            assembly,
            PART_98.read_text(encoding="utf-8"),
            PART_185.read_text(encoding="utf-8"),
        )


def test_negative_control_ticket_definition_drift_fails() -> None:
    sql_98 = PART_98.read_text(encoding="utf-8")
    sql_185 = PART_185.read_text(encoding="utf-8")
    drifted_sql_185 = sql_185.replace(
        "version BIGINT NOT NULL DEFAULT 0",
        "version INT NOT NULL DEFAULT 0",
        1,
    )
    assert drifted_sql_185 != sql_185

    with pytest.raises(AssertionError):
        _assert_ticket_definition_contract(sql_98, drifted_sql_185)
