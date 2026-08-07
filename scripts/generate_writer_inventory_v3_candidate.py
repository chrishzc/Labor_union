"""Generate blocked post-legacy writer inventory evidence."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from shared_kernel.writer_inventory import (  # noqa: E402
    WriterFinding,
    scan_production_writers,
    writer_scan_fingerprint,
)


ROOTS = ("api", "domains", "infrastructure", "line", "scripts", "subsystems")
OUTPUT_DIRECTORY = REPOSITORY_ROOT / "document" / "架構重整" / "evidence" / "writer_inventory_v3"
RUNTIME_ROOTS = (*ROOTS, "ui")
LEGACY_SUBSIDY_PROJECTION_FIELDS = (
    "subsidy_refund_receivable",
    "subsidy_refund_refunded",
)
EVIDENCE_ONLY_PATHS = frozenset(
    {
        "scripts/generate_formal_architecture_baseline.py",
        "scripts/validate_formal_architecture_baseline.py",
        "scripts/generate_writer_inventory_v3_candidate.py",
        "scripts/validate_writer_inventory_v3_candidate.py",
    }
)


def _owner_candidate(relative_path: str) -> str | None:
    parts = Path(relative_path).parts
    if parts[0] == "subsystems":
        return _subsystem_owner(parts[1]) if len(parts) > 1 else None
    if parts[0] == "line":
        return "line_integration"
    if parts[0] == "scripts":
        return "global_infrastructure"
    if parts[:2] == ("infrastructure", "mysql"):
        return _mysql_owner(parts[-1])
    if parts[:2] == ("infrastructure", "migration"):
        return "global_infrastructure"
    return None


def _subsystem_owner(name: str) -> str | None:
    return {
        "access": "access_control",
        "anomalies": "anomalies",
        "bootstrap": "case_import",
        "case_import": "case_import",
        "client_finance": "client_finance",
        "finance_import": "finance_import",
        "government_subsidy": "government_subsidy",
        "line": "line_integration",
        "orders": "orders",
        "payroll": "payroll",
        "scheduling": "scheduling",
        "staff_payables": "staff_payables",
    }.get(name)


def _mysql_owner(filename: str) -> str | None:
    prefixes = (
        ("anomaly_", "anomalies"),
        ("assignment_", "scheduling"),
        ("background_job_", "global_infrastructure"),
        ("beclass_", "case_import"),
        ("case_", "case_import"),
        ("client_", "client_finance"),
        ("finance_import_", "finance_import"),
        ("financial_adjustment_", "client_finance"),
        ("government_subsidy_", "government_subsidy"),
        ("leave_", "scheduling"),
        ("order_", "orders"),
        ("payroll_", "payroll"),
        ("scheduling_", "scheduling"),
        ("staff_", "staff_payables"),
    )
    for prefix, owner in prefixes:
        if filename.startswith(prefix):
            return owner
    if filename in {"mysql_adapter.py", "unit_of_work.py"}:
        return "global_infrastructure"
    return None


def _finding_record(finding: WriterFinding) -> dict[str, Any]:
    owner = _owner_candidate(finding.relative_path)
    writer_type = _writer_type(finding)
    recommendation = _recommendation_candidate(finding, owner, writer_type)
    return {
        "identity": finding.identity,
        "relative_path": finding.relative_path,
        "symbol": finding.symbol,
        "method": finding.method,
        "operation": finding.operation,
        "table": finding.table,
        "fingerprint": finding.fingerprint,
        "owner_candidate": owner,
        "runtime_class_candidate": _runtime_class(finding.relative_path),
        "writer_type_candidate": writer_type,
        "recommendation_candidate": recommendation,
        "high_risk_tags": _high_risk_tags(finding, owner, writer_type),
        "candidate_disposition": _candidate_disposition(finding),
        "effective_disposition": "blocked",
        "approved_to_remove": False,
        "requires_strong_model_review": True,
        "unresolved_reason": None if owner else "owner_not_deterministic_from_path",
    }


def _runtime_class(relative_path: str) -> str:
    if relative_path.startswith("scripts/"):
        return "maintenance_or_migration"
    return "production"


def _candidate_disposition(finding: WriterFinding) -> str:
    if finding.operation == "COMMIT":
        return "allowed_transaction_boundary_candidate"
    return "canonical_writer_candidate"


def _writer_type(finding: WriterFinding) -> str:
    if finding.operation == "COMMIT":
        return "outer_transaction_boundary_candidate"
    if finding.relative_path.startswith("scripts/migrate_"):
        return "migration_writer_candidate"
    if finding.operation == "DYNAMIC":
        return "dynamic_sql_writer_candidate"
    return "canonical_persistence_writer_candidate"


def _high_risk_tags(
    finding: WriterFinding,
    owner: str | None,
    writer_type: str,
) -> list[str]:
    text = " ".join((finding.relative_path, finding.symbol, finding.table)).lower()
    tags: set[str] = set()
    if writer_type == "outer_transaction_boundary_candidate":
        tags.add("transaction_boundary")
    if writer_type == "dynamic_sql_writer_candidate":
        tags.add("dynamic_sql")
    if writer_type == "migration_writer_candidate" or finding.operation in {"ALTER", "CREATE", "TRUNCATE"}:
        tags.add("schema_or_data_migration")
    if owner == "line_integration" or "line_" in text:
        tags.add("line_integration")
    if owner == "access_control" or "admin_" in text or "session" in text:
        tags.add("access_or_audit")
    if owner == "client_finance" or any(term in text for term in ("refund", "reversal", "client_payment")):
        tags.add("client_finance")
    if owner == "staff_payables" or any(term in text for term in ("staff_payment", "staff_obligation", "settlement", "payout")):
        tags.add("staff_payables_or_month_close")
    if owner == "government_subsidy" or "subsidy" in text:
        tags.add("government_subsidy")
    if finding.table == "orders" or owner == "orders":
        tags.add("order_lifecycle")
    if finding.table == "unknown":
        tags.add("table_unresolved")
    if finding.relative_path == "infrastructure/mysql/mysql_adapter.py":
        tags.add("broad_direct_database_adapter")
    return sorted(tags)


def _recommendation_candidate(
    finding: WriterFinding,
    owner: str | None,
    writer_type: str,
) -> str:
    if finding.relative_path == "infrastructure/mysql/mysql_adapter.py":
        return "migrate_then_remove_candidate"
    if finding.relative_path in {
        "infrastructure/mysql/background_job_repository.py",
        "infrastructure/mysql/unit_of_work.py",
    }:
        return "retain_canonical_candidate"
    if owner == "global_infrastructure" and (
        finding.relative_path.startswith("scripts/")
        or writer_type == "migration_writer_candidate"
    ):
        return "retain_restricted_maintenance_candidate"
    if owner is not None and writer_type == "canonical_persistence_writer_candidate":
        return "retain_canonical_candidate"
    return "strong_review_required_candidate"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _legacy_subsidy_projection_boundary() -> dict[str, Any]:
    runtime_paths = tuple(
        path
        for root in RUNTIME_ROOTS
        for path in sorted((REPOSITORY_ROOT / root).rglob("*.py"))
    )
    callers = [
        path.relative_to(REPOSITORY_ROOT).as_posix()
        for path in runtime_paths
        if path.relative_to(REPOSITORY_ROOT).as_posix() not in EVIDENCE_ONLY_PATHS
        and any(
            field in path.read_text(encoding="utf-8")
            for field in LEGACY_SUBSIDY_PROJECTION_FIELDS
        )
    ]
    return {
        "table": "client_payments",
        "fields": LEGACY_SUBSIDY_PROJECTION_FIELDS,
        "semantic_role": "legacy_projection_only_not_client_finance_ssot",
        "runtime_field_callers": callers,
        "writer_disposition": "blocked_no_removal_authorization",
    }


def main() -> int:
    findings = scan_production_writers(REPOSITORY_ROOT, ROOTS)
    records = [_finding_record(finding) for finding in findings]
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    evidence_path = OUTPUT_DIRECTORY / "writer_inventory_v3_candidate.findings.jsonl"
    evidence_path.write_text("".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records), encoding="utf-8")
    evidence_hash = sha256(evidence_path.read_bytes()).hexdigest()
    manifest = {
        "contract": "production-writer-inventory/v3-candidate",
        "roots": ROOTS,
        "finding_count": len(records),
        "scan_fingerprint": writer_scan_fingerprint(findings),
        "evidence_sha256": evidence_hash,
        "owner_candidate_counts": dict(sorted(Counter(record["owner_candidate"] or "unresolved" for record in records).items())),
        "candidate_disposition_counts": dict(sorted(Counter(record["candidate_disposition"] for record in records).items())),
        "writer_type_candidate_counts": dict(sorted(Counter(record["writer_type_candidate"] for record in records).items())),
        "recommendation_candidate_counts": dict(sorted(Counter(record["recommendation_candidate"] for record in records).items())),
        "high_risk_count": sum(bool(record["high_risk_tags"]) for record in records),
        "high_risk_tag_counts": dict(sorted(Counter(tag for record in records for tag in record["high_risk_tags"]).items())),
        "unresolved_count": sum(record["owner_candidate"] is None for record in records),
        "legacy_subsidy_projection_boundary": _legacy_subsidy_projection_boundary(),
        "effective_disposition": "blocked",
        "approved_to_remove": False,
    }
    _write_json(OUTPUT_DIRECTORY / "writer_inventory_v3_candidate.manifest.json", manifest)
    print(f"writer_inventory_v3_candidate findings={len(records)} unresolved={manifest['unresolved_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
