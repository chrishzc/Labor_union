"""Validate reviewed writer dispositions against immutable v3 candidates."""

from __future__ import annotations

import ast
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIRECTORY = REPOSITORY_ROOT / "document" / "架構重整" / "03_追蹤清單與證據" / "evidence" / "writer_inventory_v3"
CANDIDATE_PATH = EVIDENCE_DIRECTORY / "writer_inventory_v3_candidate.findings.jsonl"
CANDIDATE_MANIFEST_PATH = EVIDENCE_DIRECTORY / "writer_inventory_v3_candidate.manifest.json"
DISPOSITION_PATH = EVIDENCE_DIRECTORY / "writer_inventory_v3_disposition.records.jsonl"
DISPOSITION_MANIFEST_PATH = EVIDENCE_DIRECTORY / "writer_inventory_v3_disposition.manifest.json"
FINAL_DISPOSITIONS = frozenset({"retain_canonical", "retain_restricted", "migrate_then_remove", "gone", "needs_decision"})
REQUIRED_FIELDS = frozenset({"identity", "fingerprint", "owner", "transaction_boundary", "runtime_caller", "replacement_evidence", "final_disposition", "approved_to_remove"})
PRODUCTION_SOURCE_ROOTS = ("api", "domains", "infrastructure", "line", "scripts", "services", "subsystems", "ui")
RETIRED_SCHEDULING_WRITERS = frozenset(
    {
        "mark_resume_sent",
        "mark_resume_sent_for_case",
        "reply_matching_inquiry",
        "update_matching_info_sent",
    }
)


def _records(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _candidate_index() -> dict[str, dict[str, object]]:
    return {str(record["identity"]): record for record in _records(CANDIDATE_PATH)}


def _require_candidate_freshness(manifest: dict[str, object]) -> None:
    candidate_manifest = json.loads(CANDIDATE_MANIFEST_PATH.read_text(encoding="utf-8"))
    observed_hash = sha256(CANDIDATE_PATH.read_bytes()).hexdigest()
    if candidate_manifest["evidence_sha256"] != observed_hash:
        raise ValueError("candidate manifest hash is stale")
    if manifest["candidate_evidence_sha256"] != observed_hash:
        raise ValueError("disposition evidence is stale against candidate")


def _require_record(record: dict[str, object], candidate: dict[str, object]) -> None:
    if set(record) != REQUIRED_FIELDS:
        raise ValueError("disposition record fields are invalid")
    if record["fingerprint"] != candidate["fingerprint"]:
        raise ValueError("disposition fingerprint differs from candidate")
    if record["final_disposition"] not in FINAL_DISPOSITIONS:
        raise ValueError("final disposition is invalid")
    _require_removal_contract(record)
    _require_text_fields(record)


def _require_removal_contract(record: dict[str, object]) -> None:
    approved = record["approved_to_remove"]
    if not isinstance(approved, bool):
        raise ValueError("approved_to_remove must be bool")
    if approved and record["final_disposition"] != "gone":
        raise ValueError("only gone records may approve removal")
    if approved and not str(record["replacement_evidence"]).strip():
        raise ValueError("removal approval requires replacement evidence")


def _require_text_fields(record: dict[str, object]) -> None:
    for field in REQUIRED_FIELDS - {"approved_to_remove"}:
        if not isinstance(record[field], str) or not record[field].strip():
            raise ValueError(f"{field} must be non-empty text")


def validate() -> dict[str, int]:
    manifest = json.loads(DISPOSITION_MANIFEST_PATH.read_text(encoding="utf-8"))
    _require_candidate_freshness(manifest)
    candidate_records = _records(CANDIDATE_PATH)
    candidates = _candidate_index()
    records = _records(DISPOSITION_PATH)
    identities = [str(record["identity"]) for record in records]
    if len(identities) != len(set(identities)):
        raise ValueError("disposition identities are duplicated")
    for record in records:
        candidate = candidates.get(str(record["identity"]))
        if candidate is None:
            raise ValueError("disposition identity is absent from candidate")
        _require_record(record, candidate)
    _require_manifest_counts(manifest, records, candidate_records)
    _require_scheduling_legacy_exit(records, candidate_records)
    _require_payroll_typed_ownership(records)
    _require_line_webhook_typed_boundary(records)
    return {"records": len(records), "approved_to_remove": sum(record["approved_to_remove"] is True for record in records)}


def _require_scheduling_legacy_exit(
    records: list[dict[str, object]],
    candidates: list[dict[str, object]],
) -> None:
    legacy_identities = {
        str(candidate["identity"])
        for candidate in candidates
        if candidate["relative_path"] == "infrastructure/mysql/mysql_adapter.py"
        and candidate["symbol"] in RETIRED_SCHEDULING_WRITERS
    }
    reviewed = {str(record["identity"]): record for record in records}
    if not legacy_identities:
        _require_legacy_adapter_definitions_removed()
        return
    for identity in legacy_identities:
        record = reviewed[identity]
        caller = str(record["runtime_caller"]).lower()
        if record["owner"] != "scheduling" or record["final_disposition"] != "migrate_then_remove":
            raise ValueError("retired Scheduling writer has an invalid disposition")
        if "no production caller" not in caller and "410 gone" not in caller:
            raise ValueError("retired Scheduling writer lacks an unreachable caller receipt")
    used_symbols = _production_call_symbols(RETIRED_SCHEDULING_WRITERS)
    if used_symbols:
        raise ValueError(f"retired Scheduling writer still has production callers: {sorted(used_symbols)}")


def _require_legacy_adapter_definitions_removed() -> None:
    adapter = REPOSITORY_ROOT / "infrastructure" / "mysql" / "mysql_adapter.py"
    tree = ast.parse(adapter.read_text(encoding="utf-8"), filename=str(adapter))
    definitions = {
        node.name for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    remaining = definitions & RETIRED_SCHEDULING_WRITERS
    if remaining:
        raise ValueError(f"retired Scheduling writer definitions remain: {sorted(remaining)}")
    used_symbols = _production_call_symbols(RETIRED_SCHEDULING_WRITERS)
    if used_symbols:
        raise ValueError(f"retired Scheduling writer still has production callers: {sorted(used_symbols)}")


def _production_call_symbols(symbols: frozenset[str]) -> set[str]:
    usages: set[str] = set()
    excluded = REPOSITORY_ROOT / "infrastructure" / "mysql" / "mysql_adapter.py"
    for root in PRODUCTION_SOURCE_ROOTS:
        for path in (REPOSITORY_ROOT / root).rglob("*.py"):
            if path == excluded:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and _called_symbol(node) in symbols:
                    usages.add(_called_symbol(node))
    return usages


def _called_symbol(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _require_payroll_typed_ownership(records: list[dict[str, object]]) -> None:
    payroll_records = [record for record in records if record["owner"] == "payroll"]
    if not payroll_records:
        raise ValueError("Payroll writer inventory is empty")
    for record in payroll_records:
        path = str(record["identity"]).split(":", 1)[0]
        if not path.startswith(("infrastructure/mysql/payroll_", "subsystems/payroll/")):
            raise ValueError("Payroll writer is outside the typed ownership boundary")
        if record["final_disposition"] not in {"retain_canonical", "retain_restricted"}:
            raise ValueError("Payroll legacy writer exit is incomplete")
        if "typed" not in str(record["runtime_caller"]).lower():
            raise ValueError("Payroll writer lacks a typed runtime caller receipt")


def _require_line_webhook_typed_boundary(records: list[dict[str, object]]) -> None:
    webhook = next(
        (
            record for record in records
            if str(record["identity"]).startswith("line/line_bot.py:line_webhook:")
        ),
        None,
    )
    if webhook is not None and webhook["final_disposition"] != "retain_canonical":
        raise ValueError("LINE webhook outer transaction lacks typed ownership")
    source = REPOSITORY_ROOT / "line" / "line_bot.py"
    function = next(
        node for node in ast.parse(source.read_text(encoding="utf-8")).body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "line_webhook"
    )
    direct_mutations = [
        node for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
        and node.args[0].value.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "REPLACE"))
    ]
    if direct_mutations:
        raise ValueError("LINE webhook route contains direct mutation SQL")


def _require_manifest_counts(manifest, records, candidates) -> None:
    candidate_identities = {str(record["identity"]) for record in candidates}
    unresolved = sum(record["unresolved_reason"] == "owner_not_deterministic_from_path" for record in candidates)
    migration = sum(record["recommendation_candidate"] == "migrate_then_remove_candidate" for record in candidates)
    reviewed_identities = {str(record["identity"]) for record in records}
    missing_identities = candidate_identities - reviewed_identities
    if missing_identities:
        raise ValueError(
            "disposition is incomplete: "
            f"{len(missing_identities)} candidate identities are unreviewed"
        )
    if manifest.get("candidate_unique_identity_count") != len(candidate_identities):
        raise ValueError("candidate unique identity count is inconsistent")
    covered_unresolved = sum(record["unresolved_reason"] == "owner_not_deterministic_from_path" and str(record["identity"]) in reviewed_identities for record in candidates)
    covered_migration = sum(record["recommendation_candidate"] == "migrate_then_remove_candidate" and str(record["identity"]) in reviewed_identities for record in candidates)
    counts = Counter(str(record["final_disposition"]) for record in records)
    if manifest["record_count"] != len(records) or manifest["covered_candidate_unresolved_count"] != covered_unresolved:
        raise ValueError("disposition coverage count is inconsistent")
    if manifest["covered_candidate_migrate_then_remove_count"] != covered_migration:
        raise ValueError("migration candidate coverage count is inconsistent")
    if covered_unresolved != unresolved or covered_migration != migration:
        raise ValueError("expected initial disposition slice is incomplete")
    if manifest["approved_to_remove_count"] != sum(record["approved_to_remove"] is True for record in records):
        raise ValueError("removal approval count is inconsistent")
    if manifest["final_disposition_counts"] != dict(sorted(counts.items())):
        raise ValueError("final disposition count is inconsistent")


if __name__ == "__main__":
    result = validate()
    print(f"writer_inventory_v3_disposition records={result['records']} approved_to_remove={result['approved_to_remove']}")
