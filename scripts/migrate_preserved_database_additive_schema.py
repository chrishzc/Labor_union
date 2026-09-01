"""
File: migrate_preserved_database_additive_schema.py
Description: 驗證 release chain，並以本機備份證據安全執行隔離候選或原地 additive MySQL schema 升級。
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time as time_module
from typing import Any, Callable, Iterable, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pymysql

from infrastructure.migration.cutover import (
    AppendOnlyCutoverJournal,
    reconcile_switch_state,
)
from scripts.schema_assembly import validate_schema_assembly
from infrastructure.migration.maintenance import (
    MaintenanceWindowToken,
    SourcePrincipalEvidence,
)
from infrastructure.migration.mysql_safety import (
    inspect_source_read_only_principal,
)
from infrastructure.migration.preflight import (
    SourceSafetyReceipt,
    build_source_safety_receipt,
    fingerprint_source_data_evidence,
)
from infrastructure.migration.rehearsal_runtime import (
    CandidateReadSmokePort,
    CandidateRuntimeConfig,
    EphemeralCandidateRestartPort,
)
from shared_kernel.migration_release import (
    MigrationReleaseManifest,
    load_migration_release_manifest,
)

APPLY_CONFIRMATION = "APPLY_PRESERVED_DATABASE_ADDITIVE_SCHEMA"


@dataclass(frozen=True, slots=True)
class VerificationReceipt:
    verification_id: str
    phase: str
    status: str
    evidence: Mapping[str, Any]


def run_manifest_verifications(
    contracts: Iterable[Any],
    *,
    phase: str,
    validators: Mapping[str, Any],
) -> tuple[VerificationReceipt, ...]:
    selected = tuple(item for item in contracts if item.phase == phase)
    missing = [
        item.verification_id
        for item in selected
        if item.verification_id not in validators
    ]
    if missing:
        raise ValueError("verification validator missing: " + ",".join(missing))
    receipts = []
    for item in selected:
        evidence = validators[item.verification_id]()
        _require_passed_runtime_receipt(
            evidence, "verification", item.verification_id
        )
        receipts.append(
            VerificationReceipt(
                item.verification_id, item.phase, "passed", dict(evidence)
            )
        )
    return tuple(receipts)


def _post_schema_verification_validators(
    owned_objects: Mapping[str, Any],
) -> dict[str, Callable[[], Mapping[str, Any]]]:
    """Bind each released post-schema contract to its owned artifacts."""

    artifacts_by_verification: dict[str, set[str]] = {}
    for manifest in getattr(RELEASE_MANIFEST, "manifests", ()):
        artifact_names = {
            schema.artifact.name for schema in manifest.schema_artifacts
        }
        for contract in manifest.verification_contracts:
            if contract.phase != "post-schema":
                continue
            artifacts_by_verification.setdefault(
                contract.verification_id, set()
            ).update(artifact_names)

    validators: dict[str, Callable[[], Mapping[str, Any]]] = {}
    for verification_id, artifact_names in artifacts_by_verification.items():
        selected_names = tuple(sorted(artifact_names))

        def validate(
            names: tuple[str, ...] = selected_names,
        ) -> Mapping[str, Any]:
            states = {name: owned_objects.get(name) for name in names}
            if not states or any(state != "exact" for state in states.values()):
                raise UpgradeBlocked(
                    "post-schema owned objects are not exact: " + str(states)
                )
            return {"status": "passed", "owned_objects": states}

        validators[verification_id] = validate
    return validators


def restart_and_run_read_smoke(
    restart_targets: Iterable[str],
    smoke_ids: Iterable[str],
    restart_port: Any,
    smoke_port: Any,
) -> dict[str, tuple[Mapping[str, Any], ...]]:
    restart_receipts = tuple(
        _require_passed_runtime_receipt(
            restart_port.restart(target), "restart", target
        )
        for target in restart_targets
    )
    smoke_receipts = tuple(
        _require_passed_runtime_receipt(smoke_port.run(smoke_id), "smoke", smoke_id)
        for smoke_id in smoke_ids
    )
    return {
        "restart_receipts": restart_receipts,
        "smoke_receipts": smoke_receipts,
    }


def _require_passed_runtime_receipt(
    receipt: Mapping[str, Any],
    receipt_kind: str,
    receipt_id: str,
) -> Mapping[str, Any]:
    if receipt.get("status") != "passed":
        raise ValueError(f"{receipt_kind} failed: {receipt_id}")
    return dict(receipt)


ROOT = PROJECT_ROOT
LEGACY_SCHEMA_PARTS = (
    ROOT / "db" / "schema_parts" / "61_finance_import_reprocessing.sql",
    ROOT / "db" / "schema_parts" / "104_order_lifecycle_state_history.sql",
    ROOT / "db" / "schema_parts" / "105_order_service_time_terms.sql",
    ROOT / "db" / "schema_parts" / "106_order_lifecycle_control_facts.sql",
    ROOT / "db" / "schema_parts" / "107_system_alert_current_projection.sql",
    ROOT / "db" / "schema_parts" / "108_matching_records_resume_delivery.sql",
)
SCHEMA_PARTS = LEGACY_SCHEMA_PARTS
IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")
DEFAULT_RELEASE_MANIFESTS = (
    "labor_union_2026_08_02_v2.json",
    "labor_union_2026_08_08_v2_strict_v1.json",
    "labor_union_2026_08_09_v3_strict_v1.json",
    "labor_union_2026_08_09_v4_strict_v1.json",
    "labor_union_2026_08_09_v5_strict_v1.json",
    "labor_union_2026_08_09_v6_strict_v1.json",
    "labor_union_2026_08_09_v7_strict_v1.json",
    "labor_union_2026_08_09_v8_strict_v1.json",
    "labor_union_2026_08_09_v9_strict_v1.json",
    "labor_union_2026_08_12_line_stage13_strict_v1.json",
    "labor_union_2026_08_12_wp68_v1.json",
    "labor_union_2026_08_11_provisional_registration_case_issue_strict_v1.json",
    "labor_union_2026_08_11_line_stage11_v1.json",
    "labor_union_2026_08_11_line_stage12_v1.json",
    "labor_union_2026_08_13_wp72_v1.json",
    "labor_union_2026_08_14_client_refund_snapshot_v1.json",
    "labor_union_2026_08_14_government_overpayment_v1.json",
    "labor_union_2026_08_14_line_staff_self_service_v1.json",
    "labor_union_2026_08_14_government_outbox_intent_type_repair_v1.json",
    "labor_union_2026_08_14_wp77_v2.json",
    "labor_union_2026_08_14_wp80_v2.json",
    "labor_union_2026_08_14_wp90_import_warning_tracking_v1.json",
    "labor_union_2026_08_14_wp91_hcm_partial_formal_case_v1.json",
    "labor_union_2026_08_14_wp92_client_beclass_transition_binding_v1.json",
    "labor_union_2026_08_14_wp93_pending_completion_status_v1.json",
    "labor_union_2026_08_15_wp90_finance_source_warning_v1.json",
    "labor_union_2026_08_15_wp95_hcm_resubmission_v1.json",
    "labor_union_2026_08_15_staff_leave_intake_v1.json",
    "labor_union_2026_08_15_line_notification_catalog_v1.json",
    "labor_union_2026_08_16_scheduling_service_day_logs_v1.json",
    "labor_union_2026_08_16_scheduling_service_day_checkpoints_v1.json",
    "labor_union_2026_08_16_line_notification_recurring_intents_v1.json",
    "labor_union_2026_08_16_scheduling_service_day_log_outbox_retry_v1.json",
    "labor_union_2026_08_16_scheduling_rebuild_notification_invalidation_v1.json",
    "labor_union_2026_08_16_access_control_totp_root_v1.json",
    "labor_union_2026_08_16_access_control_password_challenge_v1.json",
    "labor_union_2026_08_16_access_control_security_alert_outbox_v1.json",
    "labor_union_2026_08_15_schema_assembly_v1.json",
    "labor_union_2026_08_15_staff_retirement_v1.json",
    "labor_union_2026_08_20_line_rich_menu_publication_step_saga_v1.json",
    "labor_union_2026_08_21_customer_service_human_escalation_v1.json",
    "labor_union_2026_08_22_matching_coordination_successor_v1.json",
    "labor_union_2026_08_26_controlled_file_storage_foundation_v1.json",
    "labor_union_2026_08_26_contract_external_signing_successor_v1.json",
    "labor_union_2026_08_26_historical_order_review_remediation_v1.json",
    "labor_union_2026_08_26_finance_recovery_evidence_v1.json",
    "labor_union_2026_08_27_historical_order_adoption_noop_v1.json",
    "labor_union_2026_08_27_anomaly_reclassification_disposition_v1.json",
    "labor_union_2026_08_28_historical_operational_baseline_v1.json",
    "labor_union_2026_08_28_historical_baseline_projector_v1.json",
    "labor_union_2026_08_28_service_before_replacement_v1.json",
    "labor_union_2026_08_28_order_lifecycle_pending_status_v1.json",
    "labor_union_2026_08_28_historical_baseline_projector_v2.json",
    "labor_union_2026_08_30_controlled_file_reference_finalize_leases_v1.json",
    "labor_union_2026_08_30_current_anomaly_issues_v1.json",
    "labor_union_2026_08_30_client_hcm_correction_versioning_v1.json",
    "labor_union_2026_08_30_hcm_resubmission_canonical_review_version_v1.json",
    "labor_union_2026_08_30_line_identity_role_scope_v1.json",
    "labor_union_2026_08_31_historical_owner_payment_settlement_v1.json",
    "labor_union_2026_08_31_task96_owner_contract_successors_v1.json",
    "labor_union_2026_09_01_task96_line_safe_review_link_v1.json",
    "labor_union_2026_09_01_task96_line_identity_revocation_role_binding_fk_v1.json",
    "labor_union_2026_09_01_task96_government_subsidy_return_excess_recovery_v1.json",
    "labor_union_2026_09_01_task96_scheduling_service_day_attachment_kind_v1.json",
    "labor_union_2026_09_01_historical_order_pairing_resolution_reused_v1.json",
    "labor_union_2026_09_01_historical_service_accounting_v1.json",
    "labor_union_2026_09_01_client_payment_destination_configuration_v1.json",
)
MYSQL_DUMP_MARKER = b"MySQL dump"
VERIFYABLE_CANDIDATE_STATUSES = frozenset(
    {"schema_applied", "backfilled", "verified"}
)
LEGACY_KNOWLEDGE_TABLES = frozenset({
    "knowledge_items",
    "knowledge_item_events",
    "knowledge_apply_receipts",
    "knowledge_item_versions",
    "knowledge_answer_requests",
    "knowledge_jobs",
    "knowledge_indexes",
    "knowledge_answer_receipts",
    "knowledge_answer_sources",
})
LEGACY_KNOWLEDGE_PRESERVED_TABLES = frozenset({
    "knowledge_answer_requests",
    "knowledge_jobs",
})
LEGACY_KNOWLEDGE_REBUILD_TABLES = (
    LEGACY_KNOWLEDGE_TABLES - LEGACY_KNOWLEDGE_PRESERVED_TABLES
)
LEGACY_KNOWLEDGE_DROP_ORDER = (
    "knowledge_answer_sources",
    "knowledge_answer_receipts",
    "knowledge_jobs",
    "knowledge_answer_requests",
    "knowledge_indexes",
    "knowledge_item_events",
    "knowledge_apply_receipts",
    "knowledge_item_versions",
    "knowledge_items",
)
MANIFEST_DRIVEN_RELEASE = False

OWNED_OBJECTS: dict[str, dict[str, Any]] = {
    "61_finance_import_reprocessing.sql": {
        "tables": {
            "finance_import_reprocess_runs": {
                "id", "batch_id", "actor", "classifier_version",
                "plan_fingerprint", "selected_count", "changed_count",
                "dispatch_count", "reconciled_count", "pending_count",
                "request_summary", "result_summary", "status",
            },
        },
        "triggers": {
            "trg_finance_import_reprocess_runs_before_update",
            "trg_finance_import_reprocess_runs_before_delete",
        },
    },
    "104_order_lifecycle_state_history.sql": {
        "tables": {
            "order_lifecycle_state_events": {
                "id", "case_no", "trigger_event", "before_status",
                "after_status", "actor", "business_date",
                "expected_version", "idempotency_key",
                "facts_snapshot",
            },
        },
        "triggers": {
            "trg_order_lifecycle_state_events_before_update",
            "trg_order_lifecycle_state_events_before_delete",
        },
    },
    "105_order_service_time_terms.sql": {
        "tables": {
            "orders": {
                "service_start_time", "service_end_time",
                "service_end_day_offset",
            },
        },
        "triggers": set(),
    },
    "106_order_lifecycle_control_facts.sql": {
        "tables": {
            "orders": {"lifecycle_version"},
            "order_lifecycle_control_events": {
                "id", "case_no", "control_type", "control_key", "scope",
                "action", "actor", "reason", "expected_version",
                "idempotency_key", "payload_hash", "payload_snapshot",
            },
            "order_lifecycle_control_state": {
                "case_no", "control_type", "control_key", "scope", "state",
                "current_event_id", "release_policy", "expires_at_utc",
                "confirmed_start_date", "deposit_settlement_identity_hash",
            },
            "order_lifecycle_projection_outbox": {
                "id", "case_no", "lifecycle_event_id", "intent_key",
                "scope", "alert_code", "action", "payload_hash",
                "payload_snapshot", "status", "attempt_count",
            },
        },
        "triggers": {
            "trg_order_lifecycle_control_events_before_update",
            "trg_order_lifecycle_control_events_before_delete",
            "trg_order_lifecycle_control_state_before_delete",
        },
    },
    "107_system_alert_current_projection.sql": {
        "tables": {
            "system_alerts": {
                "id", "alert_code", "source_domain", "case_key", "reason",
                "details", "status", "claimed_by", "claimed_at",
                "resolved_by", "resolved_at", "resolution_reason",
                "created_at", "updated_at",
            },
        },
        "triggers": set(),
    },
    "108_matching_records_resume_delivery.sql": {
        "tables": {
            "matching_records": {"sent_resume_at"},
        },
        "triggers": set(),
    },
}


@dataclass(frozen=True, slots=True)
class ReleaseSelection:
    """Validated migration artifacts selected for one runner operation."""

    release_id: str
    source_baseline_id: str
    fingerprint: str
    manifests: tuple[MigrationReleaseManifest, ...]
    schema_artifacts: tuple[Any, ...]
    backfills: tuple[Any, ...]
    verification_contracts: tuple[Any, ...]
    required_restart_targets: tuple[str, ...]
    post_cutover_smoke_ids: tuple[str, ...]
    artifacts: tuple[dict[str, Any], ...]
    descriptors: Mapping[str, Mapping[str, Any]]


def _legacy_release_selection() -> ReleaseSelection:
    payload = [
        {
            "name": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in SCHEMA_PARTS
    ]
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return ReleaseSelection(
        release_id="legacy-preserve-runner-v1",
        source_baseline_id="legacy-runner-owned-objects-v1",
        fingerprint=fingerprint,
        manifests=(),
        schema_artifacts=(),
        backfills=(),
        verification_contracts=(),
        required_restart_targets=(),
        post_cutover_smoke_ids=(),
        artifacts=(),
        descriptors=OWNED_OBJECTS,
    )


RELEASE_MANIFEST = _legacy_release_selection()


def configure_release_manifests(
    manifest_paths: Iterable[Path], *, include_backfills: bool = True,
) -> None:
    """Select a validated, ordered manifest chain for the current process."""

    paths = tuple(Path(path).expanduser().resolve() for path in manifest_paths)
    if not paths:
        return
    manifests = tuple(
        load_migration_release_manifest(path, ROOT) for path in paths
    )
    _validate_release_chain(manifests)
    schema_paths = tuple(
        path for manifest in manifests for path in manifest.schema_paths(ROOT)
    )
    descriptors: dict[str, dict[str, Any]] = {}
    for manifest in manifests:
        for name, descriptor in manifest.owned_object_descriptors(ROOT).items():
            if name in descriptors:
                raise UpgradeBlocked(f"duplicate migration artifact: {name}")
            descriptors[name] = descriptor
    selection = ReleaseSelection(
        release_id=manifests[-1].release_id,
        source_baseline_id=manifests[0].source_baseline_id,
        fingerprint=_manifest_chain_fingerprint(manifests),
        manifests=manifests,
        schema_artifacts=tuple(
            item for manifest in manifests for item in manifest.schema_artifacts
        ),
        backfills=(
            tuple(item for manifest in manifests for item in manifest.backfills)
            if include_backfills
            else ()
        ),
        verification_contracts=_unique_verification_contracts(manifests),
        required_restart_targets=_ordered_unique(
            target
            for manifest in manifests
            for target in manifest.required_restart_targets
        ),
        post_cutover_smoke_ids=_ordered_unique(
            smoke_id
            for manifest in manifests
            for smoke_id in manifest.post_cutover_smoke_ids
        ),
        artifacts=tuple(
            {
                "name": schema.artifact.name,
                "relative_path": schema.artifact.relative_path,
                "sha256": schema.artifact.sha256,
                "release_id": manifest.release_id,
            }
            for manifest in manifests
            for schema in manifest.schema_artifacts
        ),
        descriptors=descriptors,
    )
    global RELEASE_MANIFEST, SCHEMA_PARTS, OWNED_OBJECTS
    global MANIFEST_DRIVEN_RELEASE
    RELEASE_MANIFEST = selection
    SCHEMA_PARTS = schema_paths
    OWNED_OBJECTS = descriptors
    MANIFEST_DRIVEN_RELEASE = True


def _validate_release_chain(
    manifests: tuple[MigrationReleaseManifest, ...],
) -> None:
    release_ids = tuple(item.release_id for item in manifests)
    if len(release_ids) != len(set(release_ids)):
        raise UpgradeBlocked("migration release IDs must be unique")
    ordinals = tuple(
        int(path.name.split("_", 1)[0])
        for manifest in manifests
        for path in manifest.schema_paths(ROOT)
    )
    if ordinals != tuple(sorted(ordinals)) or len(ordinals) != len(set(ordinals)):
        raise UpgradeBlocked("migration artifacts must be unique and ordered")


def _manifest_chain_fingerprint(
    manifests: tuple[MigrationReleaseManifest, ...],
) -> str:
    payload = [
        {"release_id": item.release_id, "fingerprint": item.fingerprint}
        for item in manifests
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _unique_verification_contracts(
    manifests: tuple[MigrationReleaseManifest, ...],
) -> tuple[Any, ...]:
    contracts: dict[tuple[str, str], Any] = {}
    for manifest in manifests:
        for contract in manifest.verification_contracts:
            key = (contract.phase, contract.verification_id)
            previous = contracts.get(key)
            if previous is not None and previous != contract:
                raise UpgradeBlocked("verification contract conflict")
            contracts[key] = contract
    return tuple(contracts.values())


class UpgradeBlocked(RuntimeError):
    """Fail-closed safety or drift condition."""


def _configure_default_release_manifests() -> None:
    assembly_errors = validate_schema_assembly()
    if assembly_errors:
        raise UpgradeBlocked("schema assembly is invalid: " + "; ".join(assembly_errors))
    release_directory = ROOT / "db" / "migration_releases"
    configure_release_manifests(
        (release_directory / name for name in DEFAULT_RELEASE_MANIFESTS),
        include_backfills=False,
    )


_configure_default_release_manifests()


def _normalized_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key).casefold(): value for key, value in row.items()}


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    user: str
    password: str

    def connect(
        self,
        database: str | None = None,
        *,
        timeout_seconds: float | None = None,
    ):
        kwargs: dict[str, Any] = {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "charset": "utf8mb4",
            "cursorclass": pymysql.cursors.DictCursor,
            "autocommit": True,
        }
        if database:
            kwargs["database"] = database
        if timeout_seconds is not None:
            bounded = float(timeout_seconds)
            if not 0 < bounded <= LOCAL_ADDITIVE_MAX_DURATION_MS / 1000:
                raise ValueError("database client timeout is outside the local additive bound")
            # PyMySQL enforces these at the socket boundary.  A Python elapsed
            # check alone cannot bound a blocked server-side DDL statement.
            kwargs["connect_timeout"] = bounded
            kwargs["read_timeout"] = bounded
            kwargs["write_timeout"] = bounded
        return pymysql.connect(**kwargs)


@dataclass(frozen=True)
class DatabaseDescriptor:
    """A non-secret, single-purpose connection descriptor for rehearsal work."""

    role: str
    database: str
    config: DatabaseConfig


@dataclass(frozen=True)
class SeparateDatabaseConfig:
    """Routes source reads and candidate writes through different principals."""

    source: DatabaseDescriptor
    candidate: DatabaseDescriptor

    def connect(
        self,
        database: str | None = None,
        *,
        timeout_seconds: float | None = None,
    ):
        if database == self.source.database:
            return self.source.config.connect(database, timeout_seconds=timeout_seconds)
        if database in {None, self.candidate.database}:
            return self.candidate.config.connect(database, timeout_seconds=timeout_seconds)
        raise UpgradeBlocked("database is outside the preserve-data descriptors")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


VERIFYABLE_CANDIDATE_STATUSES = frozenset({"schema_applied", "backfilled", "verified"})
PURE_RETIREMENT_ARTIFACTS = frozenset({
    "153_retire_empty_legacy_field_inventory.sql",
})
INTENTIONALLY_RETIRED_EMPTY_TABLES = frozenset({
    "finance_import_reclassification_events",
})
DECLARED_LIFECYCLE_BACKFILL_TABLES = frozenset({
    "order_lifecycle_control_events",
    "order_lifecycle_control_state",
})


def _canonical_json(value: Any) -> bytes:
    def default(item: Any) -> Any:
        if isinstance(item, (date, datetime, time)):
            return item.isoformat()
        if isinstance(item, Decimal):
            return str(item)
        if isinstance(item, bytes):
            return {"bytes_hex": item.hex()}
        if isinstance(item, timedelta):
            return {
                "timedelta_microseconds": (
                    item.days * 86_400_000_000
                    + item.seconds * 1_000_000
                    + item.microseconds
                )
            }
        raise TypeError(f"unsupported canonical JSON type: {type(item).__name__}")

    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        default=default,
    ).encode("utf-8")


def _atomic_write(path: Path, payload: bytes) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_transient_lock_retry(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _replace_with_transient_lock_retry(source: Path, target: Path) -> None:
    """Retry short Windows scanner locks without hiding persistent failures."""
    retry_delays_seconds = (0.05, 0.1, 0.2, 0.4)
    for retry_delay_seconds in retry_delays_seconds:
        try:
            os.replace(source, target)
            return
        except PermissionError:
            time_module.sleep(retry_delay_seconds)
    os.replace(source, target)


def write_receipt(path: str | Path, receipt: Mapping[str, Any]) -> str:
    target = Path(path)
    _atomic_write(target, _canonical_json(receipt) + b"\n")
    return str(target.expanduser().resolve())


def read_receipt(path: str | Path) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise UpgradeBlocked(f"invalid receipt: {target}") from exc
    if not isinstance(data, dict):
        raise UpgradeBlocked("receipt root must be an object")
    return data


def _read_env_bytes(path: Path) -> tuple[bytes, dict[str, str]]:
    raw = path.expanduser().resolve().read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UpgradeBlocked("environment file must be strict UTF-8") from exc
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return raw, values


def config_from_env(path: Path) -> tuple[DatabaseConfig, str]:
    _, values = _read_env_bytes(path)
    source = values.get(
        "DB_DATABASE", os.getenv("DB_DATABASE", "")
    ).strip()
    return (
        DatabaseConfig(
            host=values.get(
                "DB_HOST", os.getenv("DB_HOST", "127.0.0.1")
            ),
            port=int(values.get("DB_PORT", os.getenv("DB_PORT", "3306"))),
            user=values.get("DB_USER", os.getenv("DB_USER", "root")),
            password=values.get(
                "DB_PASSWORD", os.getenv("DB_PASSWORD", "")
            ),
        ),
        source,
    )


def load_database_descriptor(
    path: Path,
    expected_role: str,
) -> DatabaseDescriptor:
    """Load a non-secret rehearsal descriptor; credentials stay in its env var."""
    try:
        payload = json.loads(path.expanduser().resolve().read_text("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpgradeBlocked("database descriptor is not valid strict UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise UpgradeBlocked("database descriptor must be an object")
    if payload.get("contract") != "preserve-data/database-descriptor/v1":
        raise UpgradeBlocked("database descriptor contract is unsupported")
    if payload.get("role") != expected_role:
        raise UpgradeBlocked(f"database descriptor must have role {expected_role}")
    _reject_descriptor_secret(payload)
    database = _descriptor_text(payload, "database")
    host = _descriptor_text(payload, "host")
    user = _descriptor_text(payload, "user")
    password_env = _descriptor_text(payload, "password_env")
    password = os.getenv(password_env, "")
    if not password:
        raise UpgradeBlocked("database descriptor password environment is empty")
    try:
        port = int(payload.get("port"))
    except (TypeError, ValueError) as exc:
        raise UpgradeBlocked("database descriptor port is invalid") from exc
    if not 1 <= port <= 65535:
        raise UpgradeBlocked("database descriptor port is invalid")
    if not IDENTIFIER.fullmatch(database):
        raise UpgradeBlocked("database descriptor database is invalid")
    return DatabaseDescriptor(
        expected_role,
        database,
        DatabaseConfig(host=host, port=port, user=user, password=password),
    )


def load_source_principal_evidence(path: Path) -> SourcePrincipalEvidence:
    payload = _read_json_object(path, "source principal evidence")
    privileges = payload.get("privileges")
    if not isinstance(privileges, list) or not all(
        isinstance(value, str) and value.strip() for value in privileges
    ):
        raise UpgradeBlocked("source principal evidence privileges are invalid")
    return SourcePrincipalEvidence(
        principal=_descriptor_text(payload, "principal"),
        source_database=_descriptor_text(payload, "source_database"),
        privileges=frozenset(privileges),
    )


def load_maintenance_token(path: Path) -> MaintenanceWindowToken:
    payload = _read_json_object(path, "maintenance token")
    required = (
        "token_id", "source_database", "source_schema_sha256",
        "source_data_sha256", "write_freeze_started_at", "expires_at",
        "issuer", "fingerprint",
    )
    try:
        values = {name: _descriptor_text(payload, name) for name in required}
    except UpgradeBlocked:
        raise
    return MaintenanceWindowToken(**values)


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.expanduser().resolve().read_text("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpgradeBlocked(f"{label} is not valid strict UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise UpgradeBlocked(f"{label} must be an object")
    return payload


def _descriptor_text(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise UpgradeBlocked(f"database descriptor {name} is required")
    return value.strip()


def _reject_descriptor_secret(payload: Mapping[str, Any]) -> None:
    if any(name in payload for name in ("password", "DB_PASSWORD")):
        raise UpgradeBlocked("database descriptor must not contain a password")


def validate_database_names(source: str, candidate: str) -> None:
    if not IDENTIFIER.fullmatch(source) or not IDENTIFIER.fullmatch(candidate):
        raise UpgradeBlocked("database names must match [A-Za-z0-9_]+")
    if source.casefold() == candidate.casefold():
        raise UpgradeBlocked("candidate database must differ from source")


def validate_rehearsal_database_names(source: str, candidate: str) -> None:
    validate_database_names(source, candidate)
    for database in (source, candidate):
        if not database.casefold().startswith("lu_test_"):
            raise UpgradeBlocked(
                "rehearsal databases must use the lu_test_* namespace"
            )


def _require_production_authority_credential_gate(args: argparse.Namespace) -> None:
    """Formal runs require the reviewed principal and maintenance-window evidence."""
    if args.rehearsal:
        return
    required = (
        args.source_read_descriptor,
        args.candidate_write_descriptor,
        args.source_principal_evidence,
        args.maintenance_token,
        args.receipt_directory,
    )
    if not all(required):
        raise UpgradeBlocked(
            "production credential gate requires source/candidate descriptors, "
            "source principal evidence, maintenance token, and receipt directory"
        )
    if not all(Path(value).expanduser().is_file() for value in required[:-1]):
        raise UpgradeBlocked(
            "production credential gate requires existing safety evidence files"
        )


def build_descriptor_runtime(
    source_descriptor_path: Path,
    candidate_descriptor_path: Path,
    source: str,
    candidate: str,
) -> SeparateDatabaseConfig:
    source_descriptor = load_database_descriptor(
        source_descriptor_path, "source-read"
    )
    candidate_descriptor = load_database_descriptor(
        candidate_descriptor_path, "candidate-write"
    )
    if source_descriptor.database != source:
        raise UpgradeBlocked("source descriptor database identity mismatch")
    if candidate_descriptor.database != candidate:
        raise UpgradeBlocked("candidate descriptor database identity mismatch")
    if (
        source_descriptor.config.host == candidate_descriptor.config.host
        and source_descriptor.config.port == candidate_descriptor.config.port
        and source_descriptor.config.user == candidate_descriptor.config.user
    ):
        raise UpgradeBlocked("source and candidate principals must differ")
    _require_dedicated_rehearsal_databases(source, candidate)
    return SeparateDatabaseConfig(source_descriptor, candidate_descriptor)


def _require_dedicated_rehearsal_databases(source: str, candidate: str) -> None:
    forbidden = {"mysql_db", "union_db"}
    if source.casefold() in forbidden or candidate.casefold() in forbidden:
        raise UpgradeBlocked("operational databases are not rehearsal targets")


def _candidate_schema_is_exact(states: Mapping[str, str]) -> bool:
    return all(
        state == "exact" or (
            name in PURE_RETIREMENT_ARTIFACTS and state == "absent"
        )
        for name, state in states.items()
    )


def run_source_safety_preflight(
    config: SeparateDatabaseConfig,
    source: str,
    candidate: str,
    principal_evidence_path: Path,
    maintenance_token_path: Path,
    receipt_directory: Path,
    *,
    mode: str,
) -> dict[str, Any]:
    """Validate independent source authority and immutable plan facts."""
    plan = build_plan(config, source, candidate)
    source_safety = _validate_live_source_safety(
        config, source, plan, principal_evidence_path, maintenance_token_path
    )
    receipt = _source_safety_receipt(mode, candidate, plan, source_safety)
    receipt_path = _preflight_receipt_path(receipt_directory, mode, plan)
    saved_receipt, created = _write_append_only_receipt(receipt_path, receipt)
    if created:
        _append_journal_event(
            receipt_directory, "source_safety_preflight", saved_receipt
        )
    return {**saved_receipt, "receipt_path": str(receipt_path)}


def _validate_live_source_safety(
    config: SeparateDatabaseConfig,
    source: str,
    plan: Mapping[str, Any],
    principal_evidence_path: Path,
    maintenance_token_path: Path,
) -> SourceSafetyReceipt:
    declared_evidence = load_source_principal_evidence(principal_evidence_path)
    inspected_evidence = inspect_source_read_only_principal(
        config.source.config, source
    )
    if declared_evidence != inspected_evidence:
        raise UpgradeBlocked("source principal evidence does not match live principal")
    token = load_maintenance_token(maintenance_token_path)
    try:
        source_safety = build_source_safety_receipt(
            plan,
            inspected_evidence,
            token,
            now=datetime.now(timezone.utc),
        )
    except ValueError as exc:
        raise UpgradeBlocked(str(exc)) from exc
    return source_safety


def _source_safety_receipt(
    mode: str,
    candidate: str,
    plan: Mapping[str, Any],
    source_safety: SourceSafetyReceipt,
) -> dict[str, Any]:
    return {
        "kind": "preserve_data_source_safety_preflight",
        "status": "passed",
        "created_at": _now(),
        "mode": mode,
        "source": asdict(source_safety),
        "plan_fingerprint": plan.get("plan_fingerprint"),
        "candidate_database": candidate,
    }


def recover_interrupted_switch(
    environment_file: Path,
    switch_receipt_path: Path,
    receipt_directory: Path,
) -> dict[str, Any]:
    """Report the sole safe next action; recovery never guesses a config state."""
    receipt = read_receipt(switch_receipt_path)
    before_sha256 = str(receipt.get("before_sha256") or "")
    after_sha256 = str(receipt.get("after_sha256") or "")
    if not before_sha256 or not after_sha256:
        raise UpgradeBlocked("switch receipt lacks configuration digests")
    current_sha256 = _sha256_file(environment_file.expanduser().resolve())
    restart_receipt = receipt.get("post_restart") or {}
    reconciliation = reconcile_switch_state(
        current_config_sha256=current_sha256,
        before_sha256=before_sha256,
        after_sha256=after_sha256,
        restart_receipt_present=bool(restart_receipt.get("restart_receipts")),
        smoke_receipt_present=bool(restart_receipt.get("read_smokes")),
    )
    result = {
        "kind": "interrupted_switch_recovery",
        "status": "reconciled",
        "created_at": _now(),
        "switch_receipt_sha256": _sha256_file(switch_receipt_path),
        "state": reconciliation.state,
        "next_action": reconciliation.next_action,
    }
    saved_receipt, created = _write_append_only_receipt(
        _recovery_receipt_path(receipt_directory, switch_receipt_path), result
    )
    if created:
        _append_journal_event(receipt_directory, "switch_reconciled", saved_receipt)
    if reconciliation.state == "ambiguous":
        raise UpgradeBlocked("interrupted switch state is ambiguous; manual review required")
    return saved_receipt


def _preflight_receipt_path(
    receipt_directory: Path, mode: str, plan: Mapping[str, Any]
) -> Path:
    fingerprint = str(plan.get("plan_fingerprint") or "unknown")[:16]
    return receipt_directory.expanduser().resolve() / (
        f"preflight-{mode}-{fingerprint}.json"
    )


def _recovery_receipt_path(receipt_directory: Path, switch_receipt: Path) -> Path:
    digest = _sha256_file(switch_receipt)[:16]
    return receipt_directory.expanduser().resolve() / f"recovery-{digest}.json"


def _write_append_only_receipt(
    path: Path, receipt: Mapping[str, Any]
) -> tuple[dict[str, Any], bool]:
    payload = _canonical_json(receipt)
    if path.exists():
        existing = read_receipt(path)
        if _receipt_without_timestamp(existing) != _receipt_without_timestamp(receipt):
            raise UpgradeBlocked("append-only receipt path already has different content")
        return existing, False
    _atomic_write(path, payload)
    return dict(receipt), True


def _receipt_without_timestamp(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in receipt.items() if key != "created_at"
    }


def _append_journal_event(
    receipt_directory: Path, event_type: str, receipt: Mapping[str, Any]
) -> None:
    AppendOnlyCutoverJournal(
        receipt_directory.expanduser().resolve() / "cutover.journal.jsonl"
    ).append(event_type, receipt)


def _database_connection_config(
    config: DatabaseConfig | SeparateDatabaseConfig,
    database: str,
) -> DatabaseConfig:
    if isinstance(config, SeparateDatabaseConfig):
        if database == config.source.database:
            return config.source.config
        if database == config.candidate.database:
            return config.candidate.config
        raise UpgradeBlocked("database is outside the preserve-data descriptors")
    return config


def _candidate_connection_config(
    config: DatabaseConfig | SeparateDatabaseConfig,
    candidate: str,
) -> DatabaseConfig:
    return _database_connection_config(config, candidate)


def server_identity(
    config: DatabaseConfig | SeparateDatabaseConfig, database: str
) -> dict[str, Any]:
    connection = config.connect(database)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT DATABASE() AS db, @@hostname AS server, "
                "@@version AS version"
            )
            row = cursor.fetchone()
    finally:
        connection.close()
    if not row or row.get("db") != database:
        raise UpgradeBlocked("connected database does not match the explicit target")
    if not str(row.get("server") or "").strip():
        raise UpgradeBlocked("connected MySQL server identity is unavailable")
    connection_config = _database_connection_config(config, database)
    if not str(connection_config.host).strip():
        raise UpgradeBlocked("configured host is required for the connected-host check")
    return {
        "database": row["db"],
        "server": str(row["server"]),
        "version": str(row["version"]),
        "host": connection_config.host,
        "port": connection_config.port,
    }


def database_exists(
    config: DatabaseConfig | SeparateDatabaseConfig, database: str
) -> bool:
    connection = config.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS n FROM information_schema.schemata "
                "WHERE schema_name=%s",
                (database,),
            )
            return int(cursor.fetchone()["n"]) == 1
    finally:
        connection.close()


def _show_create_owned_table_names() -> set[str]:
    """Return every owned table whose exact DDL may be needed by a comparator."""
    return {
        table
        for owned in OWNED_OBJECTS.values()
        for table in (
            *owned.get("tables", {}),
            *(key[0] for key in owned.get("checks", {})),
        )
    }


def _schema_snapshot(
    config: DatabaseConfig,
    database: str,
    *,
    owned_part: str | None = None,
) -> dict[str, Any]:
    scoped_tables: set[str] | None = None
    scoped_triggers: set[str] | None = None
    scoped_views: set[str] | None = None
    if owned_part is not None:
        expected = OWNED_OBJECTS[owned_part]
        scoped_tables = set(expected.get("tables", {}))
        scoped_tables.update(expected.get("parent_columns", {}))
        for contract_name in ("indexes", "foreign_keys", "checks"):
            scoped_tables.update(
                table_name
                for table_name, _ in expected.get(contract_name, {})
            )
        scoped_triggers = set(expected.get("triggers", {}))
        scoped_views = set(expected.get("views", {}))
    connection = config.connect(database)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name,column_name,column_type,is_nullable,"
                "column_default,extra,generation_expression "
                "FROM information_schema.columns "
                "WHERE table_schema=%s ORDER BY table_name,ordinal_position",
                (database,),
            )
            columns = [_normalized_row(row) for row in cursor.fetchall()]
            if scoped_tables is not None:
                columns = [
                    row for row in columns
                    if row["table_name"] in scoped_tables
                ]
            cursor.execute(
                "SELECT table_name,index_name,non_unique,"
                "GROUP_CONCAT(column_name ORDER BY seq_in_index) AS columns "
                "FROM information_schema.statistics WHERE table_schema=%s "
                "GROUP BY table_name,index_name,non_unique "
                "ORDER BY table_name,index_name",
                (database,),
            )
            indexes = [_normalized_row(row) for row in cursor.fetchall()]
            if scoped_tables is not None:
                indexes = [
                    row for row in indexes
                    if row["table_name"] in scoped_tables
                ]
            cursor.execute(
                "SELECT trigger_name,event_manipulation,event_object_table,"
                "action_timing,action_statement FROM information_schema.triggers "
                "WHERE trigger_schema=%s ORDER BY trigger_name",
                (database,),
            )
            triggers = [_normalized_row(row) for row in cursor.fetchall()]
            if scoped_tables is not None and scoped_triggers is not None:
                triggers = [
                    row for row in triggers
                    if row["trigger_name"] in scoped_triggers
                    or row["event_object_table"] in scoped_tables
                ]
            cursor.execute(
                "SELECT table_name,view_definition FROM information_schema.views "
                "WHERE table_schema=%s ORDER BY table_name",
                (database,),
            )
            views = [_normalized_row(row) for row in cursor.fetchall()]
            if scoped_views is not None:
                views = [
                    row for row in views
                    if row["table_name"] in scoped_views
                ]
            cursor.execute(
                "SELECT tc.table_name,tc.constraint_name,tc.constraint_type,"
                "tc.enforced,cc.check_clause "
                "FROM information_schema.table_constraints tc "
                "LEFT JOIN information_schema.check_constraints cc "
                "ON cc.constraint_schema=tc.constraint_schema "
                "AND cc.constraint_name=tc.constraint_name "
                "WHERE tc.constraint_schema=%s "
                "ORDER BY tc.table_name,tc.constraint_name",
                (database,),
            )
            constraints = [
                _normalized_row(row) for row in cursor.fetchall()
            ]
            if scoped_tables is not None:
                constraints = [
                    row for row in constraints
                    if row["table_name"] in scoped_tables
                ]
            cursor.execute(
                "SELECT table_name,constraint_name,column_name,"
                "ordinal_position,referenced_table_name,"
                "referenced_column_name "
                "FROM information_schema.key_column_usage "
                "WHERE constraint_schema=%s "
                "ORDER BY table_name,constraint_name,ordinal_position",
                (database,),
            )
            key_columns = [
                _normalized_row(row) for row in cursor.fetchall()
            ]
            if scoped_tables is not None:
                key_columns = [
                    row for row in key_columns
                    if row["table_name"] in scoped_tables
                ]
            cursor.execute(
                "SELECT table_name,constraint_name,update_rule,delete_rule "
                "FROM information_schema.referential_constraints "
                "WHERE constraint_schema=%s "
                "ORDER BY table_name,constraint_name",
                (database,),
            )
            foreign_keys = [
                _normalized_row(row) for row in cursor.fetchall()
            ]
            if scoped_tables is not None:
                foreign_keys = [
                    row for row in foreign_keys
                    if row["table_name"] in scoped_tables
                ]
            owned_table_names = (
                scoped_tables
                if scoped_tables is not None
                else _show_create_owned_table_names()
            )
            table_names = sorted(
                {
                    row["table_name"] for row in columns
                    if row["table_name"] in owned_table_names
                    or row["table_name"] == "finance_import_batches"
                }
            )
            show_create_tables: dict[str, str] = {}
            for table_name in table_names:
                safe_table = table_name.replace("`", "``")
                cursor.execute(f"SHOW CREATE TABLE `{safe_table}`")
                create_row = _normalized_row(cursor.fetchone() or {})
                create_sql = create_row.get("create table")
                if not isinstance(create_sql, str):
                    raise UpgradeBlocked(
                        f"SHOW CREATE TABLE missing for {table_name}"
                    )
                show_create_tables[table_name] = create_sql
    finally:
        connection.close()
    payload = {
        "columns": columns,
        "indexes": indexes,
        "triggers": triggers,
        "views": views,
        "constraints": constraints,
        "key_columns": key_columns,
        "foreign_keys": foreign_keys,
        "show_create_tables": show_create_tables,
    }
    return {"sha256": _sha256_bytes(_canonical_json(payload)), **payload}


def _table_evidence(config: DatabaseConfig, database: str) -> dict[str, Any]:
    connection = config.connect(database)
    evidence: dict[str, Any] = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema=%s AND table_type='BASE TABLE' "
                "ORDER BY table_name",
                (database,),
            )
            names = [
                _normalized_row(row)["table_name"]
                for row in cursor.fetchall()
            ]
            for name in names:
                cursor.execute(f"SELECT COUNT(*) AS n FROM `{name}`")
                count = int(cursor.fetchone()["n"])
                cursor.execute(f"CHECKSUM TABLE `{name}`")
                checksum_row = _normalized_row(cursor.fetchone() or {})
                checksum = checksum_row.get("checksum")
                cursor.execute(
                    "SELECT column_name FROM information_schema.key_column_usage "
                    "WHERE table_schema=%s AND table_name=%s "
                    "AND constraint_name='PRIMARY' ORDER BY ordinal_position",
                    (database, name),
                )
                primary = [
                    _normalized_row(row)["column_name"]
                    for row in cursor.fetchall()
                ]
                pk_hash = None
                if primary:
                    projection = ",".join(f"`{column}`" for column in primary)
                    cursor.execute(
                        f"SELECT {projection} FROM `{name}` "
                        f"ORDER BY {projection}"
                    )
                    pk_hash = _sha256_bytes(
                        _canonical_json(cursor.fetchall())
                    )
                evidence[name] = {
                    "count": count,
                    "checksum": checksum,
                    "primary_key_sha256": pk_hash,
                }
    finally:
        connection.close()
    return evidence


def _local_stable_table_fingerprint(
    count: int, checksum: Any, primary_key_sha256: str | None,
) -> str:
    """Stable row evidence independent of dump formatting or auto-increment metadata."""
    return _sha256_bytes(_canonical_json({
        "count": int(count),
        "checksum": checksum,
        "primary_key_sha256": primary_key_sha256,
    }))


def _local_data_fingerprint(evidence: Mapping[str, str]) -> str:
    return _sha256_bytes(_canonical_json(dict(sorted(evidence.items()))))


def _normalize_database_qualifiers(
    value: Any, databases: Iterable[str]
) -> str:
    text = str(value or "")
    for database in databases:
        qualified = re.compile(
            rf"(?i)(?:`{re.escape(database)}`|{re.escape(database)})\."
        )
        text = qualified.sub("<database>.", text)
    return text


def _restored_schema_program_evidence(
    snapshot: Mapping[str, Any],
    database: str,
    equivalent_databases: Iterable[str] = (),
    *,
    include_triggers: bool = True,
) -> dict[str, Any]:
    database_names = (database, *tuple(equivalent_databases))
    triggers = [
        {
            "trigger_name": row["trigger_name"],
            "event_manipulation": row["event_manipulation"],
            "event_object_table": row["event_object_table"],
            "action_timing": row["action_timing"],
            "action_statement": _normalize_database_qualifiers(
                row["action_statement"], database_names
            ),
        }
        for row in snapshot["triggers"]
        if include_triggers
    ]
    views = [
        {
            "table_name": row["table_name"],
            "view_definition": _normalize_database_qualifiers(
                row["view_definition"], database_names
            ),
        }
        for row in snapshot["views"]
    ]
    payload = {"triggers": triggers, "views": views}
    return {
        **payload,
        "sha256": _sha256_bytes(_canonical_json(payload)),
    }


def _system_alert_projection_state(snapshot: Mapping[str, Any]) -> str:
    rows = [
        row for row in snapshot["columns"]
        if row["table_name"] == "system_alerts"
    ]
    if not rows:
        return "drift"
    columns = {row["column_name"]: row for row in rows}
    names = set(columns)
    legacy_names = {
        "id", "event_type", "description", "status", "created_at",
        "resolved_at", "resolved_by",
    }
    current_names = {
        "id", "alert_code", "source_domain", "case_key", "reason", "details",
        "status", "claimed_by", "claimed_at", "resolved_by", "resolved_at",
        "resolution_reason", "created_at", "updated_at",
    }
    if names == legacy_names:
        expected = {
            "id": ("int", "NO"),
            "event_type": ("varchar(50)", "NO"),
            "description": ("text", "NO"),
            "status": ("enum('pending','resolved')", "YES"),
            "created_at": ("timestamp", "YES"),
            "resolved_at": ("timestamp", "YES"),
            "resolved_by": ("varchar(50)", "YES"),
        }
        return (
            "absent"
            if all(
                str(columns[name]["column_type"]).casefold() == column_type
                and columns[name]["is_nullable"] == nullable
                for name, (column_type, nullable) in expected.items()
            )
            else "drift"
        )
    if not (
        names == current_names
        or names == current_names | {"event_type", "description"}
    ):
        # Migration 107 adds all projection columns in one ALTER statement.
        # A proper subset is therefore not a resumable statement boundary.
        return "drift"
    transitional_with_legacy = (
        names == current_names | {"event_type", "description"}
    )
    expected = {
        "id": ("int", "NO"),
        "alert_code": ("varchar(50)", "NO"),
        "source_domain": ("varchar(50)", "NO"),
        "case_key": ("varchar(100)", "NO"),
        "reason": ("varchar(500)", "NO"),
        "details": ("json", "NO"),
        "status": ("enum('open','claimed','resolved')", "NO"),
        "claimed_by": ("varchar(100)", "YES"),
        "claimed_at": ("datetime", "YES"),
        "resolved_by": ("varchar(100)", "YES"),
        "resolved_at": ("datetime", "YES"),
        "resolution_reason": ("varchar(500)", "YES"),
        "created_at": ("timestamp", "YES"),
        "updated_at": ("timestamp", "YES"),
    }
    for name, (column_type, nullable) in expected.items():
        actual_type = str(columns[name]["column_type"]).casefold()
        actual_nullable = columns[name]["is_nullable"]
        if transitional_with_legacy and name == "status":
            allowed_status = {
                "enum('pending','resolved')",
                "enum('pending','open','claimed','resolved')",
                "enum('open','claimed','resolved')",
            }
            if actual_type not in allowed_status:
                return "drift"
            if actual_nullable not in {"YES", "NO"}:
                return "drift"
            continue
        if transitional_with_legacy and name == "resolved_by":
            if actual_type not in {"varchar(50)", "varchar(100)"}:
                return "drift"
            if actual_nullable != "YES":
                return "drift"
            continue
        if transitional_with_legacy and name == "resolved_at":
            if actual_type not in {"timestamp", "datetime"}:
                return "drift"
            if actual_nullable != "YES":
                return "drift"
            continue
        if actual_type != column_type:
            return "drift"
        if (
            transitional_with_legacy
            and name in {
                "alert_code", "source_domain", "case_key", "reason",
                "details",
            }
        ):
            if actual_nullable not in {"YES", "NO"}:
                return "drift"
        elif actual_nullable != nullable:
            return "drift"
    if transitional_with_legacy:
        for name in (
            "alert_code", "source_domain", "case_key", "reason", "details",
            "claimed_by", "claimed_at", "resolution_reason",
        ):
            if columns[name]["column_default"] is not None:
                return "drift"
        status_default = columns["status"]["column_default"]
        if status_default not in {"pending", "open"}:
            return "drift"
        if "on update current_timestamp" not in str(
            columns["updated_at"]["extra"]
        ).casefold():
            return "drift"
        final_columns = (
            all(
                columns[name]["is_nullable"] == "NO"
                for name in {
                    "alert_code", "source_domain", "case_key", "reason",
                    "details", "status",
                }
            )
            and columns["status"]["column_type"].casefold()
            == "enum('open','claimed','resolved')"
            and status_default == "open"
            and columns["event_type"]["is_nullable"] == "YES"
            and columns["description"]["is_nullable"] == "YES"
            and columns["resolved_by"]["column_type"].casefold()
            == "varchar(100)"
            and columns["resolved_at"]["column_type"].casefold()
            == "datetime"
        )
        if not final_columns:
            return "partial"
    if (
        columns["status"]["column_default"] != "open"
        or "on update current_timestamp" not in str(
            columns["updated_at"]["extra"]
        ).casefold()
    ):
        return "drift"
    for name in {"event_type", "description"} & names:
        if columns[name]["is_nullable"] != "YES":
            return "drift"
    indexes = {
        row["index_name"]: (
            int(row["non_unique"]), str(row["columns"]).casefold()
        )
        for row in snapshot["indexes"]
        if row["table_name"] == "system_alerts"
    }
    unique_identity = indexes.get("uq_alert_case")
    status_index = indexes.get("idx_system_alert_status")
    if (
        unique_identity is not None
        and unique_identity != (0, "alert_code,case_key")
    ):
        return "drift"
    if status_index is not None and status_index != (1, "status"):
        return "drift"
    if (
        transitional_with_legacy
        and (unique_identity is None or status_index is None)
    ):
        return "partial"
    if unique_identity is None or status_index is None:
        return "drift"
    return "exact"


def _matching_records_resume_delivery_state(
    snapshot: Mapping[str, Any],
) -> str:
    rows = [
        row for row in snapshot["columns"]
        if row["table_name"] == "matching_records"
    ]
    if not rows:
        return "drift"
    columns = {row["column_name"]: row for row in rows}
    required = {
        "id", "case_no", "staff_id", "caregiver_accepted",
        "sent_at", "replied_at", "sent_info_1_at", "sent_info_2_at",
    }
    missing = required - set(columns)
    if missing:
        return "partial" if required.intersection(columns) else "drift"
    column = columns.get("sent_resume_at")
    if column is None:
        return "absent"
    if (
        str(column["column_type"]).casefold() == "datetime"
        and column["is_nullable"] == "YES"
        and column["column_default"] is None
        and str(column["extra"] or "") == ""
        and str(column.get("generation_expression") or "") == ""
    ):
        return "exact"
    return "drift"


GOVERNMENT_OUTBOX_REPAIR_ARTIFACT = (
    "192_government_subsidy_outbox_intent_type_repair.sql"
)
GOVERNMENT_OUTBOX_INTENTS_BEFORE_REPAIR = (
    "government_subsidy_receipt_applied",
    "government_subsidy_receipt_allocated",
    "government_subsidy_reversal_applied",
    "government_subsidy_anomaly_root_changed",
)
GOVERNMENT_OUTBOX_INTENTS_AFTER_REPAIR = (
    *GOVERNMENT_OUTBOX_INTENTS_BEFORE_REPAIR,
    "government_subsidy_overpayment_established",
    "government_subsidy_overpayment_offset",
    "government_overpayment_return_payable",
    "government_overpayment_return_payout",
)


def _enum_column_type(values: Iterable[str]) -> str:
    return "enum(" + ",".join(f"'{value}'" for value in values) + ")"


def _government_outbox_intent_type_repair_state(
    snapshot: Mapping[str, Any],
) -> str:
    column = next((
        row for row in snapshot["columns"]
        if row["table_name"] == "government_subsidy_outbox"
        and row["column_name"] == "intent_type"
    ), None)
    if column is None:
        return "drift"
    actual = _normalize_column_type_contract(column["column_type"])
    if actual == _enum_column_type(GOVERNMENT_OUTBOX_INTENTS_AFTER_REPAIR):
        return "exact"
    if actual == _enum_column_type(GOVERNMENT_OUTBOX_INTENTS_BEFORE_REPAIR):
        return "absent"
    return "drift"


def _owned_classification(
    snapshot: Mapping[str, Any], *, defer_missing_triggers: bool = False
) -> dict[str, str]:
    present_columns: dict[str, set[str]] = {}
    for row in snapshot["columns"]:
        present_columns.setdefault(row["table_name"], set()).add(
            row["column_name"]
        )
    present_triggers = {row["trigger_name"] for row in snapshot["triggers"]}
    legacy_knowledge_state = _legacy_knowledge_schema_state(snapshot)
    result: dict[str, str] = {}
    for part, expected in OWNED_OBJECTS.items():
        if {"indexes", "foreign_keys", "checks"} <= set(expected):
            result[part] = _release_descriptor_metadata_state(
                snapshot,
                part,
                expected,
                defer_missing_triggers=defer_missing_triggers,
            )
            continue
        if part in PURE_RETIREMENT_ARTIFACTS:
            has_retired_table = any(
                table in present_columns for table in INTENTIONALLY_RETIRED_EMPTY_TABLES
            )
            has_retired_trigger = any(
                "reclassification_events" in trigger for trigger in present_triggers
            )
            result[part] = "partial" if has_retired_table or has_retired_trigger else "absent"
            continue
        if expected.get("views"):
            result[part] = _descriptor_presence_state(
                expected,
                present_columns,
                present_triggers,
                snapshot.get("views", ()),
                defer_missing_triggers=defer_missing_triggers,
            )
            continue
        if (
            part in {
                "148_knowledge_retrieval.sql",
                "163_knowledge_runtime.sql",
            }
            and legacy_knowledge_state is not None
        ):
            result[part] = (
                "partial"
                if legacy_knowledge_state == "exact"
                else "drift"
            )
            continue
        if part == "107_system_alert_current_projection.sql":
            result[part] = _system_alert_projection_state(snapshot)
            continue
        if part == "108_matching_records_resume_delivery.sql":
            result[part] = _matching_records_resume_delivery_state(snapshot)
            continue
        if part in {
            "61_finance_import_reprocessing.sql",
            "104_order_lifecycle_state_history.sql",
            "105_order_service_time_terms.sql",
            "106_order_lifecycle_control_facts.sql",
            "148_knowledge_retrieval.sql",
            "163_knowledge_runtime.sql",
            "186_line_identity_management.sql",
        }:
            if part == "186_line_identity_management.sql":
                result[part] = _line_identity_management_state(snapshot)
                continue
            result[part] = _canonical_artifact_metadata_state(
                snapshot, part, defer_missing_triggers=defer_missing_triggers
            )
            continue
        table_states = []
        for table, columns in expected["tables"].items():
            actual = present_columns.get(table)
            if actual is None:
                table_states.append("absent")
            elif columns.issubset(actual):
                table_states.append("exact")
            elif not columns.intersection(actual):
                table_states.append("absent")
            else:
                table_states.append("partial")
        trigger_states = [
            "exact" if trigger in present_triggers else "absent"
            for trigger in expected["triggers"]
            if not defer_missing_triggers or trigger in present_triggers
        ]
        states = table_states + trigger_states
        if states and all(state == "absent" for state in states):
            result[part] = "absent"
        elif states and all(state == "exact" for state in states):
            result[part] = "exact"
        elif "drift" in states:
            result[part] = "drift"
        else:
            result[part] = "partial"
    for artifact in RELEASE_MANIFEST.artifacts:
        name = str(artifact["name"])
        if name in result:
            continue
        if name == GOVERNMENT_OUTBOX_REPAIR_ARTIFACT:
            result[name] = _government_outbox_intent_type_repair_state(snapshot)
            continue
        descriptor = RELEASE_MANIFEST.descriptors.get(name)
        if descriptor is None:
            raise UpgradeBlocked(f"missing descriptor for release artifact: {name}")
        result[name] = _descriptor_presence_state(
            descriptor, present_columns, present_triggers, snapshot.get("views", ()),
            defer_missing_triggers=defer_missing_triggers,
        )
    return result


def _descriptor_presence_state(
    descriptor: Mapping[str, Any],
    present_columns: Mapping[str, set[str]],
    present_triggers: set[str],
    present_views: Iterable[Mapping[str, Any]] = (),
    *,
    defer_missing_triggers: bool = False,
) -> str:
    """Classify an append-only artifact by its released table/trigger names."""
    states: list[str] = []
    for table, columns in (descriptor.get("tables") or {}).items():
        actual = present_columns.get(str(table))
        required = {str(column) for column in columns}
        if actual is None:
            states.append("absent")
        elif required.issubset(actual):
            states.append("exact")
        elif required.intersection(actual):
            states.append("partial")
        else:
            states.append("absent")
    for trigger in descriptor.get("triggers") or ():
        if not defer_missing_triggers or str(trigger) in present_triggers:
            states.append("exact" if str(trigger) in present_triggers else "absent")
    states.extend(_owned_view_states(descriptor, present_views))
    if not states or all(state == "absent" for state in states):
        return "absent"
    if "drift" in states:
        return "drift"
    if all(state == "exact" for state in states):
        return "exact"
    return "partial"


def _owned_view_states(
    descriptor: Mapping[str, Any], present_views: Iterable[Mapping[str, Any]],
) -> list[str]:
    actual = {
        str(view["table_name"]): _view_definition_digest(view["view_definition"])
        for view in present_views
    }
    states: list[str] = []
    for view_name, contract in (descriptor.get("views") or {}).items():
        actual_digest = actual.get(str(view_name))
        if actual_digest is None:
            states.append("absent")
        elif actual_digest == contract["definition_sha256"]:
            states.append("exact")
        else:
            states.append("drift")
    return states


def _view_definition_digest(definition: Any) -> str:
    without_database = re.sub(
        r"(\b(?:from|join)\s*(?:\(\s*)*)`[^`]+`\.",
        r"\1",
        str(definition),
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"\s+", " ", without_database.strip()).casefold()
    return _sha256_bytes(normalized.encode("utf-8"))


def schema_artifacts() -> list[dict[str, Any]]:
    artifacts = []
    for path in SCHEMA_PARTS:
        raw = path.read_bytes()
        raw.decode("utf-8")
        artifacts.append(
            {
                "name": path.name,
                "path": str(path),
                "size": len(raw),
                "sha256": _sha256_bytes(raw),
            }
        )
    return artifacts


def local_additive_release_qualification(
    release_id: str | None = None,
    artifact_name: str | None = None,
) -> dict[str, Any]:
    """Return the canonical, non-secret qualification projection for local fast updates."""
    def json_safe(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): json_safe(item) for key, item in value.items()}
        if isinstance(value, (set, frozenset, tuple, list)):
            return [json_safe(item) for item in value]
        return value

    schema: list[dict[str, Any]] = []
    backfills: list[dict[str, Any]] = []
    raw_descriptors = dict(RELEASE_MANIFEST.descriptors)
    manifests = tuple(
        manifest for manifest in RELEASE_MANIFEST.manifests
        if release_id is None or manifest.release_id == release_id
    )
    if release_id is not None and not manifests:
        raise UpgradeBlocked(f"unknown release qualification: {release_id}")
    for manifest in manifests:
        for item in manifest.schema_artifacts:
            artifact = item.artifact
            if artifact_name is not None and artifact.name != artifact_name:
                continue
            path = (ROOT / artifact.relative_path).resolve()
            actual_hash = _sha256_file(path)
            if actual_hash != artifact.sha256:
                raise UpgradeBlocked(f"release artifact hash mismatch: {artifact.name}")
            canonical = _canonical_artifact_descriptor(artifact.name)
            descriptor_valid = all(
                key in canonical for key in ("tables", "indexes", "foreign_keys", "checks", "triggers")
            )
            schema.append({
                "name": artifact.name,
                "relative_path": artifact.relative_path,
                "sha256": artifact.sha256,
                "data_effect": item.data_effect,
                "dependencies": list(artifact.dependencies),
                "descriptor": json_safe(canonical),
                "descriptor_valid": descriptor_valid,
                "release_id": manifest.release_id,
            })
        for item in manifest.backfills:
            backfills.append({"id": item.backfill_id, "artifact": item.artifact.name})
    if artifact_name is not None and not schema:
        raise UpgradeBlocked(f"unknown release artifact qualification: {artifact_name}")
    selected_names = {item["name"] for item in schema}
    descriptors = {
        name: json_safe(value)
        for name, value in raw_descriptors.items()
        if not selected_names or name in selected_names
    }
    if release_id is not None:
        if len(manifests) != 1:
            raise UpgradeBlocked(f"release qualification is ambiguous: {release_id}")
        selected_fingerprint = manifests[0].fingerprint
    else:
        selected_fingerprint = RELEASE_MANIFEST.fingerprint
    return {
        "contract": "local-additive-release-qualification/v1",
        "release_id": release_id or RELEASE_MANIFEST.release_id,
        "release_fingerprint": selected_fingerprint,
        "schema_artifacts": schema,
        "backfills": backfills,
        "descriptors": descriptors,
        "application_compatibility": [
            "fresh-bootstrap",
            "preserve-data-candidate",
            "descriptor-exact",
        ],
    }


def local_additive_source_snapshot(config: DatabaseConfig, source: str) -> dict[str, Any]:
    """Expose the existing read-only snapshot/classifier as a typed fast-path boundary."""
    snapshot = _schema_snapshot(config, source)
    return {"snapshot": snapshot, "owned_states": _owned_classification(snapshot, defer_missing_triggers=True)}


def local_additive_target_state(
    config: DatabaseConfig,
    source: str,
    artifact: str,
    descriptor: Mapping[str, Any],
    *,
    snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the selected target state, reusing an explicit plan snapshot."""
    if snapshot is None:
        snapshot = _schema_snapshot(config, source)
    normalized_descriptor = _normalize_local_descriptor(descriptor)
    state = _metadata_state_for_artifact(
        json.loads(json.dumps(snapshot)),
        normalized_descriptor,
        artifact,
        defer_missing_triggers=False,
    )
    owned_tables = set(descriptor.get("tables", {})) | set(descriptor.get("parent_columns", {}))
    target = {
        "tables": [row for row in snapshot.get("columns", ()) if row.get("table_name") in descriptor.get("tables", {})],
        "indexes": [row for row in snapshot.get("indexes", ()) if row.get("table_name") in owned_tables],
        "foreign_keys": [row for row in snapshot.get("foreign_keys", ()) if row.get("table_name") in owned_tables],
        "checks": [row for row in snapshot.get("constraints", ()) if row.get("table_name") in owned_tables and row.get("constraint_type") == "CHECK"],
        "triggers": [row for row in snapshot.get("triggers", ()) if row.get("event_object_table") in owned_tables],
    }
    return {
        "state": state,
        "targeted_fingerprint": _sha256_bytes(_canonical_json(target)),
        "server_identity": server_identity(config, source),
    }


def _normalize_local_descriptor(descriptor: Mapping[str, Any]) -> dict[str, Any]:
    """Convert JSON descriptor lists to the canonical comparator's tuple shape."""
    normalized = deepcopy(descriptor)
    for contract_kind in ("indexes", "foreign_keys", "checks"):
        contracts = normalized.get(contract_kind, {})
        normalized_contracts: dict[Any, Any] = {}
        for key, contract in contracts.items():
            if isinstance(key, str):
                match = re.fullmatch(
                    r"\('([A-Za-z0-9_]+)', '([A-Za-z0-9_]+)'\)", key
                )
                if match:
                    key = (match.group(1), match.group(2))
            normalized_contracts[key] = contract
        normalized[contract_kind] = normalized_contracts
    for contract in normalized.get("indexes", {}).values():
        if isinstance(contract, Mapping) and "columns" in contract:
            contract["columns"] = tuple(str(item).casefold() for item in contract["columns"])
        if isinstance(contract, Mapping) and "non_unique" in contract:
            contract["non_unique"] = int(contract["non_unique"])
    for contract in normalized.get("foreign_keys", {}).values():
        if isinstance(contract, Mapping):
            for key in ("columns", "referenced_columns"):
                if key in contract:
                    contract[key] = tuple(contract[key])
    return normalized


def local_additive_descriptor_state(
    snapshot: Mapping[str, Any], descriptor: Mapping[str, Any], artifact: str,
) -> str:
    """Use the canonical descriptor comparator without exposing its implementation."""
    return _metadata_state_for_artifact(
        json.loads(json.dumps(snapshot)),
        _normalize_local_descriptor(descriptor),
        artifact,
        # Post-apply verification is strict: a missing owned trigger is not
        # an exact compatible projection and cannot be deferred.
        defer_missing_triggers=False,
    )


def _modified_parent_predecessor_absent_state(
    snapshot: Mapping[str, Any],
    descriptor: dict[str, Any],
    artifact: str,
    *,
    defer_missing_triggers: bool,
) -> str | None:
    """Recognize the exact predecessor before an additive parent-column MODIFY."""
    predecessor_columns = {
        "1015_controlled_file_reference_finalize_leases.sql": {
            "scheduling_service_day_log_attachments": {
                "provider_media_id": {
                    "column_type": "varchar(191)",
                    "is_nullable": "NO",
                    "column_default": None,
                    "extra": "",
                },
            },
        },
        "1018_hcm_resubmission_canonical_review_version.sql": {
            "case_import_hcm_correction_events": {
                "prior_occurrence_id": {
                    "column_type": "bigint",
                    "is_nullable": "NO",
                    "column_default": None,
                    "extra": "",
                },
            },
        },
        "1021_task96_owner_contract_successors.sql": {
            "client_profile_change_requests": {
                "status": {
                    "column_type": (
                        "enum('pending','approved','partially_approved',"
                        "'rejected','reverted')"
                    ),
                    "is_nullable": "NO",
                    "column_default": "pending",
                    "extra": "",
                },
            },
        },
        "1026_task96_scheduling_service_day_attachment_kind.sql": {
            "scheduling_service_day_log_attachments": {
                "attachment_kind": {
                    "column_type": "enum('meal_photo')",
                    "is_nullable": "NO",
                    "column_default": None,
                    "extra": "",
                },
            },
        },
        "1027_historical_order_pairing_resolution_reused.sql": {
            "historical_order_pairing_evidence": {
                "resolution": {
                    "column_type": (
                        "enum('blank','staff_missing','staff_ambiguous',"
                        "'evidence_only','assignment_candidate',"
                        "'assignment_conflict')"
                    ),
                    "is_nullable": "NO",
                    "column_default": None,
                    "extra": "",
                },
            },
        },
    }.get(artifact)
    if predecessor_columns is None:
        return None

    columns = {
        (row["table_name"], row["column_name"]): row
        for row in snapshot["columns"]
    }
    for table, expected_columns in predecessor_columns.items():
        for name, expected in expected_columns.items():
            row = columns.get((table, name))
            if row is None:
                return None
            actual_default = row["column_default"]
            if isinstance(actual_default, str):
                actual_default = actual_default.casefold()
            actual_extra = re.sub(r"\s+", " ", str(row["extra"] or "")).casefold()
            if (
                _normalize_column_type_contract(row["column_type"])
                != expected["column_type"]
                or row["is_nullable"] != expected["is_nullable"]
                or actual_default != expected["column_default"]
                or actual_extra != expected["extra"]
            ):
                return None

    successor_only = deepcopy(descriptor)
    for table, expected_columns in predecessor_columns.items():
        for name in expected_columns:
            successor_only["parent_columns"][table].pop(name, None)
    if _artifact_metadata_state(
        snapshot,
        successor_only,
        artifact,
        defer_missing_triggers=defer_missing_triggers,
    ) == "absent":
        return "absent"
    return None


def _metadata_state_for_artifact(
    snapshot: Mapping[str, Any],
    descriptor: dict[str, Any],
    artifact: str,
    *,
    defer_missing_triggers: bool,
) -> str:
    if artifact == "1004_controlled_file_storage_foundation.sql":
        return _controlled_file_storage_foundation_state(
            snapshot,
            descriptor,
            defer_missing_triggers=defer_missing_triggers,
        )
    if artifact == "1005_contract_external_signing_successor.sql":
        return _contract_external_signing_successor_state(
            snapshot,
            descriptor,
            defer_missing_triggers=defer_missing_triggers,
        )
    if artifact == "1008_historical_order_adoption_noop_constraint.sql":
        return _historical_order_adoption_noop_constraint_state(
            snapshot,
            descriptor,
        )
    if artifact == "1013_order_lifecycle_pending_status_constraint.sql":
        return _order_lifecycle_pending_status_constraint_state(
            snapshot,
            descriptor,
        )
    if artifact == "1028_historical_service_accounting.sql":
        return _historical_service_accounting_state(
            snapshot,
            descriptor,
            defer_missing_triggers=defer_missing_triggers,
        )
    if artifact == "204_scheduling_service_day_logs.sql":
        return _scheduling_service_day_logs_successor_state(
            snapshot,
            descriptor,
            defer_missing_triggers=defer_missing_triggers,
        )
    predecessor_state = _modified_parent_predecessor_absent_state(
        snapshot,
        descriptor,
        artifact,
        defer_missing_triggers=defer_missing_triggers,
    )
    if predecessor_state is not None:
        return predecessor_state
    return _artifact_metadata_state(
        snapshot,
        descriptor,
        artifact,
        defer_missing_triggers=defer_missing_triggers,
    )


# 本機 qualified additive 例外的唯一執行邊界；update_local_database 只負責路由。
LOCAL_ADDITIVE_MAX_DURATION_MS = 30_000
LOCAL_ADDITIVE_LOCK_TIMEOUT_SECONDS = 5
LOCAL_ADDITIVE_SYSTEM_DATABASES = frozenset(
    {"information_schema", "mysql", "performance_schema", "sys"}
)
LOCAL_ADDITIVE_TARGET_PREFIX = ""


class LocalAdditiveBlocked(RuntimeError):
    """Bounded, redacted failure for the local-development additive route."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "additive_blocked",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(str(message)[:240])
        self.code = code
        self.details = dict(details or {})


def _local_canonical_json(value: Any) -> bytes:
    return _canonical_json(value)


def _local_digest(value: bytes) -> str:
    return _sha256_bytes(value)


def _local_payload_digest(payload: Mapping[str, Any]) -> str:
    body = dict(payload)
    body.pop("payload_digest", None)
    body.pop("_path", None)
    body.pop("_canonical_artifact", None)
    return _local_digest(_local_canonical_json(body))


def _local_read_qualification(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raise ValueError("qualification receipt has UTF-8 BOM")
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise LocalAdditiveBlocked(
            "qualification receipt is unreadable", code="qualification_invalid"
        ) from error
    if not isinstance(payload, dict):
        raise LocalAdditiveBlocked(
            "qualification receipt must be an object", code="qualification_invalid"
        )
    if payload.get("payload_digest") != _local_payload_digest(payload):
        raise LocalAdditiveBlocked(
            "qualification receipt digest mismatch", code="qualification_invalid"
        )
    return payload


def _local_manifest_artifact(qualification: Mapping[str, Any]) -> tuple[Any, Any]:
    release_id = qualification.get("release_id")
    artifact = qualification.get("artifact")
    if not isinstance(release_id, str) or not isinstance(artifact, Mapping):
        raise LocalAdditiveBlocked(
            "qualification identity is incomplete", code="qualification_invalid"
        )
    name = artifact.get("name")
    if not isinstance(name, str):
        raise LocalAdditiveBlocked(
            "qualification artifact identity is incomplete", code="qualification_invalid"
        )
    canonical = local_additive_release_qualification(release_id, name)
    items = canonical.get("schema_artifacts", ())
    if len(items) != 1 or items[0].get("name") != name:
        raise LocalAdditiveBlocked(
            "qualification artifact is not canonical", code="qualification_invalid"
        )
    matching_manifests = tuple(
        manifest for manifest in RELEASE_MANIFEST.manifests
        if manifest.release_id == release_id
    )
    if len(matching_manifests) != 1:
        raise LocalAdditiveBlocked(
            "qualification manifest selection is unavailable or ambiguous",
            code="qualification_invalid",
        )
    return items[0], matching_manifests[0].descriptor_artifact


def _local_manifest_path(release_id: str) -> Path:
    matches: list[Path] = []
    for path in sorted((ROOT / "db" / "migration_releases").glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        if (
            payload.get("contract") == "migration-release-manifest/v1"
            and payload.get("release_id") == release_id
        ):
            matches.append(path)
    if len(matches) != 1:
        raise LocalAdditiveBlocked(
            "published release manifest is missing or ambiguous",
            code="qualification_invalid",
        )
    return matches[0]


def _local_manifest_inventory(manifest: Any) -> list[dict[str, Any]]:
    return [
        {
            "name": item.artifact.name,
            "sha256": item.artifact.sha256,
            "data_effect": item.data_effect,
            "dependencies": list(item.artifact.dependencies),
        }
        for item in manifest.schema_artifacts
    ]


_LOCAL_REQUIRED_PREREQUISITE_NAMES = frozenset({
    "156_line_publication_media_order_group.sql",
    "159_line_messaging_publication_runtime.sql",
})


def _local_json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _local_json_safe(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset, tuple, list)):
        return [_local_json_safe(item) for item in value]
    return value


def _local_prerequisite_descriptor(name: str) -> dict[str, Any]:
    """Return only the current-successor objects required by Rich Menu Option B."""
    descriptor = deepcopy(_canonical_artifact_descriptor(name))
    if name == "156_line_publication_media_order_group.sql":
        table = "line_rich_menu_publication_tasks"
        descriptor["tables"] = {table: descriptor["tables"][table]}
        descriptor["indexes"] = {
            key: value for key, value in descriptor["indexes"].items()
            if key[0] == table
        }
        descriptor["foreign_keys"] = {
            key: value for key, value in descriptor["foreign_keys"].items()
            if key[0] == table
        }
        descriptor["checks"] = {
            key: value for key, value in descriptor["checks"].items()
            if key[0] == table
        }
        descriptor["triggers"] = {
            key: value for key, value in descriptor["triggers"].items()
            if value["event_object_table"] == table
        }
        descriptor["parent_columns"] = {}
    elif name == "159_line_messaging_publication_runtime.sql":
        table = "line_rich_menu_publication_step_receipts"
        descriptor["tables"] = {table: descriptor["tables"][table]}
        descriptor["indexes"] = {
            key: value for key, value in descriptor["indexes"].items()
            if key[0] == table
        }
        descriptor["foreign_keys"] = {
            key: value for key, value in descriptor["foreign_keys"].items()
            if key[0] == table
        }
        descriptor["checks"] = {}
        descriptor["triggers"] = {
            key: value for key, value in descriptor["triggers"].items()
            if value["event_object_table"] == table
        }
        descriptor["parent_columns"] = {
            "line_domain_outbox": {
                "max_attempts": {
                    "column_type": "int unsigned",
                    "is_nullable": "NO",
                    "column_default": "3",
                    "extra": "",
                },
                "error_message": {
                    "column_type": "varchar(1000)",
                    "is_nullable": "YES",
                    "column_default": None,
                    "extra": "",
                },
            }
        }
    else:
        raise LocalAdditiveBlocked(
            f"unsupported local prerequisite projection: {name}",
            code="qualification_invalid",
        )
    return _local_json_safe(descriptor)


def _local_prerequisite_projection_sha256(projection: Mapping[str, Any]) -> str:
    return _local_digest(_local_canonical_json(projection))


def _local_validate_prerequisite_policy(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Validate local-only prerequisite artifacts independently of published deps."""
    raw = payload.get("local_prerequisites")
    if raw is None:
        return []
    if not isinstance(raw, list) or not raw:
        raise LocalAdditiveBlocked(
            "local additive schema prerequisites are missing",
            code="qualification_invalid",
        )
    prerequisites: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise LocalAdditiveBlocked(
                "local additive schema prerequisite is invalid",
                code="qualification_invalid",
            )
        name = item.get("name")
        relative_path = item.get("relative_path")
        sha256 = item.get("sha256")
        required_state = item.get("required_state")
        projection = item.get("projection")
        projection_sha256 = item.get("projection_sha256")
        if (
            not isinstance(name, str)
            or not isinstance(relative_path, str)
            or not isinstance(sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", sha256)
            or not isinstance(projection, Mapping)
            or not isinstance(projection_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", projection_sha256)
            or required_state != "exact"
        ):
            raise LocalAdditiveBlocked(
                "local additive schema prerequisite contract is invalid",
                code="qualification_invalid",
            )
        prerequisites.append({
            "name": name,
            "relative_path": relative_path,
            "sha256": sha256,
            "required_state": "exact",
            "projection": dict(projection),
            "projection_sha256": projection_sha256,
        })
    if {item["name"] for item in prerequisites} != _LOCAL_REQUIRED_PREREQUISITE_NAMES:
        raise LocalAdditiveBlocked(
            "local additive schema prerequisites are incomplete",
            code="qualification_invalid",
        )
    if len(prerequisites) != len(_LOCAL_REQUIRED_PREREQUISITE_NAMES):
        raise LocalAdditiveBlocked(
            "local additive schema prerequisites are duplicated",
            code="qualification_invalid",
        )
    for item in prerequisites:
        matches = [
            artifact for artifact in RELEASE_MANIFEST.artifacts
            if artifact["name"] == item["name"]
        ]
        if len(matches) != 1:
            raise LocalAdditiveBlocked(
                f"published prerequisite artifact is unavailable: {item['name']}",
                code="qualification_invalid",
            )
        canonical = matches[0]
        if (
            item["relative_path"] != canonical["relative_path"]
            or item["sha256"] != canonical["sha256"]
        ):
            raise LocalAdditiveBlocked(
                f"local prerequisite artifact identity differs: {item['name']}",
                code="qualification_hash_mismatch",
            )
        path = ROOT / item["relative_path"]
        if not path.is_file() or _local_digest(path.read_bytes()) != item["sha256"]:
            raise LocalAdditiveBlocked(
                f"local prerequisite artifact bytes changed: {item['name']}",
                code="qualification_hash_mismatch",
            )
        canonical_projection = _local_prerequisite_descriptor(item["name"])
        if item["projection"] != canonical_projection:
            raise LocalAdditiveBlocked(
                f"local prerequisite projection differs: {item['name']}",
                code="qualification_invalid",
            )
        if item["projection_sha256"] != _local_prerequisite_projection_sha256(
            canonical_projection
        ):
            raise LocalAdditiveBlocked(
                f"local prerequisite projection hash differs: {item['name']}",
                code="qualification_hash_mismatch",
            )
    return prerequisites


def _local_verify_prerequisite_metadata(
    snapshot: Mapping[str, Any],
    qualification: Mapping[str, Any],
) -> None:
    """Require exact current metadata for the runtime tables used by Option B."""
    prerequisites = qualification.get("local_prerequisites")
    if prerequisites is None:
        return
    if not isinstance(prerequisites, list):
        raise LocalAdditiveBlocked(
            "local additive schema prerequisites are missing",
            code="qualification_invalid",
        )
    for item in prerequisites:
        name = str(item["name"])
        descriptor = item.get("projection")
        if not isinstance(descriptor, Mapping):
            raise LocalAdditiveBlocked(
                f"local prerequisite projection is missing: {name}",
                code="qualification_invalid",
            )
        state = _artifact_metadata_state(
            json.loads(json.dumps(snapshot)), _normalize_local_descriptor(descriptor), name,
            defer_missing_triggers=False,
        )
        if state != str(item.get("required_state")):
            raise LocalAdditiveBlocked(
                f"local prerequisite metadata is {state}: {name}",
                code="prerequisite_schema_state_blocked",
            )


def _local_validate_target_projection(
    payload: Mapping[str, Any],
    artifact: Mapping[str, Any],
    descriptor_sha256: str,
) -> None:
    """Accept full-schema drift only with hash-bound exact owned projections."""

    preserve = payload.get("preserve_data_candidate")
    fresh = payload.get("fresh_bootstrap")
    if preserve.get("candidate_schema_fingerprint") == fresh.get("schema_fingerprint"):
        return

    projection = payload.get("target_projection")
    policy_evidence = payload.get("policy_evidence")
    if not isinstance(projection, Mapping) or not isinstance(policy_evidence, Mapping):
        raise LocalAdditiveBlocked(
            "fresh/preserve schema fingerprints differ", code="qualification_invalid"
        )
    fresh_fingerprint = projection.get("fresh_fingerprint")
    preserve_fingerprint = projection.get("preserve_candidate_fingerprint")
    expected = {
        "contract": "local-additive-target-projection/v1",
        "artifact_name": artifact.get("name"),
        "descriptor_sha256": descriptor_sha256,
        "fresh_state": "exact",
        "preserve_candidate_state": "exact",
    }
    if any(projection.get(key) != value for key, value in expected.items()):
        raise LocalAdditiveBlocked(
            "qualified target projection is incomplete or non-exact",
            code="qualification_invalid",
        )
    if (
        not isinstance(fresh_fingerprint, str)
        or not re.fullmatch(r"[0-9a-f]{64}", fresh_fingerprint)
        or preserve_fingerprint != fresh_fingerprint
    ):
        raise LocalAdditiveBlocked(
            "fresh/preserve target projections differ", code="qualification_invalid"
        )
    if (
        policy_evidence.get("fresh_target_projection_fingerprint")
        != fresh_fingerprint
        or policy_evidence.get("preserve_candidate_target_projection_fingerprint")
        != preserve_fingerprint
    ):
        raise LocalAdditiveBlocked(
            "target projection evidence is not canonically bound",
            code="qualification_invalid",
        )


def _local_validate_qualification(path: Path) -> dict[str, Any]:
    payload = _local_read_qualification(path)
    canonical, descriptor_artifact = _local_manifest_artifact(payload)
    manifest_path = _local_manifest_path(payload["release_id"])
    matching_manifest = next(
        manifest for manifest in RELEASE_MANIFEST.manifests
        if manifest.release_id == payload["release_id"]
    )
    artifact = payload["artifact"]
    policy = payload.get("policy")
    if not isinstance(policy, Mapping) or policy.get("local_in_place_eligible") is not True:
        raise LocalAdditiveBlocked(
            "release is not local in-place eligible", code="qualification_invalid"
        )
    if canonical.get("data_effect") != "schema_only" or artifact.get("data_effect") != canonical.get("data_effect"):
        raise LocalAdditiveBlocked(
            "canonical release data effect is not schema_only", code="replacement_required"
        )
    if local_additive_release_qualification(payload["release_id"], artifact["name"]).get("backfills"):
        raise LocalAdditiveBlocked(
            "release declares backfills and is not local additive", code="replacement_required"
        )
    if any(policy.get(key) != 0 for key in ("seed", "backfill", "destructive")):
        raise LocalAdditiveBlocked(
            "release has forbidden data effects", code="replacement_required"
        )
    _local_validate_prerequisite_policy(payload)
    if payload.get("published_manifest_sha256") != _sha256_file(manifest_path):
        raise LocalAdditiveBlocked(
            "published manifest hash differs from qualification policy",
            code="qualification_hash_mismatch",
        )
    if payload.get("manifest_artifact_inventory") != _local_manifest_inventory(matching_manifest):
        raise LocalAdditiveBlocked(
            "published manifest inventory differs from qualification policy",
            code="qualification_invalid",
        )
    metadata_backup = payload.get("metadata_backup")
    preserve = payload.get("preserve_data_candidate")
    fresh = payload.get("fresh_bootstrap")
    policy_evidence = payload.get("policy_evidence")
    if not isinstance(policy_evidence, Mapping):
        raise LocalAdditiveBlocked(
            "local-only qualification policy evidence is missing",
            code="qualification_invalid",
        )
    required_policy_evidence = {
        "fresh_schema_fingerprint": fresh.get("schema_fingerprint"),
        "preserve_source_schema_fingerprint": preserve.get("source_schema_fingerprint"),
        "preserve_candidate_schema_fingerprint": preserve.get("candidate_schema_fingerprint"),
        "source_dump_sha256": preserve.get("source_dump_sha256"),
        "candidate_dump_sha256": preserve.get("candidate_dump_sha256"),
    }
    if any(
        policy_evidence.get(key) != value
        for key, value in required_policy_evidence.items()
    ):
        raise LocalAdditiveBlocked(
            "qualification engine evidence is not canonically bound",
            code="qualification_invalid",
        )
    if payload.get("release_fingerprint") != local_additive_release_qualification(payload["release_id"]).get("release_fingerprint"):
        raise LocalAdditiveBlocked(
            "qualification release fingerprint changed", code="qualification_invalid"
        )
    if artifact.get("sql_sha256") != canonical.get("sha256"):
        raise LocalAdditiveBlocked(
            "qualification SQL hash differs from manifest", code="qualification_hash_mismatch"
        )
    if artifact.get("descriptor_sha256") != descriptor_artifact.sha256:
        raise LocalAdditiveBlocked(
            "qualification descriptor hash differs from manifest", code="qualification_hash_mismatch"
        )
    try:
        for statement in split_sql(
            (ROOT / canonical["relative_path"]).read_text(encoding="utf-8")
        ):
            _local_classify_statement(statement)
    except LocalAdditiveBlocked as error:
        raise LocalAdditiveBlocked(
            "published release contains a forbidden local additive effect",
            code="replacement_required",
        ) from error
    if not isinstance(metadata_backup, Mapping) or metadata_backup.get("status") != "verified":
        raise LocalAdditiveBlocked(
            "verified source backup metadata is required", code="backup_required"
        )
    if not isinstance(preserve, Mapping) or preserve.get("status") != "verified":
        raise LocalAdditiveBlocked(
            "preserve-data engine qualification is required", code="qualification_required"
        )
    if not isinstance(fresh, Mapping) or fresh.get("status") != "verified":
        raise LocalAdditiveBlocked(
            "fresh engine qualification is required", code="qualification_required"
        )
    if not preserve.get("candidate_schema_fingerprint") or not fresh.get("schema_fingerprint"):
        raise LocalAdditiveBlocked(
            "engine qualification fingerprints are incomplete", code="qualification_invalid"
        )
    for evidence_key in ("source_dump_sha256", "candidate_dump_sha256"):
        value = preserve.get(evidence_key)
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise LocalAdditiveBlocked(
                "preserve-data dump evidence is incomplete", code="qualification_invalid"
            )
    _local_validate_target_projection(payload, artifact, descriptor_artifact.sha256)
    payload["_path"] = path
    payload["_canonical_artifact"] = canonical
    return payload


def _local_discover_qualification(
    qualification_path: Path | None = None,
    *,
    release_id: str | None = None,
    artifact_name: str | None = None,
) -> dict[str, Any]:
    selected_release_id = release_id or RELEASE_MANIFEST.release_id
    selected_release_fingerprint = local_additive_release_qualification(
        selected_release_id
    )["release_fingerprint"]
    if qualification_path is not None:
        path = Path(qualification_path).expanduser().resolve()
        receipt_root = (ROOT / "validation" / "receipts").resolve()
        try:
            path.relative_to(receipt_root)
        except ValueError:
            raise LocalAdditiveBlocked(
                "explicit qualification must be a published validation receipt",
                code="qualification_invalid",
            ) from None
        if not path.name.startswith("PROV-") or not path.name.endswith(".json"):
            raise LocalAdditiveBlocked(
                "explicit qualification must be a published validation receipt",
                code="qualification_invalid",
            )
        selected = _local_validate_qualification(path)
        if (
            selected.get("release_id") != selected_release_id
            or selected.get("release_fingerprint") != selected_release_fingerprint
            or (
                artifact_name is not None
                and selected.get("artifact", {}).get("name") != artifact_name
            )
        ):
            raise LocalAdditiveBlocked(
                f"explicit qualification does not match release {selected_release_id}",
                code="qualification_stale",
            )
        return selected
    paths = sorted((ROOT / "validation" / "receipts").rglob("PROV-*-local-additive-qualification-*.json"))
    valid: list[dict[str, Any]] = []
    for path in paths:
        try:
            valid.append(_local_validate_qualification(path))
        except LocalAdditiveBlocked:
            continue
    current = [
        item for item in valid
        if item.get("release_id") == selected_release_id
        and item.get("release_fingerprint") == selected_release_fingerprint
        and (
            artifact_name is None
            or item.get("artifact", {}).get("name") == artifact_name
        )
    ]
    if not current:
        raise LocalAdditiveBlocked(
            f"release {selected_release_id} has no valid qualification receipt",
            code="qualification_missing",
            details={"release_id": selected_release_id},
        )
    signatures = {
        _local_digest(_local_canonical_json({
            key: item.get(key)
            for key in (
                "release_id", "release_fingerprint", "artifact",
                "published_manifest_sha256", "manifest_artifact_inventory",
                "policy", "policy_evidence",
            )
        }))
        for item in current
    }
    if len(signatures) != 1:
        raise LocalAdditiveBlocked(
            "conflicting local additive qualification receipts",
            code="qualification_ambiguous",
        )
    return sorted(current, key=lambda item: str(item.get("_path", "")))[0]


LOCAL_ADDITIVE_BASELINE_ARTIFACT = "1003_matching_coordination_successor.sql"


def _local_ordered_upgrade_entries() -> tuple[dict[str, Any], ...]:
    """Project the canonical manifest chain from the approved local baseline."""
    entries: list[dict[str, Any]] = []
    baseline_found = False
    for manifest in RELEASE_MANIFEST.manifests:
        for item in manifest.schema_artifacts:
            artifact = item.artifact
            if artifact.name == LOCAL_ADDITIVE_BASELINE_ARTIFACT:
                if baseline_found:
                    raise LocalAdditiveBlocked(
                        "local additive baseline is duplicated",
                        code="release_chain_invalid",
                    )
                baseline_found = True
            if not baseline_found:
                continue
            entries.append({
                "release_id": manifest.release_id,
                "release_fingerprint": manifest.fingerprint,
                "data_effect": item.data_effect,
                "artifact": {
                    "name": artifact.name,
                    "relative_path": artifact.relative_path,
                    "sha256": artifact.sha256,
                },
                "descriptor": local_additive_release_qualification(
                    manifest.release_id, artifact.name
                )["schema_artifacts"][0]["descriptor"],
            })
    if not baseline_found or not entries:
        raise LocalAdditiveBlocked(
            "local additive baseline is unavailable in the canonical chain",
            code="release_chain_invalid",
        )
    return tuple(entries)


def _local_receipt_reference(path: Any) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(ROOT.resolve()))
    except ValueError:
        return str(resolved)


def _local_ordered_chain_plan(
    config: Any,
    source: str,
    snapshot: Mapping[str, Any],
    *,
    qualification_path: Path | None = None,
) -> dict[str, Any]:
    """Classify one continuous exact prefix and qualify every missing release."""
    entries = _local_ordered_upgrade_entries()
    explicit_release_id: str | None = None
    explicit_artifact_name: str | None = None
    if qualification_path is not None:
        explicit_path = Path(qualification_path).expanduser().resolve()
        receipt_root = (ROOT / "validation" / "receipts").resolve()
        try:
            explicit_path.relative_to(receipt_root)
        except ValueError:
            raise LocalAdditiveBlocked(
                "explicit qualification must be a published validation receipt",
                code="qualification_invalid",
            ) from None
        explicit_qualification = _local_validate_qualification(explicit_path)
        explicit_release_id = explicit_qualification.get("release_id")
        explicit_artifact = explicit_qualification.get("artifact")
        explicit_artifact_name = (
            explicit_artifact.get("name")
            if isinstance(explicit_artifact, Mapping)
            else None
        )
        if (
            not isinstance(explicit_release_id, str)
            or not isinstance(explicit_artifact_name, str)
        ):
            raise LocalAdditiveBlocked(
                "explicit qualification identity is incomplete",
                code="qualification_invalid",
            )
    artifacts: list[dict[str, Any]] = []
    dependency_gap_seen = False
    for entry in entries:
        artifact = entry["artifact"]
        state = local_additive_target_state(
            config,
            source,
            artifact["name"],
            entry["descriptor"],
            snapshot=snapshot,
        )["state"]
        if (
            dependency_gap_seen
            and state not in {"absent", "exact"}
            and _local_parent_tables_dependency_pending(snapshot, entry["descriptor"])
        ):
            state = "dependency_pending"
        projected = {
            "release_id": entry["release_id"],
            "release_fingerprint": entry["release_fingerprint"],
            "name": artifact["name"],
            "state": state,
            "data_effect": entry.get("data_effect", "schema_only"),
            "qualification": "not_required" if state == "exact" else "pending",
            "blocked_reason": None,
        }
        artifacts.append(projected)
        if state in {"absent", "dependency_pending"}:
            dependency_gap_seen = True

    chain_details = {
        "baseline_release_id": entries[0]["release_id"],
        "latest_release_id": entries[-1]["release_id"],
        "artifacts": artifacts,
    }
    baseline = artifacts[0]
    if baseline["state"] != "exact":
        baseline["blocked_reason"] = "approved_baseline_not_exact"
        raise LocalAdditiveBlocked(
            f"approved baseline is not exact: {baseline['name']}={baseline['state']}",
            code="baseline_not_exact",
            details={
                **chain_details,
                "release_id": baseline["release_id"],
                "artifact": baseline["name"],
                "state": baseline["state"],
            },
        )
    blocked = next(
        (
            item for item in artifacts
            if item["state"] not in {"absent", "dependency_pending", "exact"}
        ),
        None,
    )
    if blocked is not None:
        blocked["blocked_reason"] = f"schema_state_{blocked['state']}"
        raise LocalAdditiveBlocked(
            f"release artifact state is {blocked['state']}: {blocked['name']}",
            code="schema_state_blocked",
            details={
                **chain_details,
                "release_id": blocked["release_id"],
                "artifact": blocked["name"],
                "state": blocked["state"],
            },
        )
    missing_seen = False
    for item in artifacts:
        if item["state"] in {"absent", "dependency_pending"}:
            missing_seen = True
            continue
        if missing_seen:
            item["blocked_reason"] = "exact_after_absent_chain_hole"
            raise LocalAdditiveBlocked(
                f"release chain hole before exact artifact: {item['name']}",
                code="schema_chain_hole",
                details={
                    **chain_details,
                    "release_id": item["release_id"],
                    "artifact": item["name"],
                    "state": item["state"],
                },
            )

    pending: list[dict[str, Any]] = []
    for projected, entry in zip(artifacts, entries, strict=True):
        if projected["state"] not in {"absent", "dependency_pending"}:
            continue
        if projected["data_effect"] != "schema_only":
            projected["qualification"] = "not_eligible"
            projected["blocked_reason"] = "replacement_required"
            raise LocalAdditiveBlocked(
                f"{entry['artifact']['name']} requires the preserve-data replacement route",
                code="replacement_required",
                details={
                    **chain_details,
                    "release_id": entry["release_id"],
                    "artifact": entry["artifact"]["name"],
                    "state": projected["state"],
                    "data_effect": projected["data_effect"],
                },
            )
        try:
            qualification = _local_discover_qualification(
                qualification_path
                if (
                    entry["release_id"] == explicit_release_id
                    and entry["artifact"]["name"] == explicit_artifact_name
                )
                else None,
                release_id=entry["release_id"],
                artifact_name=entry["artifact"]["name"],
            )
            _local_verify_hashes(qualification)
        except LocalAdditiveBlocked as error:
            projected["qualification"] = "blocked"
            projected["blocked_reason"] = error.code
            details = {
                **chain_details,
                "release_id": entry["release_id"],
                "artifact": entry["artifact"]["name"],
                "state": projected["state"],
                **error.details,
            }
            raise LocalAdditiveBlocked(
                f"{entry['artifact']['name']}: {error}",
                code=error.code,
                details=details,
            ) from error
        receipt = _local_receipt_reference(qualification["_path"])
        projected["qualification"] = "exact"
        projected["qualification_receipt"] = receipt
        pending.append({
            "release_id": entry["release_id"],
            "release_fingerprint": entry["release_fingerprint"],
            "artifact": entry["artifact"]["name"],
            "qualification_receipt": receipt,
        })
    return {
        "baseline_release_id": entries[0]["release_id"],
        "latest_release_id": entries[-1]["release_id"],
        "artifacts": artifacts,
        "pending_releases": pending,
    }


def _local_parent_tables_dependency_pending(
    snapshot: Mapping[str, Any], descriptor: Mapping[str, Any]
) -> bool:
    """Defer only a future descriptor whose prerequisite parent tables are all absent."""
    parent_tables = set(descriptor.get("parent_columns", {}))
    if not parent_tables:
        return False
    present_tables = {
        str(row.get("table_name"))
        for row in snapshot.get("columns", ())
        if row.get("table_name")
    }
    return parent_tables.isdisjoint(present_tables)


def _local_verify_hashes(qualification: Mapping[str, Any]) -> None:
    artifact = qualification["artifact"]
    canonical = qualification["_canonical_artifact"]
    sql_path = ROOT / canonical["relative_path"]
    _, descriptor_artifact = _local_manifest_artifact(qualification)
    descriptor_path = ROOT / descriptor_artifact.relative_path
    if _local_digest(sql_path.read_bytes()) != artifact["sql_sha256"]:
        raise LocalAdditiveBlocked("canonical SQL hash changed", code="qualification_hash_mismatch")
    if _local_digest(descriptor_path.read_bytes()) != artifact["descriptor_sha256"]:
        raise LocalAdditiveBlocked("canonical descriptor hash changed", code="qualification_hash_mismatch")


def _local_connect(config: Any, database: str | None, timeout_ms: int) -> Any:
    if not 1 <= int(timeout_ms) <= LOCAL_ADDITIVE_MAX_DURATION_MS:
        raise LocalAdditiveBlocked("database client timeout is invalid", code="duration_invalid")
    try:
        return config.connect(database, timeout_seconds=float(timeout_ms) / 1000)
    except (AttributeError, TypeError, ValueError) as error:
        raise LocalAdditiveBlocked(
            "database driver cannot enforce bounded connect/read/write timeouts",
            code="client_timeout_unavailable",
        ) from error


def _local_capture_backup_rows(
    config: Any, source: str, table_names: Iterable[str],
) -> dict[str, Any]:
    """Capture stable row evidence for the qualification-selected tables."""
    names = tuple(str(table) for table in table_names)
    if not names or any(not IDENTIFIER.fullmatch(table) for table in names):
        raise LocalAdditiveBlocked(
            "source backup table identity is invalid", code="backup_required"
        )
    connection = _local_connect(config, source, LOCAL_ADDITIVE_MAX_DURATION_MS)
    try:
        with connection.cursor() as cursor:
            counts: dict[str, int] = {}
            actual_fingerprints: dict[str, str] = {}
            for table in names:
                cursor.execute(f"SELECT COUNT(*) AS n FROM `{table}`")
                row = cursor.fetchone() or {}
                actual = row.get("n", 0) if isinstance(row, Mapping) else row[0]
                counts[table] = int(actual)
                cursor.execute(f"CHECKSUM TABLE `{table}`")
                checksum_row = _normalized_row(cursor.fetchone() or {})
                checksum = checksum_row.get("checksum")
                cursor.execute(
                    "SELECT column_name FROM information_schema.key_column_usage "
                    "WHERE table_schema=DATABASE() AND table_name=%s "
                    "AND constraint_name='PRIMARY' ORDER BY ordinal_position",
                    (table,),
                )
                primary = [
                    _normalized_row(item)["column_name"]
                    for item in cursor.fetchall()
                ]
                pk_hash = None
                if primary:
                    projection = ",".join(f"`{column}`" for column in primary)
                    cursor.execute(
                        f"SELECT {projection} FROM `{table}` ORDER BY {projection}"
                    )
                    pk_hash = _sha256_bytes(_canonical_json(cursor.fetchall()))
                actual_fingerprints[str(table)] = _local_stable_table_fingerprint(
                    int(actual), checksum, pk_hash
                )
            return {
                "data_row_counts": counts,
                "data_fingerprints": actual_fingerprints,
                "data_fingerprint_sha256": _local_data_fingerprint(
                    actual_fingerprints
                ),
            }
    finally:
        connection.close()


def _local_verify_backup_rows(config: Any, source: str, expected: Mapping[str, Any]) -> None:
    """Verify stable row evidence before and after any in-place DDL."""
    counts = expected.get("data_row_counts")
    fingerprints = expected.get("data_fingerprints")
    expected_global = expected.get("data_fingerprint_sha256")
    if not isinstance(counts, Mapping) or not isinstance(fingerprints, Mapping):
        raise LocalAdditiveBlocked("source backup row evidence is missing", code="backup_required")
    if not isinstance(expected_global, str):
        raise LocalAdditiveBlocked("source backup data fingerprint is missing", code="backup_required")
    actual = _local_capture_backup_rows(config, source, counts.keys())
    if actual["data_row_counts"] != dict(counts):
        raise LocalAdditiveBlocked("source backup row fingerprint changed", code="backup_required")
    if actual["data_fingerprints"] != dict(fingerprints):
        raise LocalAdditiveBlocked("source backup row fingerprint changed", code="backup_required")
    if actual["data_fingerprint_sha256"] != expected_global:
        raise LocalAdditiveBlocked("source backup data fingerprint changed", code="backup_required")


def _local_classify_statement(statement: str) -> str:
    normalized = re.sub(r"\s+", " ", statement.strip()).casefold()
    if normalized.startswith("create table"):
        if re.search(r"\bas\s+select\b|\bselect\b", normalized):
            raise LocalAdditiveBlocked("CTAS is outside additive allowlist", code="forbidden_sql_effect")
        return "create_table"
    if normalized.startswith("drop trigger if exists"):
        return "drop_trigger_if_exists"
    if normalized.startswith("create unique index") or normalized.startswith("create index"):
        return "create_index"
    if normalized.startswith("create trigger"):
        body = normalized.split("for each row", 1)[-1]
        if re.search(r"\b(insert|update|delete|replace|truncate|alter|drop|create)\b", body):
            raise LocalAdditiveBlocked("trigger DML is outside additive allowlist", code="forbidden_sql_effect")
        return "create_trigger"
    if normalized.startswith("alter table"):
        canonical_1008 = re.sub(
            r"\s+",
            " ",
            split_sql(
                (ROOT / "db" / "schema_parts" / "1008_historical_order_adoption_noop_constraint.sql")
                .read_text(encoding="utf-8")
            )[0].strip(),
        ).casefold()
        canonical_1013 = re.sub(
            r"\s+",
            " ",
            split_sql(
                (ROOT / "db" / "schema_parts" / "1013_order_lifecycle_pending_status_constraint.sql")
                .read_text(encoding="utf-8")
            )[0].strip(),
        ).casefold()
        canonical_1023 = re.sub(
            r"\s+",
            " ",
            split_sql(
                (ROOT / "db" / "schema_parts" /
                 "1023_task96_line_safe_review_link_matching_outbox_v1.sql")
                .read_text(encoding="utf-8")
            )[0].strip(),
        ).casefold()
        controlled_parent_replacement = (
            normalized.startswith("alter table controlled_file_staging_objects ")
            and "modify column purpose enum(" in normalized
            and "'unsigned_contract'" in normalized
            and "drop check chk_controlled_file_staging_owner_purpose" in normalized
            and "add constraint chk_controlled_file_staging_owner_purpose check" in normalized
        ) or (
            normalized.startswith("alter table controlled_file_objects ")
            and "modify column purpose enum(" in normalized
            and "'unsigned_contract'" in normalized
            and "drop check chk_controlled_file_object_owner_purpose" in normalized
            and "add constraint chk_controlled_file_object_owner_purpose check" in normalized
        )
        controlled_fk_rebuild = normalized in {
            "alter table controlled_file_objects drop foreign key "
            "fk_controlled_file_object_supersedes",
        }
        if controlled_parent_replacement:
            return "controlled_file_purpose_widen"
        if controlled_fk_rebuild:
            return "controlled_file_fk_rebuild"
        if normalized in {canonical_1008, canonical_1013}:
            return "controlled_check_replacement"
        if normalized == canonical_1023:
            return "matching_outbox_successor"
        if re.search(r"\b(drop|modify|change|rename|truncate)\b", normalized):
            raise LocalAdditiveBlocked("destructive ALTER is outside additive allowlist", code="forbidden_sql_effect")
        if not re.search(r"\badd\s+(column|index|unique|constraint|fulltext|spatial)\b", normalized):
            raise LocalAdditiveBlocked("ALTER is not additive", code="forbidden_sql_effect")
        return "alter_add_only"
    if re.search(r"\b(insert|update|delete|replace|truncate|load data|call)\b", normalized):
        raise LocalAdditiveBlocked("SQL statement is outside additive allowlist: data mutation", code="forbidden_sql_effect")
    raise LocalAdditiveBlocked("SQL statement is outside additive allowlist", code="forbidden_sql_effect")


def _local_journal_path(root: Path, source: str, release_id: str) -> Path:
    if not IDENTIFIER.fullmatch(source) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]*", release_id
    ):
        raise LocalAdditiveBlocked(
            "additive journal identity is invalid", code="journal_invalid"
        )
    return (
        Path(root)
        / "fast_additive"
        / f"{source}.{release_id}.journal.jsonl"
    )


def _local_receipt_path(root: Path, source: str) -> Path:
    return Path(root) / "fast_additive" / f"{source}.receipt.json"


def _local_append_event(root: Path, source: str, release_id: str, state: str, previous: Mapping[str, Any] | None = None, **fields: Any) -> dict[str, Any]:
    path = _local_journal_path(root, source, release_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        "sequence": int((previous or {}).get("sequence", 0)) + 1,
        "at": _now(),
        "state": state,
        "release_id": release_id,
        "previous_digest": str((previous or {}).get("event_digest", "")),
        **fields,
    }
    event["event_digest"] = _local_digest(_local_canonical_json(event))
    with path.open("ab") as handle:
        handle.write(_local_canonical_json(event) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    return event


def _local_read_events(root: Path, source: str, release_id: str) -> list[dict[str, Any]]:
    path = _local_journal_path(root, source, release_id)
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    previous = ""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for expected, line in enumerate((item for item in lines if item), 1):
            event = json.loads(line)
            digest = event.pop("event_digest", None)
            if event.get("sequence") != expected or event.get("previous_digest", "") != previous or digest != _local_digest(_local_canonical_json(event)):
                raise ValueError("journal integrity")
            event["event_digest"] = digest
            events.append(event)
            previous = digest
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise LocalAdditiveBlocked("additive journal integrity failed", code="journal_invalid") from error
    return events


def _local_write_receipt(root: Path, source: str, payload: Mapping[str, Any]) -> None:
    path = _local_receipt_path(root, source)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(_local_canonical_json(payload) + b"\n")
    with temporary.open("ab") as handle:
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def _local_verified_ordinals(events: list[dict[str, Any]], release_id: str, source: str, baseline: str) -> dict[int, str]:
    verified: dict[int, str] = {}
    for event in events:
        if event.get("state") != "statement_verified":
            continue
        if event.get("release_id") != release_id or event.get("source_database") != source or event.get("source_schema_sha256") != baseline:
            raise LocalAdditiveBlocked("additive journal baseline changed", code="journal_conflict")
        ordinal = event.get("ordinal")
        statement_hash = event.get("statement_sha256")
        if not isinstance(ordinal, int) or not isinstance(statement_hash, str):
            raise LocalAdditiveBlocked("additive journal statement identity is incomplete", code="journal_invalid")
        if ordinal in verified and verified[ordinal] != statement_hash:
            raise LocalAdditiveBlocked("additive journal ordinal hash conflict", code="journal_conflict")
        verified[ordinal] = statement_hash
    return verified


def _local_resume_context(
    events: list[dict[str, Any]],
    release_id: str,
    source: str,
    statement_hashes: list[str],
    current_schema_sha256: str,
) -> tuple[str, dict[int, str]]:
    """Load an immutable pre-apply baseline and deterministic statement progress."""
    if not events:
        return current_schema_sha256, {}
    baseline_event = events[0]
    if baseline_event.get("state") != "baseline_captured":
        raise LocalAdditiveBlocked(
            "additive journal lacks immutable pre-apply baseline",
            code="journal_invalid",
        )
    baseline = baseline_event.get("source_schema_sha256")
    recorded_hashes = baseline_event.get("statement_hashes")
    if (
        baseline_event.get("release_id") != release_id
        or baseline_event.get("source_database") != source
        or not isinstance(baseline, str)
        or recorded_hashes != statement_hashes
    ):
        raise LocalAdditiveBlocked("additive journal baseline changed", code="journal_conflict")
    verified: dict[int, str] = {}
    started: set[int] = set()
    for event in events[1:]:
        if event.get("release_id") != release_id or event.get("source_database") != source:
            raise LocalAdditiveBlocked("additive journal identity changed", code="journal_conflict")
        ordinal = event.get("ordinal")
        if event.get("state") == "statement_started":
            if not isinstance(ordinal, int) or not 1 <= ordinal <= len(statement_hashes) or ordinal in started:
                raise LocalAdditiveBlocked("additive journal statement progression is invalid", code="journal_invalid")
            started.add(ordinal)
        elif event.get("state") == "statement_verified":
            if not isinstance(ordinal, int) or not 1 <= ordinal <= len(statement_hashes) or ordinal in verified:
                raise LocalAdditiveBlocked("additive journal statement progression is invalid", code="journal_invalid")
            if event.get("statement_sha256") != statement_hashes[ordinal - 1] or ordinal not in started:
                raise LocalAdditiveBlocked("additive journal statement hash conflict", code="journal_conflict")
            verified[ordinal] = str(event["statement_sha256"])
            started.remove(ordinal)
    if started:
        raise LocalAdditiveBlocked(
            "additive journal contains an unverified DDL outcome",
            code="resume_uncertain",
        )
    if set(verified) != set(range(1, max(verified, default=0) + 1)):
        raise LocalAdditiveBlocked("additive journal statement progression has a gap", code="journal_invalid")
    return baseline, verified


@contextmanager
def _local_maintenance_lock(config: Any, source: str, timeout: int) -> Any:
    connection = _local_connect(config, None, LOCAL_ADDITIVE_MAX_DURATION_MS)
    lock_name = f"labor_union:additive:{source}"
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s,%s) AS locked", (lock_name, timeout))
            row = cursor.fetchone() or {}
            locked = row.get("locked", 0) if isinstance(row, Mapping) else row[0]
            if int(locked or 0) != 1:
                raise LocalAdditiveBlocked("additive maintenance lock timeout", code="lock_timeout")
        yield connection
    finally:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT RELEASE_LOCK(%s) AS released", (lock_name,))
                row = cursor.fetchone() or {}
                released = row.get("released", 0) if isinstance(row, Mapping) else row[0]
                if int(released or 0) != 1:
                    raise LocalAdditiveBlocked("additive maintenance lock was not released", code="lock_release_failed")
        finally:
            connection.close()


def local_additive_plan(
    config: Any,
    source: str,
    *,
    receipt_root: Path,
    qualification_path: Path | None = None,
) -> dict[str, Any]:
    if (
        not IDENTIFIER.fullmatch(source)
        or source.casefold() in LOCAL_ADDITIVE_SYSTEM_DATABASES
    ):
        raise LocalAdditiveBlocked(
            "daily additive requires a non-system local database",
            code="target_profile_blocked",
        )
    if not database_exists(config, source):
        raise LocalAdditiveBlocked("source database is absent; recovery is required", code="recovery_required")
    snapshot = local_additive_source_snapshot(config, source)["snapshot"]
    chain = _local_ordered_chain_plan(
        config,
        source,
        snapshot,
        qualification_path=qualification_path,
    )
    pending = chain["pending_releases"]
    identity = server_identity(config, source)
    if not pending:
        return {
            "status": "current",
            "route": "daily_additive",
            "selected_strategy": "additive",
            "target_profile": "local-development",
            "local_qualified_additive_exception": True,
            "source_database": source,
            "source_identity": {
                "database": source,
                "server": identity["server"],
                "schema_sha256": snapshot["sha256"],
            },
            "source_schema_sha256": snapshot["sha256"],
            "release_id": chain["latest_release_id"],
            "release_fingerprint": _local_ordered_upgrade_entries()[-1]["release_fingerprint"],
            **chain,
            "backup_required": False,
            "duration_guard_ms": LOCAL_ADDITIVE_MAX_DURATION_MS,
            "estimated_duration_ms": 0,
            "verified_ordinals": [],
            "statement_hashes": [],
        }
    next_release = pending[0]
    qualification_reference = Path(next_release["qualification_receipt"])
    if not qualification_reference.is_absolute():
        qualification_reference = ROOT / qualification_reference
    qualification = _local_discover_qualification(
        qualification_reference,
        release_id=next_release["release_id"],
        artifact_name=next_release["artifact"],
    )
    _local_verify_hashes(qualification)
    artifact = qualification["_canonical_artifact"]
    statements = split_sql((ROOT / artifact["relative_path"]).read_text(encoding="utf-8"))
    statement_hashes = [_local_digest(statement.encode("utf-8")) for statement in statements]
    _local_verify_prerequisite_metadata(snapshot, qualification)
    events = _local_read_events(
        receipt_root, source, qualification["release_id"]
    )
    resume_baseline, verified = _local_resume_context(
        events,
        qualification["release_id"],
        source,
        statement_hashes,
        snapshot["sha256"],
    )
    return {
        "status": "ready",
        "route": "daily_additive",
        "selected_strategy": "additive",
        "target_profile": "local-development",
        "local_qualified_additive_exception": True,
        "source_database": source,
        "source_identity": {"database": source, "server": identity["server"], "schema_sha256": snapshot["sha256"]},
        "source_schema_sha256": snapshot["sha256"],
        "release_id": qualification["release_id"],
        "release_fingerprint": qualification["release_fingerprint"],
        **chain,
        "artifact": {"name": artifact["name"], "state": "absent", "data_effect": "schema_only"},
        "backup_required": True,
        "duration_guard_ms": LOCAL_ADDITIVE_MAX_DURATION_MS,
        "estimated_duration_ms": 0,
        "qualification_receipt": _local_receipt_reference(qualification["_path"]),
        "resume_baseline_schema_sha256": resume_baseline,
        "verified_ordinals": sorted(verified),
        "statement_hashes": statement_hashes,
    }


def _local_validate_backup(
    config: Any,
    source: str,
    qualification: Mapping[str, Any],
    baseline_schema_sha256: str,
    *,
    backup_dump_path: Path | None,
    backup_receipt_path: Path | None,
) -> dict[str, Any]:
    """Validate a machine-local pre-Apply dump and its stable evidence."""
    if backup_dump_path is None or backup_receipt_path is None:
        raise LocalAdditiveBlocked(
            "local pre-apply backup is required", code="backup_required"
        )
    dump_path = Path(backup_dump_path).expanduser().resolve()
    receipt_path = Path(backup_receipt_path).expanduser().resolve()
    try:
        receipt = read_receipt(receipt_path)
        identity = server_identity(config, source)
        dump = validate_dump(dump_path, receipt_path, source, identity)
    except (OSError, UpgradeBlocked) as error:
        raise LocalAdditiveBlocked(
            "local pre-apply backup is invalid", code="backup_required"
        ) from error
    required = {
        "kind": "local_additive_source_backup",
        "release_id": qualification["release_id"],
        "database": source,
        "server": identity["server"],
        "host": identity["host"],
        "port": identity["port"],
        "schema_sha256": baseline_schema_sha256,
    }
    if any(receipt.get(key) != value for key, value in required.items()):
        raise LocalAdditiveBlocked(
            "local pre-apply backup identity differs", code="backup_required"
        )
    reference_counts = (
        qualification.get("metadata_backup", {}).get("data_row_counts")
    )
    local_counts = receipt.get("data_row_counts")
    local_fingerprints = receipt.get("data_fingerprints")
    local_global = receipt.get("data_fingerprint_sha256")
    if not isinstance(reference_counts, Mapping) or not isinstance(local_counts, Mapping):
        raise LocalAdditiveBlocked(
            "local pre-apply backup row evidence is missing", code="backup_required"
        )
    if set(local_counts) != set(reference_counts):
        raise LocalAdditiveBlocked(
            "local pre-apply backup table scope differs", code="backup_required"
        )
    if not isinstance(local_fingerprints, Mapping) or set(local_fingerprints) != set(reference_counts):
        raise LocalAdditiveBlocked(
            "local pre-apply backup row evidence is missing", code="backup_required"
        )
    if not isinstance(local_global, str) or not re.fullmatch(r"[0-9a-f]{64}", local_global):
        raise LocalAdditiveBlocked(
            "local pre-apply backup data digest is missing", code="backup_required"
        )
    _local_verify_backup_rows(config, source, receipt)
    return {
        **receipt,
        "dump_path": dump["path"],
        "receipt_path": str(receipt_path),
    }


def local_additive_prepare_backup(
    config: Any,
    source: str,
    *,
    receipt_root: Path,
    backup_dump_path: Path,
    backup_receipt_path: Path,
    mysql_container: str | None = None,
    qualification_path: Path | None = None,
) -> dict[str, Any]:
    """Create or validate the immutable machine-local backup for one release."""
    preview = local_additive_plan(
        config,
        source,
        receipt_root=receipt_root,
        qualification_path=qualification_path,
    )
    if preview["status"] == "current":
        return preview
    qualification = (
        _local_discover_qualification(
            release_id=preview["release_id"],
            artifact_name=preview["artifact"]["name"],
        )
        if qualification_path is None
        else _local_discover_qualification(
            qualification_path,
            release_id=preview["release_id"],
            artifact_name=preview["artifact"]["name"],
        )
    )
    dump_path = Path(backup_dump_path).expanduser().resolve()
    receipt_path = Path(backup_receipt_path).expanduser().resolve()
    events = _local_read_events(
        receipt_root, source, qualification["release_id"]
    )
    if dump_path.exists() or receipt_path.exists():
        if not dump_path.is_file() or not receipt_path.is_file():
            raise LocalAdditiveBlocked(
                "local pre-apply backup set is incomplete", code="backup_required"
            )
        return _local_validate_backup(
            config,
            source,
            qualification,
            preview["resume_baseline_schema_sha256"],
            backup_dump_path=dump_path,
            backup_receipt_path=receipt_path,
        )
    if events:
        raise LocalAdditiveBlocked(
            "original local pre-apply backup is missing", code="backup_required"
        )
    reference_counts = (
        qualification.get("metadata_backup", {}).get("data_row_counts")
    )
    if not isinstance(reference_counts, Mapping):
        raise LocalAdditiveBlocked(
            "qualification backup table scope is missing", code="backup_required"
        )
    before_snapshot = local_additive_source_snapshot(config, source)["snapshot"]
    if before_snapshot["sha256"] != preview["source_schema_sha256"]:
        raise LocalAdditiveBlocked(
            "source changed before backup", code="source_changed"
        )
    before_rows = _local_capture_backup_rows(
        config, source, reference_counts.keys()
    )
    temporary_dump = dump_path.with_suffix(dump_path.suffix + ".preparing")
    temporary_receipt = receipt_path.with_suffix(
        receipt_path.suffix + ".preparing"
    )
    if temporary_dump.exists() or temporary_receipt.exists():
        raise LocalAdditiveBlocked(
            "unfinished local backup requires review", code="backup_required"
        )
    create_source_dump(
        config,
        source,
        temporary_dump,
        temporary_receipt,
        mysql_container=mysql_container,
    )
    after_snapshot = local_additive_source_snapshot(config, source)["snapshot"]
    after_rows = _local_capture_backup_rows(
        config, source, reference_counts.keys()
    )
    if after_snapshot["sha256"] != before_snapshot["sha256"] or after_rows != before_rows:
        raise LocalAdditiveBlocked(
            "source changed while backup was created", code="source_changed"
        )
    identity = server_identity(config, source)
    receipt = read_receipt(temporary_receipt)
    receipt.update({
        "kind": "local_additive_source_backup",
        "release_id": qualification["release_id"],
        "database": source,
        "server": identity["server"],
        "host": identity["host"],
        "port": identity["port"],
        "schema_sha256": before_snapshot["sha256"],
        **before_rows,
    })
    write_receipt(temporary_receipt, receipt)
    _local_validate_backup(
        config,
        source,
        qualification,
        before_snapshot["sha256"],
        backup_dump_path=temporary_dump,
        backup_receipt_path=temporary_receipt,
    )
    dump_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_dump.replace(dump_path)
    temporary_receipt.replace(receipt_path)
    return _local_validate_backup(
        config,
        source,
        qualification,
        before_snapshot["sha256"],
        backup_dump_path=dump_path,
        backup_receipt_path=receipt_path,
    )


def local_additive_apply(
    config: Any,
    source: str,
    *,
    receipt_root: Path,
    duration_guard_ms: int = LOCAL_ADDITIVE_MAX_DURATION_MS,
    lock_timeout_seconds: int = LOCAL_ADDITIVE_LOCK_TIMEOUT_SECONDS,
    qualification_path: Path | None = None,
    backup_dump_path: Path | None = None,
    backup_receipt_path: Path | None = None,
) -> dict[str, Any]:
    if not 1 <= duration_guard_ms <= LOCAL_ADDITIVE_MAX_DURATION_MS:
        raise LocalAdditiveBlocked("duration guard must be between 1 and 30000 ms", code="duration_invalid")
    if not 1 <= lock_timeout_seconds <= LOCAL_ADDITIVE_LOCK_TIMEOUT_SECONDS:
        raise LocalAdditiveBlocked("lock timeout must be between 1 and 5 seconds", code="duration_invalid")
    preview = local_additive_plan(
        config,
        source,
        receipt_root=receipt_root,
        qualification_path=qualification_path,
    )
    if preview["status"] == "current":
        return preview
    qualification = (
        _local_discover_qualification(
            release_id=preview["release_id"],
            artifact_name=preview["artifact"]["name"],
        )
        if qualification_path is None
        else _local_discover_qualification(
            qualification_path,
            release_id=preview["release_id"],
            artifact_name=preview["artifact"]["name"],
        )
    )
    artifact = qualification["_canonical_artifact"]
    sql_path = ROOT / artifact["relative_path"]
    statements = split_sql(sql_path.read_text(encoding="utf-8"))
    classes = [_local_classify_statement(statement) for statement in statements]
    started = time_module.monotonic()
    events = _local_read_events(
        receipt_root, source, qualification["release_id"]
    )
    statement_hashes = [_local_digest(statement.encode("utf-8")) for statement in statements]
    baseline, verified = _local_resume_context(
        events,
        qualification["release_id"],
        source,
        statement_hashes,
        preview["source_schema_sha256"],
    )
    local_backup = _local_validate_backup(
        config,
        source,
        qualification,
        baseline,
        backup_dump_path=backup_dump_path,
        backup_receipt_path=backup_receipt_path,
    )
    previous: Mapping[str, Any] | None = events[-1] if events else None
    if not events:
        previous = _local_append_event(
            receipt_root,
            source,
            qualification["release_id"],
            "baseline_captured",
            None,
            source_database=source,
            source_schema_sha256=baseline,
            statement_hashes=statement_hashes,
            data_fingerprint_sha256=local_backup["data_fingerprint_sha256"],
        )
    with _local_maintenance_lock(config, source, lock_timeout_seconds):
        locked_snapshot = local_additive_source_snapshot(config, source)["snapshot"]
        if not events and locked_snapshot["sha256"] != baseline:
            raise LocalAdditiveBlocked("source changed after plan or lock", code="source_changed")
        if server_identity(config, source)["database"] != source:
            raise LocalAdditiveBlocked("source changed after plan or lock", code="source_changed")
        _local_verify_backup_rows(config, source, local_backup)
        connection = _local_connect(config, source, duration_guard_ms)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET SESSION lock_wait_timeout=%s", (lock_timeout_seconds,))
                cursor.execute("SET SESSION innodb_lock_wait_timeout=%s", (lock_timeout_seconds,))
                previous = _local_append_event(receipt_root, source, qualification["release_id"], "maintenance_lock_acquired", previous, source_database=source, source_schema_sha256=baseline)
                for ordinal, (statement, statement_class) in enumerate(zip(statements, classes), 1):
                    statement_hash = _local_digest(statement.encode("utf-8"))
                    if ordinal in verified:
                        if verified[ordinal] != statement_hash:
                            raise LocalAdditiveBlocked("additive journal ordinal hash conflict", code="journal_conflict")
                        continue
                    if (time_module.monotonic() - started) * 1000 >= duration_guard_ms:
                        raise LocalAdditiveBlocked("additive duration guard exceeded", code="blocked_duration_exceeded")
                    previous = _local_append_event(receipt_root, source, qualification["release_id"], "statement_started", previous, source_database=source, source_schema_sha256=baseline, ordinal=ordinal, statement_sha256=statement_hash, classification=statement_class)
                    try:
                        cursor.execute(statement)
                    except (TimeoutError, OSError) as error:
                        raise LocalAdditiveBlocked(
                            "bounded DDL client timeout; outcome requires reconciliation",
                            code="blocked_duration_exceeded",
                        ) from error
                    elapsed = int((time_module.monotonic() - started) * 1000)
                    previous = _local_append_event(receipt_root, source, qualification["release_id"], "statement_verified", previous, source_database=source, source_schema_sha256=baseline, ordinal=ordinal, statement_sha256=statement_hash, classification=statement_class, outcome="applied", elapsed_ms=elapsed)
                    if elapsed >= duration_guard_ms:
                        raise LocalAdditiveBlocked("additive duration guard exceeded", code="blocked_duration_exceeded")
        finally:
            connection.close()
        # Keep the post-DDL descriptor read under the named lock so another
        # local process cannot change the contract between apply and verify.
        after = local_additive_source_snapshot(config, source)["snapshot"]
        descriptor = local_additive_release_qualification(qualification["release_id"], artifact["name"])["schema_artifacts"][0]["descriptor"]
        if local_additive_descriptor_state(after, descriptor, artifact["name"]) != "exact":
            raise LocalAdditiveBlocked("post-apply descriptor is not exact", code="descriptor_drift")
        _local_verify_backup_rows(config, source, local_backup)
    elapsed = int((time_module.monotonic() - started) * 1000)
    result = {
        **preview,
        "status": "completed",
        "elapsed_ms": elapsed,
        "post_schema_sha256": after["sha256"],
        "backup_receipt": local_backup["receipt_path"],
        "backup_dump_sha256": local_backup["sha256"],
    }
    previous = _local_append_event(receipt_root, source, qualification["release_id"], "completed", previous, source_database=source, source_schema_sha256=baseline, post_schema_sha256=after["sha256"], elapsed_ms=elapsed, backup_receipt=local_backup["receipt_path"], backup_dump_sha256=local_backup["sha256"])
    _local_write_receipt(receipt_root, source, result)
    return result


def build_plan(
    config: DatabaseConfig,
    source: str,
    candidate: str,
    allowed_partial_artifacts: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    validate_database_names(source, candidate)
    source_identity = server_identity(config, source)
    source_snapshot = _schema_snapshot(config, source)
    source_objects = _owned_classification(
        source_snapshot, defer_missing_triggers=True
    )
    blocking_states = _blocking_schema_states(
        source_objects, allowed_partial_artifacts
    )
    if blocking_states:
        raise UpgradeBlocked(
            f"source contains partial/drift owned objects: {blocking_states}"
        )
    candidate_exists = database_exists(config, candidate)
    source_data = _table_evidence(config, source)
    retired_nonempty = sorted(
        table
        for table in INTENTIONALLY_RETIRED_EMPTY_TABLES
        if int((source_data.get(table) or {}).get("count", 0)) != 0
    )
    if retired_nonempty:
        raise UpgradeBlocked(
            "retired tables are not empty: " + ", ".join(retired_nonempty)
        )
    legacy_knowledge_rebuild = _legacy_knowledge_rebuild_plan(
        source_snapshot, source_data
    )
    candidate_data = (
        _table_evidence(config, candidate) if candidate_exists else None
    )
    candidate_matches_source = (
        _candidate_preserves_source_data(source_data, candidate_data)
        if candidate_exists and candidate_data is not None
        else None
    )
    plan = {
        "contract": "preserved-database-additive-upgrade/v1",
        "release_id": RELEASE_MANIFEST.release_id,
        "release_fingerprint": RELEASE_MANIFEST.fingerprint,
        "created_at": _now(),
        "source": source_identity,
        "candidate_database": candidate,
        "candidate_exists": candidate_exists,
        "candidate_precondition": "source_data_must_match_before_apply",
        "candidate_matches_source": candidate_matches_source,
        "schema_artifacts": schema_artifacts(),
        "source_schema_sha256": source_snapshot["sha256"],
        "source_objects": source_objects,
        "source_data": source_data,
        "legacy_knowledge_empty_rebuild": legacy_knowledge_rebuild,
        "phase_order": [path.name for path in SCHEMA_PARTS],
        "status": (
            "blocked"
            if candidate_exists and not candidate_matches_source
            else "ready"
        ),
    }
    plan["plan_fingerprint"] = _sha256_bytes(_canonical_json(plan))
    return plan


# 保持單一 preflight，讓空表、外部 FK 與 fingerprint 共同決定資格。
def _legacy_knowledge_rebuild_plan(
    snapshot: Mapping[str, Any],
    source_data: Mapping[str, Any],
) -> dict[str, Any]:
    if _legacy_knowledge_schema_state(snapshot) != "exact":
        return {"eligible": False}
    nonempty = sorted(
        table for table in LEGACY_KNOWLEDGE_REBUILD_TABLES
        if int((source_data.get(table) or {}).get("count", 0)) != 0
    )
    if nonempty:
        raise UpgradeBlocked(
            "legacy Knowledge tables are not empty: " + ", ".join(nonempty)
        )
    preserved_state = _canonical_artifact_metadata_state(
        snapshot,
        "163_knowledge_runtime.sql",
        owned_tables=LEGACY_KNOWLEDGE_PRESERVED_TABLES,
    )
    if preserved_state != "exact":
        raise UpgradeBlocked(
            "preserved Knowledge request/job tables are not canonical-exact"
        )
    inbound = _external_knowledge_inbound_foreign_keys(snapshot)
    if inbound:
        raise UpgradeBlocked(
            "legacy Knowledge tables have external inbound foreign keys: "
            + ", ".join(inbound)
        )
    return {
        "eligible": True,
        "contract": "legacy-knowledge-stage8-preserved-queue-rebuild/v2",
        "tables": sorted(LEGACY_KNOWLEDGE_TABLES),
        "preserved_tables": sorted(LEGACY_KNOWLEDGE_PRESERVED_TABLES),
        "rebuild_tables": sorted(LEGACY_KNOWLEDGE_REBUILD_TABLES),
        "source_schema_sha256": snapshot["sha256"],
    }


def _external_knowledge_inbound_foreign_keys(
    snapshot: Mapping[str, Any],
) -> tuple[str, ...]:
    return tuple(sorted({
        f"{row['table_name']}.{row['constraint_name']}"
        for row in snapshot.get("key_columns", ())
        if str(row.get("referenced_table_name")) in LEGACY_KNOWLEDGE_TABLES
        and str(row["table_name"]) not in LEGACY_KNOWLEDGE_TABLES
    }))


def _blocking_schema_states(
    states: Mapping[str, str],
    allowed_partial_artifacts: frozenset[str],
) -> dict[str, str]:
    return {
        name: state
        for name, state in states.items()
        if state == "drift"
        or (
            state == "partial"
            and name not in allowed_partial_artifacts
            and name not in PURE_RETIREMENT_ARTIFACTS
        )
    }


def _candidate_preserves_source_data(
    source_data: Mapping[str, Any],
    candidate_data: Mapping[str, Any],
) -> bool:
    for table, expected in source_data.items():
        if candidate_data.get(table) != expected:
            return False
    return True


def _validate_plan_integrity(
    plan: Mapping[str, Any], fresh: Mapping[str, Any]
) -> None:
    fingerprint_payload = dict(plan)
    recorded_fingerprint = fingerprint_payload.pop("plan_fingerprint", None)
    if not isinstance(recorded_fingerprint, str) or (
        _sha256_bytes(_canonical_json(fingerprint_payload))
        != recorded_fingerprint
    ):
        raise UpgradeBlocked("plan fingerprint is invalid")
    for key in (
        "release_id",
        "release_fingerprint",
        "schema_artifacts",
        "phase_order",
    ):
        if plan.get(key) != fresh.get(key):
            raise UpgradeBlocked(f"plan artifact changed after planning: {key}")
    for key in ("release_id", "release_fingerprint"):
        if plan.get(key) != fresh.get(key):
            raise UpgradeBlocked(f"plan release changed after planning: {key}")
    if plan.get("candidate_database") != fresh.get("candidate_database"):
        raise UpgradeBlocked("plan candidate identity mismatch")
    planned_source = plan.get("source") or {}
    fresh_source = fresh.get("source") or {}
    for key in ("database", "server", "host", "port"):
        if planned_source.get(key) != fresh_source.get(key):
            raise UpgradeBlocked(f"plan source identity mismatch: {key}")


def validate_dump(
    dump_path: Path, receipt_path: Path, source: str, identity: Mapping[str, Any]
) -> dict[str, Any]:
    path = dump_path.expanduser().resolve()
    if not path.is_file() or path.stat().st_size <= 0:
        raise UpgradeBlocked("source dump is missing or empty")
    head = path.read_bytes()[: 1024 * 1024]
    if MYSQL_DUMP_MARKER not in head:
        raise UpgradeBlocked("source backup is not a mysqldump artifact")
    markers = (
        f"Database: {source}".encode("utf-8"),
        f"Current Database: `{source}`".encode("utf-8"),
    )
    if not any(marker in head for marker in markers):
        raise UpgradeBlocked("source backup does not identify source database")
    receipt = read_receipt(receipt_path)
    expected = {
        "database": source,
        "server": identity["server"],
        "sha256": _sha256_file(path),
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise UpgradeBlocked(f"source backup receipt mismatch: {key}")
    return {"path": str(path), "size": path.stat().st_size, **expected}


def _client_environment(config: DatabaseConfig) -> dict[str, str]:
    environment = os.environ.copy()
    environment["MYSQL_PWD"] = config.password
    return environment


def _mysql_base(
    config: DatabaseConfig,
    executable: str,
    *,
    container: str | None = None,
) -> list[str]:
    prefix = [executable]
    host = config.host
    port = config.port
    if container:
        if not IDENTIFIER.fullmatch(container.replace("-", "_")):
            raise UpgradeBlocked("invalid mysql container name")
        prefix = [
            "docker", "exec", "-i", "-e", "MYSQL_PWD",
            container, executable,
        ]
        host = "127.0.0.1"
        port = 3306
    return prefix + [
        "--host", host, "--port", str(port),
        "--user", config.user, "--default-character-set=utf8mb4",
    ]


def create_source_dump(
    config: DatabaseConfig,
    source: str,
    dump_path: Path,
    receipt_path: Path,
    *,
    mysqldump: str = "mysqldump",
    mysql_container: str | None = None,
) -> dict[str, Any]:
    identity = server_identity(config, source)
    target = dump_path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    command = _mysql_base(
        config, mysqldump, container=mysql_container
    ) + [
        "--single-transaction", "--routines", "--events", "--triggers",
        "--no-tablespaces", "--hex-blob", source,
    ]
    with target.open("wb") as output:
        completed = subprocess.run(
            command, stdout=output, stderr=subprocess.PIPE,
            env=_client_environment(config), check=False,
        )
    if completed.returncode != 0 or target.stat().st_size <= 0:
        raise UpgradeBlocked("mysqldump failed or produced an empty artifact")
    receipt = {
        "kind": "source_backup",
        "created_at": _now(),
        "database": source,
        "server": identity["server"],
        "sha256": _sha256_file(target),
        "size": target.stat().st_size,
        "exit_code": completed.returncode,
    }
    write_receipt(receipt_path, receipt)
    return receipt


def restore_candidate(
    config: DatabaseConfig | SeparateDatabaseConfig,
    source: str,
    candidate: str,
    dump_path: Path,
    backup_receipt_path: Path,
    operation_receipt_path: Path,
    *,
    mysql: str = "mysql",
    mysql_container: str | None = None,
) -> dict[str, Any]:
    validate_database_names(source, candidate)
    candidate_config = _candidate_connection_config(config, candidate)
    if database_exists(config, candidate):
        raise UpgradeBlocked("candidate must not exist before restore")
    identity = server_identity(config, source)
    dump = validate_dump(dump_path, backup_receipt_path, source, identity)
    prepared = {
        "kind": "preserved_database_upgrade",
        "status": "prepared",
        "phase": "restore",
        "created_at": _now(),
        "source": identity,
        "candidate_database": candidate,
        "source_dump": dump,
    }
    write_receipt(operation_receipt_path, prepared)
    connection = candidate_config.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE `{candidate}` CHARACTER SET utf8mb4")
    finally:
        connection.close()
    command = _mysql_base(
        candidate_config, mysql, container=mysql_container
    ) + [candidate]
    with dump_path.expanduser().resolve().open("rb") as source_handle:
        completed = subprocess.run(
            command, stdin=source_handle, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_client_environment(candidate_config),
            check=False,
        )
    if completed.returncode != 0:
        prepared.update(
            status="partial", failed_phase="restore",
            mysql_exit_code=completed.returncode,
        )
        write_receipt(operation_receipt_path, prepared)
        raise UpgradeBlocked("mysql restore failed; candidate retained")
    source_data = _table_evidence(config, source)
    candidate_data = _table_evidence(config, candidate)
    if source_data != candidate_data:
        prepared.update(status="partial", failed_phase="restore_validation")
        write_receipt(operation_receipt_path, prepared)
        raise UpgradeBlocked("restored candidate differs from source")
    source_snapshot = _schema_snapshot(config, source)
    source_trigger_visibility = bool(source_snapshot["triggers"])
    source_programs = _restored_schema_program_evidence(
        source_snapshot, source, include_triggers=source_trigger_visibility
    )
    candidate_programs = _restored_schema_program_evidence(
        _schema_snapshot(config, candidate), candidate, (source,),
        include_triggers=source_trigger_visibility,
    )
    if source_programs != candidate_programs:
        prepared.update(
            status="partial", failed_phase="restore_program_validation"
        )
        write_receipt(operation_receipt_path, prepared)
        raise UpgradeBlocked(
            "restored candidate triggers/views differ from source"
        )
    prepared.update(
        status="restored", restored_at=_now(),
        candidate=server_identity(config, candidate),
        restored_data=candidate_data,
        restored_programs=candidate_programs,
        source_trigger_visibility=source_trigger_visibility,
    )
    write_receipt(operation_receipt_path, prepared)
    return prepared


def split_sql(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""
        if quote:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
            current.append(char)
        elif char == "-" and next_char == "-" and (
            index + 2 == len(sql) or sql[index + 2].isspace()
        ):
            while index < len(sql) and sql[index] not in "\r\n":
                index += 1
            current.append("\n")
            continue
        elif char == "#":
            while index < len(sql) and sql[index] not in "\r\n":
                index += 1
            current.append("\n")
            continue
        elif char == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)
        index += 1
    trailing = "".join(current).strip()
    if trailing:
        statements.append(trailing)
    return statements


def _split_top_level(value: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    escaped = False
    for char in value:
        if quote:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
            current.append(char)
        elif char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
        else:
            current.append(char)
    trailing = "".join(current).strip()
    if trailing:
        parts.append(trailing)
    return parts


def _sql_without_unsafe_rendering_differences(value: Any) -> str:
    text = str(value or "")
    text = re.sub(
        r"(?i)_(?:utf8mb4|utf8mb3|utf8|latin1|ascii|binary)"
        r"(?=\\?['\"])",
        "",
        text,
    )
    text = text.replace("\\'", "'").replace('\\"', '"')
    text = re.sub(
        r"(?i)(`?[A-Za-z0-9_]+`?)\s+REGEXP\s+"
        r"('(?:''|[^'])*')",
        r"regexp_like(\1,\2)",
        text,
    )
    normalized: list[str] = []
    quote: str | None = None
    escaped = False
    pending_space = False
    for char in text:
        if quote:
            normalized.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            if pending_space and normalized:
                normalized.append(" ")
            pending_space = False
            quote = char
            normalized.append(char)
        elif char == "`":
            continue
        elif char.isspace():
            pending_space = True
        else:
            if pending_space and normalized:
                normalized.append(" ")
            pending_space = False
            normalized.append(char.casefold())
    return "".join(normalized).strip()


def _strip_outer_sql_parentheses(value: str) -> str:
    result = value.strip()
    while result.startswith("(") and result.endswith(")"):
        try:
            _, closing = _extract_parenthesized(result, 0)
        except UpgradeBlocked:
            break
        if closing != len(result) - 1:
            break
        result = result[1:-1]
    return result


def _split_top_level_boolean(
    value: str, keyword: str
) -> list[str] | None:
    parts: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None
    escaped = False
    index = 0
    lowered = value.casefold()
    target = keyword.casefold()
    while index < len(value):
        char = value[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            index += 1
            continue
        if char == "(":
            depth += 1
            index += 1
            continue
        if char == ")":
            depth -= 1
            index += 1
            continue
        if depth == 0 and lowered.startswith(target, index):
            before = value[index - 1] if index else " "
            after_index = index + len(target)
            after = value[after_index] if after_index < len(value) else " "
            if (
                not (before.isalnum() or before == "_")
                and not (after.isalnum() or after == "_")
            ):
                parts.append(value[start:index].strip())
                start = after_index
                index = after_index
                continue
        index += 1
    if not parts:
        return None
    parts.append(value[start:].strip())
    return parts


def _compact_sql_atom(value: str) -> str:
    compact: list[str] = []
    quote: str | None = None
    escaped = False
    for char in value:
        if quote:
            compact.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in {"'", '"'}:
            quote = char
            compact.append(char)
        elif not char.isspace():
            compact.append(char)
    return "".join(compact)


def _boolean_contract_tree(value: str) -> tuple[str, Any]:
    expression = _strip_outer_sql_parentheses(value)
    for keyword in ("or", "and"):
        parts = _split_top_level_boolean(expression, keyword)
        if parts:
            return (
                keyword,
                tuple(_boolean_contract_tree(part) for part in parts),
            )
    unary_not = re.match(r"^not\b(.*)$", expression, re.I | re.S)
    if unary_not:
        return _negate_boolean_contract_tree(
            _boolean_contract_tree(unary_not.group(1))
        )
    return ("atom", _compact_sql_atom(expression))


def _negate_boolean_contract_tree(
    node: tuple[str, Any],
) -> tuple[str, Any]:
    operator, payload = node
    if operator == "and":
        return (
            "or",
            tuple(
                _negate_boolean_contract_tree(child) for child in payload
            ),
        )
    if operator == "or":
        return (
            "and",
            tuple(
                _negate_boolean_contract_tree(child) for child in payload
            ),
        )
    if operator == "not":
        return payload
    return ("not", node)


def _render_boolean_contract_tree(node: tuple[str, Any]) -> str:
    operator, payload = node
    if operator == "atom":
        return f"atom({payload})"
    if operator == "not":
        return f"not({_render_boolean_contract_tree(payload)})"
    return (
        f"{operator}("
        + ",".join(
            _render_boolean_contract_tree(child) for child in payload
        )
        + ")"
    )


def _canonical_boolean_contract(value: str) -> str:
    return _render_boolean_contract_tree(_boolean_contract_tree(value))


def _normalize_sql_contract(value: Any) -> str:
    lexical = _sql_without_unsafe_rendering_differences(value)
    lexical = re.sub(
        r"\(\s*([A-Za-z0-9_]+\s*[+\-*/]\s*[A-Za-z0-9_]+)\s*\)"
        r"\s*(<=|>=|<>|!=|=|<|>)",
        r"\1\2",
        lexical,
    )
    return _canonical_boolean_contract(lexical)


def _extract_parenthesized(value: str, opening: int) -> tuple[str, int]:
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(opening, len(value)):
        char = value[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return value[opening + 1:index], index
    raise UpgradeBlocked("canonical schema artifact has unbalanced parentheses")


def _parse_column_definition(definition: str) -> tuple[str, dict[str, Any]]:
    match = re.match(r"^`?([A-Za-z0-9_]+)`?\s+(.+)$", definition, re.S)
    if not match:
        raise UpgradeBlocked("canonical column definition is invalid")
    name, remainder = match.groups()
    type_match = re.match(
        r"^([A-Za-z]+(?:\s+UNSIGNED)?(?:\([^)]*\))?"
        r"(?:\s+UNSIGNED)?)(?=\s|$)",
        remainder,
        re.I | re.S,
    )
    if not type_match:
        raise UpgradeBlocked(f"canonical column type is invalid: {name}")
    column_type = _normalize_column_type_contract(type_match.group(1))
    upper = remainder.upper()
    nullable = "NO" if (
        "NOT NULL" in upper or "PRIMARY KEY" in upper
    ) else "YES"
    default_match = re.search(
        r"\bDEFAULT\s+("
        r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"|"
        r"[A-Za-z_]+(?:\(\d*\))?|[-+]?\d+(?:\.\d+)?"
        r")",
        remainder,
        re.I,
    )
    default: Any = None
    if default_match:
        token = default_match.group(1)
        if token.upper() != "NULL":
            default = token.strip("'\"").casefold()
            if default in {"false", "true"}:
                default = "0" if default == "false" else "1"
    extra_parts: list[str] = []
    if (
        default is not None
        and re.fullmatch(r"current_timestamp(?:\(\d*\))?", default)
    ):
        extra_parts.append("default_generated")
    if "AUTO_INCREMENT" in upper:
        extra_parts.append("auto_increment")
    update_match = re.search(
        r"\bON\s+UPDATE\s+([A-Za-z_]+(?:\(\d*\))?)",
        remainder,
        re.I,
    )
    if update_match:
        extra_parts.append(
            "on update " + update_match.group(1).casefold()
        )
    generated_extra = _generated_column_extra(remainder)
    if generated_extra:
        extra_parts.append(generated_extra)
    return name, {
        "column_type": column_type,
        "is_nullable": nullable,
        "column_default": default,
        "extra": " ".join(extra_parts),
    }


def _generated_column_extra(remainder: str) -> str:
    """Return MySQL's canonical generated-column EXTRA without false positives."""
    generated_pattern = re.compile(
        r"\bGENERATED\s+ALWAYS\s+AS\s*\(", re.I | re.S
    )
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(remainder):
        char = remainder[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"', "`"}:
            quote = char
            index += 1
            continue
        match = generated_pattern.match(remainder, index)
        if match:
            opening = remainder.find("(", index, match.end())
            _, closing = _extract_parenthesized(remainder, opening)
            storage = re.search(
                r"\b(STORED|VIRTUAL)\b", remainder[closing + 1 :], re.I
            )
            if storage:
                return storage.group(1).casefold() + " generated"
            return "generated"
        index += 1
    return ""


def _normalize_column_type_contract(value: Any) -> str:
    normalized: list[str] = []
    quote: str | None = None
    escaped = False
    pending_space = False
    for char in str(value or ""):
        if quote:
            normalized.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            if pending_space and normalized and normalized[-1] not in "(,":
                normalized.append(" ")
            pending_space = False
            quote = char
            normalized.append(char)
        elif char.isspace():
            pending_space = True
        elif char in "(),":
            while normalized and normalized[-1] == " ":
                normalized.pop()
            normalized.append(char)
            pending_space = False
        else:
            if pending_space and normalized and normalized[-1] not in "(,":
                normalized.append(" ")
            pending_space = False
            normalized.append(char.casefold())
    contract = "".join(normalized).strip()
    return "tinyint(1)" if contract in {"bool", "boolean"} else contract


def _parse_index_columns(value: str) -> tuple[str, ...]:
    return tuple(
        re.sub(r"\s+(?:ASC|DESC)\b", "", item, flags=re.I)
        .strip()
        .strip("`")
        .casefold()
        for item in _split_top_level(value)
    )


def _canonical_artifact_descriptor(part_name: str) -> dict[str, Any]:
    path = next(
        (path for path in SCHEMA_PARTS if path.name == part_name),
        None,
    )
    if path is None:
        raise UpgradeBlocked(f"canonical schema part is missing: {part_name}")
    sql = path.read_text(encoding="utf-8")
    descriptor: dict[str, Any] = {
        "tables": {},
        "indexes": {},
        "foreign_keys": {},
        "checks": {},
        "triggers": {},
        "parent_columns": {},
    }
    create_pattern = re.compile(
        r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+`?([A-Za-z0-9_]+)`?\s*\(",
        re.I,
    )
    for match in create_pattern.finditer(sql):
        table = match.group(1)
        body, _ = _extract_parenthesized(sql, match.end() - 1)
        columns: dict[str, Any] = {}
        for definition in _split_top_level(body):
            normalized = definition.strip()
            upper = normalized.upper()
            if upper.startswith(("PRIMARY KEY", "UNIQUE KEY", "INDEX ", "KEY ")):
                index_match = re.match(
                    r"^(PRIMARY\s+KEY|UNIQUE\s+KEY|INDEX|KEY)"
                    r"(?:\s+`?([A-Za-z0-9_]+)`?)?\s*\(",
                    normalized,
                    re.I,
                )
                if not index_match:
                    raise UpgradeBlocked("canonical index definition is invalid")
                inside, _ = _extract_parenthesized(
                    normalized, index_match.end() - 1
                )
                kind = re.sub(
                    r"\s+", " ", index_match.group(1)
                ).upper()
                name = (
                    "PRIMARY"
                    if kind == "PRIMARY KEY"
                    else str(index_match.group(2))
                )
                descriptor["indexes"][(table, name)] = {
                    "non_unique": 0 if kind in {
                        "PRIMARY KEY", "UNIQUE KEY"
                    } else 1,
                    "columns": _parse_index_columns(inside),
                }
                continue
            if upper.startswith("CONSTRAINT "):
                constraint_match = re.match(
                    r"^CONSTRAINT\s+`?([A-Za-z0-9_]+)`?\s+(.+)$",
                    normalized,
                    re.I | re.S,
                )
                if not constraint_match:
                    raise UpgradeBlocked(
                        "canonical constraint definition is invalid"
                    )
                name, contract = constraint_match.groups()
                if re.match(r"^FOREIGN\s+KEY", contract, re.I):
                    local_open = contract.index("(")
                    local, local_end = _extract_parenthesized(
                        contract, local_open
                    )
                    reference = re.search(
                        r"REFERENCES\s+`?([A-Za-z0-9_]+)`?\s*\(",
                        contract[local_end + 1:],
                        re.I,
                    )
                    if not reference:
                        raise UpgradeBlocked(
                            "canonical foreign key reference is invalid"
                        )
                    reference_offset = local_end + 1 + reference.end() - 1
                    remote, _ = _extract_parenthesized(
                        contract, reference_offset
                    )
                    update = re.search(
                        r"ON\s+UPDATE\s+(RESTRICT|CASCADE|SET\s+NULL|NO\s+ACTION)",
                        contract,
                        re.I,
                    )
                    delete = re.search(
                        r"ON\s+DELETE\s+(RESTRICT|CASCADE|SET\s+NULL|NO\s+ACTION)",
                        contract,
                        re.I,
                    )
                    descriptor["foreign_keys"][(table, name)] = {
                        "columns": _parse_index_columns(local),
                        "referenced_table": reference.group(1).casefold(),
                        "referenced_columns": _parse_index_columns(remote),
                        "update_rule": (
                            re.sub(r"\s+", " ", update.group(1)).upper()
                            if update else "RESTRICT"
                        ),
                        "delete_rule": (
                            re.sub(r"\s+", " ", delete.group(1)).upper()
                            if delete else "RESTRICT"
                        ),
                    }
                elif re.match(r"^CHECK\s*\(", contract, re.I):
                    opening = contract.index("(")
                    clause, _ = _extract_parenthesized(contract, opening)
                    descriptor["checks"][(table, name)] = (
                        _normalize_sql_contract(clause)
                    )
                continue
            name, column = _parse_column_definition(normalized)
            columns[name] = column
            if "PRIMARY KEY" in upper:
                descriptor["indexes"][(table, "PRIMARY")] = {
                    "non_unique": 0,
                    "columns": (name.casefold(),),
                }
        descriptor["tables"][table] = columns
    trigger_pattern = re.compile(
        r"CREATE\s+TRIGGER\s+`?([A-Za-z0-9_]+)`?\s+"
        r"(BEFORE|AFTER)\s+(INSERT|UPDATE|DELETE)\s+ON\s+"
        r"`?([A-Za-z0-9_]+)`?\s+FOR\s+EACH\s+ROW\s+(.+?)(?=;\s*(?:$|\n))",
        re.I | re.S,
    )
    for match in trigger_pattern.finditer(sql + "\n"):
        name, timing, event, table, body = match.groups()
        descriptor["triggers"][name] = {
            "action_timing": timing.upper(),
            "event_manipulation": event.upper(),
            "event_object_table": table,
            "action_statement": _normalize_sql_contract(body),
        }
    if part_name == "105_order_service_time_terms.sql":
        descriptor["parent_columns"]["orders"] = {
            "service_start_time": {
                "column_type": "time",
                "is_nullable": "YES",
                "column_default": None,
                "extra": "",
            },
            "service_end_time": {
                "column_type": "time",
                "is_nullable": "YES",
                "column_default": None,
                "extra": "",
            },
            "service_end_day_offset": {
                "column_type": "tinyint unsigned",
                "is_nullable": "YES",
                "column_default": None,
                "extra": "",
            },
        }
        descriptor["checks"].update(
            {
                ("orders", "chk_orders_service_time_terms_complete"):
                    _normalize_sql_contract(
                        "((service_start_time IS NULL AND "
                        "service_end_time IS NULL AND "
                        "service_end_day_offset IS NULL) OR "
                        "(service_start_time IS NOT NULL AND "
                        "service_end_time IS NOT NULL AND "
                        "service_end_day_offset IS NOT NULL))"
                    ),
                ("orders", "chk_orders_service_end_day_offset"):
                    _normalize_sql_contract(
                        "service_end_day_offset IS NULL OR "
                        "service_end_day_offset IN (0,1)"
                    ),
            }
        )
    if part_name == "106_order_lifecycle_control_facts.sql":
        descriptor["parent_columns"]["orders"] = {
            "lifecycle_version": {
                "column_type": "bigint unsigned",
                "is_nullable": "NO",
                "column_default": "0",
                "extra": "",
            }
        }
    if part_name == "163_knowledge_runtime.sql":
        descriptor["parent_columns"]["knowledge_items"] = {
            "source_identity": {
                "column_type": "varchar(191)",
                "is_nullable": "YES",
                "column_default": None,
                "extra": "",
            }
        }
        descriptor["indexes"][(
            "knowledge_items",
            "uq_knowledge_source_identity",
        )] = {
            "non_unique": 0,
            "columns": ("source_identity",),
        }
    if part_name == "186_line_identity_management.sql":
        descriptor["tables"]["line_identity_revocation_requests"][
            "active_marker"
        ]["extra"] = "stored generated"
        descriptor["parent_columns"]["line_identity_bindings"] = {
            "binding_status": {
                "column_type": "enum('unbound','pending_review','bound','revocation_pending','revoked')",
                "is_nullable": "NO",
                "column_default": "unbound",
                "extra": "",
            },
            "active_subject_key": {
                "column_type": "varchar(400)",
                "is_nullable": "YES",
                "column_default": None,
                "extra": "stored generated",
            },
        }
        descriptor["parent_columns"]["line_identity_binding_events"] = {
            "action": {
                "column_type": "enum('claim_submitted','bound','revocation_requested','revoked','rebound','legacy_imported')",
                "is_nullable": "NO",
                "column_default": None,
                "extra": "",
            }
        }
    if part_name == "185_customer_service_runtime.sql":
        descriptor["tables"]["customer_service_tickets"][
            "active_marker"
        ]["extra"] = "stored generated"
    if part_name == "1024_task96_line_identity_revocation_role_binding_fk.sql":
        descriptor["foreign_keys"][(
            "line_identity_revocation_requests",
            "fk_line_identity_revocation_role_binding",
        )] = {
            "columns": ("line_user_id", "subject_type"),
            "referenced_table": "line_identity_role_bindings",
            "referenced_columns": ("line_user_id", "subject_type"),
            "update_rule": "RESTRICT",
            "delete_rule": "RESTRICT",
        }
    if part_name == "1026_task96_scheduling_service_day_attachment_kind.sql":
        descriptor["parent_columns"]["scheduling_service_day_log_attachments"] = {
            "attachment_kind": _column_contract(
                "enum('meal_photo','baby_log_photo')", "NO"
            )
        }
    if part_name == "1027_historical_order_pairing_resolution_reused.sql":
        descriptor["parent_columns"]["historical_order_pairing_evidence"] = {
            "resolution": _column_contract(
                "enum('blank','staff_missing','staff_ambiguous',"
                "'evidence_only','assignment_candidate','assignment_reused',"
                "'assignment_conflict')",
                "NO",
            )
        }
    if part_name == "1028_historical_service_accounting.sql":
        historical_statuses = (
            "enum('待補件','洽談中','訂單成立','服務中','訂單完成','訂單取消',"
            "'歷史訂單－未服務','歷史訂單－服務中','歷史訂單－服務完成',"
            "'歷史訂單－帳務完成')"
        )
        descriptor["parent_columns"]["orders"] = {
            "status": _column_contract(historical_statuses, "NO", "洽談中")
        }
        for column_name in ("before_status", "after_status"):
            descriptor["checks"][(
                "order_lifecycle_state_events",
                f"chk_order_lifecycle_state_event_{column_name}",
            )] = _normalize_sql_contract(
                f"{column_name} IN ('待補件','洽談中','訂單成立','服務中',"
                "'訂單完成','訂單取消','歷史訂單－未服務','歷史訂單－服務中',"
                "'歷史訂單－服務完成','歷史訂單－帳務完成')"
            )
    if part_name == "1005_contract_external_signing_successor.sql":
        purpose_column = _column_contract(
            "enum('unsigned_contract','final_signed_contract',"
            "'service_date_confirmation','baby_log_photo','meal_photo',"
            "'order_notice','staff_resume','staff_certificate',"
            "'staff_health_exam','rich_menu_background')",
            "NO",
        )
        descriptor["parent_columns"]["controlled_file_staging_objects"] = {
            "purpose": purpose_column,
        }
        descriptor["parent_columns"]["controlled_file_objects"] = {
            "purpose": purpose_column,
        }
        owner_purpose = _normalize_sql_contract(
            "(owner_type = 'contract_signing' AND purpose IN "
            "('unsigned_contract', 'final_signed_contract')) OR "
            "(owner_type = 'scheduling' AND purpose IN "
            "('service_date_confirmation', 'baby_log_photo', 'meal_photo')) OR "
            "(owner_type = 'orders' AND purpose = 'order_notice') OR "
            "(owner_type = 'staff' AND purpose IN "
            "('staff_resume', 'staff_certificate', 'staff_health_exam')) OR "
            "(owner_type = 'line_integration' AND purpose = 'rich_menu_background')"
        )
        descriptor["checks"][(
            "controlled_file_staging_objects",
            "chk_controlled_file_staging_owner_purpose",
        )] = owner_purpose
        descriptor["checks"][(
            "controlled_file_objects",
            "chk_controlled_file_object_owner_purpose",
        )] = owner_purpose
        descriptor["indexes"][(
            "controlled_file_staging_objects",
            "idx_controlled_file_staging_owner",
        )] = {
            "non_unique": 1,
            "columns": (
                "owner_type", "subject_reference", "purpose", "staging_state", "id",
            ),
        }
        descriptor["indexes"][(
            "controlled_file_objects",
            "uq_controlled_file_version_identity",
        )] = {
            "non_unique": 0,
            "columns": (
                "id", "owner_type", "subject_reference", "object_key", "purpose",
                "version_number",
            ),
        }
        descriptor["indexes"][(
            "controlled_file_objects",
            "idx_controlled_file_object_owner",
        )] = {
            "non_unique": 1,
            "columns": ("owner_type", "subject_reference", "purpose", "id"),
        }
        descriptor["foreign_keys"][(
            "controlled_file_objects",
            "fk_controlled_file_object_supersedes",
        )] = {
            "columns": (
                "supersedes_object_id", "owner_type", "subject_reference", "object_key",
                "purpose", "supersedes_version_number",
            ),
            "referenced_table": "controlled_file_objects",
            "referenced_columns": (
                "id", "owner_type", "subject_reference", "object_key", "purpose",
                "version_number",
            ),
            "update_rule": "RESTRICT",
            "delete_rule": "RESTRICT",
        }
    if part_name == "1007_finance_recovery_evidence.sql":
        evidence_column = _column_contract("varchar(500)", "YES")
        evidence_check = _normalize_sql_contract(
            "evidence_reference IS NULL OR "
            "CHAR_LENGTH(TRIM(evidence_reference)) > 0"
        )
        for table, check_name in (
            (
                "client_over_refund_recovery_events",
                "chk_client_over_refund_recovery_event_evidence",
            ),
            (
                "client_over_refund_recovery_matchings",
                "chk_client_over_refund_recovery_matching_evidence",
            ),
            (
                "staff_overpayment_recovery_events",
                "chk_staff_overpayment_recovery_event_evidence",
            ),
            (
                "staff_overpayment_recovery_matchings",
                "chk_staff_overpayment_recovery_matching_evidence",
            ),
        ):
            descriptor["parent_columns"][table] = {
                "evidence_reference": deepcopy(evidence_column),
            }
            descriptor["checks"][(table, check_name)] = evidence_check
    if part_name == "1008_historical_order_adoption_noop_constraint.sql":
        descriptor["checks"][(
            "historical_order_adoption_receipts",
            "chk_historical_order_adoption_shape",
        )] = _normalize_sql_contract(
            "(outcome = 'unmatched_case' AND lifecycle_event_id IS NULL "
            "AND expected_version IS NULL AND resulting_version IS NULL) OR "
            "(outcome = 'adopted' AND expected_version IS NOT NULL "
            "AND case_no IS NOT NULL AND ((lifecycle_event_id IS NULL "
            "AND resulting_version = expected_version) OR "
            "(lifecycle_event_id IS NOT NULL AND resulting_version = "
            "expected_version + 1))) OR (outcome IN "
            "('review_required','current_conflict') AND lifecycle_event_id "
            "IS NULL AND expected_version IS NOT NULL AND resulting_version "
            "= expected_version AND case_no IS NOT NULL)"
        )
    if part_name == "1013_order_lifecycle_pending_status_constraint.sql":
        descriptor["checks"][(
            "order_lifecycle_state_events",
            "chk_order_lifecycle_state_event_before_status",
        )] = _normalize_sql_contract(
            "before_status IN ('待補件','洽談中','訂單成立','服務中','訂單完成','訂單取消')"
        )
    if part_name == "1015_controlled_file_reference_finalize_leases.sql":
        descriptor["parent_columns"]["scheduling_service_day_log_attachments"] = {
            "provider_media_id": _column_contract("varchar(191)", "YES"),
            "controlled_file_object_id": _column_contract("bigint unsigned", "YES"),
        }
        descriptor["indexes"][(
            "scheduling_service_day_log_attachments",
            "uq_scheduling_service_day_log_attachment_controlled_file",
        )] = {
            "non_unique": 0,
            "columns": ("controlled_file_object_id",),
        }
        descriptor["foreign_keys"][(
            "scheduling_service_day_log_attachments",
            "fk_scheduling_service_day_log_attachment_controlled_file",
        )] = {
            "columns": ("controlled_file_object_id",),
            "referenced_table": "controlled_file_objects",
            "referenced_columns": ("id",),
            "update_rule": "RESTRICT",
            "delete_rule": "RESTRICT",
        }
        descriptor["checks"][(
            "scheduling_service_day_log_attachments",
            "chk_scheduling_service_day_log_attachment_reference_source",
        )] = _normalize_sql_contract(
            "(provider_media_id IS NOT NULL AND controlled_file_object_id IS NULL) "
            "OR (provider_media_id IS NULL AND controlled_file_object_id IS NOT NULL)"
        )
    if part_name == "1017_client_hcm_correction_versioning.sql":
        descriptor["parent_columns"]["clients"] = {
            "client_hcm_correction_version": _column_contract(
                "bigint unsigned", "NO", "0"
            )
        }
    if part_name == "1018_hcm_resubmission_canonical_review_version.sql":
        descriptor["parent_columns"]["case_import_hcm_correction_events"] = {
            "prior_occurrence_id": _column_contract("bigint", "YES"),
            "canonical_review_identity": _column_contract("varchar(191)", "YES"),
            "expected_review_version": _column_contract("bigint unsigned", "YES"),
            "resulting_review_version": _column_contract("bigint unsigned", "YES"),
        }
        descriptor["indexes"][(
            "case_import_hcm_correction_events",
            "uq_hcm_correction_event_review_version",
        )] = {
            "non_unique": 0,
            "columns": ("canonical_review_identity", "resulting_review_version"),
        }
        descriptor["indexes"][(
            "case_import_hcm_correction_events",
            "idx_hcm_correction_event_canonical_review",
        )] = {
            "non_unique": 1,
            "columns": ("canonical_review_identity", "id"),
        }
        descriptor["foreign_keys"][(
            "case_import_hcm_correction_events",
            "fk_hcm_correction_event_canonical_review",
        )] = {
            "columns": ("canonical_review_identity",),
            "referenced_table": "case_import_hcm_review_rows",
            "referenced_columns": ("review_identity",),
            "update_rule": "RESTRICT",
            "delete_rule": "RESTRICT",
        }
        descriptor["checks"][(
            "case_import_hcm_correction_events",
            "chk_hcm_correction_event_review_version",
        )] = _normalize_sql_contract(
            "(canonical_review_identity IS NULL "
            "AND expected_review_version IS NULL "
            "AND resulting_review_version IS NULL) OR "
            "(canonical_review_identity IS NOT NULL "
            "AND CHAR_LENGTH(TRIM(canonical_review_identity)) > 0 "
            "AND expected_review_version IS NOT NULL "
            "AND resulting_review_version = expected_review_version + 1)"
        )
    if part_name == "1019_line_identity_role_scope.sql":
        descriptor["parent_columns"]["line_platform_users"] = {
            "selected_identity_role": _column_contract(
                "enum('customer','staff')", "YES"
            )
        }
    if part_name == "1021_task96_owner_contract_successors.sql":
        descriptor["parent_columns"]["clients"] = {
            "client_profile_version": _column_contract(
                "bigint unsigned", "NO", "0"
            )
        }
        descriptor["parent_columns"]["client_profile_change_requests"] = {
            "status": _column_contract(
                "enum('pending','approved','approved_applied','partially_approved','rejected','reverted')",
                "NO",
                "pending",
            ),
            "request_version": _column_contract("bigint unsigned", "NO", "0"),
            "client_profile_version": _column_contract("bigint unsigned", "NO", "0"),
            "reason": _column_contract("varchar(500)", "YES"),
            "idempotency_key": _column_contract("varchar(191)", "YES"),
            "preview_fingerprint": _column_contract("char(64)", "YES"),
            "command_fingerprint": _column_contract("char(64)", "YES"),
            "correlation_id": _column_contract("varchar(191)", "YES"),
            "review_reason": _column_contract("varchar(500)", "YES"),
        }
        descriptor["indexes"][(
            "client_profile_change_requests",
            "uq_client_profile_change_request_idempotency",
        )] = {"non_unique": 0, "columns": ("idempotency_key",)}
        descriptor["checks"][(
            "client_profile_change_requests",
            "chk_client_profile_change_request_fingerprints",
        )] = _normalize_sql_contract(
            "(preview_fingerprint IS NULL OR preview_fingerprint REGEXP '^[0-9a-f]{64}$') "
            "AND (command_fingerprint IS NULL OR command_fingerprint REGEXP '^[0-9a-f]{64}$')"
        )
    if part_name == "61_finance_import_reprocessing.sql":
        _remove_retired_reclassification_audit_contract(descriptor)
        descriptor["indexes"][(
            "finance_import_batches",
            "uq_finance_import_batch_id_status",
        )] = {
            "non_unique": 0,
            "columns": ("id", "status"),
        }
    return descriptor


def _remove_retired_reclassification_audit_contract(
    descriptor: dict[str, Any],
) -> None:
    """Release part 153 retires this obsolete audit table after part 61 runs."""
    retired_table = "finance_import_reclassification_events"
    descriptor["tables"].pop(retired_table, None)
    for key in ("indexes", "foreign_keys", "checks"):
        for contract_key in list(descriptor[key]):
            if contract_key[0] == retired_table:
                descriptor[key].pop(contract_key)
    for trigger_name, trigger in list(descriptor["triggers"].items()):
        if trigger["event_object_table"] == retired_table:
            descriptor["triggers"].pop(trigger_name)


# Kept as one declarative block so the historical metadata fingerprint is auditable.
def _legacy_knowledge_stage8_descriptor() -> dict[str, Any]:
    descriptor = _canonical_artifact_descriptor(
        "163_knowledge_runtime.sql"
    )
    descriptor["parent_columns"] = {}
    descriptor["tables"]["knowledge_items"] = {
        "id": _column_contract("bigint unsigned", "NO", None, "auto_increment"),
        "source_identity": _column_contract("varchar(191)", "NO"),
        "title": _column_contract("varchar(500)", "NO"),
        "lifecycle_status": _column_contract(
            "enum('draft','reviewed','published','retired')", "NO", "draft"
        ),
        "current_version": _column_contract("int unsigned", "NO", "1"),
        "source_digest": _column_contract("char(64)", "NO"),
        "source_uri": _column_contract("varchar(1000)", "YES"),
        "created_by_actor_id": _column_contract("varchar(191)", "NO"),
        "created_at_utc": _column_contract(
            "datetime(6)", "NO", "current_timestamp(6)", "default_generated"
        ),
        "updated_at_utc": _column_contract(
            "datetime(6)",
            "NO",
            "current_timestamp(6)",
            "default_generated on update current_timestamp(6)",
        ),
    }
    descriptor["tables"]["knowledge_item_versions"] = {
        "id": _column_contract("bigint unsigned", "NO", None, "auto_increment"),
        "item_id": _column_contract("bigint unsigned", "NO"),
        "item_version": _column_contract("int unsigned", "NO"),
        "content": _column_contract("mediumtext", "NO"),
        "source_digest": _column_contract("char(64)", "NO"),
        "event_type": _column_contract(
            "enum('ingested','reviewed','published','retired')", "NO"
        ),
        "actor_id": _column_contract("varchar(191)", "NO"),
        "reason": _column_contract("varchar(500)", "YES"),
        "idempotency_key": _column_contract("varchar(191)", "NO"),
        "recorded_at_utc": _column_contract(
            "datetime(6)", "NO", "current_timestamp(6)", "default_generated"
        ),
    }
    descriptor["tables"]["knowledge_answer_sources"][
        "source_version"
    ]["column_type"] = "int unsigned"
    descriptor["indexes"].update({
        ("knowledge_items", "PRIMARY"): {
            "non_unique": 0, "columns": ("id",),
        },
        ("knowledge_items", "uq_knowledge_source_identity"): {
            "non_unique": 0, "columns": ("source_identity",),
        },
        ("knowledge_items", "idx_knowledge_lifecycle"): {
            "non_unique": 1, "columns": ("lifecycle_status", "id"),
        },
    })
    descriptor["foreign_keys"].pop(
        ("knowledge_item_versions", "fk_knowledge_version_actor"), None
    )
    descriptor["checks"][(
        "knowledge_items", "chk_knowledge_source_digest"
    )] = _normalize_sql_contract(
        "source_digest REGEXP '^[0-9a-f]{64}$'"
    )
    return descriptor


def _column_contract(
    column_type: str,
    is_nullable: str,
    column_default: Any = None,
    extra: str = "",
) -> dict[str, Any]:
    return {
        "column_type": column_type,
        "is_nullable": is_nullable,
        "column_default": column_default,
        "extra": extra,
    }


def _show_create_check_clauses(
    create_sql: str,
) -> dict[tuple[str, str], str]:
    create_match = re.search(
        r"CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+"
        r"`?([A-Za-z0-9_]+)`?\s*\(",
        create_sql,
        re.I,
    )
    if not create_match:
        raise UpgradeBlocked("SHOW CREATE TABLE contract is invalid")
    table = create_match.group(1)
    body, _ = _extract_parenthesized(
        create_sql, create_match.end() - 1
    )
    checks: dict[tuple[str, str], str] = {}
    for definition in _split_top_level(body):
        constraint = re.match(
            r"^CONSTRAINT\s+`?([A-Za-z0-9_]+)`?\s+CHECK\s*\(",
            definition.strip(),
            re.I | re.S,
        )
        if not constraint:
            continue
        clause, _ = _extract_parenthesized(
            definition, constraint.end() - 1
        )
        checks[(table, constraint.group(1))] = clause
    return checks


def _normalize_foreign_key_rule(value: Any) -> str:
    rule = re.sub(r"\s+", " ", str(value or "")).upper()
    return "RESTRICT" if rule == "NO ACTION" else rule


def _normalize_check_contract(value: Any) -> str:
    raw = str(value or "")
    normalized = (
        raw
        if re.match(r"^(?:atom|and|or|not)\(", raw)
        else _normalize_sql_contract(raw)
    )
    previous = None
    while normalized != previous:
        previous = normalized
        normalized = re.sub(r"([=<>])\(([^()]*)\)", r"\1\2", normalized)
    normalized = re.sub(
        r"atom\(([a-z0-9_]+)regexp_like\(not,([^()]*)\)\)",
        r"not(atom(regexp_like(\1,\2)))",
        normalized,
    )
    normalized = _flatten_associative_contract(normalized)
    return normalized.replace("=false", "=0").replace("=true", "=1")


def _flatten_associative_contract(value: str) -> str:
    """Canonicalize nested normalized AND/OR calls as associative lists."""
    call = _normalized_contract_call(value)
    if call is None:
        return value
    name, arguments = call
    flattened = [_flatten_associative_contract(item) for item in arguments]
    if name in {"and", "or"}:
        expanded: list[str] = []
        for item in flattened:
            nested = _normalized_contract_call(item)
            if nested is not None and nested[0] == name:
                expanded.extend(nested[1])
            else:
                expanded.append(item)
        flattened = expanded
    return f"{name}({','.join(flattened)})"


def _normalized_contract_call(value: str) -> tuple[str, list[str]] | None:
    opening = value.find("(")
    if opening <= 0 or not value.endswith(")"):
        return None
    name = value[:opening]
    depth = 0
    start = opening + 1
    arguments: list[str] = []
    for index in range(start, len(value) - 1):
        char = value[index]
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                return None
            depth -= 1
        elif char == "," and depth == 0:
            arguments.append(value[start:index])
            start = index + 1
    if depth != 0:
        return None
    arguments.append(value[start:-1])
    return name, arguments


def _canonical_artifact_metadata_state(
    snapshot: Mapping[str, Any],
    part_name: str,
    *,
    defer_missing_triggers: bool = False,
    owned_tables: frozenset[str] | None = None,
) -> str:
    descriptor = _canonical_artifact_descriptor(part_name)
    _apply_legacy_knowledge_identifier_contract(descriptor, snapshot, part_name)
    return _artifact_metadata_state(
        snapshot,
        descriptor,
        part_name,
        defer_missing_triggers=defer_missing_triggers,
        owned_tables=owned_tables,
    )


def _release_descriptor_metadata_state(
    snapshot: Mapping[str, Any],
    part_name: str,
    released: Mapping[str, Any],
    *,
    defer_missing_triggers: bool = False,
) -> str:
    """Fail closed unless released metadata equals the canonical SQL contract."""
    canonical = _canonical_artifact_descriptor(part_name)
    parent_tables = set(canonical.get("parent_columns", {}))

    def released_projection(kind: str) -> dict[Any, Any]:
        released_contracts = released.get(kind, {})
        return {
            key: value
            for key, value in canonical[kind].items()
            if key in released_contracts or key[0] not in parent_tables
        }

    projections = {
        "tables": {
            table: set(columns)
            for table, columns in canonical["tables"].items()
        },
        "triggers": set(canonical["triggers"]),
        "indexes": released_projection("indexes"),
        "foreign_keys": released_projection("foreign_keys"),
        "checks": released_projection("checks"),
    }
    for kind, expected in projections.items():
        if released.get(kind) != expected:
            raise UpgradeBlocked(
                f"release descriptor differs from canonical SQL: {part_name}:{kind}"
            )
    if part_name in {
        "1026_task96_scheduling_service_day_attachment_kind.sql",
        "1027_historical_order_pairing_resolution_reused.sql",
        "1028_historical_service_accounting.sql",
    }:
        if released.get("parent_columns") != canonical.get("parent_columns"):
            raise UpgradeBlocked(
                f"release descriptor differs from canonical SQL: {part_name}:parent_columns"
            )
    if part_name == "1005_contract_external_signing_successor.sql":
        return _contract_external_signing_successor_state(
            snapshot,
            canonical,
            defer_missing_triggers=defer_missing_triggers,
        )
    if part_name == "1008_historical_order_adoption_noop_constraint.sql":
        return _historical_order_adoption_noop_constraint_state(
            snapshot,
            canonical,
        )
    if part_name == "1013_order_lifecycle_pending_status_constraint.sql":
        return _order_lifecycle_pending_status_constraint_state(
            snapshot,
            canonical,
        )
    if part_name == "1028_historical_service_accounting.sql":
        return _historical_service_accounting_state(
            snapshot,
            canonical,
            defer_missing_triggers=defer_missing_triggers,
        )
    if part_name == "204_scheduling_service_day_logs.sql":
        return _scheduling_service_day_logs_successor_state(
            snapshot,
            canonical,
            defer_missing_triggers=defer_missing_triggers,
        )
    predecessor_state = _modified_parent_predecessor_absent_state(
        snapshot,
        canonical,
        part_name,
        defer_missing_triggers=defer_missing_triggers,
    )
    if predecessor_state is not None:
        return predecessor_state
    state = _artifact_metadata_state(
        snapshot,
        canonical,
        part_name,
        defer_missing_triggers=defer_missing_triggers,
    )
    if part_name == "1004_controlled_file_storage_foundation.sql":
        return _controlled_file_storage_foundation_state(
            snapshot,
            canonical,
            defer_missing_triggers=defer_missing_triggers,
            initial_state=state,
        )
    return state


def _controlled_file_storage_foundation_state(
    snapshot: Mapping[str, Any],
    descriptor: Mapping[str, Any],
    *,
    defer_missing_triggers: bool,
    initial_state: str | None = None,
) -> str:
    """Accept 1004 only in its exact predecessor or canonical 1005 shape."""
    canonical = deepcopy(descriptor)
    state = initial_state or _artifact_metadata_state(
        snapshot,
        canonical,
        "1004_controlled_file_storage_foundation.sql",
        defer_missing_triggers=defer_missing_triggers,
    )
    if state != "drift":
        return state
    successor = _canonical_artifact_descriptor(
        "1005_contract_external_signing_successor.sql"
    )
    for table in (
        "controlled_file_staging_objects",
        "controlled_file_objects",
    ):
        canonical["tables"][table]["purpose"] = deepcopy(
            successor["parent_columns"][table]["purpose"]
        )
    for key, clause in successor["checks"].items():
        if key[0] in {
            "controlled_file_staging_objects",
            "controlled_file_objects",
        }:
            canonical["checks"][key] = clause
    return _artifact_metadata_state(
        snapshot,
        canonical,
        "1004_controlled_file_storage_foundation.sql",
        defer_missing_triggers=defer_missing_triggers,
    )


def _scheduling_service_day_logs_successor_state(
    snapshot: Mapping[str, Any],
    descriptor: Mapping[str, Any],
    *,
    defer_missing_triggers: bool,
) -> str:
    """Accept part 204 in its exact original or approved 1015 bridge shape."""

    canonical = deepcopy(descriptor)
    state = _artifact_metadata_state(
        snapshot,
        canonical,
        "204_scheduling_service_day_logs.sql",
        defer_missing_triggers=defer_missing_triggers,
    )
    if state != "drift":
        return state
    successor = _canonical_artifact_descriptor(
        "1015_controlled_file_reference_finalize_leases.sql"
    )
    table = "scheduling_service_day_log_attachments"
    canonical["tables"][table].update(
        deepcopy(successor["parent_columns"][table])
    )
    for kind in ("indexes", "foreign_keys", "checks"):
        for key, contract in successor[kind].items():
            if key[0] == table:
                canonical[kind][key] = deepcopy(contract)
    return _artifact_metadata_state(
        snapshot,
        canonical,
        "204_scheduling_service_day_logs.sql",
        defer_missing_triggers=defer_missing_triggers,
    )


def _historical_order_adoption_noop_constraint_state(
    snapshot: Mapping[str, Any],
    descriptor: Mapping[str, Any],
) -> str:
    """Accept only the exact predecessor or successor check contract."""
    key = (
        "historical_order_adoption_receipts",
        "chk_historical_order_adoption_shape",
    )
    constraints = {
        (str(row["table_name"]), str(row["constraint_name"])): row
        for row in snapshot.get("constraints", ())
    }
    row = constraints.get(key)
    if row is None or row.get("constraint_type") != "CHECK":
        return "drift"
    show_create_checks: dict[tuple[str, str], str] = {}
    for create_sql in snapshot.get("show_create_tables", {}).values():
        show_create_checks.update(_show_create_check_clauses(create_sql))
    actual = _normalize_check_contract(
        show_create_checks.get(key, row.get("check_clause") or "")
    )
    successor = _normalize_check_contract(descriptor["checks"][key])
    predecessor = _normalize_check_contract(_normalize_sql_contract(
        "(outcome = 'unmatched_case' AND lifecycle_event_id IS NULL "
        "AND expected_version IS NULL AND resulting_version IS NULL) OR "
        "(outcome = 'adopted' AND lifecycle_event_id IS NOT NULL "
        "AND expected_version IS NOT NULL AND resulting_version = "
        "expected_version + 1 AND case_no IS NOT NULL) OR (outcome IN "
        "('review_required','current_conflict') AND lifecycle_event_id IS NULL "
        "AND expected_version IS NOT NULL AND resulting_version = "
        "expected_version AND case_no IS NOT NULL)"
    ))
    if actual == successor:
        return "exact"
    if actual == predecessor:
        return "absent"
    return "drift"


def _order_lifecycle_pending_status_constraint_state(
    snapshot: Mapping[str, Any],
    descriptor: Mapping[str, Any],
) -> str:
    """Accept the released predecessor, 1013 shape, or exact later successor."""
    key = (
        "order_lifecycle_state_events",
        "chk_order_lifecycle_state_event_before_status",
    )
    constraints = {
        (str(row["table_name"]), str(row["constraint_name"])): row
        for row in snapshot.get("constraints", ())
    }
    row = constraints.get(key)
    if row is None or row.get("constraint_type") != "CHECK":
        return "drift"
    show_create_checks: dict[tuple[str, str], str] = {}
    for create_sql in snapshot.get("show_create_tables", {}).values():
        show_create_checks.update(_show_create_check_clauses(create_sql))
    actual = _normalize_check_contract(
        show_create_checks.get(key, row.get("check_clause") or "")
    )
    successor = _normalize_check_contract(descriptor["checks"][key])
    historical_successor = _normalize_check_contract(
        _canonical_artifact_descriptor(
            "1028_historical_service_accounting.sql"
        )["checks"][key]
    )
    predecessor = _normalize_check_contract(_normalize_sql_contract(
        "before_status IN ('洽談中','訂單成立','服務中','訂單完成','訂單取消')"
    ))
    if actual in {successor, historical_successor}:
        return "exact"
    if actual == predecessor:
        return "absent"
    return "drift"


def _historical_service_accounting_state(
    snapshot: Mapping[str, Any],
    descriptor: Mapping[str, Any],
    *,
    defer_missing_triggers: bool,
) -> str:
    """Accept only the released normal-status predecessor or the full successor."""
    present_columns = {
        (str(row["table_name"]), str(row["column_name"]))
        for row in snapshot.get("columns", ())
    }
    owned_columns = {
        (table, column)
        for table, columns in descriptor["tables"].items()
        for column in columns
    }
    if owned_columns.intersection(present_columns):
        return _artifact_metadata_state(
            snapshot,
            descriptor,
            "1028_historical_service_accounting.sql",
            defer_missing_triggers=defer_missing_triggers,
        )

    order_status = next(
        (
            row
            for row in snapshot.get("columns", ())
            if row["table_name"] == "orders" and row["column_name"] == "status"
        ),
        None,
    )
    predecessor_status = _normalize_column_type_contract(
        "enum('待補件','洽談中','訂單成立','服務中','訂單完成','訂單取消')"
    )
    if order_status is None or _normalize_column_type_contract(
        order_status.get("column_type")
    ) != predecessor_status:
        return "drift"

    constraints = {
        (str(row["table_name"]), str(row["constraint_name"])): row
        for row in snapshot.get("constraints", ())
    }
    show_create_checks: dict[tuple[str, str], str] = {}
    for create_sql in snapshot.get("show_create_tables", {}).values():
        show_create_checks.update(_show_create_check_clauses(create_sql))
    for column_name in ("before_status", "after_status"):
        key = (
            "order_lifecycle_state_events",
            f"chk_order_lifecycle_state_event_{column_name}",
        )
        row = constraints.get(key)
        if row is None or row.get("constraint_type") != "CHECK":
            return "drift"
        actual = _normalize_check_contract(
            show_create_checks.get(key, row.get("check_clause") or "")
        )
        predecessor = _normalize_check_contract(_normalize_sql_contract(
            f"{column_name} IN ('待補件','洽談中','訂單成立','服務中',"
            "'訂單完成','訂單取消')"
        ))
        if actual != predecessor:
            return "drift"
    return "absent"


def _contract_external_signing_successor_state(
    snapshot: Mapping[str, Any],
    descriptor: dict[str, Any],
    *,
    defer_missing_triggers: bool,
) -> str:
    """Distinguish the exact 1004 parent contract from a drifted 1005 source."""
    present_columns = {
        (str(row["table_name"]), str(row["column_name"]))
        for row in snapshot.get("columns", ())
    }
    successor_columns = {
        (table, column)
        for table, columns in descriptor["tables"].items()
        for column in columns
    }
    if successor_columns.intersection(present_columns):
        return _artifact_metadata_state(
            snapshot,
            descriptor,
            "1005_contract_external_signing_successor.sql",
            defer_missing_triggers=defer_missing_triggers,
        )

    predecessor_type = _normalize_column_type_contract(
        "enum('final_signed_contract','service_date_confirmation',"
        "'baby_log_photo','meal_photo','order_notice','staff_resume',"
        "'staff_certificate','staff_health_exam','rich_menu_background')"
    )
    successor_type = descriptor["parent_columns"][
        "controlled_file_objects"
    ]["purpose"]["column_type"]
    purpose_rows = {
        str(row["table_name"]): row
        for row in snapshot.get("columns", ())
        if row["column_name"] == "purpose"
        and row["table_name"] in {
            "controlled_file_staging_objects",
            "controlled_file_objects",
        }
    }
    if not purpose_rows:
        predecessor = deepcopy(descriptor)
        parent_tables = set(predecessor["parent_columns"])
        predecessor["parent_columns"] = {}
        for kind in ("indexes", "foreign_keys", "checks"):
            predecessor[kind] = {
                key: contract
                for key, contract in predecessor[kind].items()
                if key[0] not in parent_tables
            }
        predecessor["triggers"] = {
            name: contract
            for name, contract in predecessor["triggers"].items()
            if contract["event_object_table"] not in parent_tables
        }
        predecessor_state = _artifact_metadata_state(
            snapshot,
            predecessor,
            "1005_contract_external_signing_successor.sql",
            defer_missing_triggers=defer_missing_triggers,
        )
        return "absent" if predecessor_state == "absent" else "drift"
    if len(purpose_rows) != 2 or any(
        _normalize_column_type_contract(row["column_type"])
        not in {predecessor_type, successor_type}
        or row["is_nullable"] != "NO"
        or row["column_default"] is not None
        or str(row["extra"] or "") != ""
        for row in purpose_rows.values()
    ):
        return "drift"

    predecessor_check = _normalize_sql_contract(
        "(owner_type = 'contract_signing' AND purpose = 'final_signed_contract') OR "
        "(owner_type = 'scheduling' AND purpose IN "
        "('service_date_confirmation', 'baby_log_photo', 'meal_photo')) OR "
        "(owner_type = 'orders' AND purpose = 'order_notice') OR "
        "(owner_type = 'staff' AND purpose IN "
        "('staff_resume', 'staff_certificate', 'staff_health_exam')) OR "
        "(owner_type = 'line_integration' AND purpose = 'rich_menu_background')"
    )
    show_create_checks: dict[tuple[str, str], str] = {}
    for create_sql in snapshot.get("show_create_tables", {}).values():
        show_create_checks.update(_show_create_check_clauses(create_sql))
    constraint_checks = {
        (str(row["table_name"]), str(row["constraint_name"])): str(
            row.get("check_clause") or ""
        )
        for row in snapshot.get("constraints", ())
        if row.get("constraint_type") == "CHECK"
    }
    expected_check_keys = {
        "controlled_file_staging_objects": (
            "controlled_file_staging_objects",
            "chk_controlled_file_staging_owner_purpose",
        ),
        "controlled_file_objects": (
            "controlled_file_objects",
            "chk_controlled_file_object_owner_purpose",
        ),
    }
    predecessor_check = _normalize_check_contract(predecessor_check)
    successor_checks = {
        table: descriptor["checks"][key]
        for table, key in expected_check_keys.items()
    }
    modes: list[str] = []
    for table, key in expected_check_keys.items():
        actual_check = _normalize_check_contract(
            show_create_checks.get(key, constraint_checks.get(key, ""))
        )
        actual_type = _normalize_column_type_contract(
            purpose_rows[table]["column_type"]
        )
        if actual_type == predecessor_type and actual_check == predecessor_check:
            modes.append("predecessor")
            continue
        if actual_type == successor_type and actual_check == successor_checks[table]:
            modes.append("successor")
            continue
        return "drift"

    foreign_key_present = any(
        row.get("table_name") == "controlled_file_objects"
        and row.get("constraint_name") == "fk_controlled_file_object_supersedes"
        and row.get("constraint_type") == "FOREIGN KEY"
        for row in snapshot.get("constraints", ())
    )
    if modes == ["predecessor", "predecessor"] and foreign_key_present:
        return "absent"
    return "partial"


def _auto_fk_supporting_index_keys(
    indexes: Mapping[tuple[str, str], Mapping[str, Any]],
    descriptor: Mapping[str, Any],
    extra_keys: set[tuple[str, str]],
) -> set[tuple[str, str]]:
    """Allow only MySQL's unambiguously named FK-support index side effect."""
    foreign_keys = descriptor.get("foreign_keys", {})
    allowed: set[tuple[str, str]] = set()
    for key in extra_keys:
        index = indexes[key]
        if int(index.get("non_unique", 1)) != 1:
            continue
        table, index_name = key
        matches = [
            fk_key for fk_key, contract in foreign_keys.items()
            if fk_key[0] == table
            and tuple(str(column).casefold() for column in contract["columns"])
            == tuple(index["columns"])
        ]
        # INFORMATION_SCHEMA does not expose an origin flag.  MySQL names an
        # implicit InnoDB supporting index after the FK constraint; requiring
        # that identity is the mechanical proof that this is not an unrelated
        # user-owned index with merely overlapping columns.
        if len(matches) == 1 and index_name == matches[0][1]:
            allowed.add(key)
    return allowed


# 保持單一 metadata comparator，避免 canonical 與 compatibility 契約判讀分叉。
def _artifact_metadata_state(
    snapshot: Mapping[str, Any],
    descriptor: dict[str, Any],
    part_name: str,
    *,
    defer_missing_triggers: bool = False,
    owned_tables: frozenset[str] | None = None,
) -> str:
    if owned_tables is not None:
        _limit_descriptor_to_owned_tables(descriptor, owned_tables)
    columns_by_table: dict[str, dict[str, Mapping[str, Any]]] = {}
    for row in snapshot["columns"]:
        columns_by_table.setdefault(row["table_name"], {})[
            row["column_name"]
        ] = row
    required_tables = descriptor["tables"]
    parent_columns = descriptor["parent_columns"]
    owned_presence: list[bool] = []
    for table, expected_columns in {
        **required_tables, **parent_columns
    }.items():
        actual = columns_by_table.get(table, {})
        for name, expected in expected_columns.items():
            row = actual.get(name)
            owned_presence.append(row is not None)
            if row is None:
                continue
            actual_default = row["column_default"]
            if isinstance(actual_default, str):
                actual_default = actual_default.casefold()
            actual_extra = re.sub(
                r"\s+", " ", str(row["extra"] or "")
            ).casefold()
            type_matches = (
                _normalize_column_type_contract(row["column_type"])
                == expected["column_type"]
            )
            successor_type = _matching_coordination_successor_column_type(
                part_name, table, name
            )
            successor_type_matches = (
                successor_type is not None
                and _normalize_column_type_contract(row["column_type"])
                == successor_type
            )
            if (
                not (type_matches or successor_type_matches)
                or row["is_nullable"] != expected["is_nullable"]
                or actual_default != expected["column_default"]
                or actual_extra != expected["extra"]
            ):
                return "drift"
        allowed_extra_columns = _allowed_later_artifact_columns(
            part_name, table
        )
        if table in required_tables and actual:
            if set(actual) != set(expected_columns) | allowed_extra_columns:
                return "drift"
    indexes = {
        (row["table_name"], row["index_name"]): {
            "non_unique": int(row["non_unique"]),
            "columns": tuple(
                item.casefold() for item in str(row["columns"]).split(",")
            ),
        }
        for row in snapshot["indexes"]
    }
    # A parent-table ALTER owns only its explicitly declared objects.  Unknown
    # object rejection is exclusive only for tables created by this artifact.
    owned_tables = set(required_tables)
    expected_index_keys = {
        key for key in descriptor["indexes"] if key[0] in owned_tables
    }
    actual_index_keys = {
        key for key in indexes if key[0] in owned_tables
    }
    extra_index_keys = actual_index_keys - expected_index_keys
    allowed_later_indexes = _allowed_later_artifact_indexes(part_name)
    allowed_later_index_keys = {
        key for key in extra_index_keys
        if indexes[key] == allowed_later_indexes.get(key)
    }
    if extra_index_keys - allowed_later_index_keys - _auto_fk_supporting_index_keys(
        indexes, descriptor, extra_index_keys
    ):
        return "drift"
    if expected_index_keys - actual_index_keys and actual_index_keys:
        return "partial"
    for key, expected in descriptor["indexes"].items():
        actual = indexes.get(key)
        owned_presence.append(actual is not None)
        if actual is not None and actual != expected:
            return "drift"
    constraints = {
        (row["table_name"], row["constraint_name"]): row
        for row in snapshot.get("constraints", [])
    }
    key_columns: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in snapshot.get("key_columns", []):
        key_columns.setdefault(
            (row["table_name"], row["constraint_name"]), []
        ).append(row)
    foreign_rules = {
        (row["table_name"], row["constraint_name"]): row
        for row in snapshot.get("foreign_keys", [])
    }
    expected_foreign_keys = {
        key for key in descriptor["foreign_keys"] if key[0] in owned_tables
    }
    actual_foreign_keys = {
        key for key, row in constraints.items()
        if key[0] in owned_tables and row.get("constraint_type") == "FOREIGN KEY"
    }
    if actual_foreign_keys - expected_foreign_keys:
        return "drift"
    if expected_foreign_keys - actual_foreign_keys and actual_foreign_keys:
        return "partial"
    show_create_checks: dict[tuple[str, str], str] = {}
    for create_sql in snapshot.get("show_create_tables", {}).values():
        show_create_checks.update(_show_create_check_clauses(create_sql))
    for key, expected in descriptor["foreign_keys"].items():
        row = constraints.get(key)
        owned_presence.append(row is not None)
        if row is None:
            continue
        columns = key_columns.get(key, [])
        rules = foreign_rules.get(key, {})
        actual = {
            "columns": tuple(
                item["column_name"].casefold() for item in columns
            ),
            "referenced_table": str(
                columns[0]["referenced_table_name"] if columns else ""
            ).casefold(),
            "referenced_columns": tuple(
                str(item["referenced_column_name"]).casefold()
                for item in columns
            ),
            "update_rule": _normalize_foreign_key_rule(
                rules.get("update_rule")
            ),
            "delete_rule": _normalize_foreign_key_rule(
                rules.get("delete_rule")
            ),
        }
        if row["constraint_type"] != "FOREIGN KEY" or actual != expected:
            return "drift"
    allowed_later_checks = _allowed_later_artifact_checks(part_name)
    for key, expected_clause in descriptor["checks"].items():
        row = constraints.get(key)
        owned_presence.append(row is not None)
        if row is None:
            continue
        actual_clause = show_create_checks.get(key, row.get("check_clause"))
        if (
            row["constraint_type"] != "CHECK"
            or str(row.get("enforced") or "YES").upper() != "YES"
            or _normalize_check_contract(actual_clause) not in {
                _normalize_check_contract(expected_clause),
                *(
                    [_normalize_check_contract(allowed_later_checks[key])]
                    if key in allowed_later_checks
                    else []
                ),
            }
        ):
            return "drift"
    expected_checks = {key for key in descriptor["checks"] if key[0] in owned_tables}
    actual_checks = {
        key for key, row in constraints.items()
        if key[0] in owned_tables and row.get("constraint_type") == "CHECK"
    }
    if actual_checks - expected_checks:
        return "drift"
    if expected_checks - actual_checks and actual_checks:
        return "partial"
    triggers = {
        row["trigger_name"]: {
            "action_timing": str(row["action_timing"]).upper(),
            "event_manipulation": str(
                row["event_manipulation"]
            ).upper(),
            "event_object_table": row["event_object_table"],
            "action_statement": (
                row["action_statement"]
                if row["action_statement"]
                in {
                    item["action_statement"]
                    for item in descriptor["triggers"].values()
                }
                else _normalize_sql_contract(row["action_statement"])
            ),
        }
        for row in snapshot["triggers"]
    }
    expected_trigger_names = set(descriptor["triggers"])
    actual_owned_trigger_names = {
        name for name, value in triggers.items()
        if value["event_object_table"] in owned_tables
    }
    if actual_owned_trigger_names - expected_trigger_names:
        return "drift"
    if (
        expected_trigger_names - actual_owned_trigger_names
        and not defer_missing_triggers
        and any(owned_presence)
    ):
        return "partial"
    for name, expected in descriptor["triggers"].items():
        actual = triggers.get(name)
        if actual is None and defer_missing_triggers:
            continue
        owned_presence.append(actual is not None)
        if actual is not None and actual != expected:
            return "drift"
    if not owned_presence or not any(owned_presence):
        return "absent"
    if not all(owned_presence):
        return "partial"
    return "exact"


def _limit_descriptor_to_owned_tables(
    descriptor: dict[str, Any], owned_tables: frozenset[str]
) -> None:
    for contract_kind in ("tables", "parent_columns"):
        descriptor[contract_kind] = {
            table: contract
            for table, contract in descriptor[contract_kind].items()
            if table in owned_tables
        }
    for contract_kind in ("indexes", "foreign_keys", "checks"):
        descriptor[contract_kind] = {
            key: contract
            for key, contract in descriptor[contract_kind].items()
            if key[0] in owned_tables
        }
    descriptor["triggers"] = {
        name: contract
        for name, contract in descriptor["triggers"].items()
        if contract["event_object_table"] in owned_tables
    }


# 保持單一 fingerprint gate，完整核對 legacy 主體、可選 148 子表與 triggers。
def _legacy_knowledge_schema_state(
    snapshot: Mapping[str, Any],
) -> str | None:
    columns = {
        (str(row["table_name"]), str(row["column_name"]))
        for row in snapshot.get("columns", ())
    }
    signatures = {
        ("knowledge_items", "current_version"),
        ("knowledge_items", "lifecycle_status"),
        ("knowledge_item_versions", "actor_id"),
    }
    if not signatures.intersection(columns):
        return None
    legacy_descriptor = _legacy_knowledge_stage8_descriptor()
    state = _artifact_metadata_state(
        snapshot, legacy_descriptor, "legacy_knowledge_stage8"
    )
    if state != "exact" or not _owned_metadata_names_are_exact(
        snapshot, legacy_descriptor
    ):
        return "drift"
    child_tables = frozenset({
        "knowledge_item_events", "knowledge_apply_receipts",
    })
    child_descriptor = _canonical_artifact_descriptor(
        "148_knowledge_retrieval.sql"
    )
    _apply_legacy_knowledge_identifier_contract(
        child_descriptor, snapshot, "148_knowledge_retrieval.sql"
    )
    _limit_descriptor_to_owned_tables(child_descriptor, child_tables)
    child_state = _canonical_artifact_metadata_state(
        snapshot,
        "148_knowledge_retrieval.sql",
        owned_tables=child_tables,
    )
    if child_state not in {"absent", "exact"}:
        return "drift"
    if child_state == "exact" and not _owned_metadata_names_are_exact(
        snapshot, child_descriptor
    ):
        return "drift"
    expected_triggers = {
        "trg_knowledge_item_versions_before_update",
        "trg_knowledge_item_versions_before_delete",
    }
    actual_triggers = {
        str(row["trigger_name"])
        for row in snapshot.get("triggers", ())
        if str(row["event_object_table"]) in LEGACY_KNOWLEDGE_TABLES
    }
    return "exact" if actual_triggers == expected_triggers else "drift"


# 保持 indexes 與 constraints 同步核對，避免各自接受不一致的額外 object。
def _owned_metadata_names_are_exact(
    snapshot: Mapping[str, Any],
    descriptor: Mapping[str, Any],
) -> bool:
    tables = set(descriptor["tables"])
    expected_indexes = set(descriptor["indexes"])
    expected_foreign_keys = set(descriptor["foreign_keys"])
    allowed_indexes = expected_indexes | expected_foreign_keys
    actual_indexes = {
        (str(row["table_name"]), str(row["index_name"]))
        for row in snapshot.get("indexes", ())
        if str(row["table_name"]) in tables
    }
    expected_constraints = (
        {(table, "PRIMARY") for table in tables}
        | {
            key for key, contract in descriptor["indexes"].items()
            if int(contract["non_unique"]) == 0
        }
        | expected_foreign_keys
        | set(descriptor["checks"])
    )
    actual_constraints = {
        (str(row["table_name"]), str(row["constraint_name"]))
        for row in snapshot.get("constraints", ())
        if str(row["table_name"]) in tables
    }
    return (
        expected_indexes <= actual_indexes <= allowed_indexes
        and actual_constraints == expected_constraints
    )


def _apply_legacy_knowledge_identifier_contract(
    descriptor: dict[str, Any],
    snapshot: Mapping[str, Any],
    part_name: str,
) -> None:
    if part_name not in {"148_knowledge_retrieval.sql", "163_knowledge_runtime.sql"}:
        return
    identifier_type = _knowledge_item_identifier_type(snapshot)
    if identifier_type != "bigint unsigned":
        return
    if part_name == "148_knowledge_retrieval.sql":
        descriptor["tables"]["knowledge_items"]["id"]["column_type"] = identifier_type
        descriptor["tables"]["knowledge_item_events"]["knowledge_item_id"]["column_type"] = identifier_type
    else:
        descriptor["tables"]["knowledge_item_versions"]["item_id"]["column_type"] = identifier_type


def _allowed_later_artifact_columns(
    part_name: str,
    table: str,
) -> set[str]:
    if (
        part_name == "148_knowledge_retrieval.sql"
        and table == "knowledge_items"
    ):
        return {"source_identity"}
    return set()


def _matching_coordination_successor_column_type(
    part_name: str, table: str, column: str,
) -> str | None:
    """Return the only published successor type allowed on the 1003 parent table."""
    if part_name != "1003_matching_coordination_successor.sql" or table != "matching_coordination_outbox":
        return None
    successor_types = {
        "intent_type": (
            "enum('line_matching_interaction','line_criteria_diff_resend',"
            "'assignment_conversion_requested','rematch_requested',"
            "'orders_terms_update_requested','line_bilateral_notification',"
            "'line_client_decision','customer_service_ticket')"
        ),
        "target_owner": (
            "enum('line_integration','assignment_workflow','orders_workflow',"
            "'customer_service')"
        ),
    }
    value = successor_types.get(column)
    return (
        _normalize_column_type_contract(value)
        if value is not None
        else None
    )


def _allowed_later_artifact_indexes(
    part_name: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Return exact successor index contracts valid on an earlier artifact."""
    if part_name == "104_order_lifecycle_state_history.sql":
        return {
            (
                "order_lifecycle_state_events",
                "uq_order_lifecycle_state_event_case_identity",
            ): {
                "non_unique": 0,
                "columns": ("id", "case_no"),
            }
        }
    if part_name == "148_knowledge_retrieval.sql":
        return {
            ("knowledge_items", "uq_knowledge_source_identity"): {
                "non_unique": 0,
                "columns": ("source_identity",),
            }
        }
    return {}


def _allowed_later_artifact_checks(
    part_name: str,
) -> dict[tuple[str, str], str]:
    """Return checks whose exact shape is owned by a declared successor."""
    if part_name == "104_order_lifecycle_state_history.sql":
        successor = _canonical_artifact_descriptor(
            "1013_order_lifecycle_pending_status_constraint.sql"
        )
        return dict(successor["checks"])
    if part_name == "1003_matching_coordination_successor.sql":
        # 1023 intentionally evolves this existing CHECK while adding its own
        # safe-link roots. Derive the clause from the hash-bound SQL artifact so
        # the compatibility exception cannot drift from the published successor.
        successor_path = ROOT / "db" / "schema_parts" / (
            "1023_task96_line_safe_review_link_matching_outbox_v1.sql"
        )
        for statement in split_sql(successor_path.read_text(encoding="utf-8")):
            marker = "ADD CONSTRAINT CHK_MATCHING_OUTBOX_TARGET CHECK"
            position = statement.upper().find(marker)
            if position < 0:
                continue
            opening = statement.upper().find("CHECK", position) + len("CHECK")
            clause, _ = _extract_parenthesized(statement, statement.find("(", opening))
            return {
                ("matching_coordination_outbox", "chk_matching_outbox_target"): clause
            }
    return {}


def _line_identity_management_state(snapshot: Mapping[str, Any]) -> str:
    canonical_state = _canonical_artifact_metadata_state(
        snapshot, "186_line_identity_management.sql"
    )
    if canonical_state == "exact":
        return "exact"
    if _is_line_identity_canonical_menu_successor_state(snapshot):
        return "exact"
    if _is_recoverable_line_identity_legacy_state(snapshot):
        return "partial"
    return "drift"


def _is_line_identity_canonical_menu_successor_state(
    snapshot: Mapping[str, Any],
) -> bool:
    columns = {
        (row["table_name"], row["column_name"]): row
        for row in snapshot.get("columns", ())
    }
    canonical_column = columns.get(
        ("line_identity_revocation_requests", "canonical_default_menu_publication_id")
    )
    default_column = columns.get(
        ("line_identity_revocation_requests", "default_menu_publication_id")
    )
    if canonical_column is None or default_column is None:
        return False
    if canonical_column["column_type"] != "bigint unsigned":
        return False
    if str(default_column.get("is_nullable")) != "YES":
        return False
    constraints = {
        row["constraint_name"]
        for row in snapshot.get("constraints", ())
        if row["table_name"] == "line_identity_revocation_requests"
    }
    return {
        "fk_line_identity_revocation_canonical_publication",
        "chk_line_identity_revocation_publication_source",
    }.issubset(constraints)


# Kept cohesive because this is one released legacy metadata fingerprint.
def _is_recoverable_line_identity_legacy_state(
    snapshot: Mapping[str, Any],
) -> bool:
    columns = {
        (row["table_name"], row["column_name"]): row
        for row in snapshot.get("columns", ())
    }
    if any(
        table == "line_identity_revocation_requests"
        for table, _column in columns
    ):
        return False
    allowed_types = {
        ("line_identity_bindings", "binding_status"): {
            "enum('unbound','pending_review','bound','revoked')",
            "enum('unbound','pending_review','bound','revocation_pending','revoked')",
        },
        ("line_identity_bindings", "active_subject_key"): {"varchar(400)"},
        ("line_identity_binding_events", "action"): {
            "enum('claim_submitted','bound','revoked','rebound','legacy_imported')",
            "enum('claim_submitted','bound','revocation_requested','revoked','rebound','legacy_imported')",
        },
    }
    for key, expected_types in allowed_types.items():
        row = columns.get(key)
        if row is None or row["column_type"] not in expected_types:
            return False
    active_key = columns[("line_identity_bindings", "active_subject_key")]
    return "generated" in str(active_key.get("extra") or "").casefold()


def schema_statements_for_state(
    part: Path,
    state: str,
    snapshot: Mapping[str, Any],
) -> list[str]:
    statements = split_sql(part.read_text(encoding="utf-8"))
    if (
        part.name == "1005_contract_external_signing_successor.sql"
        and state == "partial"
    ):
        return _contract_external_signing_recovery_statements(
            statements, snapshot
        )
    if part.name == "148_knowledge_retrieval.sql" and state == "partial":
        return _knowledge_retrieval_recovery_statements(statements, snapshot)
    if part.name == "185_customer_service_runtime.sql" and state == "partial":
        return _customer_service_runtime_recovery_statements(
            statements, snapshot
        )
    if part.name != "163_knowledge_runtime.sql" or state != "partial":
        if part.name == "186_line_identity_management.sql" and state == "partial":
            if not _is_recoverable_line_identity_legacy_state(snapshot):
                raise UpgradeBlocked("line identity management partial state is not resumable")
        return statements
    return _knowledge_runtime_recovery_statements(statements, snapshot)


def _contract_external_signing_recovery_statements(
    statements: list[str], snapshot: Mapping[str, Any]
) -> list[str]:
    """Resume only the unreconciled suffix of the 1005 parent-table ALTERs."""
    columns = {
        (str(row["table_name"]), str(row["column_name"])): row
        for row in snapshot.get("columns", ())
    }
    successor_type = _normalize_column_type_contract(
        "enum('unsigned_contract','final_signed_contract',"
        "'service_date_confirmation','baby_log_photo','meal_photo',"
        "'order_notice','staff_resume','staff_certificate',"
        "'staff_health_exam','rich_menu_background')"
    )
    staging_current = _normalize_column_type_contract(
        columns[("controlled_file_staging_objects", "purpose")]["column_type"]
    ) == successor_type
    object_current = _normalize_column_type_contract(
        columns[("controlled_file_objects", "purpose")]["column_type"]
    ) == successor_type
    foreign_key_present = any(
        row.get("table_name") == "controlled_file_objects"
        and row.get("constraint_name") == "fk_controlled_file_object_supersedes"
        and row.get("constraint_type") == "FOREIGN KEY"
        for row in snapshot.get("constraints", ())
    )
    if not staging_current:
        start = 0
    elif not object_current and foreign_key_present:
        start = 1
    elif not object_current:
        start = 2
    elif not foreign_key_present:
        start = 3
    else:
        start = 4

    present_triggers = {
        str(row["trigger_name"]) for row in snapshot.get("triggers", ())
    }
    remaining: list[str] = []
    for statement in statements[start:]:
        trigger_match = re.match(
            r"\s*CREATE\s+TRIGGER\s+`?([A-Za-z0-9_]+)`?",
            statement,
            flags=re.IGNORECASE,
        )
        if trigger_match and trigger_match.group(1) in present_triggers:
            continue
        remaining.append(statement)
    return remaining


def _receipt_resumable_partial_artifacts(
    receipt: Mapping[str, Any], candidate: str
) -> frozenset[str]:
    """Authorize reconciliation only for hash-bound durable statement steps."""
    if receipt.get("candidate_database") != candidate:
        return frozenset()
    resumable: set[str] = set()
    parts = {part.name: part for part in SCHEMA_PARTS}
    for step in receipt.get("schema_steps", ()):
        if step.get("status") not in {"prepared", "failed", "applied"}:
            continue
        if step.get("status") == "applied" and (
            step.get("verification_status") != "pending_part_completion"
            or step.get("after_part_state") != "partial"
        ):
            continue
        part_name = str(step.get("part") or "")
        part = parts.get(part_name)
        index = int(step.get("index") or 0)
        if part is None or index < 1:
            continue
        statements = split_sql(part.read_text(encoding="utf-8"))
        if index > len(statements):
            continue
        expected_sha = _sha256_bytes(statements[index - 1].encode("utf-8"))
        if step.get("statement_sha256") == expected_sha:
            resumable.add(part_name)
    return frozenset(resumable)


def _customer_service_runtime_recovery_statements(
    statements: list[str],
    snapshot: Mapping[str, Any],
) -> list[str]:
    present_tables = {
        str(row["table_name"]) for row in snapshot.get("columns", ())
    }
    tickets = "customer_service_tickets"
    events = "customer_service_ticket_events"
    ticket_state = _canonical_artifact_metadata_state(
        snapshot,
        "185_customer_service_runtime.sql",
        owned_tables=frozenset({tickets}),
    )
    if (
        len(statements) == 2
        and tickets in present_tables
        and events not in present_tables
        and ticket_state == "exact"
    ):
        return [statements[1]]
    raise UpgradeBlocked(
        "customer service runtime partial state is not resumable"
    )


def _knowledge_retrieval_recovery_statements(
    statements: list[str],
    snapshot: Mapping[str, Any],
) -> list[str]:
    return _knowledge_foreign_key_compatible_statements(statements, snapshot)


def _knowledge_runtime_recovery_statements(
    statements: list[str],
    snapshot: Mapping[str, Any],
) -> list[str]:
    columns = {
        (row["table_name"], row["column_name"])
        for row in snapshot.get("columns", ())
    }
    indexes = {
        (row["table_name"], row["index_name"])
        for row in snapshot.get("indexes", ())
    }
    source_column = ("knowledge_items", "source_identity") in columns
    source_index = (
        "knowledge_items", "uq_knowledge_source_identity"
    ) in indexes
    if source_index and not source_column:
        raise UpgradeBlocked(
            "knowledge runtime index exists without source_identity"
        )
    statements = _knowledge_foreign_key_compatible_statements(statements, snapshot)
    if not source_column:
        return statements
    remaining = statements[1:]
    if source_index:
        return remaining
    add_index = (
        "ALTER TABLE knowledge_items "
        "ADD UNIQUE KEY uq_knowledge_source_identity (source_identity)"
    )
    return [add_index, *remaining]


def _knowledge_foreign_key_compatible_statements(
    statements: list[str],
    snapshot: Mapping[str, Any],
) -> list[str]:
    identifier_type = _knowledge_item_identifier_type(snapshot)
    if identifier_type == "bigint":
        return statements
    replacements = (
        ("knowledge_item_id BIGINT NOT NULL", "knowledge_item_id BIGINT UNSIGNED NOT NULL"),
        ("item_id BIGINT NOT NULL", "item_id BIGINT UNSIGNED NOT NULL"),
    )
    return [_replace_statement_types(statement, replacements) for statement in statements]


def _knowledge_item_identifier_type(snapshot: Mapping[str, Any]) -> str:
    columns = {
        (str(row.get("table_name")), str(row.get("column_name"))): row
        for row in snapshot.get("columns", ())
    }
    row = columns.get(("knowledge_items", "id"))
    if row is None:
        return "bigint"
    column_type = _normalize_column_type_contract(row.get("column_type"))
    if column_type in {"bigint", "bigint unsigned"}:
        return column_type
    raise UpgradeBlocked("knowledge_items.id type is not a supported legacy shape")


def _replace_statement_types(
    statement: str,
    replacements: tuple[tuple[str, str], ...],
) -> str:
    for source, target in replacements:
        statement = statement.replace(source, target)
    return statement


def apply_schema(
    config: DatabaseConfig | SeparateDatabaseConfig,
    source: str,
    candidate: str,
    plan_path: Path,
    operation_receipt_path: Path,
    *,
    mysql_container: str | None = None,
    allowed_partial_artifacts: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    validate_database_names(source, candidate)
    operation_receipt = read_receipt(operation_receipt_path)
    if operation_receipt.get("status") == "schema_applied":
        if operation_receipt.get("candidate_database") != candidate:
            raise UpgradeBlocked("operation receipt targets another candidate")
        return run_candidate_post_schema(
            config,
            source,
            candidate,
            operation_receipt_path,
            mysql_container=mysql_container,
        )
    plan = read_receipt(plan_path)
    if plan.get("status") != "ready":
        raise UpgradeBlocked("plan is not ready")
    existing_receipt = read_receipt(operation_receipt_path)
    schema_artifacts = plan.get("schema_artifacts") or []
    artifact_names = [
        str(artifact.get("name"))
        for artifact in schema_artifacts
        if isinstance(artifact, Mapping) and artifact.get("name")
    ]
    canonical_release_fingerprint = plan.get("release_fingerprint")
    if len(artifact_names) == 1 and isinstance(plan.get("release_id"), str):
        canonical_release_fingerprint = local_additive_release_qualification(
            str(plan["release_id"]), artifact_names[0]
        )["release_fingerprint"]
    existing_receipt.update(
        release_id=plan.get("release_id"),
        release_fingerprint=canonical_release_fingerprint,
        plan_release_fingerprint=plan.get("release_fingerprint"),
        artifact_names=artifact_names,
        artifact_name=(artifact_names[0] if len(artifact_names) == 1 else None),
    )
    write_receipt(operation_receipt_path, existing_receipt)
    allowed_partial_artifacts = allowed_partial_artifacts.union(
        _receipt_resumable_partial_artifacts(existing_receipt, candidate)
    )
    if existing_receipt.get("status") == "schema_applied":
        return run_candidate_post_schema(
            config, source, candidate, operation_receipt_path,
            mysql_container=mysql_container,
        )
    fresh = (
        build_plan(config, source, candidate, allowed_partial_artifacts)
        if allowed_partial_artifacts
        else build_plan(config, source, candidate)
    )
    _validate_plan_integrity(plan, fresh)
    if fresh["source_schema_sha256"] != plan.get("source_schema_sha256"):
        raise UpgradeBlocked("source schema changed after planning")
    if fresh["source_data"] != plan.get("source_data"):
        raise UpgradeBlocked("source data changed after planning")
    if not database_exists(config, candidate):
        raise UpgradeBlocked("candidate has not been restored")
    # Preserve compatibility with legacy/minimal operation receipts while
    # enforcing the source-data invariant for receipts produced by the real
    # restore workflow.  The latter always records candidate_data.
    if isinstance(existing_receipt.get("candidate_data"), Mapping):
        candidate_data = _table_evidence(config, candidate)
        if not _candidate_preserves_source_data(
            plan.get("source_data") or {}, candidate_data
        ):
            raise UpgradeBlocked("candidate data does not match restored source")
    candidate_identity = server_identity(config, candidate)
    if candidate_identity["server"] != plan["source"]["server"]:
        raise UpgradeBlocked("candidate is on a different server")
    rebuild_plan = plan.get("legacy_knowledge_empty_rebuild") or {}
    if rebuild_plan.get("eligible") is True:
        _rebuild_empty_legacy_knowledge_candidate(
            config, candidate, existing_receipt, operation_receipt_path
        )
    before = _schema_snapshot(config, candidate)
    states = _owned_classification(before)
    preapply_states = _owned_classification(
        before, defer_missing_triggers=True
    )
    blocking_states = _blocking_schema_states(
        preapply_states, allowed_partial_artifacts
    )
    if blocking_states:
        raise UpgradeBlocked(
            f"candidate schema is partial/drift: {blocking_states}"
        )
    receipt = existing_receipt
    if receipt.get("candidate_database") != candidate:
        raise UpgradeBlocked("operation receipt targets another candidate")
    steps = receipt.setdefault("schema_steps", [])
    connection = config.connect(candidate)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS db")
            if cursor.fetchone()["db"] != candidate:
                raise UpgradeBlocked("mutation connection is not candidate")
            for part in SCHEMA_PARTS:
                statements = schema_statements_for_state(
                    part, states.get(part.name, "absent"), before
                )
                if states.get(part.name) == "exact":
                    steps.append(
                        {
                            "part": part.name,
                            "index": 0,
                            "status": "exact",
                            "outcome": "existing_part_skipped",
                            "verified_at": _now(),
                        }
                    )
                    write_receipt(operation_receipt_path, receipt)
                    continue
                part_before = _schema_snapshot(
                    config, candidate, owned_part=part.name
                )
                before_state = _owned_classification(part_before)[part.name]
                if before_state == "drift":
                    raise UpgradeBlocked(
                        f"candidate schema drift before {part.name}"
                    )
                part_steps: list[dict[str, Any]] = []
                for index, statement in enumerate(statements, start=1):
                    step = {
                        "part": part.name,
                        "index": index,
                        "statement_sha256": _sha256_bytes(
                            statement.encode("utf-8")
                        ),
                        "status": "prepared",
                        "before_schema_sha256": part_before["sha256"],
                        "before_part_state": before_state,
                        "prepared_at": _now(),
                    }
                    steps.append(step)
                    part_steps.append(step)
                    receipt.update(status="partial", phase="schema_apply")
                    write_receipt(operation_receipt_path, receipt)
                    try:
                        cursor.execute(statement)
                    except Exception as exc:
                        statement_after = _schema_snapshot(
                            config, candidate, owned_part=part.name
                        )
                        after_state = _owned_classification(
                            statement_after
                        )[part.name]
                        step.update(
                            status="failed",
                            error_type=type(exc).__name__,
                            after_schema_sha256=statement_after["sha256"],
                            after_part_state=after_state,
                            failed_at=_now(),
                        )
                        write_receipt(operation_receipt_path, receipt)
                        raise
                    step.update(
                        status="applied",
                        verification_status="pending_part_completion",
                        applied_at=_now(),
                    )
                    write_receipt(operation_receipt_path, receipt)
                part_after = _schema_snapshot(
                    config, candidate, owned_part=part.name
                )
                after_state = _owned_classification(part_after)[part.name]
                if part_steps:
                    part_steps[-1].update(
                        status=("exact" if after_state == "exact" else "applied"),
                        verification_status=(
                            "exact"
                            if after_state == "exact"
                            else "pending_part_completion"
                        ),
                        after_schema_sha256=part_after["sha256"],
                        after_part_state=after_state,
                        verified_at=(
                            _now() if after_state == "exact" else None
                        ),
                    )
                write_receipt(operation_receipt_path, receipt)
                if after_state == "drift":
                    raise UpgradeBlocked(
                        f"candidate schema drift after {part.name}"
                    )
    finally:
        connection.close()
    after = _schema_snapshot(config, candidate)
    states = _owned_classification(after)
    if not _candidate_schema_is_exact(states):
        receipt.update(status="partial", owned_objects=states)
        write_receipt(operation_receipt_path, receipt)
        raise UpgradeBlocked(f"schema postcheck is not exact: {states}")
    receipt.update(
        status="schema_applied", phase="schema_complete",
        schema_applied_at=_now(), candidate_schema_sha256=after["sha256"],
        owned_objects=states,
    )
    write_receipt(operation_receipt_path, receipt)
    return run_candidate_post_schema(
        config, source, candidate, operation_receipt_path,
        mysql_container=mysql_container,
    )


# Kept together so the destructive candidate-only rebuild and receipt stay atomic to audit.
def _rebuild_empty_legacy_knowledge_candidate(
    config: DatabaseConfig | SeparateDatabaseConfig,
    candidate: str,
    receipt: dict[str, Any],
    receipt_path: Path,
) -> None:
    snapshot = _schema_snapshot(config, candidate)
    if _legacy_knowledge_schema_state(snapshot) != "exact":
        states = _owned_classification(snapshot)
        if all(
            states.get(part) == "exact"
            for part in (
                "148_knowledge_retrieval.sql",
                "163_knowledge_runtime.sql",
            )
        ):
            receipt["legacy_knowledge_empty_rebuild"] = {
                "status": "exact_replay",
                "candidate_schema_sha256": snapshot["sha256"],
            }
            write_receipt(receipt_path, receipt)
            return
        raise UpgradeBlocked(
            "candidate legacy Knowledge fingerprint changed before rebuild"
        )
    evidence = _table_evidence(config, candidate)
    rebuild_plan = _legacy_knowledge_rebuild_plan(snapshot, evidence)
    preserved_before = {
        table: evidence[table]
        for table in sorted(LEGACY_KNOWLEDGE_PRESERVED_TABLES)
    }
    parts = {
        path.name: path
        for path in SCHEMA_PARTS
        if path.name in {
            "148_knowledge_retrieval.sql", "163_knowledge_runtime.sql",
        }
    }
    if set(parts) != {
        "148_knowledge_retrieval.sql", "163_knowledge_runtime.sql",
    }:
        raise UpgradeBlocked("canonical Knowledge schema parts are unavailable")
    rebuild = {
        "status": "prepared",
        "contract": rebuild_plan["contract"],
        "before_schema_sha256": snapshot["sha256"],
        "tables": list(LEGACY_KNOWLEDGE_DROP_ORDER),
        "preserved_tables": sorted(LEGACY_KNOWLEDGE_PRESERVED_TABLES),
        "preserved_before": preserved_before,
        "prepared_at": _now(),
    }
    receipt.update(status="partial", phase="legacy_knowledge_rebuild")
    receipt["legacy_knowledge_empty_rebuild"] = rebuild
    write_receipt(receipt_path, receipt)
    connection = config.connect(candidate)
    try:
        with connection.cursor() as cursor:
            for table in LEGACY_KNOWLEDGE_DROP_ORDER:
                if table in LEGACY_KNOWLEDGE_PRESERVED_TABLES:
                    continue
                cursor.execute(f"DROP TABLE IF EXISTS `{table}`")
            for part_name in (
                "148_knowledge_retrieval.sql",
                "163_knowledge_runtime.sql",
            ):
                for statement in split_sql(
                    parts[part_name].read_text(encoding="utf-8")
                ):
                    cursor.execute(statement)
    finally:
        connection.close()
    after = _schema_snapshot(config, candidate)
    states = _owned_classification(after)
    if any(
        states.get(part) != "exact"
        for part in (
            "148_knowledge_retrieval.sql", "163_knowledge_runtime.sql",
        )
    ):
        rebuild.update(status="failed", owned_objects=states)
        write_receipt(receipt_path, receipt)
        raise UpgradeBlocked("rebuilt Knowledge schema is not exact")
    preserved_after = {
        table: _table_evidence(config, candidate)[table]
        for table in sorted(LEGACY_KNOWLEDGE_PRESERVED_TABLES)
    }
    if preserved_after != preserved_before:
        rebuild.update(status="failed", preserved_after=preserved_after)
        write_receipt(receipt_path, receipt)
        raise UpgradeBlocked("preserved Knowledge request/job data changed")
    rebuild.update(
        status="completed",
        after_schema_sha256=after["sha256"],
        preserved_after=preserved_after,
        completed_at=_now(),
    )
    write_receipt(receipt_path, receipt)


def _run_orders_library_step(
    config: DatabaseConfig | SeparateDatabaseConfig,
    candidate: str,
    operation: Callable[[Any], dict[str, Any]],
    *,
    label: str,
    commit: bool = False,
) -> dict[str, Any]:
    """Run one approved Orders migration library step in runner-owned UoW.

    The former implementation launched child CLIs.  That made target
    confirmation, receipts, and commit ownership invisible to this runner.
    Library steps now receive the runner's candidate connection; only this
    composition boundary may commit or rollback it.
    """
    connection = config.connect(candidate)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS database_name")
            identity = cursor.fetchone()
            if not isinstance(identity, Mapping) or identity.get("database_name") != candidate:
                raise UpgradeBlocked(f"{label} connection is not the explicit candidate")
        result = operation(connection)
        if not isinstance(result, dict):
            raise UpgradeBlocked(f"{label} returned a non-object receipt")
        if commit:
            connection.commit()
        return result
    except Exception:
        if commit:
            connection.rollback()
        raise
    finally:
        connection.close()


def _require_orders_step_status(
    result: Mapping[str, Any],
    *,
    label: str,
    accepted: frozenset[str],
) -> dict[str, Any]:
    status = result.get("status")
    if status not in accepted:
        raise UpgradeBlocked(f"{label} did not reach an accepted state: {status!r}")
    return dict(result)


def _run_order_control_library_step(
    connection: Any,
    *,
    mode: str,
    target_database: str,
    backup_receipt: str | None = None,
    plan_receipt: str | None = None,
) -> dict[str, Any]:
    """Compose the immutable ORD-01 library helpers without its CLI owner.

    ``migrate_order_lifecycle_control_facts.py`` is a published, hash-locked
    migration artifact and therefore cannot be edited to remove its historical
    CLI commit.  The canonical runner deliberately calls its pure inspection
    and write helpers here, retaining this runner as the sole commit owner.
    """
    from scripts import migrate_order_lifecycle_control_facts as control_facts

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT DATABASE() AS database_name, @@hostname AS server"
        )
        identity = cursor.fetchone()
        if not isinstance(identity, Mapping) or identity.get("database_name") != target_database:
            raise UpgradeBlocked("order lifecycle control target identity mismatch")
        schema = control_facts._fetch_schema_snapshot(cursor)
        control_facts._assert_schema(schema)
        schema_fingerprint = control_facts._schema_fingerprint(schema)
        order_count, rows = control_facts._load_orders(
            cursor, lock=mode == "apply"
        )
        bootstrappable, review_required = control_facts.classify_legacy_rows(rows)
        dataset_fingerprint = control_facts._dataset_fingerprint(
            bootstrappable, review_required
        )
        before_counts = control_facts._control_counts(cursor)
        plan = None
        backup = None
        if mode == "apply":
            if not backup_receipt or not plan_receipt:
                raise UpgradeBlocked(
                    "order lifecycle apply requires backup and prior dry-run plan"
                )
            backup = control_facts.validate_backup(
                backup_receipt, target_database=target_database
            )
            plan = control_facts.validate_plan(
                plan_receipt,
                target_database=target_database,
                server=str(identity["server"]),
            )
            current_plan_identity = {
                "orders": order_count,
                "cancelled": len(rows),
                "bootstrappable": len(bootstrappable),
                "review_required": len(review_required),
                "dataset_fingerprint": dataset_fingerprint,
                "schema_fingerprint": schema_fingerprint,
            }
            for field, value in current_plan_identity.items():
                if plan.get(field) != value:
                    raise UpgradeBlocked(f"order lifecycle plan drift: {field}")

        existing_count = 0
        created_count = 0
        if mode in {"verify", "apply"}:
            rows_by_case = {row["case_no"]: row for row in rows}
            for item in bootstrappable:
                _event_id, exists = control_facts._assert_existing_identity(
                    cursor, item
                )
                if exists:
                    existing_count += 1
                    continue
                if mode == "verify":
                    raise UpgradeBlocked(
                        "missing bootstrap cancellation: " + item["case_no"]
                    )
                if int(rows_by_case[item["case_no"]]["lifecycle_version"]) != 0:
                    raise UpgradeBlocked(
                        "legacy order has nonzero lifecycle_version: "
                        + item["case_no"]
                    )
                control_facts._insert_bootstrap(cursor, item)
                created_count += 1
        after_counts = control_facts._control_counts(cursor)
    return {
        "migration": control_facts.MIGRATION_ID,
        "mode": mode,
        "database": identity["database_name"],
        "server": identity["server"],
        "orders": order_count,
        "cancelled": len(rows),
        "bootstrappable": len(bootstrappable),
        "review_required": len(review_required),
        "existing": existing_count,
        "created": created_count,
        "dataset_fingerprint": dataset_fingerprint,
        "schema_fingerprint": schema_fingerprint,
        "before_counts": before_counts,
        "after_counts": after_counts,
        "backup": backup,
        "plan_receipt": (
            {
                "path": str(Path(plan_receipt).expanduser().resolve()),
                "sha256": _sha256_bytes(_canonical_json(plan)),
            }
            if plan is not None and plan_receipt is not None
            else None
        ),
        "rollback": {
            "strategy": "restore_dump_to_new_database_then_switch",
            "source_database": target_database,
        },
    }


def _candidate_preddl_dump(
    config: DatabaseConfig | SeparateDatabaseConfig,
    candidate: str,
    target: Path,
    *,
    mysqldump: str = "mysqldump",
    mysql_container: str | None = None,
) -> dict[str, Any]:
    candidate_config = _candidate_connection_config(config, candidate)
    command = _mysql_base(
        candidate_config, mysqldump, container=mysql_container
    ) + [
        "--single-transaction", "--routines", "--events", "--triggers",
        "--hex-blob", "--databases", candidate,
    ]
    with target.open("wb") as output:
        completed = subprocess.run(
            command, stdout=output, stderr=subprocess.PIPE,
            env=_client_environment(candidate_config), check=False,
        )
    if completed.returncode != 0 or not target.is_file() or target.stat().st_size <= 0:
        raise UpgradeBlocked("candidate pre-DDL mysqldump failed")
    return {
        "path": str(target),
        "sha256": _sha256_file(target),
        "size": target.stat().st_size,
    }


def run_candidate_post_schema(
    config: DatabaseConfig | SeparateDatabaseConfig,
    source: str,
    candidate: str,
    operation_receipt_path: Path,
    *,
    mysql_container: str | None = None,
) -> dict[str, Any]:
    receipt = read_receipt(operation_receipt_path)
    if receipt.get("status") != "schema_applied":
        raise UpgradeBlocked("post-schema phase requires schema_applied receipt")
    if server_identity(config, candidate)["database"] != candidate:
        raise UpgradeBlocked("post-schema target is not candidate")
    if _uses_catalog_post_schema_contract():
        if getattr(RELEASE_MANIFEST, "backfills", ()):
            raise UpgradeBlocked(
                "manifest backfill execution is not supported by this runner"
            )
        owned_objects = receipt.get("owned_objects")
        verification_receipts = ()
        if isinstance(owned_objects, Mapping):
            verification_receipts = run_manifest_verifications(
                RELEASE_MANIFEST.verification_contracts,
                phase="post-schema",
                validators=_post_schema_verification_validators(owned_objects),
            )
        receipt.update(
            status="backfilled",
            phase="post_schema_complete",
            backfilled_at=_now(),
            backfills=(),
            post_schema_verification_receipts=tuple(
                {
                    "verification_id": item.verification_id,
                    "phase": item.phase,
                    "status": item.status,
                    "evidence": dict(item.evidence),
                }
                for item in verification_receipts
            ),
        )
        write_receipt(operation_receipt_path, receipt)
        return receipt
    artifact_dir = operation_receipt_path.expanduser().resolve().parent
    backup = artifact_dir / f"{candidate}.pre_backfill.sql"
    plan = artifact_dir / f"{candidate}.backfill.plan.json"
    backfill_receipt = artifact_dir / f"{candidate}.backfill.receipt.json"
    candidate_config = _candidate_connection_config(config, candidate)
    candidate_backup = _candidate_preddl_dump(
        config, candidate, backup, mysql_container=mysql_container
    )
    receipt["candidate_pre_backfill_dump"] = candidate_backup
    write_receipt(operation_receipt_path, receipt)
    # These three historical child scripts are library-only.  Their approved
    # behavior is now composed here, after candidate identity and backup
    # checks, with this runner owning every connection and commit boundary.
    from scripts import (
        migrate_order_contract_identity as contract_identity,
        migrate_order_details_lifecycle_version_view as lifecycle_view,
    )

    dry = _run_orders_library_step(
        candidate_config,
        candidate,
        lambda connection: _run_order_control_library_step(
            connection,
            mode="dry-run",
            target_database=candidate,
        ),
        label="order lifecycle control dry-run",
    )
    write_receipt(plan, dry)
    applied = _run_orders_library_step(
        candidate_config,
        candidate,
        lambda connection: _run_order_control_library_step(
            connection,
            mode="apply",
            target_database=candidate,
            backup_receipt=str(backup),
            plan_receipt=str(plan),
        ),
        label="order lifecycle control apply",
        commit=True,
    )
    applied["receipt_status"] = "committed_by_canonical_runner"
    write_receipt(backfill_receipt, applied)
    verified = _run_orders_library_step(
        candidate_config,
        candidate,
        lambda connection: _run_order_control_library_step(
            connection,
            mode="verify",
            target_database=candidate,
        ),
        label="order lifecycle control verify",
    )
    write_receipt(artifact_dir / f"{candidate}.backfill.verify.json", verified)
    if int(verified.get("review_required", -1)) != 0:
        raise UpgradeBlocked("order lifecycle control backfill has unresolved rows")

    contract_apply = _run_orders_library_step(
        candidate_config,
        candidate,
        contract_identity.migrate,
        label="order contract identity apply",
        commit=True,
    )
    contract_verify = _run_orders_library_step(
        candidate_config,
        candidate,
        contract_identity.migrate,
        label="order contract identity verify",
    )
    if contract_verify.get("status") not in {"already_retired", "renamed"}:
        raise UpgradeBlocked("order contract identity verification failed")

    view_dry = _run_orders_library_step(
        candidate_config,
        candidate,
        lambda connection: lifecycle_view.run_migration(connection),
        label="order details view dry-run",
    )
    view_dry = _require_orders_step_status(
        view_dry,
        label="order details view dry-run",
        accepted=frozenset({"ready", "existing"}),
    )
    view_apply = _run_orders_library_step(
        candidate_config,
        candidate,
        lambda connection: lifecycle_view.run_migration(connection, apply=True),
        label="order details view apply",
        commit=True,
    )
    view_apply = _require_orders_step_status(
        view_apply,
        label="order details view apply",
        accepted=frozenset({"applied", "existing"}),
    )
    view_verify = _run_orders_library_step(
        candidate_config,
        candidate,
        lambda connection: lifecycle_view.run_migration(connection),
        label="order details view verify",
    )
    view_verify = _require_orders_step_status(
        view_verify,
        label="order details view verify",
        accepted=frozenset({"existing"}),
    )
    receipt.update(
        status="backfilled",
        phase="post_schema_complete",
        backfilled_at=_now(),
        backfill={
            "dry_run": dry,
            "apply": applied,
            "verify": verified,
            "plan_sha256": _sha256_file(plan),
            "receipt_sha256": _sha256_file(backfill_receipt),
        },
        contract_identity=contract_apply,
        contract_identity_verify=contract_verify,
        view={"dry_run": view_dry, "apply": view_apply, "verify": view_verify},
    )
    write_receipt(operation_receipt_path, receipt)
    return receipt


def _uses_catalog_post_schema_contract() -> bool:
    return MANIFEST_DRIVEN_RELEASE


def _replace_database_setting(raw: bytes, before: str, after: str) -> bytes:
    text = raw.decode("utf-8")
    pattern = re.compile(
        r"(?m)^([ \t]*DB_DATABASE[ \t]*=[ \t]*)([^\r\n]*)(\r?)$"
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise UpgradeBlocked("environment must contain exactly one DB_DATABASE")
    value = matches[0].group(2)
    parsed = re.fullmatch(
        r"([ \t]*)(?:(['\"])([A-Za-z0-9_]+)\2|([A-Za-z0-9_]+))"
        r"([ \t]*)",
        value,
    )
    if parsed is None:
        raise UpgradeBlocked("environment DB_DATABASE format is unsupported")
    current = parsed.group(3) or parsed.group(4)
    if current != before:
        raise UpgradeBlocked("environment DB_DATABASE is stale")
    quote = parsed.group(2) or ""
    replacement_value = (
        f"{parsed.group(1)}{quote}{after}{quote}{parsed.group(5)}"
    )
    replacement = (
        f"{matches[0].group(1)}{replacement_value}{matches[0].group(3)}"
    )
    updated = text[: matches[0].start()] + replacement + text[matches[0].end():]
    return updated.encode("utf-8")


def switch_environment(
    environment_file: Path,
    source: str,
    candidate: str,
    verified_receipt_path: Path,
    switch_receipt_path: Path,
    config: DatabaseConfig | SeparateDatabaseConfig | None = None,
) -> dict[str, Any]:
    verified = read_receipt(verified_receipt_path)
    if verified.get("status") != "verified":
        raise UpgradeBlocked("candidate is not verified")
    source_identity = verified.get("source") or {}
    candidate_identity = verified.get("candidate") or {}
    if (
        verified.get("candidate_database") != candidate
        or source_identity.get("database") != source
        or candidate_identity.get("database") != candidate
        or source_identity.get("server") != candidate_identity.get("server")
    ):
        raise UpgradeBlocked("verified receipt database identity mismatch")
    raw, environment = _read_env_bytes(environment_file)
    try:
        environment_port = int(environment.get("DB_PORT", "3306"))
        verified_port = int(source_identity.get("port"))
    except (TypeError, ValueError) as exc:
        raise UpgradeBlocked(
            "verified environment port identity is invalid"
        ) from exc
    if (
        environment.get("DB_HOST", "127.0.0.1")
        != str(source_identity.get("host"))
        or environment_port != verified_port
    ):
        raise UpgradeBlocked("environment connection identity is stale")
    connection_config = config
    _, configured_environment = _read_env_bytes(environment_file)
    configured_source = str(configured_environment.get("DB_DATABASE") or "")
    if configured_source != source:
        raise UpgradeBlocked("environment source database is stale")
    if connection_config is None:
        connection_config, configured_source = config_from_env(environment_file)
        if configured_source != source:
            raise UpgradeBlocked("environment source database is stale")
    current_source_identity = server_identity(connection_config, source)
    current_candidate_identity = server_identity(connection_config, candidate)
    if (
        current_source_identity.get("server") != source_identity.get("server")
        or current_candidate_identity.get("server")
        != candidate_identity.get("server")
    ):
        raise UpgradeBlocked("verified server identity is stale")
    if _table_evidence(connection_config, source) != verified.get("source_data"):
        raise UpgradeBlocked("verified source data fingerprint is stale")
    if _table_evidence(connection_config, candidate) != verified.get("candidate_data"):
        raise UpgradeBlocked("verified candidate data fingerprint is stale")
    updated = _replace_database_setting(raw, source, candidate)
    receipt = {
        "kind": "database_switch",
        "status": "prepared",
        "created_at": _now(),
        "environment_file": str(environment_file.expanduser().resolve()),
        "source_database": source,
        "candidate_database": candidate,
        "before_sha256": _sha256_bytes(raw),
        "after_sha256": _sha256_bytes(updated),
        "verified_receipt_sha256": _sha256_file(verified_receipt_path),
    }
    write_receipt(switch_receipt_path, receipt)
    _atomic_write(environment_file, updated)
    receipt.update(status="switched", switched_at=_now())
    write_receipt(switch_receipt_path, receipt)
    return receipt


def rollback_environment(
    environment_file: Path, switch_receipt_path: Path
) -> dict[str, Any]:
    receipt = read_receipt(switch_receipt_path)
    if receipt.get("status") != "switched":
        raise UpgradeBlocked("switch receipt is not rollback eligible")
    current = environment_file.expanduser().resolve().read_bytes()
    if _sha256_bytes(current) != receipt.get("after_sha256"):
        raise UpgradeBlocked("environment changed after switch")
    source = str(receipt.get("source_database") or "")
    candidate = str(receipt.get("candidate_database") or "")
    validate_database_names(source, candidate)
    before = _replace_database_setting(current, candidate, source)
    if _sha256_bytes(before) != receipt.get("before_sha256"):
        raise UpgradeBlocked("environment cannot reconstruct switch baseline")
    _atomic_write(environment_file, before)
    if _sha256_bytes(environment_file.expanduser().resolve().read_bytes()) != (
        receipt.get("before_sha256")
    ):
        raise UpgradeBlocked("environment rollback verification failed")
    receipt.update(status="rolled_back", rolled_back_at=_now())
    write_receipt(switch_receipt_path, receipt)
    return receipt


def _verify_legacy_system_alert_rows(
    config: DatabaseConfig, source: str, candidate: str
) -> dict[str, Any]:
    legacy_fields = (
        "id,event_type,description,status,created_at,resolved_at,resolved_by"
    )
    source_connection = config.connect(source)
    candidate_connection = config.connect(candidate)
    try:
        with source_connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {legacy_fields} FROM system_alerts ORDER BY id"
            )
            source_rows = cursor.fetchall()
        with candidate_connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {legacy_fields},alert_code,source_domain,case_key,"
                "reason,details,claimed_by,claimed_at,resolution_reason "
                "FROM system_alerts ORDER BY id"
            )
            candidate_rows = cursor.fetchall()
    finally:
        source_connection.close()
        candidate_connection.close()
    if len(source_rows) != len(candidate_rows):
        raise UpgradeBlocked("legacy system_alerts row count changed")
    for before, after in zip(source_rows, candidate_rows, strict=True):
        for field in (
            "id", "event_type", "description", "created_at", "resolved_at",
            "resolved_by",
        ):
            if before[field] != after[field]:
                raise UpgradeBlocked(
                    f"legacy system_alerts field changed: {field}"
                )
        expected_status = (
            "open" if before["status"] == "pending" else "resolved"
        )
        event_type = str(before["event_type"]).strip() or "LEGACY"
        description = str(before["description"]).strip()
        expected_reason = description[:500] or "Legacy system alert"
        if (
            after["status"] != expected_status
            or after["alert_code"] != event_type
            or after["source_domain"] != "LEGACY"
            or after["case_key"] != f"legacy-alert:{before['id']}"
            or after["reason"] != expected_reason
        ):
            raise UpgradeBlocked("legacy system_alerts projection mismatch")
        details = after["details"]
        if isinstance(details, str):
            details = json.loads(details)
        if details != {
            "legacy_event_type": event_type,
            "migration": "system_alert_current_projection_v1",
        }:
            raise UpgradeBlocked("legacy system_alerts details mismatch")
    return {
        "mode": "legacy_migrated",
        "row_count": len(source_rows),
        "status_mapping": "pending_to_open_resolved_unchanged",
    }


def _table_projection_evidence(
    config: DatabaseConfig,
    database: str,
    table: str,
    columns: list[str],
    *,
    column_sources: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    sources = dict(column_sources or {})
    if (
        not IDENTIFIER.fullmatch(table)
        or not columns
        or any(not IDENTIFIER.fullmatch(name) for name in columns)
        or any(
            not IDENTIFIER.fullmatch(name)
            for name in (*sources.keys(), *sources.values())
        )
        or not set(sources).issubset(columns)
    ):
        raise UpgradeBlocked("preserved table projection is invalid")
    connection = config.connect(database)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema=%s AND table_name=%s",
                (database, table),
            )
            available = {
                _normalized_row(row)["column_name"]
                for row in cursor.fetchall()
            }
            actual_columns = [sources.get(name, name) for name in columns]
            missing = set(actual_columns) - available
            if missing:
                raise UpgradeBlocked(
                    f"candidate {table} lost legacy columns: "
                    + ",".join(sorted(missing))
                )
            projection = ",".join(
                f"`{sources.get(name, name)}` AS `{name}`"
                for name in columns
            )
            cursor.execute(
                "SELECT column_name FROM information_schema.key_column_usage "
                "WHERE table_schema=%s AND table_name=%s "
                "AND constraint_name='PRIMARY' ORDER BY ordinal_position",
                (database, table),
            )
            primary = [
                _normalized_row(row)["column_name"]
                for row in cursor.fetchall()
            ]
            ordering = (
                ",".join(f"`{name}`" for name in primary)
                if primary
                else projection
            )
            cursor.execute(
                f"SELECT {projection} FROM `{table}` "
                f"ORDER BY {ordering}"
            )
            rows = cursor.fetchall()
    finally:
        connection.close()
    return {
        "columns": columns,
        "row_count": len(rows),
        "rows_sha256": _sha256_bytes(_canonical_json(rows)),
    }


def _table_columns(
    snapshot: Mapping[str, Any], table: str
) -> list[str]:
    """Return a table's columns in ordinal order from a schema snapshot."""
    return [
        row["column_name"]
        for row in snapshot["columns"]
        if row["table_name"] == table
    ]


def _verify_source_column_projection_preserved(
    config: DatabaseConfig,
    source: str,
    candidate: str,
    table: str,
    source_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify legacy values while allowing additive candidate columns."""
    source_columns = _table_columns(source_snapshot, table)
    before = _table_projection_evidence(
        config, source, table, source_columns
    )
    after = _table_projection_evidence(
        config, candidate, table, source_columns
    )
    if after != before:
        raise UpgradeBlocked(f"preserved table projection changed: {table}")
    return after


def _verify_matching_records_preservation(
    config: DatabaseConfig,
    source: str,
    candidate: str,
    source_snapshot: Mapping[str, Any],
    source_resume_state: str,
) -> dict[str, Any]:
    source_columns = [
        row["column_name"] for row in source_snapshot["columns"]
        if row["table_name"] == "matching_records"
    ]
    before = _table_projection_evidence(
        config, source, "matching_records", source_columns
    )
    after = _table_projection_evidence(
        config, candidate, "matching_records", source_columns
    )
    if after != before:
        raise UpgradeBlocked("matching_records legacy data changed")
    connection = config.connect(candidate)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS n FROM matching_records "
                "WHERE sent_resume_at IS NOT NULL"
            )
            non_null_count = int(cursor.fetchone()["n"])
    finally:
        connection.close()
    if source_resume_state == "absent" and non_null_count:
        raise UpgradeBlocked("sent_resume_at was inferred or backfilled")
    return {
        **after,
        "source_resume_state": source_resume_state,
        "sent_resume_non_null_count": non_null_count,
    }


def _verify_orders_preservation(
    config: DatabaseConfig,
    source: str,
    candidate: str,
    source_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    source_columns = [
        row["column_name"] for row in source_snapshot["columns"]
        if row["table_name"] == "orders"
    ]
    before = _table_projection_evidence(
        config, source, "orders", source_columns
    )
    renamed_columns = (
        {"contract_id": "contract_identity"}
        if "contract_id" in source_columns
        else None
    )
    if renamed_columns is None:
        after = _table_projection_evidence(
            config, candidate, "orders", source_columns
        )
    else:
        after = _table_projection_evidence(
            config,
            candidate,
            "orders",
            source_columns,
            column_sources=renamed_columns,
        )
    if after != before:
        raise UpgradeBlocked("orders legacy data changed")
    return after


def _verify_knowledge_source_identity_backfill(
    config: DatabaseConfig,
    source: str,
    candidate: str,
    source_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    source_columns = [
        name for name in _table_columns(source_snapshot, "knowledge_items")
        if name not in {"source_identity", "updated_at"}
    ]
    before = _table_projection_evidence(
        config, source, "knowledge_items", source_columns
    )
    after = _table_projection_evidence(
        config, candidate, "knowledge_items", source_columns
    )
    if after != before:
        raise UpgradeBlocked("knowledge_items facts changed during backfill")
    source_rows = _knowledge_source_identity_rows(config, source)
    candidate_rows = _knowledge_source_identity_rows(config, candidate)
    expected = [
        {
            "id": row["id"],
            "source_identity": (
                row["source_identity"] or f"knowledge:{row['id']}"
            ),
        }
        for row in source_rows
    ]
    if candidate_rows != expected:
        raise UpgradeBlocked("knowledge source identity backfill is invalid")
    return {"projection": after, "rows": len(candidate_rows)}


def _knowledge_source_identity_rows(
    config: DatabaseConfig,
    database: str,
) -> list[dict[str, Any]]:
    connection = config.connect(database)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, source_identity FROM knowledge_items ORDER BY id"
            )
            return [dict(row) for row in cursor.fetchall()]
    finally:
        connection.close()


def verify_candidate(
    config: DatabaseConfig,
    source: str,
    candidate: str,
    operation_receipt_path: Path,
) -> dict[str, Any]:
    receipt = read_receipt(operation_receipt_path)
    if receipt.get("status") not in VERIFYABLE_CANDIDATE_STATUSES:
        raise UpgradeBlocked("candidate has not completed schema/backfill")
    source_snapshot = _schema_snapshot(config, source)
    source_objects = _owned_classification(
        source_snapshot, defer_missing_triggers=True
    )
    source_alert_state = _system_alert_projection_state(source_snapshot)
    source_resume_state = _matching_records_resume_delivery_state(
        source_snapshot
    )
    source_data = _table_evidence(config, source)
    candidate_snapshot = _schema_snapshot(config, candidate)
    candidate_data = _table_evidence(config, candidate)
    legacy_rebuild = receipt.get("legacy_knowledge_empty_rebuild") or {}
    rebuilt_empty_knowledge = legacy_rebuild.get("status") in {
        "completed", "exact_replay",
    }
    backfill_verify = ((receipt.get("backfill") or {}).get("verify") or {})
    backfill_result = backfill_verify.get("result") or {}
    verified_lifecycle_backfill = (
        backfill_verify.get("exit_code") == 0
        and backfill_result.get("mode") == "verify"
        and int(backfill_result.get("review_required", -1)) == 0
    )
    additive_projection_preservation: dict[str, Any] = {}
    for table, evidence in source_data.items():
        actual = candidate_data.get(table)
        if not actual:
            if (
                table in INTENTIONALLY_RETIRED_EMPTY_TABLES
                and int(evidence.get("count", 0)) == 0
            ):
                additive_projection_preservation[table] = {
                    "mode": "reviewed_empty_table_retirement",
                    "row_count": 0,
                }
                continue
            raise UpgradeBlocked(f"preserved table is missing: {table}")
        if (
            actual.get("count") != evidence.get("count")
            or actual.get("primary_key_sha256")
            != evidence.get("primary_key_sha256")
        ):
            if not (
                verified_lifecycle_backfill
                and table in DECLARED_LIFECYCLE_BACKFILL_TABLES
            ):
                raise UpgradeBlocked(f"preserved table changed: {table}")
            additive_projection_preservation[table] = {
                "mode": "verified_declared_lifecycle_backfill",
                "source": evidence,
                "candidate": actual,
            }
            continue
        if (
            rebuilt_empty_knowledge
            and table in LEGACY_KNOWLEDGE_REBUILD_TABLES
        ):
            if int(evidence.get("count", 0)) != 0:
                raise UpgradeBlocked(
                    "legacy Knowledge rebuild receipt contains nonempty data"
                )
            additive_projection_preservation[table] = {
                "mode": "reviewed_empty_schema_rebuild",
                "row_count": 0,
            }
            continue
        if (
            rebuilt_empty_knowledge
            and table in LEGACY_KNOWLEDGE_PRESERVED_TABLES
            and actual != evidence
        ):
            raise UpgradeBlocked(
                f"preserved Knowledge request/job data changed: {table}"
            )
        source_columns = _table_columns(source_snapshot, table)
        candidate_columns = _table_columns(candidate_snapshot, table)
        has_additive_columns = source_columns != candidate_columns
        has_contract_identity_rename = (
            table == "orders"
            and "contract_id" in source_columns
            and "contract_identity" in candidate_columns
        )
        has_knowledge_identity_backfill = (
            table == "knowledge_items"
            and source_objects.get("163_knowledge_runtime.sql") == "partial"
        )
        has_legacy_system_alert_migration = (
            table == "system_alerts" and source_alert_state == "absent"
        )
        if (
            has_additive_columns
            and not has_contract_identity_rename
            and not has_legacy_system_alert_migration
        ):
            additive_projection_preservation[table] = (
                _verify_source_column_projection_preserved(
                    config,
                    source,
                    candidate,
                    table,
                    source_snapshot,
                )
            )
        elif has_knowledge_identity_backfill:
            additive_projection_preservation[table] = (
                _verify_knowledge_source_identity_backfill(
                    config, source, candidate, source_snapshot
                )
            )
        if (
            table not in {"orders", "matching_records"}
            and not (
                table == "system_alerts"
                and source_alert_state == "absent"
            )
            and not has_additive_columns
            and not has_knowledge_identity_backfill
            and actual.get("checksum") != evidence.get("checksum")
        ):
            # ALTER TABLE can legitimately change MySQL's physical checksum without
            # changing a preserved row (for example, an enum extension).
            additive_projection_preservation[table] = (
                _verify_source_column_projection_preserved(
                    config, source, candidate, table, source_snapshot
                )
            )
    system_alert_preservation = (
        _verify_legacy_system_alert_rows(config, source, candidate)
        if source_alert_state == "absent"
        else {"mode": "current_unchanged", "row_count": source_data[
            "system_alerts"
        ]["count"]}
    )
    matching_records_preservation = _verify_matching_records_preservation(
        config,
        source,
        candidate,
        source_snapshot,
        source_resume_state,
    )
    orders_preservation = _verify_orders_preservation(
        config, source, candidate, source_snapshot
    )
    states = _owned_classification(candidate_snapshot)
    if not _candidate_schema_is_exact(states):
        raise UpgradeBlocked(f"candidate owned schema not exact: {states}")
    connection = config.connect(candidate)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS n FROM orders o "
                "LEFT JOIN v_order_details v ON v.case_no=o.case_no "
                "WHERE v.case_no IS NULL OR "
                "v.lifecycle_version<>o.lifecycle_version"
            )
            view_mismatches = int(cursor.fetchone()["n"])
    finally:
        connection.close()
    if view_mismatches:
        raise UpgradeBlocked("v_order_details lifecycle_version mismatch")
    receipt.update(
        status="verified", verified_at=_now(), source_data=source_data,
        candidate_data=candidate_data, owned_objects=states,
        view_mismatches=0,
        system_alert_preservation=system_alert_preservation,
        matching_records_preservation=matching_records_preservation,
        orders_preservation=orders_preservation,
        additive_projection_preservation=additive_projection_preservation,
    )
    write_receipt(operation_receipt_path, receipt)
    return receipt


def complete_cutover_after_restart(
    switch_receipt_path: Path,
    restart_port: Any,
    smoke_port: Any,
) -> dict[str, Any]:
    """Restart selected targets, run read smokes, and close the cutover."""

    receipt = read_receipt(switch_receipt_path)
    if receipt.get("status") != "switched":
        raise UpgradeBlocked("switch receipt is not restart eligible")
    post_restart: dict[str, Any] = {}
    try:
        runtime_receipts = restart_and_run_read_smoke(
            RELEASE_MANIFEST.required_restart_targets,
            RELEASE_MANIFEST.post_cutover_smoke_ids,
            restart_port,
            smoke_port,
        )
        smoke_by_id = {
            item["smoke_id"]: item
            for item in runtime_receipts["smoke_receipts"]
        }
        validators = _post_restart_validators(smoke_by_id)
        verification_receipts = (
            run_manifest_verifications(
                RELEASE_MANIFEST.verification_contracts,
                phase="post-restart",
                validators=validators,
            )
            if MANIFEST_DRIVEN_RELEASE
            else ()
        )
        post_restart.update(
            runtime_receipts,
            read_smokes=runtime_receipts["smoke_receipts"],
            verification_receipts=tuple(
                {
                    "verification_id": item.verification_id,
                    "phase": item.phase,
                    "status": item.status,
                    "evidence": dict(item.evidence),
                }
                for item in verification_receipts
            ),
        )
    finally:
        shutdown = getattr(restart_port, "shutdown", None)
        post_restart["shutdown_receipts"] = (
            tuple(shutdown()) if callable(shutdown) else ()
        )
    receipt.update(
        status="completed",
        completed_at=_now(),
        post_restart=post_restart,
    )
    write_receipt(switch_receipt_path, receipt)
    return receipt


def build_candidate_runtime_config(
    config: SeparateDatabaseConfig,
    candidate_database: str,
    receipt_directory: Path,
    api_port: int,
    streamlit_port: int,
    startup_timeout_seconds: int,
) -> CandidateRuntimeConfig:
    _validate_rehearsal_runtime_ports(api_port, streamlit_port)
    if startup_timeout_seconds < 1:
        raise UpgradeBlocked("rehearsal startup timeout must be positive")
    candidate = config.candidate.config
    environment = {
        "DB_HOST": candidate.host,
        "DB_PORT": str(candidate.port),
        "DB_USER": candidate.user,
        "DB_PASSWORD": candidate.password,
        "DB_DATABASE": candidate_database,
    }
    return CandidateRuntimeConfig(
        ROOT, api_port, streamlit_port, startup_timeout_seconds, environment,
        candidate, candidate_database, receipt_directory / "candidate-runtime",
    )


def _validate_rehearsal_runtime_ports(api_port: int, streamlit_port: int) -> None:
    if api_port == streamlit_port:
        raise UpgradeBlocked("rehearsal API and Streamlit ports must differ")
    if not all(1024 <= port <= 65535 for port in (api_port, streamlit_port)):
        raise UpgradeBlocked("rehearsal runtime ports must be between 1024 and 65535")


def _post_restart_validators(
    smoke_by_id: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    def aggregate_smokes() -> Mapping[str, Any]:
        return {
            "status": "passed",
            "smoke_ids": tuple(smoke_by_id),
        }

    validators: dict[str, Any] = {
        smoke_id: (lambda item=item: item)
        for smoke_id, item in smoke_by_id.items()
    }
    validators["application-read-smoke"] = aggregate_smokes
    return validators


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    for name in (
        "check", "dry-run", "backup", "restore", "apply", "verify",
        "switch", "rollback-switch", "complete-restart",
        "recover-interrupted-switch",
    ):
        modes.add_argument(f"--{name}", action="store_true")
    parser.add_argument("--environment-file", default=str(ROOT / ".env"))
    parser.add_argument("--source-database")
    parser.add_argument("--candidate-database")
    parser.add_argument("--source-read-descriptor")
    parser.add_argument("--candidate-write-descriptor")
    parser.add_argument("--source-principal-evidence")
    parser.add_argument("--maintenance-token")
    parser.add_argument("--receipt-directory")
    parser.add_argument("--plan-receipt")
    parser.add_argument(
        "--operation-receipt", "--receipt-path", dest="operation_receipt",
        help="terminal operation receipt (required for apply and verification)",
    )
    parser.add_argument("--source-dump")
    parser.add_argument("--source-backup-receipt")
    parser.add_argument("--switch-receipt")
    parser.add_argument("--mysqldump", default="mysqldump")
    parser.add_argument("--mysql", default="mysql")
    parser.add_argument("--mysql-container")
    parser.add_argument(
        "--release-manifest",
        action="append",
        default=[],
        help="Validated release manifest; repeat to apply an ordered chain",
    )
    parser.add_argument(
        "--rehearsal",
        action="store_true",
        help="Require isolated lu_test_* source and candidate databases",
    )
    parser.add_argument(
        "--api-port", "--rehearsal-api-port", dest="api_port", type=int,
        default=18022,
    )
    parser.add_argument(
        "--streamlit-port", "--rehearsal-streamlit-port",
        dest="streamlit_port", type=int, default=18522,
    )
    parser.add_argument(
        "--startup-timeout-seconds", "--rehearsal-startup-timeout-seconds",
        dest="startup_timeout_seconds", type=int, default=30,
    )
    parser.add_argument("--runtime-evidence-directory")
    parser.add_argument("--confirm", "--confirm-apply", dest="confirm")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    environment_file = Path(args.environment_file)
    try:
        configure_release_manifests(
            Path(path) for path in args.release_manifest
        )
        if args.rehearsal:
            config, configured_source = config_from_env(environment_file)
            source = (args.source_database or configured_source).strip()
            candidate = (args.candidate_database or "").strip()
            if not source:
                raise UpgradeBlocked(
                    "source database must be explicit when .env has no DB_DATABASE"
                )
            validate_rehearsal_database_names(source, candidate)
            receipt_directory = (
                Path(args.receipt_directory)
                if args.receipt_directory
                else None
            )
        else:
            if not environment_file.is_file():
                raise FileNotFoundError(environment_file)
            source = (args.source_database or "").strip()
            candidate = (args.candidate_database or "").strip()
            validate_database_names(source, candidate)
            if not all((
                args.source_read_descriptor,
                args.candidate_write_descriptor,
                args.source_principal_evidence,
                args.maintenance_token,
                args.receipt_directory,
            )):
                raise UpgradeBlocked(
                    "source/candidate safety arguments are required"
                )
            _require_production_authority_credential_gate(args)
            config = build_descriptor_runtime(
                Path(args.source_read_descriptor),
                Path(args.candidate_write_descriptor),
                source,
                candidate,
            )
            receipt_directory = Path(args.receipt_directory)
        mode = "dry-run"
        mode = next(
            (
                name.replace("_", "-")
                for name in (
                    "check", "dry_run", "backup", "restore", "apply", "verify",
                    "switch", "rollback_switch", "complete_restart",
                    "recover_interrupted_switch",
                )
                if getattr(args, name)
            ),
            mode,
        )
        if (
            not args.rehearsal
            and mode in {
                "check", "dry-run", "backup", "switch", "complete-restart"
            }
        ):
            run_source_safety_preflight(
                config,
                source,
                candidate,
                Path(args.source_principal_evidence),
                Path(args.maintenance_token),
                receipt_directory,
                mode=mode,
            )
        if mode in {"check", "dry-run"}:
            result = build_plan(config, source, candidate)
            if mode == "dry-run":
                if not args.plan_receipt:
                    raise UpgradeBlocked("--dry-run requires --plan-receipt")
                write_receipt(args.plan_receipt, result)
        elif mode == "backup":
            if not args.source_dump or not args.source_backup_receipt:
                raise UpgradeBlocked(
                    "--backup requires --source-dump and "
                    "--source-backup-receipt"
                )
            result = create_source_dump(
                _database_connection_config(config, source),
                source,
                Path(args.source_dump),
                Path(args.source_backup_receipt), mysqldump=args.mysqldump,
                mysql_container=args.mysql_container,
            )
        elif mode == "restore":
            required = (
                args.source_dump, args.source_backup_receipt,
                args.operation_receipt,
            )
            if not all(required):
                raise UpgradeBlocked("restore receipt arguments are required")
            result = restore_candidate(
                config, source, candidate, Path(args.source_dump),
                Path(args.source_backup_receipt),
                Path(args.operation_receipt), mysql=args.mysql,
                mysql_container=args.mysql_container,
            )
        elif mode == "apply":
            if args.confirm != APPLY_CONFIRMATION:
                raise UpgradeBlocked(
                    "--apply requires --confirm " + APPLY_CONFIRMATION
                )
            if not args.plan_receipt or not args.operation_receipt:
                raise UpgradeBlocked("apply requires plan and operation receipts")
            result = apply_schema(
                config, source, candidate, Path(args.plan_receipt),
                Path(args.operation_receipt),
                mysql_container=args.mysql_container,
            )
            if (
                result.get("status") not in VERIFYABLE_CANDIDATE_STATUSES
                or not Path(args.operation_receipt).is_file()
            ):
                raise UpgradeBlocked(
                    "apply did not produce a verified terminal receipt"
                )
        elif mode == "verify":
            if not args.operation_receipt:
                raise UpgradeBlocked("verify requires operation receipt")
            result = verify_candidate(
                config, source, candidate, Path(args.operation_receipt)
            )
        elif mode == "switch":
            if not args.operation_receipt or not args.switch_receipt:
                raise UpgradeBlocked("switch receipts are required")
            result = switch_environment(
                environment_file, source, candidate,
                Path(args.operation_receipt), Path(args.switch_receipt), config,
            )
        elif mode == "complete-restart":
            if not args.switch_receipt:
                raise UpgradeBlocked("complete-restart requires switch receipt")
            if args.rehearsal and not args.runtime_evidence_directory:
                raise UpgradeBlocked(
                    "rehearsal complete-restart requires runtime evidence directory"
                )
            if args.rehearsal:
                _, database_environment = _read_env_bytes(environment_file)
                runtime_config = CandidateRuntimeConfig(
                    ROOT, args.api_port, args.streamlit_port,
                    args.startup_timeout_seconds,
                    {**database_environment, "DB_DATABASE": candidate},
                    config, candidate, Path(args.runtime_evidence_directory),
                )
            else:
                if receipt_directory is None:
                    raise UpgradeBlocked(
                        "complete-restart requires receipt directory"
                    )
                runtime_config = build_candidate_runtime_config(
                    config, candidate, receipt_directory, args.api_port,
                    args.streamlit_port, args.startup_timeout_seconds,
                )
            result = complete_cutover_after_restart(
                Path(args.switch_receipt),
                EphemeralCandidateRestartPort(runtime_config),
                CandidateReadSmokePort(runtime_config),
            )
        elif mode == "rollback-switch":
            if not args.switch_receipt:
                raise UpgradeBlocked("rollback-switch requires switch receipt")
            result = rollback_environment(
                environment_file, Path(args.switch_receipt)
            )
        elif mode == "recover-interrupted-switch":
            if args.rehearsal:
                raise UpgradeBlocked(
                    "recover-interrupted-switch requires formal safety receipts"
                )
            if not args.switch_receipt or receipt_directory is None:
                raise UpgradeBlocked(
                    "recover-interrupted-switch requires switch receipt"
                )
            result = recover_interrupted_switch(
                environment_file,
                Path(args.switch_receipt),
                receipt_directory,
            )
        else:
            raise UpgradeBlocked(f"unsupported migration mode: {mode}")
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
