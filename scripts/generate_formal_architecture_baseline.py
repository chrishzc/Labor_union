"""Generate repeatable live evidence for the approved architecture baseline."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared_kernel.writer_inventory import scan_production_writers, writer_scan_fingerprint


EVIDENCE_PATH = (
    PROJECT_ROOT
    / "document"
    / "架構重整"
    / "03_追蹤清單與證據"
    / "evidence"
    / "formal_baseline_v1.json"
)
WRITER_ROOTS = ("api", "domains", "infrastructure", "line", "scripts", "subsystems")
RUNTIME_ROOTS = ("api", "domains", "infrastructure", "line", "scripts", "subsystems", "ui")
LEGACY_FIELDS = ("subsidy_refund_receivable", "subsidy_refund_refunded")
LEGACY_MODULE = "subsystems/client_finance/subsidy_return_reconciliation.py"
EVIDENCE_ONLY_PATHS = frozenset(
    {
        "scripts/generate_formal_architecture_baseline.py",
        "scripts/validate_formal_architecture_baseline.py",
        "scripts/generate_writer_inventory_v3_candidate.py",
        "scripts/validate_writer_inventory_v3_candidate.py",
    }
)
REQUIRED_ROUTES = ("client_refund_reversal", "finance_import", "government_subsidy")
REQUIRED_TESTS = (
    "tests/test_legacy_subsidy_projection_boundary.py",
    "tests/test_client_refund_partial_allocation.py",
    "tests/test_client_refund_return_reversal.py",
    "tests/test_client_subsidy_advance.py",
    "tests/test_client_subsidy_advance_recovery_workflow.py",
)


def _sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _runtime_python_paths() -> tuple[Path, ...]:
    return tuple(path for root in RUNTIME_ROOTS for path in sorted((PROJECT_ROOT / root).rglob("*.py")))


def _legacy_field_callers(paths: tuple[Path, ...]) -> list[str]:
    return [path.relative_to(PROJECT_ROOT).as_posix() for path in paths if path.relative_to(PROJECT_ROOT).as_posix() not in EVIDENCE_ONLY_PATHS and any(field in path.read_text(encoding="utf-8") for field in LEGACY_FIELDS)]


def _legacy_module_callers(paths: tuple[Path, ...]) -> list[str]:
    # Match the retired module/function boundary, not a current business
    # operation whose descriptive name happens to contain the same words.
    tokens = (
        "subsystems.client_finance.subsidy_return_reconciliation",
        "record_client_subsidy_return(",
    )
    return [path.relative_to(PROJECT_ROOT).as_posix() for path in paths if path.relative_to(PROJECT_ROOT).as_posix() not in EVIDENCE_ONLY_PATHS | {LEGACY_MODULE} and any(token in path.read_text(encoding="utf-8") for token in tokens)]


def _api_route_evidence() -> dict[str, bool]:
    source = (PROJECT_ROOT / "api" / "main.py").read_text(encoding="utf-8")
    return {route: f"app.include_router({route}.router)" in source for route in REQUIRED_ROUTES}


def _schema_evidence() -> dict[str, bool]:
    schema = (PROJECT_ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    ledger_schema = (PROJECT_ROOT / "db" / "schema_parts" / "111_client_finance_ledger.sql").read_text(encoding="utf-8")
    advance_schema = (PROJECT_ROOT / "db" / "schema_parts" / "138_client_subsidy_advance_settlement.sql").read_text(encoding="utf-8")
    return {
        "legacy_projection_columns_preserved": all(field in schema for field in LEGACY_FIELDS),
        "canonical_client_finance_ledger_declared": "CREATE TABLE IF NOT EXISTS client_ledger_entries" in ledger_schema,
        "subsidy_advance_recovery_schema_declared": "client_subsidy_advance_recoveries" in advance_schema,
    }


def _test_evidence() -> dict[str, str]:
    return {path: _sha256(PROJECT_ROOT / path) for path in REQUIRED_TESTS}


def main() -> int:
    runtime_paths = _runtime_python_paths()
    findings = scan_production_writers(PROJECT_ROOT, WRITER_ROOTS)
    payload = {
        "contract": "formal-architecture-baseline/v1",
        "writer_inventory": {"roots": WRITER_ROOTS, "finding_count": len(findings), "scan_fingerprint": writer_scan_fingerprint(findings)},
        "legacy_projection_boundary": {
            "fields": LEGACY_FIELDS,
            "runtime_callers": _legacy_field_callers(runtime_paths),
            "retired_legacy_module": LEGACY_MODULE,
            "retired_legacy_module_path_exists": (PROJECT_ROOT / LEGACY_MODULE).exists(),
            "legacy_module_callers": _legacy_module_callers(runtime_paths),
        },
        "api_route_wiring": _api_route_evidence(),
        "schema_evidence": _schema_evidence(),
        "test_source_sha256": _test_evidence(),
    }
    EVIDENCE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"formal_architecture_baseline writers={len(findings)} legacy_runtime_callers={len(payload['legacy_projection_boundary']['runtime_callers'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
