"""
File: migration_release.py
Description: 驗證可追溯 additive migration manifest 與 owned schema object 契約。
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from shared_kernel.validation import require_canonical_text, require_sha256_hex

_IDENTITY_MAXIMUM_LENGTH = 191
_POLICY_MAXIMUM_LENGTH = 191
_RELEASE_MANIFEST_CONTRACT = "migration-release-manifest/v1"
_DESCRIPTOR_CONTRACT = "migration-owned-object-descriptors/v1"
_ALLOWED_ARGUMENT_TOKENS = frozenset(
    {"{backup}", "{candidate}", "{plan}", "{receipt}"}
)
_FORBIDDEN_ARTIFACT_PATHS = frozenset(
    {"db/schema.sql", "scripts/init_db.py"}
)
_ARTIFACT_KEYS = frozenset(
    {"dependencies", "name", "relative_path", "sha256"}
)
_TOP_LEVEL_KEYS = frozenset(
    {
        "application_compatibility",
        "artifacts",
        "backfills",
        "contract",
        "descriptor_artifact",
        "release_id",
        "release_metadata",
        "source_baseline",
        "tool_archive_policy",
        "verification_contracts",
    }
)


@dataclass(frozen=True, slots=True)
class MigrationArtifact:
    name: str
    relative_path: str
    sha256: str
    dependencies: tuple[str, ...]

    def __post_init__(self) -> None:
        require_canonical_text(self.name, "artifact name", _IDENTITY_MAXIMUM_LENGTH)
        require_canonical_text(
            self.relative_path,
            "artifact relative path",
            _IDENTITY_MAXIMUM_LENGTH,
        )
        require_sha256_hex(self.sha256, "artifact SHA-256")
        _require_unique_canonical_text(self.dependencies, "artifact dependency")


@dataclass(frozen=True, slots=True)
class SchemaMigrationArtifact:
    artifact: MigrationArtifact
    data_effect: str
    resumable_boundary_policy: str
    rollback_policy: str


@dataclass(frozen=True, slots=True)
class BackfillMigration:
    backfill_id: str
    artifact: MigrationArtifact
    dry_run_arguments: tuple[str, ...]
    apply_arguments: tuple[str, ...]
    verify_arguments: tuple[str, ...]
    transaction_boundary: str
    receipt_contract: str
    archive_policy: str


@dataclass(frozen=True, slots=True)
class VerificationContract:
    verification_id: str
    phase: str
    policy: str
    read_only: bool
    blocking: bool


@dataclass(frozen=True, slots=True)
class MigrationReleaseManifest:
    contract: str
    release_id: str
    source_baseline_id: str
    application_compatibility: tuple[str, ...]
    required_restart_targets: tuple[str, ...]
    post_cutover_smoke_ids: tuple[str, ...]
    schema_artifacts: tuple[SchemaMigrationArtifact, ...]
    descriptor_artifact: MigrationArtifact
    backfills: tuple[BackfillMigration, ...]
    verification_contracts: tuple[VerificationContract, ...]
    tool_archive_policies: tuple[str, ...]
    fingerprint: str

    def schema_paths(self, repository_root: Path) -> tuple[Path, ...]:
        return tuple(
            _resolve_artifact_path(repository_root, schema.artifact)
            for schema in self.schema_artifacts
        )

    def protected_artifacts(self) -> tuple[MigrationArtifact, ...]:
        return (
            self.descriptor_artifact,
            *(schema.artifact for schema in self.schema_artifacts),
            *(backfill.artifact for backfill in self.backfills),
        )

    def owned_object_descriptors(
        self,
        repository_root: Path,
    ) -> dict[str, dict[str, Any]]:
        payload = _load_descriptor_payload(self, repository_root)
        return {
            name: _normalize_owned_descriptor(descriptor)
            for name, descriptor in payload["descriptors"].items()
        }


def load_migration_release_manifest(
    manifest_path: Path,
    repository_root: Path,
) -> MigrationReleaseManifest:
    payload = _load_json_object(manifest_path)
    _validate_payload_shape(payload)
    _validate_safety_policies(payload)
    manifest = _build_manifest(payload)
    _validate_manifest_contract(manifest)
    _validate_artifact_dependencies(manifest)
    _validate_artifact_hashes(manifest.protected_artifacts(), repository_root)
    _validate_descriptor_catalog(manifest, repository_root)
    return manifest


def _load_json_object(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("release manifest must not contain a UTF-8 BOM")
    payload = json.loads(raw.decode("utf-8"), parse_constant=_reject_json_constant)
    if not isinstance(payload, dict):
        raise TypeError("release manifest must be a JSON object")
    return payload


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"release manifest contains unsupported constant {value}")


def _validate_payload_shape(payload: dict[str, Any]) -> None:
    _require_exact_keys(payload, _TOP_LEVEL_KEYS, "release manifest")
    _validate_metadata_shape(payload)
    _validate_artifact_shapes(payload)
    _validate_execution_shapes(payload)


def _validate_artifact_shapes(payload: dict[str, Any]) -> None:
    for artifact in payload["artifacts"]:
        _require_exact_keys(
            artifact,
            _ARTIFACT_KEYS
            | {"data_effect", "resumable_boundary_policy", "rollback_policy"},
            "schema artifact",
        )
    _require_exact_keys(
        payload["descriptor_artifact"],
        _ARTIFACT_KEYS,
        "descriptor artifact",
    )


def _validate_execution_shapes(payload: dict[str, Any]) -> None:
    for backfill in payload["backfills"]:
        _validate_backfill_shape(backfill)
    for verification in payload["verification_contracts"]:
        _require_exact_keys(
            verification,
            {"blocking", "phase", "policy", "read_only", "verification_id"},
            "verification contract",
        )


def _validate_metadata_shape(payload: dict[str, Any]) -> None:
    _validate_application_compatibility_shape(
        payload["application_compatibility"]
    )
    _validate_source_baseline_shape(payload["source_baseline"])
    _validate_release_metadata_shape(payload["release_metadata"])
    _validate_tool_archive_shape(payload["tool_archive_policy"])


def _validate_application_compatibility_shape(payload: Any) -> None:
    _require_exact_keys(
        payload,
        {
            "compatible_contracts",
            "minimum_api_contract",
            "post_cutover_smoke_ids",
            "required_restart_targets",
            "watcher_worker_compatibility",
        },
        "application compatibility",
    )


def _validate_source_baseline_shape(payload: Any) -> None:
    _require_exact_keys(
        payload,
        {
            "allowed_owned_object_states",
            "baseline_id",
            "forbidden_owned_object_states",
            "maintenance_token_required",
            "minimum_mysql_version",
            "required_character_set",
            "source_must_be_read_only",
        },
        "source baseline",
    )


def _validate_release_metadata_shape(payload: Any) -> None:
    _require_exact_keys(
        payload,
        {"application_version", "description", "published_at", "release_name"},
        "release metadata",
    )


def _validate_tool_archive_shape(payload: Any) -> None:
    _require_exact_keys(
        payload,
        {
            "artifact_hash_algorithm",
            "backup_archive_policy",
            "journal_archive_policy",
            "mysqldump_required_options",
            "receipt_archive_policy",
            "restore_required_mode",
        },
        "tool archive policy",
    )


def _validate_backfill_shape(payload: Any) -> None:
    _require_exact_keys(
        payload,
        {
            "apply_arguments",
            "archive_policy",
            "artifact",
            "backfill_id",
            "dry_run_arguments",
            "receipt_contract",
            "transaction_boundary",
            "verify_arguments",
        },
        "backfill",
    )
    _require_exact_keys(payload["artifact"], _ARTIFACT_KEYS, "backfill artifact")


def _require_exact_keys(
    payload: Any,
    expected_keys: set[str] | frozenset[str],
    field_name: str,
) -> None:
    if not isinstance(payload, dict):
        raise TypeError(f"{field_name} must be an object")
    if set(payload) != set(expected_keys):
        raise ValueError(f"{field_name} keys do not match the contract")


def _validate_safety_policies(payload: dict[str, Any]) -> None:
    baseline = payload["source_baseline"]
    if baseline["source_must_be_read_only"] is not True:
        raise ValueError("migration source must be read-only")
    if baseline["maintenance_token_required"] is not True:
        raise ValueError("migration maintenance token is required")
    if set(baseline["allowed_owned_object_states"]) != {"absent", "exact"}:
        raise ValueError("source baseline allowed states are unsafe")
    if set(baseline["forbidden_owned_object_states"]) != {"partial", "drift"}:
        raise ValueError("source baseline forbidden states are incomplete")
    _validate_tool_policy(payload["tool_archive_policy"])


def _validate_tool_policy(policy: dict[str, Any]) -> None:
    if policy["artifact_hash_algorithm"] != "sha256":
        raise ValueError("migration artifact hash algorithm must be SHA-256")
    required_dump_options = {
        "--events",
        "--hex-blob",
        "--routines",
        "--single-transaction",
        "--triggers",
    }
    if not required_dump_options.issubset(set(policy["mysqldump_required_options"])):
        raise ValueError("mysqldump safety options are incomplete")


def _build_manifest(payload: dict[str, Any]) -> MigrationReleaseManifest:
    compatibility = payload["application_compatibility"]
    source_baseline = payload["source_baseline"]
    return MigrationReleaseManifest(
        contract=payload["contract"],
        release_id=payload["release_id"],
        source_baseline_id=source_baseline["baseline_id"],
        application_compatibility=tuple(compatibility["compatible_contracts"]),
        required_restart_targets=tuple(compatibility["required_restart_targets"]),
        post_cutover_smoke_ids=tuple(compatibility["post_cutover_smoke_ids"]),
        **_build_manifest_artifact_fields(payload),
        fingerprint=hashlib.sha256(_canonical_json(payload)).hexdigest(),
    )


def _build_manifest_artifact_fields(
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_artifacts": tuple(
            _build_schema_artifact(item) for item in payload["artifacts"]
        ),
        "descriptor_artifact": _build_artifact(payload["descriptor_artifact"]),
        "backfills": tuple(_build_backfill(item) for item in payload["backfills"]),
        "verification_contracts": tuple(
            _build_verification(item)
            for item in payload["verification_contracts"]
        ),
        "tool_archive_policies": _build_tool_archive_policies(
            payload["tool_archive_policy"]
        ),
    }


def _build_tool_archive_policies(payload: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        f"{key}:{value}"
        for key, value in sorted(payload.items())
        if isinstance(value, str)
    )


def _build_artifact(payload: Any) -> MigrationArtifact:
    if not isinstance(payload, dict):
        raise TypeError("migration artifact must be a JSON object")
    return MigrationArtifact(
        name=payload["name"],
        relative_path=payload["relative_path"],
        sha256=payload["sha256"],
        dependencies=tuple(payload["dependencies"]),
    )


def _build_schema_artifact(payload: Any) -> SchemaMigrationArtifact:
    return SchemaMigrationArtifact(
        artifact=_build_artifact(payload),
        data_effect=payload["data_effect"],
        resumable_boundary_policy=payload["resumable_boundary_policy"],
        rollback_policy=payload["rollback_policy"],
    )


def _build_backfill(payload: Any) -> BackfillMigration:
    return BackfillMigration(
        backfill_id=payload["backfill_id"],
        artifact=_build_artifact(payload["artifact"]),
        dry_run_arguments=tuple(payload["dry_run_arguments"]),
        apply_arguments=tuple(payload["apply_arguments"]),
        verify_arguments=tuple(payload["verify_arguments"]),
        transaction_boundary=payload["transaction_boundary"],
        receipt_contract=payload["receipt_contract"],
        archive_policy=payload["archive_policy"],
    )


def _build_verification(payload: Any) -> VerificationContract:
    return VerificationContract(
        verification_id=payload["verification_id"],
        phase=payload["phase"],
        policy=payload["policy"],
        read_only=payload["read_only"],
        blocking=payload["blocking"],
    )


def _validate_manifest_contract(manifest: MigrationReleaseManifest) -> None:
    if manifest.contract != _RELEASE_MANIFEST_CONTRACT:
        raise ValueError("unsupported release manifest contract")
    require_canonical_text(
        manifest.release_id,
        "release id",
        _IDENTITY_MAXIMUM_LENGTH,
    )
    require_canonical_text(
        manifest.source_baseline_id,
        "source baseline id",
        _POLICY_MAXIMUM_LENGTH,
    )
    _validate_manifest_policy_sets(manifest)
    _validate_schema_contracts(manifest.schema_artifacts)
    _validate_backfills(manifest.backfills)
    _validate_verifications(manifest.verification_contracts)
    if not manifest.schema_artifacts:
        raise ValueError("release manifest must contain artifacts")


def _validate_manifest_policy_sets(
    manifest: MigrationReleaseManifest,
) -> None:
    _require_unique_canonical_text(
        manifest.application_compatibility,
        "application compatibility",
    )
    _require_unique_canonical_text(
        manifest.required_restart_targets,
        "restart target",
    )
    _require_unique_canonical_text(
        manifest.post_cutover_smoke_ids,
        "post-cutover smoke id",
    )
    _require_unique_canonical_text(
        manifest.tool_archive_policies,
        "tool archive policy",
    )


def _require_unique_canonical_text(
    values: tuple[str, ...],
    field_name: str,
) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{field_name} values must be a tuple")
    for value in values:
        require_canonical_text(value, field_name, _POLICY_MAXIMUM_LENGTH)
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} values must be unique")


def _validate_artifact_dependencies(manifest: MigrationReleaseManifest) -> None:
    prior_names: set[str] = set()
    for schema in manifest.schema_artifacts:
        artifact = schema.artifact
        if artifact.name in prior_names:
            raise ValueError("migration artifact names must be unique")
        if not set(artifact.dependencies).issubset(prior_names):
            raise ValueError("artifact dependency must reference an earlier artifact")
        prior_names.add(artifact.name)
    for backfill in manifest.backfills:
        if not set(backfill.artifact.dependencies).issubset(prior_names):
            raise ValueError("backfill dependency must reference a schema artifact")


def _validate_schema_contracts(
    schemas: tuple[SchemaMigrationArtifact, ...],
) -> None:
    for schema in schemas:
        _validate_artifact_path_policy(schema.artifact)
        require_canonical_text(
            schema.data_effect,
            "schema data effect",
            _POLICY_MAXIMUM_LENGTH,
        )
        require_canonical_text(
            schema.resumable_boundary_policy,
            "resumable boundary policy",
            _POLICY_MAXIMUM_LENGTH,
        )
        require_canonical_text(
            schema.rollback_policy,
            "schema rollback policy",
            _POLICY_MAXIMUM_LENGTH,
        )


def _validate_backfills(backfills: tuple[BackfillMigration, ...]) -> None:
    identifiers: list[str] = []
    for backfill in backfills:
        identifiers.append(backfill.backfill_id)
        _validate_artifact_path_policy(backfill.artifact)
        _validate_backfill_text(backfill)
        _validate_backfill_arguments(backfill)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("backfill identities must be unique")


def _validate_backfill_text(backfill: BackfillMigration) -> None:
    for value, field_name in (
        (backfill.backfill_id, "backfill id"),
        (backfill.transaction_boundary, "backfill transaction boundary"),
        (backfill.receipt_contract, "backfill receipt contract"),
        (backfill.archive_policy, "backfill archive policy"),
    ):
        require_canonical_text(value, field_name, _POLICY_MAXIMUM_LENGTH)


def _validate_backfill_arguments(backfill: BackfillMigration) -> None:
    argument_sets = (
        backfill.dry_run_arguments,
        backfill.apply_arguments,
        backfill.verify_arguments,
    )
    for arguments in argument_sets:
        for argument in arguments:
            require_canonical_text(argument, "backfill argument", _POLICY_MAXIMUM_LENGTH)
            if argument.startswith("{") and argument not in _ALLOWED_ARGUMENT_TOKENS:
                raise ValueError("unsupported backfill argument token")


def _validate_verifications(
    contracts: tuple[VerificationContract, ...],
) -> None:
    identifiers: list[str] = []
    for contract in contracts:
        identifiers.append(contract.verification_id)
        _validate_verification(contract)
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("verification identities must be unique")


def _validate_verification(contract: VerificationContract) -> None:
    for value, field_name in (
        (contract.verification_id, "verification id"),
        (contract.phase, "verification phase"),
        (contract.policy, "verification policy"),
    ):
        require_canonical_text(value, field_name, _POLICY_MAXIMUM_LENGTH)
    if contract.read_only is not True or contract.blocking is not True:
        raise ValueError("release verifications must be read-only and blocking")


def _validate_artifact_path_policy(artifact: MigrationArtifact) -> None:
    normalized_path = Path(artifact.relative_path).as_posix()
    if Path(normalized_path).is_absolute():
        raise ValueError("artifact path must be repository-relative")
    if normalized_path in _FORBIDDEN_ARTIFACT_PATHS:
        raise ValueError("bootstrap artifact is forbidden in preserve-data release")


def _validate_artifact_hashes(
    artifacts: tuple[MigrationArtifact, ...],
    repository_root: Path,
) -> None:
    for artifact in artifacts:
        artifact_path = _resolve_artifact_path(repository_root, artifact)
        actual_digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        if actual_digest != artifact.sha256:
            raise ValueError(f"artifact digest mismatch: {artifact.name}")


def _validate_descriptor_catalog(
    manifest: MigrationReleaseManifest,
    repository_root: Path,
) -> None:
    payload = _load_descriptor_payload(manifest, repository_root)
    if payload.get("contract") != _DESCRIPTOR_CONTRACT:
        raise ValueError("unsupported owned-object descriptor contract")
    descriptors = payload.get("descriptors")
    if not isinstance(descriptors, dict):
        raise TypeError("owned-object descriptors must be an object")
    schema_names = {schema.artifact.name for schema in manifest.schema_artifacts}
    if set(descriptors) != schema_names:
        raise ValueError("owned-object descriptors must cover every schema artifact")
    _validate_descriptor_shapes(descriptors)


def _load_descriptor_payload(
    manifest: MigrationReleaseManifest,
    repository_root: Path,
) -> dict[str, Any]:
    descriptor_path = _resolve_artifact_path(
        repository_root,
        manifest.descriptor_artifact,
    )
    return _load_json_object(descriptor_path)


def _validate_descriptor_shapes(descriptors: dict[str, Any]) -> None:
    for descriptor in descriptors.values():
        if not isinstance(descriptor, dict):
            raise TypeError("owned-object descriptor must be an object")
        if not {"tables", "triggers"} <= set(descriptor) <= {
            "tables", "triggers", "views"
        }:
            raise ValueError("owned-object descriptor keys are invalid")
        if not isinstance(descriptor["tables"], dict):
            raise TypeError("owned tables must be an object")
        if not isinstance(descriptor["triggers"], list):
            raise TypeError("owned triggers must be a list")
        _validate_owned_view_contracts(descriptor.get("views", {}))


def _validate_owned_view_contracts(views: Any) -> None:
    if not isinstance(views, dict):
        raise TypeError("owned views must be an object")
    for view_name, contract in views.items():
        require_canonical_text(str(view_name), "owned view name", _IDENTITY_MAXIMUM_LENGTH)
        if not isinstance(contract, dict) or set(contract) != {"definition_sha256"}:
            raise ValueError("owned view contract is invalid")
        require_sha256_hex(contract["definition_sha256"], "owned view definition SHA-256")


def _normalize_owned_descriptor(
    descriptor: dict[str, Any],
) -> dict[str, Any]:
    return {
        "tables": {
            table_name: set(columns)
            for table_name, columns in descriptor["tables"].items()
        },
        "triggers": set(descriptor["triggers"]),
        "views": {
            str(view_name): dict(contract)
            for view_name, contract in descriptor.get("views", {}).items()
        },
    }


def _resolve_artifact_path(
    repository_root: Path,
    artifact: MigrationArtifact,
) -> Path:
    resolved_root = repository_root.resolve()
    artifact_path = (resolved_root / artifact.relative_path).resolve()
    if not artifact_path.is_relative_to(resolved_root):
        raise ValueError("artifact path escapes repository root")
    if not artifact_path.is_file():
        raise ValueError(f"migration artifact is missing: {artifact.name}")
    return artifact_path


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
