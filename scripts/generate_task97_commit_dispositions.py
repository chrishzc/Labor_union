"""Generate a fresh-clone, per-identity Task 97 commit disposition receipt.

The writer inventory scanner deliberately reports every ``commit()`` call.  This
artifact records the semantic review of those calls without changing production
code or treating the AST receiver name as an ownership decision.
"""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import subprocess
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


ROOTS = (
    "api",
    "domains",
    "infrastructure",
    "line",
    "scripts",
    "services",
    "subsystems",
)
SOURCE_REVISION_INPUTS = (*ROOTS, "shared_kernel/writer_inventory.py")
EVIDENCE_PATH = (
    REPOSITORY_ROOT
    / "document"
    / "架構重整"
    / "03_追蹤清單與證據"
    / "evidence"
    / "task97_repository_commit_dispositions_v1.json"
)
CLASSIFICATIONS = frozenset(
    {
        "real_violation",
        "application_owned_legitimate_outer_uow",
        "false_positive_non_transaction",
    }
)

# These are semantic decisions, not receiver-name heuristics.  The line is
# retained in the evidence so a future source move cannot silently widen the
# exception to an entire module or method.
MEDIA_STAGING_VIOLATIONS = {
    ("subsystems/line/media_archive.py", 125): (
        "media metadata is committed after filesystem promotion; the database "
        "row and bytes are not protected by a reference-aware staging protocol",
        "Replace direct metadata commit with reference-aware staging, one owning "
        "application transaction, and post-commit promotion after the media/schema gate.",
        "media staging/reference/lease schema and the required DB change gates are not available",
    ),
    ("subsystems/line/rich_menu_publication_workflow.py", 860): (
        "publication metadata is committed in a second transaction after media "
        "creation, splitting the Rich Menu publication state transition",
        "Move the publication update into the canonical outer workflow and use a "
        "post-commit media intent after the media/schema gate.",
        "media staging/reference/lease schema and the required DB change gates are not available",
    ),
}

FROZEN_GENERATOR_PATH = "scripts/generate_fake_data.py"
READ_ONLY_APPLICATIONS = {
    ("api/dependencies/line_worker_operation.py", "_next_due_at"),
    ("subsystems/knowledge_retrieval/application.py", "KnowledgeApplication._query"),
    ("subsystems/knowledge_retrieval/application.py", "KnowledgeApplication.list_items"),
    ("subsystems/knowledge_retrieval/application.py", "KnowledgeApplication.list_jobs"),
    ("subsystems/line/order_group_application.py", "LineOrderGroupQueryApplication.list"),
    ("subsystems/line/order_group_application.py", "LineOrderGroupQueryApplication.get"),
    ("subsystems/line/order_group_application.py", "LineOrderGroupQueryApplication.events"),
    ("subsystems/line/identity_management_application.py", "LineIdentityManagementApplication.list"),
    ("subsystems/line/identity_management_application.py", "LineIdentityManagementApplication.detail"),
    (
        "subsystems/line/identity_management_application.py",
        "LineIdentityManagementApplication.preview_revocation",
    ),
    (
        "subsystems/line/identity_management_application.py",
        "LineIdentityManagementApplication.preview_replacement",
    ),
    ("subsystems/scheduling/matching_notification_application.py", "MatchingNotificationApplication.get_contact_state"),
    ("subsystems/customer_service/application.py", "CustomerServiceApplication._read"),
}

# Exact application/UoW owners whose transaction semantics are covered by
# focused owner tests.  This is deliberately identity-based: a subsystem path
# alone is never evidence that a commit is legitimate.
APPLICATION_OWNED_COMMIT_SYMBOLS = {
    ("subsystems/access/authentication_session.py", "AccessControlUnitOfWork.commit"),
    ("subsystems/finance_import/ingestion.py", "ingest_finance_workbook"),
    ("subsystems/jobs/command_application.py", "DurableJobCommandApplication.enqueue"),
    ("subsystems/jobs/command_application.py", "DurableJobCancellationApplication.cancel_queued"),
    ("subsystems/line/client_binding_application.py", "_ConnectionUnitOfWork.commit"),
    ("subsystems/line/identity_review_workflow.py", "_ConnectionUnitOfWork.commit"),
    ("subsystems/line/media_archive.py", "_ConnectionUnitOfWork.commit"),
    ("subsystems/line/rich_menu_publication_workflow.py", "_ConnectionUnitOfWork.commit"),
    ("subsystems/line/user_lifecycle.py", "_ConnectionUnitOfWork.commit"),
}


@dataclass(frozen=True)
class CommitLocation:
    line: int
    receiver: str
    has_uow_context: bool
    has_connection_lifecycle: bool
    has_worker_signal: bool


def _git_revision() -> str:
    dirty = subprocess.run(
        [
            "git",
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            *SOURCE_REVISION_INPUTS,
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    if dirty.stdout.strip():
        raise RuntimeError(
            "Task 97 commit dispositions require clean, committed scanner inputs"
        )
    result = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", *SOURCE_REVISION_INPUTS],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    revision = result.stdout.strip()
    if not revision:
        raise RuntimeError("Task 97 scanner inputs have no committed source revision")
    return revision


def _call_fingerprint(call: ast.Call) -> str:
    return sha256(ast.dump(call, include_attributes=False).encode("utf-8")).hexdigest()[:16]


def _receiver(call: ast.Call) -> str:
    value = call.func.value
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        return ast.unparse(value)
    return ast.unparse(value)


class _CommitLocator(ast.NodeVisitor):
    """Mirror writer_inventory's symbol and occurrence identity rules."""

    def __init__(self) -> None:
        self.symbol_stack: list[str] = []
        self.context_stack: list[tuple[bool, bool, bool]] = []
        self.occurrences: Counter[tuple[str, str]] = Counter()
        self.locations: dict[tuple[str, str, int], CommitLocation] = {}

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.symbol_stack.append(node.name)
        self.generic_visit(node)
        self.symbol_stack.pop()

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.symbol_stack.append(node.name)
        source = ast.unparse(node)
        self.context_stack.append(
            (
                "unit_of_work" in source or "unit_of_work_factory" in source,
                any(marker in source for marker in (".begin(", ".rollback(", ".close(")),
                any(marker in node.name.lower() for marker in ("worker", "consume", "claim", "attempt", "heartbeat", "monitor")),
            )
        )
        self.generic_visit(node)
        self.context_stack.pop()
        self.symbol_stack.pop()

    visit_FunctionDef = _visit_function
    visit_AsyncFunctionDef = _visit_function

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr == "commit":
            symbol = ".".join(self.symbol_stack) or "<module>"
            key = (symbol, _call_fingerprint(node))
            self.occurrences[key] += 1
            self.locations[(symbol, key[1], self.occurrences[key])] = CommitLocation(
                node.lineno,
                _receiver(node),
                *(self.context_stack[-1] if self.context_stack else (False, False, False)),
            )
        self.generic_visit(node)


def _locations(path: str) -> dict[tuple[str, str, int], CommitLocation]:
    locator = _CommitLocator()
    locator.visit(ast.parse((REPOSITORY_ROOT / path).read_text(encoding="utf-8")))
    return locator.locations


def _semantic_owner(path: str, symbol: str) -> tuple[str, str]:
    if path == "scripts/generate_fake_data.py":
        return "validation", "maintenance"
    if path.startswith("scripts/"):
        return ("global_migration" if "migrate" in path or "backfill" in path else "validation"), "maintenance"
    if path.startswith("api/dependencies/"):
        if "line" in path:
            return "line_integration", "adapter"
        if "contract" in path:
            return "contract_signing", "adapter"
        return "global_operations", "adapter"
    if path == "line/worker.py":
        return "line_delivery", "worker"
    if path.startswith("line/"):
        return "line_integration", "adapter"
    if path.startswith("infrastructure/mysql/"):
        if "admin_capability" in path:
            return "access_control", "repository"
        if "historical_baseline" in path:
            return "historical_baseline_projection", "worker"
        if path.endswith("_worker.py"):
            return "global_operations", "worker"
        if Path(path).name in {"process_reminder_anomaly_source.py"}:
            return "anomalies", "worker"
        if path.startswith("infrastructure/mysql/line_"):
            return "line_integration", "repository"
        if "knowledge" in path:
            return "knowledge_retrieval", "repository"
        if "payroll" in path:
            return "payroll", "repository_uow"
        if "case_import" in path or "beclass" in path:
            return "case_import", "repository_uow"
        if "government" in path:
            return "government_subsidy", "repository"
        if "anomaly" in path or "reminder" in path:
            return "anomalies", "repository"
        if "staff" in path:
            return "staff_payables", "repository_uow"
        if "client" in path or "financial" in path:
            return "client_finance", "repository_uow"
        if "scheduling" in path or "service_day" in path:
            return "scheduling", "repository"
        return "global_infrastructure", "repository"
    if path.startswith("subsystems/"):
        domain = path.split("/", 2)[1]
        owner = {
            "access": "access_control",
            "anomalies": "anomalies",
            "bootstrap": "case_import",
            "case_import": "case_import",
            "client_finance": "client_finance",
            "contract_signing": "contract_signing",
            "controlled_files": "controlled_files",
            "customer_service": "customer_service",
            "finance_import": "finance_import",
            "government_subsidy": "government_subsidy",
            "jobs": "global_infrastructure",
            "knowledge_retrieval": "knowledge_retrieval",
            "line": "line_integration",
            "orders": "orders",
            "payroll": "payroll",
            "runtime_monitoring": "global_infrastructure",
            "scheduling": "scheduling",
            "staff": "staff_operations",
            "staff_payables": "staff_payables",
        }.get(domain, "owner_review_required")
        if domain == "line":
            owner = {
                "media_archive.py": "line_media",
                "media_application.py": "line_media",
                "liff_media_upload.py": "line_media",
                "rich_menu_application.py": "line_rich_menu",
                "rich_menu_binding.py": "line_rich_menu",
                "rich_menu_publication_workflow.py": "line_rich_menu",
                "rich_menu_worker.py": "line_rich_menu",
                "identity_application.py": "line_identity",
                "identity_management_application.py": "line_identity",
                "identity_review_application.py": "line_identity",
                "identity_review_workflow.py": "line_identity",
                "identity_revocation_worker.py": "line_identity",
                "client_binding_application.py": "line_identity",
                "user_lifecycle.py": "line_identity",
                "delivery_admin_application.py": "line_delivery",
                "delivery_worker.py": "line_delivery",
                "order_group_application.py": "line_order_group",
                "webhook_event_consumer.py": "line_ingress",
                "webhook_intake.py": "line_ingress",
            }.get(Path(path).name, owner)
        is_worker = "worker" in path or "worker" in symbol.lower() or symbol.startswith("_consume")
        return owner, "worker" if is_worker else ("application_query" if (path, symbol) in READ_ONLY_APPLICATIONS else "application")
    return "owner_review_required", "unclassified"


def _classify(
    finding: WriterFinding,
    location: CommitLocation,
) -> tuple[str, str, str, str]:
    path_symbol = (finding.relative_path, finding.symbol)
    exception = MEDIA_STAGING_VIOLATIONS.get((finding.relative_path, location.line))
    if exception is not None:
        basis, remediation, blocker = exception
        return "real_violation", basis, remediation, blocker
    if finding.relative_path == FROZEN_GENERATOR_PATH:
        return (
            "real_violation",
            "The frozen module guard makes the entry dead in the normal runtime, but bypassing that guard reaches mutating seed code, including multiple commits/TRUNCATE in generate_schedule_data.",
            "Retire the dead generator and replace any required fixture behavior with approved disposable validation seeders; do not revive it.",
            "Retirement still requires zero-reference evidence for operator, test, and historical callers.",
        )
    if path_symbol in READ_ONLY_APPLICATIONS:
        return (
            "real_violation",
            "Exact application symbol is a read-only Query/Preview path; committing a read-only query is a query-boundary violation even when no domain row changes.",
            "Remove the no-op commit and retain a read-only UnitOfWork/query boundary.",
            "Query contract and focused zero-write regression are required before remediation; no production edit is authorized in this lane.",
        )
    if path_symbol in APPLICATION_OWNED_COMMIT_SYMBOLS:
        return (
            "application_owned_legitimate_outer_uow",
            "Exact symbol is a reviewed Application or UnitOfWork transaction owner with focused begin/commit/rollback semantics; this disposition does not apply to sibling symbols.",
            "Retain only while its focused owner transaction and caller tests remain current.",
            "Fresh-clone caller evidence and focused transaction tests are required for terminal acceptance.",
        )
    owner, layer = _semantic_owner(finding.relative_path, finding.symbol)
    if finding.relative_path.startswith("infrastructure/mysql/"):
        if finding.symbol.endswith(".commit") and _concrete_uow_commit(finding.relative_path, finding.symbol):
            return (
                "application_owned_legitimate_outer_uow",
                "Exact concrete UnitOfWork class inherits the Global MySqlUnitOfWork and delegates commit to that caller-owned implementation; Application compositions invoke unit_of_work.commit.",
                "Retain the concrete UoW implementation; preserve caller-owned commit and its focused transaction tests.",
                "Fresh-clone caller evidence must continue to show Application/worker composition owns the UoW lifecycle.",
            )
        if _exact_worker_boundary(finding, location):
            return (
                "application_owned_legitimate_outer_uow",
                "Exact worker symbol has an explicit independent transaction lifecycle (begin/commit/rollback/close), rather than a repository save method.",
                "Retain only as a bounded worker transaction with its explicit lifecycle and retry/receipt tests.",
                "Worker ownership and terminal receipt evidence remain blocked pending focused verification.",
            )
        return (
            "real_violation",
            "Infrastructure repository/adapter symbol owns a direct commit without concrete caller-owned Global UoW evidence.",
            "Move commit/rollback to the owning Application or explicit worker UoW; repositories/adapters must issue data operations only.",
            "Exact Application/worker caller and transaction-boundary evidence is missing; no production edit is authorized in this lane.",
        )
    if finding.relative_path.startswith("api/dependencies/"):
        if path_symbol == (
            "api/dependencies/contract_external_signing.py",
            "ContractExternalSigningApplication.download_unsigned",
        ):
            return (
                "application_owned_legitimate_outer_uow",
                "The exact symbol is an Application class with an explicit UnitOfWork boundary, although its current api/dependencies location is architectural placement drift.",
                "Retain the Application-owned transaction while moving composition out of the adapter package in a focused slice.",
                "Caller registration, relocation, and focused transaction evidence remain blocked in this static-only lane.",
            )
        return (
            "real_violation",
            "API dependency/adapter symbol commits directly; worker-like naming or begin/rollback/close does not make an adapter the Application transaction owner.",
            "Move commit/rollback into the owning Application or worker composition.",
            "Exact caller and transaction-owner evidence is missing; no production edit is authorized in this lane.",
        )
    if finding.relative_path.startswith("scripts/"):
        if _governed_script(finding):
            return (
                "application_owned_legitimate_outer_uow",
                "Exact operator/migration entry is an explicitly bounded maintenance transaction; this is not a repository commit owner.",
                "Retain only behind operator governance: dry-run, exact target, backup/plan, apply confirmation, verify, and terminal receipt.",
                "Required operator receipts and target-specific evidence are not available in a fresh static clone.",
            )
        return (
            "real_violation",
            "Exact script commit is not covered by the governed migration/validation operator allowlist.",
            "Retire or rewrite the script to an approved bounded runner with explicit target, plan, backup, verify, and terminal receipt.",
            "Operator caller/target and migration governance evidence is missing; no script mutation is authorized in this lane.",
        )
    if _exact_worker_boundary(finding, location):
        return (
            "application_owned_legitimate_outer_uow",
            "Exact worker symbol has explicit transaction lifecycle evidence and owns one independent worker attempt/projection boundary.",
            "Retain the worker boundary with its explicit rollback, retry, and receipt tests.",
            "Worker caller and terminal receipt evidence remain blocked pending focused verification.",
        )
    if not location.has_uow_context:
        return (
            "real_violation",
            "Exact subsystem symbol commits without an identifiable caller-owned UnitOfWork context; path/domain naming is not used as proof of ownership.",
            "Introduce or reuse the owning Application UnitOfWork and remove direct commit ownership from this symbol.",
            "Exact outer-UoW owner and focused transaction evidence are missing; no production edit is authorized in this lane.",
        )
    basis = "The exact application symbol contains an explicit UnitOfWork context and commits after typed repository/application operations."
    return (
        "application_owned_legitimate_outer_uow",
        basis,
        "Retain the commit at this owner; any future move must preserve one outer UnitOfWork and its focused transaction test.",
        "Terminal acceptance remains blocked until owner-specific semantic tests and fresh-clone caller evidence are recorded.",
    )


def _concrete_uow_commit(path: str, symbol: str) -> bool:
    parts = symbol.split(".")
    class_name = parts[-2] if len(parts) >= 2 else ""
    tree = ast.parse((REPOSITORY_ROOT / path).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        bases = {ast.unparse(base) for base in node.bases}
        if node.name == "MySqlUnitOfWork" or "MySqlUnitOfWork" in bases or "LineMySqlUnitOfWork" in bases:
            commit_method = next(
                (
                    item for item in node.body
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "commit"
                ),
                None,
            )
            if commit_method is None:
                return False
            if node.name == "MySqlUnitOfWork":
                return True
            return any(
                isinstance(item, ast.Call)
                and isinstance(item.func, ast.Attribute)
                and isinstance(item.func.value, ast.Call)
                and isinstance(item.func.value.func, ast.Name)
                and item.func.value.func.id == "super"
                and item.func.attr == "commit"
                for item in ast.walk(commit_method)
            )
    return False


def _exact_worker_boundary(finding: WriterFinding, location: CommitLocation) -> bool:
    if finding.relative_path == "line/worker.py":
        return location.has_connection_lifecycle
    worker_named_symbol = "worker" in finding.symbol.lower()
    if worker_named_symbol:
        return location.has_connection_lifecycle or location.has_uow_context
    if not (location.has_connection_lifecycle and location.has_worker_signal):
        return False
    return finding.relative_path.startswith(("subsystems/", "infrastructure/mysql/", "api/dependencies/", "line/"))


GOVERNED_SCRIPT_SYMBOLS = {
    ("scripts/backfill_canonical_accounting_projections.py", "run_migration"),
    ("scripts/bootstrap_disposable_mysql_schema.py", "bootstrap"),
    ("scripts/import_db_snapshot_fixture_v2.py", "import_fixture"),
    ("scripts/migrate_legacy_ui_dataset.py", "migrate"),
    ("scripts/migrate_order_contract_identity.py", "migrate"),
    ("scripts/migrate_order_lifecycle_control_facts.py", "run_migration"),
    ("scripts/migrate_preserved_database_additive_schema.py", "_run_orders_library_step"),
    ("scripts/migrate_scheduling_generation_bootstrap.py", "_run_apply"),
    ("scripts/reconcile_fixture_order_dates_v2.py", "reconcile"),
    ("scripts/reset_fake_database.py", "rebuild_schema"),
    ("scripts/run_case_import_invalid_scenario.py", "run"),
    ("scripts/seed_validation_beclass_review.py", "_record_invalid_root"),
}


def _governed_script(finding: WriterFinding) -> bool:
    return (finding.relative_path, finding.symbol) in GOVERNED_SCRIPT_SYMBOLS


def _zero_reference_oracle(finding: WriterFinding, classification: str) -> str:
    if classification == "false_positive_non_transaction":
        return f"Fresh-clone static call graph for {finding.relative_path}::{finding.symbol} must show no unowned mutation caller; query/frozen path has no root-writer reference."
    if (finding.relative_path, finding.symbol) in READ_ONLY_APPLICATIONS:
        return f"Fresh-clone query oracle for {finding.relative_path}::{finding.symbol}: zero writes and zero transaction-owner side effects; all callers remain read-only."
    if finding.relative_path == FROZEN_GENERATOR_PATH:
        return f"Fresh-clone static call graph for {finding.relative_path}::{finding.symbol}: zero approved runtime callers; operator/test/historical references must be enumerated before retirement."
    if classification == "real_violation":
        return f"No zero-reference success claim for {finding.relative_path}::{finding.symbol}: exact owner/caller evidence is required before remediation or removal."
    return f"Fresh-clone static call graph for {finding.relative_path}::{finding.symbol}; every caller must resolve to the recorded owner/layer, with no repository hidden-commit caller."


def build_artifact() -> dict[str, Any]:
    source_revision = _git_revision()
    findings = tuple(
        finding
        for finding in scan_production_writers(REPOSITORY_ROOT, ROOTS)
        if finding.operation == "COMMIT"
    )
    by_path: dict[str, dict[tuple[str, str, int], CommitLocation]] = {
        path: _locations(path) for path in {finding.relative_path for finding in findings}
    }
    entries: list[dict[str, Any]] = []
    for finding in findings:
        locations = by_path[finding.relative_path]
        location = locations.get((finding.symbol, finding.fingerprint, finding.occurrence))
        if location is None:
            raise RuntimeError(f"commit location not found for {finding.identity}")
        owner, layer = _semantic_owner(finding.relative_path, finding.symbol)
        classification, basis, remediation, blocker = _classify(finding, location)
        assert classification in CLASSIFICATIONS
        entries.append(
            {
                "identity": finding.identity,
                "source_path": finding.relative_path,
                "symbol": finding.symbol,
                "line": location.line,
                "method": finding.method,
                "fingerprint": finding.fingerprint,
                "owner": owner,
                "layer": layer,
                "classification": classification,
                "analysis_basis": basis,
                "replacement_or_remediation": remediation,
                "blocker": blocker,
                "zero_reference_oracle": _zero_reference_oracle(finding, classification),
                "terminal_receipt": (
                    "TASK97-COMMIT-DISPOSITION "
                    f"{'blocked' if classification == 'real_violation' else 'accepted'}; "
                    f"identity={finding.identity}; "
                    f"classification={classification}; source_revision={source_revision}"
                ),
            }
        )
    entries.sort(key=lambda entry: str(entry["identity"]))
    classification_counts = dict(
        sorted(Counter(str(entry["classification"]) for entry in entries).items())
    )
    violation_count = classification_counts.get("real_violation", 0)
    return {
        "contract": "task97-repository-commit-dispositions/v1",
        "source_revision": source_revision,
        "scanner_roots": list(ROOTS),
        "candidate_operation": "COMMIT",
        "candidate_count": len(entries),
        "unique_identity_count": len({entry["identity"] for entry in entries}),
        "scan_fingerprint": writer_scan_fingerprint(findings),
        "classification_counts": classification_counts,
        "terminal_status": "blocked" if violation_count else "passed",
        "terminal_blocker": (
            f"{violation_count} exact commit identities remain classified as real violations."
            if violation_count
            else None
        ),
        "entries": entries,
    }


def main() -> int:
    payload = build_artifact()
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "task97_repository_commit_dispositions "
        f"candidates={payload['candidate_count']} status={payload['terminal_status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
