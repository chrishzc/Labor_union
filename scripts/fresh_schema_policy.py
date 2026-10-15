"""Current table retirement decisions shared by fresh bootstrap and schema reads."""

from functools import lru_cache
import json
from pathlib import Path
import re


POLICY_PATH = Path(__file__).resolve().parents[1] / "db/schema_assembly/labor_union_fresh_table_retirements_v1.json"


@lru_cache(maxsize=1)
def retired_fresh_tables() -> frozenset[str]:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    if policy.get("contract") != "labor-union-fresh-table-retirements/v1":
        raise ValueError("invalid fresh retirement contract")
    if policy.get("existing_database_policy") != "no_drop_no_data_change":
        raise ValueError("existing databases must remain unchanged")
    entries = policy["reviewed_tables"]
    names = [entry["table"] for entry in entries]
    if len(names) != len(set(names)) or any(not re.fullmatch(r"[a-z][a-z0-9_]*", n) for n in names):
        raise ValueError("invalid or duplicated retirement table")
    for entry in entries:
        if entry["decision"] not in {"omit_fresh", "retain_fresh"} or not entry.get("reason") or not entry.get("authority"):
            raise ValueError("retirement decision lacks owner evidence")
    return frozenset(entry["table"] for entry in entries if entry["decision"] == "omit_fresh")
