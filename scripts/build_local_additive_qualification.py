"""
File: build_local_additive_qualification.py
Description: 由三份已驗證引擎證據決定性建立本機 additive qualification，並在發布前以現行 validator 複驗。
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping, Sequence

from scripts import migrate_preserved_database_additive_schema as migration
from scripts.schema_assembly import load_schema_assembly


RECEIPT_ROOT = migration.ROOT / "validation" / "receipts"
PUBLISH_NAME = re.compile(
    r"PROV-[A-Za-z0-9][A-Za-z0-9._-]*-local-additive-qualification-"
    r"[A-Za-z0-9][A-Za-z0-9._-]*\.json"
)
SHA256 = re.compile(r"[0-9a-f]{64}")
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

_COMMON_KEYS = {
    "contract",
    "status",
    "release_id",
    "artifact_name",
    "release_fingerprint",
    "published_manifest_sha256",
    "artifact_sql_sha256",
    "descriptor_sha256",
    "backfills",
}
_EVIDENCE_KEYS = {
    "metadata_backup": _COMMON_KEYS
    | {
        "schema_fingerprint",
        "backup_dump_sha256",
        "data_row_counts",
        "data_fingerprints",
    },
    "fresh_bootstrap": _COMMON_KEYS
    | {
        "schema_fingerprint",
        "target_descriptor_state",
        "target_projection",
        "target_projection_fingerprint",
        "data_rows_written",
    },
    "preserve_data_candidate": _COMMON_KEYS
    | {
        "source_schema_fingerprint",
        "candidate_schema_fingerprint",
        "source_dump_sha256",
        "candidate_dump_sha256",
        "source_data_row_counts",
        "source_data_fingerprints",
        "candidate_data_row_counts",
        "candidate_data_fingerprints",
        "target_descriptor_state",
        "target_projection",
        "target_projection_fingerprint",
    },
}
_EVIDENCE_CONTRACTS = {
    "metadata_backup": "local-additive-metadata-backup-evidence/v1",
    "fresh_bootstrap": "local-additive-fresh-bootstrap-evidence/v1",
    "preserve_data_candidate": "local-additive-preserve-data-evidence/v1",
}


class QualificationBuilderError(ValueError):
    """表示輸入證據或發布邊界不符合 qualification builder 契約。"""


_BUILDER_TOKEN = object()


class _QualificationPayload(dict[str, Any]):
    """只由本模組 build path 建立、可交給 publish path 的 process-local payload。"""

    def __init__(self, value: Mapping[str, Any], *, token: object) -> None:
        if token is not _BUILDER_TOKEN:
            raise QualificationBuilderError("qualification payload requires the builder")
        super().__init__(value)
        self._builder_token = _BUILDER_TOKEN
        self._built_digest = migration._local_payload_digest(self)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise QualificationBuilderError(f"duplicate evidence JSON key: {key}")
        result[key] = value
    return result


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        raw = Path(path).read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raise QualificationBuilderError("evidence JSON must not contain a UTF-8 BOM")
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys
        )
    except QualificationBuilderError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise QualificationBuilderError("evidence JSON is not strict UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise QualificationBuilderError("evidence JSON must be an object")
    return value


def _require_sha256(value: Any, field: str) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise QualificationBuilderError(f"{field} must be a lowercase SHA-256")
    return value


def _require_rows(value: Any, field: str) -> dict[str, int]:
    if not isinstance(value, Mapping) or not value:
        raise QualificationBuilderError(f"{field} must be a non-empty object")
    rows: dict[str, int] = {}
    for name, count in value.items():
        if (
            not isinstance(name, str)
            or IDENTIFIER.fullmatch(name) is None
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
        ):
            raise QualificationBuilderError(f"{field} contains an invalid table count")
        rows[name] = count
    return dict(sorted(rows.items()))


def _require_fingerprints(value: Any, field: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise QualificationBuilderError(f"{field} must be a non-empty object")
    fingerprints: dict[str, str] = {}
    for name, fingerprint in value.items():
        if not isinstance(name, str) or IDENTIFIER.fullmatch(name) is None:
            raise QualificationBuilderError(f"{field} contains an invalid table name")
        fingerprints[name] = _require_sha256(fingerprint, field)
    return dict(sorted(fingerprints.items()))


IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,63}")
CREATE_TABLE = re.compile(
    r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?([A-Za-z][A-Za-z0-9_]*)`?",
    re.IGNORECASE,
)


def _json_projection(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _json_projection(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (set, frozenset)):
        return sorted(_json_projection(item) for item in value)
    if isinstance(value, (list, tuple)):
        return [_json_projection(item) for item in value]
    return value


def _canonical_table_inventory() -> frozenset[str]:
    assembly = load_schema_assembly()
    paths = (assembly.base_schema_path, *assembly.active_artifact_paths)
    tables: set[str] = set()
    for path in paths:
        try:
            sql = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise QualificationBuilderError(
                "canonical schema inventory is unreadable"
            ) from error
        tables.update(name.casefold() for name in CREATE_TABLE.findall(sql))
    if not tables:
        raise QualificationBuilderError("canonical schema table inventory is empty")
    return frozenset(tables)


def _canonical_identity(release_id: str, artifact_name: str) -> dict[str, Any]:
    qualification = migration.local_additive_release_qualification(release_id, artifact_name)
    artifacts = qualification.get("schema_artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 1:
        raise QualificationBuilderError("release/artifact does not select one canonical schema artifact")
    artifact = artifacts[0]
    manifests = tuple(
        item for item in migration.RELEASE_MANIFEST.manifests
        if item.release_id == release_id
    )
    if len(manifests) != 1:
        raise QualificationBuilderError("release does not select one canonical manifest")
    manifest = manifests[0]
    manifest_path = migration._local_manifest_path(release_id)
    fresh_manifest = migration.load_migration_release_manifest(
        manifest_path, migration.ROOT
    )
    if fresh_manifest.fingerprint != manifest.fingerprint:
        raise QualificationBuilderError("canonical manifest changed after runner import")
    descriptor_sha256 = manifest.descriptor_artifact.sha256
    if artifact.get("data_effect") != "schema_only" or qualification.get("backfills") != []:
        raise QualificationBuilderError("release is not a schema-only zero-backfill qualification")
    canonical_projection = _json_projection(
        manifest.owned_object_descriptors(migration.ROOT)[artifact_name]
    )
    canonical_projection_fingerprint = migration._local_digest(
        migration._local_canonical_json(canonical_projection)
    )
    allowed_tables = _canonical_table_inventory()
    return {
        "release_id": release_id,
        "artifact_name": artifact_name,
        "release_fingerprint": qualification["release_fingerprint"],
        "published_manifest_sha256": migration._sha256_file(manifest_path),
        "artifact_sql_sha256": artifact["sha256"],
        "descriptor_sha256": descriptor_sha256,
        "manifest_artifact_inventory": migration._local_manifest_inventory(manifest),
        "artifact": artifact,
        "canonical_projection": canonical_projection,
        "canonical_projection_fingerprint": canonical_projection_fingerprint,
        "allowed_tables": allowed_tables,
    }


def _validate_evidence(
    kind: str,
    payload: dict[str, Any],
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    expected_keys = _EVIDENCE_KEYS[kind]
    if set(payload) != expected_keys:
        missing = sorted(expected_keys - set(payload))
        unexpected = sorted(set(payload) - expected_keys)
        raise QualificationBuilderError(
            f"{kind} evidence keys differ; missing={missing}, unexpected={unexpected}"
        )
    if payload["contract"] != _EVIDENCE_CONTRACTS[kind] or payload["status"] != "verified":
        raise QualificationBuilderError(f"{kind} must be final verified evidence")
    for field in (
        "release_id",
        "artifact_name",
        "release_fingerprint",
        "published_manifest_sha256",
        "artifact_sql_sha256",
        "descriptor_sha256",
    ):
        if payload[field] != identity[field]:
            raise QualificationBuilderError(f"{kind} {field} differs from canonical identity")
    if payload["backfills"] != []:
        raise QualificationBuilderError(f"{kind} backfills must be empty")
    for field in (
        "release_fingerprint",
        "published_manifest_sha256",
        "artifact_sql_sha256",
        "descriptor_sha256",
    ):
        _require_sha256(payload[field], f"{kind}.{field}")
    return payload


def build_qualification(
    *,
    release_id: str,
    artifact_name: str,
    metadata_backup: Mapping[str, Any],
    fresh_bootstrap: Mapping[str, Any],
    preserve_data_candidate: Mapping[str, Any],
    work_package: str,
) -> dict[str, Any]:
    """建立 deterministic qualification payload，不讀寫資料庫或 receipt。"""
    if SAFE_ID.fullmatch(work_package) is None:
        raise QualificationBuilderError("work_package must be a non-secret stable identifier")
    identity = _canonical_identity(release_id, artifact_name)
    metadata = _validate_evidence("metadata_backup", dict(metadata_backup), identity)
    fresh = _validate_evidence("fresh_bootstrap", dict(fresh_bootstrap), identity)
    preserve = _validate_evidence(
        "preserve_data_candidate", dict(preserve_data_candidate), identity
    )

    metadata_schema = _require_sha256(metadata["schema_fingerprint"], "metadata schema_fingerprint")
    backup_dump = _require_sha256(
        metadata["backup_dump_sha256"], "metadata backup_dump_sha256"
    )
    fresh_schema = _require_sha256(fresh["schema_fingerprint"], "fresh schema_fingerprint")
    source_schema = _require_sha256(
        preserve["source_schema_fingerprint"], "preserve source_schema_fingerprint"
    )
    candidate_schema = _require_sha256(
        preserve["candidate_schema_fingerprint"], "preserve candidate_schema_fingerprint"
    )
    source_dump = _require_sha256(preserve["source_dump_sha256"], "source_dump_sha256")
    candidate_dump = _require_sha256(
        preserve["candidate_dump_sha256"], "candidate_dump_sha256"
    )
    metadata_counts = _require_rows(metadata["data_row_counts"], "metadata data_row_counts")
    metadata_fingerprints = _require_fingerprints(
        metadata["data_fingerprints"], "metadata data_fingerprints"
    )
    source_counts = _require_rows(
        preserve["source_data_row_counts"], "preserve source_data_row_counts"
    )
    source_fingerprints = _require_fingerprints(
        preserve["source_data_fingerprints"], "preserve source_data_fingerprints"
    )
    candidate_counts = _require_rows(
        preserve["candidate_data_row_counts"], "preserve candidate_data_row_counts"
    )
    candidate_fingerprints = _require_fingerprints(
        preserve["candidate_data_fingerprints"], "preserve candidate_data_fingerprints"
    )
    evidence_tables = set(metadata_counts) | set(metadata_fingerprints)
    if not evidence_tables <= identity["allowed_tables"]:
        raise QualificationBuilderError("row evidence contains a non-canonical table")
    if not (
        metadata_schema == source_schema
        and metadata_counts == source_counts == candidate_counts
        and metadata_fingerprints == source_fingerprints == candidate_fingerprints
        and set(metadata_counts) == set(metadata_fingerprints)
    ):
        raise QualificationBuilderError("source/candidate row or source schema evidence differs")
    if isinstance(fresh["data_rows_written"], bool) or fresh["data_rows_written"] != 0:
        raise QualificationBuilderError("fresh bootstrap must write zero data rows")
    if fresh["target_descriptor_state"] != "exact" or preserve["target_descriptor_state"] != "exact":
        raise QualificationBuilderError("fresh and preserve target descriptors must be exact")
    canonical_projection = identity["canonical_projection"]
    if (
        fresh["target_projection"] != canonical_projection
        or preserve["target_projection"] != canonical_projection
    ):
        raise QualificationBuilderError("fresh or preserve target projection is not canonical")
    fresh_target = _require_sha256(
        fresh["target_projection_fingerprint"], "fresh target_projection_fingerprint"
    )
    preserve_target = _require_sha256(
        preserve["target_projection_fingerprint"], "preserve target_projection_fingerprint"
    )
    if (
        fresh_target != identity["canonical_projection_fingerprint"]
        or preserve_target != identity["canonical_projection_fingerprint"]
    ):
        raise QualificationBuilderError("fresh and preserve target projections differ")

    artifact = identity["artifact"]
    payload: dict[str, Any] = {
        "contract": "local-additive-qualification/v1",
        "work_package": work_package,
        "release_id": release_id,
        "release_fingerprint": identity["release_fingerprint"],
        "published_manifest_sha256": identity["published_manifest_sha256"],
        "manifest_artifact_inventory": identity["manifest_artifact_inventory"],
        "artifact": {
            "name": artifact_name,
            "sql_sha256": identity["artifact_sql_sha256"],
            "descriptor_sha256": identity["descriptor_sha256"],
            "data_effect": "schema_only",
            "dependencies": list(artifact.get("dependencies", ())),
        },
        "metadata_backup": {
            "status": "verified",
            "schema_sha256": metadata_schema,
            "backup_dump_sha256": backup_dump,
            "data_row_counts": metadata_counts,
            "data_fingerprints": metadata_fingerprints,
            "data_fingerprint_sha256": migration._local_data_fingerprint(
                metadata_fingerprints
            ),
        },
        "fresh_bootstrap": {
            "status": "verified",
            "schema_fingerprint": fresh_schema,
            "data_rows_written": 0,
            "target_descriptor_state": "exact",
            "target_projection_fingerprint": fresh_target,
        },
        "preserve_data_candidate": {
            "status": "verified",
            "source_schema_fingerprint": source_schema,
            "candidate_schema_fingerprint": candidate_schema,
            "source_dump_sha256": source_dump,
            "candidate_dump_sha256": candidate_dump,
            "data_row_counts": source_counts,
            "data_fingerprints": source_fingerprints,
            "candidate_data_row_counts": candidate_counts,
            "candidate_data_fingerprints": candidate_fingerprints,
            "target_descriptor_state": "exact",
            "target_projection_fingerprint": preserve_target,
        },
        "target_projection": {
            "contract": "local-additive-target-projection/v1",
            "artifact_name": artifact_name,
            "descriptor_sha256": identity["descriptor_sha256"],
            "fresh_state": "exact",
            "preserve_candidate_state": "exact",
            "fresh_fingerprint": fresh_target,
            "preserve_candidate_fingerprint": preserve_target,
        },
        "policy_evidence": {
            "fresh_schema_fingerprint": fresh_schema,
            "preserve_source_schema_fingerprint": source_schema,
            "preserve_candidate_schema_fingerprint": candidate_schema,
            "source_dump_sha256": source_dump,
            "candidate_dump_sha256": candidate_dump,
            "fresh_target_projection_fingerprint": fresh_target,
            "preserve_candidate_target_projection_fingerprint": preserve_target,
        },
        "policy": {
            "local_in_place_eligible": True,
            "seed": 0,
            "backfill": 0,
            "destructive": 0,
        },
    }
    payload["payload_digest"] = migration._local_payload_digest(payload)
    return _QualificationPayload(payload, token=_BUILDER_TOKEN)


def _serialized(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def publish_qualification(payload: Mapping[str, Any], destination: Path) -> Path:
    """先以 current validator round-trip，再以同檔案系統 atomic create 發布新 receipt。"""
    if (
        not isinstance(payload, _QualificationPayload)
        or getattr(payload, "_builder_token", None) is not _BUILDER_TOKEN
        or getattr(payload, "_built_digest", None)
        != migration._local_payload_digest(payload)
    ):
        raise QualificationBuilderError("publish requires a payload from build_qualification")
    root = RECEIPT_ROOT.resolve()
    target = Path(destination).expanduser().resolve()
    if target.parent != root or PUBLISH_NAME.fullmatch(target.name) is None:
        raise QualificationBuilderError(
            "publish path must be a PROV-*-local-additive-qualification-*.json file in validation/receipts"
        )
    root.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".qualification-", suffix=".json", dir=root, delete=False
        ) as handle:
            temporary = Path(handle.name)
            handle.write(_serialized(payload))
            handle.flush()
            os.fsync(handle.fileno())
        migration._local_validate_qualification(temporary)
        try:
            os.link(temporary, target)
        except FileExistsError as error:
            raise QualificationBuilderError("publish target already exists") from error
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build one local additive qualification receipt")
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--metadata-backup", type=Path, required=True)
    parser.add_argument("--fresh", type=Path, required=True)
    parser.add_argument("--preserve", type=Path, required=True)
    parser.add_argument("--work-package", required=True)
    parser.add_argument("--publish", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    payload = build_qualification(
        release_id=args.release_id,
        artifact_name=args.artifact,
        metadata_backup=_read_json_object(args.metadata_backup),
        fresh_bootstrap=_read_json_object(args.fresh),
        preserve_data_candidate=_read_json_object(args.preserve),
        work_package=args.work_package,
    )
    if args.publish is not None:
        publish_qualification(payload, args.publish)
    print(_serialized(payload).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
