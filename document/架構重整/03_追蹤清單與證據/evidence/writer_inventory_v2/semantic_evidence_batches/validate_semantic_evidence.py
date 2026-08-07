from __future__ import annotations

import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys


SCRIPT_PATH = Path(__file__).resolve()
BATCHES_ROOT = SCRIPT_PATH.parent
EVIDENCE_ROOT = BATCHES_ROOT.parent
REPOSITORY_ROOT = EVIDENCE_ROOT.parents[3]
FINAL_MANIFEST_PATH = EVIDENCE_ROOT / "inventory_v2_final.manifest.json"
FINAL_FINDINGS_PATH = EVIDENCE_ROOT / "inventory_v2_final.findings.jsonl"
SCHEMA_PATH = BATCHES_ROOT / "semantic_evidence.schema.json"
R2_ROOT = BATCHES_ROOT / "INV2-EVID-01-R2"
EXPECTED_FINAL_MANIFEST_SHA256 = (
    "a04b6342390e90498fd9cf6821cb3f1c3dea1a19d40b13d60df4a8dda25883e3"
)
EXPECTED_ORIGINAL_HASHES = {
    "batch_manifest.json": (
        "4b66643e772a361dc3ff661b16d752dd479033c9426f5e8a7990eeebf9561c82"
    ),
    "finding_evidence.jsonl": (
        "532f7dac6758e4f34fd4e82dc1e3b3fc94af09ec4fcec9e6b724d9e202fd362a"
    ),
    "raw_calls.json": (
        "4c84a59b9a72197d139cc52115360215e47509f52997fe9e3a9550079b9c3824"
    ),
    "unresolved.md": (
        "1fb1b6733bff53bb185b89b214fd8895e5f58a65123a292ea71cdf56cb65ae31"
    ),
    "validation_receipt.json": (
        "717682e71267e7158bfcd63f46e670e10cdf736d9615ae25d8fbd8b47f33e64e"
    ),
}
ROW_REQUIRED_KEYS = {
    "contract",
    "inventory_row_number",
    "finding_identity",
    "finding_identity_digest",
    "live_source_sha256",
    "writer_kind",
    "semantic_evidence",
    "suggestion",
    "effective_disposition",
    "approved_to_remove",
}
SEMANTIC_REQUIRED_KEYS = {
    "architecture_location",
    "architecture_references",
    "caller_evidence",
    "negative_caller_evidence",
    "writer_type",
    "high_risk",
    "high_risk_categories",
    "high_risk_reasons",
}
CALLER_REQUIRED_KEYS = {
    "path",
    "symbol",
    "line",
    "call_type",
    "evidence",
}
REFERENCE_REQUIRED_KEYS = {
    "path",
    "line_start",
    "line_end",
    "evidence",
}
NEGATIVE_CALLER_REQUIRED_KEYS = {
    "search_roots",
    "queries",
    "query_results",
    "result",
    "evidence",
}
SUGGESTION_REQUIRED_KEYS = {
    "candidate_type",
    "confidence",
    "evidence",
    "counter_evidence",
    "unresolved_questions",
    "requires_strong_model_review",
    "effective_disposition",
    "approved_to_remove",
}
ARCHITECTURE_LOCATIONS = {
    "global",
    "global.performance_ux",
    "global.deployment_governance",
    "orders",
    "assignments_scheduling",
    "payroll",
    "client_finance",
    "staff_payables",
    "government_subsidy",
    "finance_import",
    "anomalies",
    "case_import",
    "contract_integration",
    "line_integration",
    "access_control",
    "knowledge_retrieval",
}
WRITER_TYPES = {
    "allowed_read",
    "application_transaction_boundary",
    "api_hidden_transaction_boundary",
    "canonical_repository_writer",
    "cross_domain_writer",
}
CANDIDATE_TYPES = {
    "allowed_read_candidate",
    "allowed_transaction_boundary_candidate",
    "canonical_writer_candidate",
    "migrate_writer_candidate",
    "unresolved",
}
CALL_TYPES = {
    "direct",
    "indirect",
    "dependency_injection",
    "route_entry",
    "worker_entry",
    "internal_helper",
    "unit_of_work",
}
HIGH_RISK_CATEGORIES = {
    "hidden_transaction_boundary",
    "cross_domain_ownership",
    "cross_domain_transaction_criticality",
    "financial_state_mutation",
    "replay_or_idempotency_mutation",
    "occupancy_or_lock_mutation",
    "aggregate_version_mutation",
    "privacy_sensitive_import_mutation",
    "cross_domain_bootstrap_mutation",
    "financial_ledger_or_settlement_mutation",
    "refund_or_reversal_mutation",
    "security_identity_or_session_mutation",
    "external_delivery_or_signature_mutation",
    "deployment_or_expiry_governance_mutation",
}
EXPECTED_CANDIDATE_BY_WRITER_TYPE = {
    "allowed_read": "allowed_read_candidate",
    "application_transaction_boundary": (
        "allowed_transaction_boundary_candidate"
    ),
    "api_hidden_transaction_boundary": "migrate_writer_candidate",
    "canonical_repository_writer": "canonical_writer_candidate",
    "cross_domain_writer": "migrate_writer_candidate",
}


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line_number, line in enumerate(strict_text(path).splitlines(), start=1):
        if not line:
            continue
        row = json.loads(line)
        canonical_line = canonical_json_bytes(row).decode("utf-8").removesuffix("\n")
        if line != canonical_line:
            raise ValueError(f"non-canonical JSONL at {path}:{line_number}")
        rows.append(row)
    return rows


def strict_text(path: Path) -> str:
    payload = path.read_bytes()
    if payload.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"UTF-8 BOM is forbidden: {path}")
    if b"\r" in payload:
        raise ValueError(f"CR is forbidden: {path}")
    return payload.decode("utf-8", errors="strict")


def source_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8-sig", errors="strict")


def require_exact_keys(value: dict, keys: set[str], label: str) -> None:
    if set(value) != keys:
        raise ValueError(
            f"{label} keys differ: missing={sorted(keys - set(value))}, "
            f"extra={sorted(set(value) - keys)}"
        )


def symbol_at_line(tree: ast.AST, line: int) -> str:
    symbols = []
    for node in ast.walk(tree):
        if not isinstance(
            node,
            (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue
        end_line = node.end_lineno or node.lineno
        if node.lineno <= line <= end_line:
            symbols.append((node.lineno, end_line, node.name))
    symbols.sort(key=lambda item: (item[0], -item[1]))
    return ".".join(item[2] for item in symbols)


def call_names_at_line(tree: ast.AST, line: int) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        end_line = node.end_lineno or node.lineno
        if not node.lineno <= line <= end_line:
            continue
        if isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
        elif isinstance(node.func, ast.Name):
            names.add(node.func.id)
    return names


def validate_caller(caller: dict, target_symbol: str) -> None:
    require_exact_keys(caller, CALLER_REQUIRED_KEYS, "caller_evidence")
    if caller["call_type"] not in CALL_TYPES:
        raise ValueError(f"unsupported call_type: {caller['call_type']}")
    caller_path = REPOSITORY_ROOT / caller["path"]
    source = source_text(caller_path)
    source_lines = source.splitlines()
    line = caller["line"]
    if not isinstance(line, int) or not 1 <= line <= len(source_lines):
        raise ValueError(f"caller line is outside source: {caller}")
    tree = ast.parse(source, filename=caller["path"])
    actual_symbol = symbol_at_line(tree, line)
    if actual_symbol != caller["symbol"]:
        raise ValueError(
            f"caller symbol mismatch at {caller['path']}:{line}: "
            f"{actual_symbol!r} != {caller['symbol']!r}"
        )
    target_leaf = target_symbol.rsplit(".", 1)[-1]
    if target_leaf not in call_names_at_line(tree, line):
        raise ValueError(
            f"target call {target_leaf!r} not found at "
            f"{caller['path']}:{line}"
        )
    if not caller["evidence"].strip():
        raise ValueError("caller evidence text is empty")


def validate_reference(reference: dict) -> None:
    require_exact_keys(reference, REFERENCE_REQUIRED_KEYS, "reference")
    reference_path = REPOSITORY_ROOT / reference["path"]
    lines = source_text(reference_path).splitlines()
    line_start = reference["line_start"]
    line_end = reference["line_end"]
    if not 1 <= line_start <= line_end <= len(lines):
        raise ValueError(f"invalid architecture reference: {reference}")
    if not reference["evidence"].strip():
        raise ValueError("architecture reference evidence is empty")


def validate_negative_caller(evidence: dict) -> None:
    require_exact_keys(
        evidence,
        NEGATIVE_CALLER_REQUIRED_KEYS,
        "negative_caller_evidence",
    )
    if not evidence["search_roots"] or not evidence["queries"]:
        raise ValueError("negative caller search scope and queries are required")
    if [item["query"] for item in evidence["query_results"]] != evidence["queries"]:
        raise ValueError("negative caller query_results must follow query order")
    for query_result in evidence["query_results"]:
        require_exact_keys(
            query_result,
            {"query", "matches"},
            "negative caller query result",
        )
        for match in query_result["matches"]:
            require_exact_keys(
                match,
                {"path", "line", "text"},
                "negative caller search match",
            )
        actual_matches = literal_search(
            evidence["search_roots"],
            query_result["query"],
        )
        if actual_matches != query_result["matches"]:
            raise ValueError(
                f"negative caller search drift for {query_result['query']!r}"
            )
    if evidence["result"] != "no_live_caller_found":
        raise ValueError("unsupported negative caller result")
    if not evidence["evidence"].strip():
        raise ValueError("negative caller evidence text is empty")


def literal_search(search_roots: list[str], query: str) -> list[dict]:
    matches = []
    source_paths = []
    for search_root in search_roots:
        root_path = REPOSITORY_ROOT / search_root
        if root_path.is_file():
            source_paths.append(root_path)
            continue
        source_paths.extend(sorted(root_path.rglob("*.py")))
    for source_path in sorted(set(source_paths)):
        relative_path = source_path.relative_to(REPOSITORY_ROOT).as_posix()
        for line_number, text in enumerate(
            source_text(source_path).splitlines(),
            start=1,
        ):
            if query in text:
                matches.append(
                    {
                        "path": relative_path,
                        "line": line_number,
                        "text": text,
                    }
                )
    return matches


def validate_row(row: dict, final_row: dict) -> None:
    require_exact_keys(row, ROW_REQUIRED_KEYS, "row")
    if row["contract"] != "production-writer-semantic-evidence/v1":
        raise ValueError("unsupported semantic evidence contract")
    for key in (
        "inventory_row_number",
        "finding_identity",
        "finding_identity_digest",
        "live_source_sha256",
        "writer_kind",
    ):
        if row[key] != final_row[key]:
            raise ValueError(f"final finding mismatch at row {row['inventory_row_number']}")
    source_path = REPOSITORY_ROOT / row["finding_identity"]["path"]
    if sha256_path(source_path) != row["live_source_sha256"]:
        raise ValueError(f"stale source at row {row['inventory_row_number']}")
    if row["effective_disposition"] != "blocked":
        raise ValueError("effective disposition must remain blocked")
    if row["approved_to_remove"] is not False:
        raise ValueError("approved_to_remove must remain false")

    semantic = row["semantic_evidence"]
    require_exact_keys(semantic, SEMANTIC_REQUIRED_KEYS, "semantic_evidence")
    if semantic["architecture_location"] not in ARCHITECTURE_LOCATIONS:
        raise ValueError("unsupported architecture_location")
    if semantic["writer_type"] not in WRITER_TYPES:
        raise ValueError("unsupported writer_type")
    if not semantic["architecture_references"]:
        raise ValueError("architecture references are required")
    for reference in semantic["architecture_references"]:
        validate_reference(reference)
    if bool(semantic["caller_evidence"]) == bool(
        semantic["negative_caller_evidence"]
    ):
        raise ValueError(
            "provide either positive or negative caller evidence, not both"
        )
    target_symbol = row["finding_identity"]["symbol"]
    for caller in semantic["caller_evidence"]:
        validate_caller(caller, target_symbol)
    for negative_evidence in semantic["negative_caller_evidence"]:
        validate_negative_caller(negative_evidence)
    if not set(semantic["high_risk_categories"]).issubset(HIGH_RISK_CATEGORIES):
        raise ValueError("unsupported high-risk category")
    if semantic["high_risk"] and (
        not semantic["high_risk_categories"]
        or not semantic["high_risk_reasons"]
    ):
        raise ValueError("high-risk row requires at least one reason")
    if not semantic["high_risk"] and (
        semantic["high_risk_categories"]
        or semantic["high_risk_reasons"]
    ):
        raise ValueError("non-high-risk row cannot carry risk categories or reasons")
    if semantic["writer_type"] == "allowed_read" and semantic["high_risk"]:
        raise ValueError(
            "allowed read cannot be high risk without a separate exposure contract"
        )

    suggestion = row["suggestion"]
    require_exact_keys(suggestion, SUGGESTION_REQUIRED_KEYS, "suggestion")
    if suggestion["candidate_type"] not in CANDIDATE_TYPES:
        raise ValueError("unsupported candidate_type")
    expected_candidate = EXPECTED_CANDIDATE_BY_WRITER_TYPE[
        semantic["writer_type"]
    ]
    if suggestion["candidate_type"] != expected_candidate:
        raise ValueError(
            f"writer type/candidate mismatch at row {row['inventory_row_number']}"
        )
    if suggestion["confidence"] not in {"high", "medium", "low"}:
        raise ValueError("unsupported confidence")
    if suggestion["requires_strong_model_review"] is not True:
        raise ValueError("strong model review flag must remain true")
    if suggestion["effective_disposition"] != "blocked":
        raise ValueError("suggestion disposition must remain blocked")
    if suggestion["approved_to_remove"] is not False:
        raise ValueError("suggestion removal approval must remain false")
    if not suggestion["evidence"].strip():
        raise ValueError("suggestion evidence is empty")


def validate_manifest(manifest: dict, evidence_path: Path) -> None:
    if manifest["contract"] != "semantic-evidence-batch-manifest/v2":
        raise ValueError("unsupported batch manifest contract")
    if manifest["batch_id"] != "INV2-EVID-01-R2":
        raise ValueError("unexpected batch id")
    if manifest["row_start"] != 1 or manifest["row_end"] != 50:
        raise ValueError("unexpected row range")
    if manifest["input_manifest_sha256"] != EXPECTED_FINAL_MANIFEST_SHA256:
        raise ValueError("unexpected final inventory manifest")
    if manifest["may_mutate"] is not False:
        raise ValueError("batch may not mutate production")
    if manifest["execution_authority"] != "none":
        raise ValueError("batch has forbidden execution authority")
    if manifest["original_batch_hashes"] != EXPECTED_ORIGINAL_HASHES:
        raise ValueError("original batch hash contract changed")
    if manifest["schema_sha256"] != sha256_path(SCHEMA_PATH):
        raise ValueError("schema digest mismatch")
    if manifest["validator_sha256"] != sha256_path(SCRIPT_PATH):
        raise ValueError("validator digest mismatch")
    if manifest["finding_evidence_sha256"] != sha256_path(evidence_path):
        raise ValueError("finding evidence digest mismatch")


def main() -> None:
    for filename, expected_digest in EXPECTED_ORIGINAL_HASHES.items():
        original_path = BATCHES_ROOT / "INV2-EVID-01" / filename
        if sha256_path(original_path) != expected_digest:
            raise ValueError(f"original batch changed: {filename}")
    if sha256_path(FINAL_MANIFEST_PATH) != EXPECTED_FINAL_MANIFEST_SHA256:
        raise ValueError("Final Inventory manifest is stale")

    manifest_path = R2_ROOT / "batch_manifest.json"
    evidence_path = R2_ROOT / "finding_evidence.jsonl"
    unresolved_path = R2_ROOT / "unresolved.md"
    for path in (
        SCHEMA_PATH,
        SCRIPT_PATH,
        manifest_path,
        evidence_path,
        unresolved_path,
    ):
        strict_text(path)

    manifest = json.loads(strict_text(manifest_path))
    validate_manifest(manifest, evidence_path)
    final_rows = load_jsonl(FINAL_FINDINGS_PATH)
    final_by_number = {
        row["inventory_row_number"]: row
        for row in final_rows
    }
    rows = load_jsonl(evidence_path)
    row_numbers = [row["inventory_row_number"] for row in rows]
    if row_numbers != list(range(1, 51)):
        raise ValueError("R2 must contain rows 1 through 50 exactly once")
    if len({row["finding_identity_digest"] for row in rows}) != 50:
        raise ValueError("finding identity digests must be unique")
    for row in rows:
        validate_row(row, final_by_number[row["inventory_row_number"]])

    disposition_counts = Counter(
        row["suggestion"]["candidate_type"]
        for row in rows
    )
    high_risk_rows = [
        row["inventory_row_number"]
        for row in rows
        if row["semantic_evidence"]["high_risk"]
    ]
    receipt = {
        "contract": "semantic-evidence-validation-receipt/v2",
        "result": "pass",
        "validation_scope": (
            "structural-integrity, live-source, caller replay, architecture "
            "reference bounds and candidate consistency"
        ),
        "semantic_disposition_complete": False,
        "semantic_unresolved_rows": manifest["unresolved_row_numbers"],
        "validator_sha256": sha256_path(SCRIPT_PATH),
        "schema_sha256": sha256_path(SCHEMA_PATH),
        "final_manifest_sha256": sha256_path(FINAL_MANIFEST_PATH),
        "batch_manifest": {
            "path": manifest_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "sha256": sha256_path(manifest_path),
        },
        "finding_evidence": {
            "path": evidence_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "sha256": sha256_path(evidence_path),
        },
        "unresolved": {
            "path": unresolved_path.relative_to(REPOSITORY_ROOT).as_posix(),
            "sha256": sha256_path(unresolved_path),
        },
        "canonicalization": (
            "raw artifact SHA-256; JSONL rows use sorted-key compact JSON, "
            "UTF-8 without BOM, one LF per row"
        ),
        "row_count": len(rows),
        "identity_unique_count": len(rows),
        "structured_caller_evidence_count": sum(
            len(row["semantic_evidence"]["caller_evidence"])
            for row in rows
        ),
        "negative_caller_evidence_count": sum(
            len(row["semantic_evidence"]["negative_caller_evidence"])
            for row in rows
        ),
        "architecture_reference_count": sum(
            len(row["semantic_evidence"]["architecture_references"])
            for row in rows
        ),
        "disposition_counts": dict(sorted(disposition_counts.items())),
        "high_risk_rows": high_risk_rows,
        "effective_disposition_blocked_count": sum(
            row["effective_disposition"] == "blocked"
            for row in rows
        ),
        "approved_to_remove_true_count": sum(
            row["approved_to_remove"] is True
            for row in rows
        ),
        "original_batch_unchanged": True,
        "validator_write_paths": [
            (R2_ROOT / "validation_receipt.json")
            .relative_to(REPOSITORY_ROOT)
            .as_posix()
        ],
    }
    receipt_path = R2_ROOT / "validation_receipt.json"
    receipt_path.write_bytes(canonical_json_bytes(receipt))
    print(
        "SEMANTIC_EVIDENCE_VALIDATION_PASS "
        f"rows={len(rows)} callers="
        f"{receipt['structured_caller_evidence_count']} "
        f"high_risk={len(high_risk_rows)}"
    )


if __name__ == "__main__":
    main()
