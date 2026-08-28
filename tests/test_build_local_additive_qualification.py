"""
File: test_build_local_additive_qualification.py
Description: 驗證 qualification builder 的決定性輸出、證據防竄改、零寫入 preview 與 atomic publish 邊界。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import build_local_additive_qualification as builder
from scripts import migrate_preserved_database_additive_schema as migration


def _inputs() -> tuple[str, str, dict, dict, dict]:
    entry = migration._local_ordered_upgrade_entries()[1]
    release_id = entry["release_id"]
    artifact_name = entry["artifact"]["name"]
    identity = builder._canonical_identity(release_id, artifact_name)
    common = {
        "status": "verified",
        "release_id": release_id,
        "artifact_name": artifact_name,
        "release_fingerprint": identity["release_fingerprint"],
        "published_manifest_sha256": identity["published_manifest_sha256"],
        "artifact_sql_sha256": identity["artifact_sql_sha256"],
        "descriptor_sha256": identity["descriptor_sha256"],
        "backfills": [],
    }
    rows = {"orders": 3, "staff": 2}
    fingerprints = {"orders": "1" * 64, "staff": "2" * 64}
    metadata = {
        **common,
        "contract": "local-additive-metadata-backup-evidence/v1",
        "schema_fingerprint": "3" * 64,
        "backup_dump_sha256": "9" * 64,
        "data_row_counts": rows,
        "data_fingerprints": fingerprints,
    }
    fresh = {
        **common,
        "contract": "local-additive-fresh-bootstrap-evidence/v1",
        "schema_fingerprint": "4" * 64,
        "target_descriptor_state": "exact",
        "target_projection": identity["canonical_projection"],
        "target_projection_fingerprint": identity["canonical_projection_fingerprint"],
        "data_rows_written": 0,
    }
    preserve = {
        **common,
        "contract": "local-additive-preserve-data-evidence/v1",
        "source_schema_fingerprint": "3" * 64,
        "candidate_schema_fingerprint": "6" * 64,
        "source_dump_sha256": "7" * 64,
        "candidate_dump_sha256": "8" * 64,
        "source_data_row_counts": rows,
        "source_data_fingerprints": fingerprints,
        "candidate_data_row_counts": rows,
        "candidate_data_fingerprints": fingerprints,
        "target_descriptor_state": "exact",
        "target_projection": identity["canonical_projection"],
        "target_projection_fingerprint": identity["canonical_projection_fingerprint"],
    }
    return release_id, artifact_name, metadata, fresh, preserve


def _build(metadata=None, fresh=None, preserve=None):
    release_id, artifact_name, default_metadata, default_fresh, default_preserve = _inputs()
    return builder.build_qualification(
        release_id=release_id,
        artifact_name=artifact_name,
        metadata_backup=metadata or default_metadata,
        fresh_bootstrap=fresh or default_fresh,
        preserve_data_candidate=preserve or default_preserve,
        work_package="LDU-1003-CURRENT-01",
    )


def test_same_input_builds_same_validator_accepted_payload(tmp_path: Path) -> None:
    first = _build()
    second = _build()
    assert first == second
    assert first["payload_digest"] == migration._local_payload_digest(first)
    path = tmp_path / "qualification.json"
    path.write_bytes(builder._serialized(first))
    validated = migration._local_validate_qualification(path)
    assert validated["release_id"] == first["release_id"]
    assert validated["artifact"]["name"] == first["artifact"]["name"]


@pytest.mark.parametrize(
    ("evidence_name", "field", "value"),
    (
        ("metadata", "status", "draft"),
        ("metadata", "release_id", "wrong-release"),
        ("fresh", "artifact_name", "wrong.sql"),
        ("fresh", "published_manifest_sha256", "0" * 64),
        ("preserve", "artifact_sql_sha256", "0" * 64),
        ("preserve", "descriptor_sha256", "0" * 64),
        ("preserve", "target_descriptor_state", "partial"),
        ("preserve", "backfills", [{"id": "forbidden"}]),
    ),
)
def test_identity_status_target_and_backfill_tampering_fails_closed(
    evidence_name: str, field: str, value
) -> None:
    _, _, metadata, fresh, preserve = _inputs()
    selected = {"metadata": metadata, "fresh": fresh, "preserve": preserve}[evidence_name]
    selected[field] = value
    with pytest.raises(builder.QualificationBuilderError):
        _build(metadata, fresh, preserve)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("candidate_data_row_counts", {"orders": 4, "staff": 2}),
        ("candidate_data_fingerprints", {"orders": "9" * 64, "staff": "2" * 64}),
        ("target_projection_fingerprint", "9" * 64),
        ("source_dump_sha256", "not-a-hash"),
    ),
)
def test_preserve_rows_projection_and_dump_tampering_fails_closed(field: str, value) -> None:
    _, _, metadata, fresh, preserve = _inputs()
    preserve[field] = value
    with pytest.raises(builder.QualificationBuilderError):
        _build(metadata, fresh, preserve)


def test_matching_tampered_target_projections_fail_closed() -> None:
    _, _, metadata, fresh, preserve = _inputs()
    tampered = {"tables": {"invented_secret_table": ["password"]}}
    fingerprint = migration._local_digest(migration._local_canonical_json(tampered))
    fresh["target_projection"] = tampered
    fresh["target_projection_fingerprint"] = fingerprint
    preserve["target_projection"] = tampered
    preserve["target_projection_fingerprint"] = fingerprint
    with pytest.raises(builder.QualificationBuilderError, match="not canonical"):
        _build(metadata, fresh, preserve)


def test_boolean_zero_and_noncanonical_table_fail_closed() -> None:
    _, _, metadata, fresh, preserve = _inputs()
    fresh["data_rows_written"] = False
    with pytest.raises(builder.QualificationBuilderError):
        _build(metadata, fresh, preserve)
    fresh["data_rows_written"] = 0
    metadata["data_row_counts"]["password_dump"] = 1
    metadata["data_fingerprints"]["password_dump"] = "a" * 64
    preserve["source_data_row_counts"]["password_dump"] = 1
    preserve["source_data_fingerprints"]["password_dump"] = "a" * 64
    preserve["candidate_data_row_counts"]["password_dump"] = 1
    preserve["candidate_data_fingerprints"]["password_dump"] = "a" * 64
    with pytest.raises(builder.QualificationBuilderError, match="non-canonical table"):
        _build(metadata, fresh, preserve)


def test_canonical_base_schema_tables_are_allowed() -> None:
    identity = builder._canonical_identity(*_inputs()[:2])
    assert {
        "orders",
        "staff",
        "caregiver_matching_plans",
        "staff_leave_requests",
        "finance_import_batches",
    } <= identity["allowed_tables"]
    assert "password_dump" not in identity["allowed_tables"]


def test_unknown_evidence_fields_are_rejected_to_avoid_secret_copying() -> None:
    _, _, metadata, fresh, preserve = _inputs()
    metadata["password"] = "must-not-copy"
    with pytest.raises(builder.QualificationBuilderError, match="unexpected"):
        _build(metadata, fresh, preserve)


def test_preview_writes_only_stdout(tmp_path: Path, capsys) -> None:
    release_id, artifact_name, metadata, fresh, preserve = _inputs()
    paths = {}
    for name, value in (("metadata", metadata), ("fresh", fresh), ("preserve", preserve)):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        paths[name] = path
    before = sorted(tmp_path.iterdir())
    assert builder.main([
        "--release-id", release_id,
        "--artifact", artifact_name,
        "--metadata-backup", str(paths["metadata"]),
        "--fresh", str(paths["fresh"]),
        "--preserve", str(paths["preserve"]),
        "--work-package", "LDU-1003-CURRENT-01",
    ]) == 0
    assert sorted(tmp_path.iterdir()) == before
    assert json.loads(capsys.readouterr().out)["payload_digest"] == _build()["payload_digest"]


def test_publish_is_new_atomic_file_and_round_trips(monkeypatch, tmp_path: Path) -> None:
    receipt_root = tmp_path / "validation" / "receipts"
    monkeypatch.setattr(builder, "RECEIPT_ROOT", receipt_root)
    target = receipt_root / "PROV-test-local-additive-qualification-1004.json"
    payload = _build()
    assert builder.publish_qualification(payload, target) == target.resolve()
    assert migration._local_validate_qualification(target)["payload_digest"] == payload["payload_digest"]
    assert list(receipt_root.glob(".qualification-*.json")) == []
    with pytest.raises(builder.QualificationBuilderError, match="already exists"):
        builder.publish_qualification(payload, target)


def test_publish_rejects_wrong_directory_or_filename(monkeypatch, tmp_path: Path) -> None:
    receipt_root = tmp_path / "validation" / "receipts"
    monkeypatch.setattr(builder, "RECEIPT_ROOT", receipt_root)
    payload = _build()
    for target in (
        tmp_path / "PROV-test-local-additive-qualification-1004.json",
        receipt_root / "qualification.json",
        receipt_root / "nested" / "PROV-test-local-additive-qualification-1004.json",
    ):
        with pytest.raises(builder.QualificationBuilderError, match="publish path"):
            builder.publish_qualification(payload, target)


def test_publish_rejects_hand_built_or_copied_payload(monkeypatch, tmp_path: Path) -> None:
    receipt_root = tmp_path / "validation" / "receipts"
    monkeypatch.setattr(builder, "RECEIPT_ROOT", receipt_root)
    target = receipt_root / "PROV-test-local-additive-qualification-1004.json"
    with pytest.raises(builder.QualificationBuilderError, match="build_qualification"):
        builder.publish_qualification(dict(_build()), target)


def test_publish_rejects_direct_constructor_and_mutated_build_result(
    monkeypatch, tmp_path: Path
) -> None:
    receipt_root = tmp_path / "validation" / "receipts"
    monkeypatch.setattr(builder, "RECEIPT_ROOT", receipt_root)
    target = receipt_root / "PROV-test-local-additive-qualification-1004.json"
    with pytest.raises(builder.QualificationBuilderError, match="requires the builder"):
        builder._QualificationPayload(dict(_build()), token=object())
    payload = _build()
    payload["secret"] = "must-not-publish"
    with pytest.raises(builder.QualificationBuilderError, match="build_qualification"):
        builder.publish_qualification(payload, target)


def test_strict_json_reader_rejects_bom_non_object_and_invalid_utf8(tmp_path: Path) -> None:
    for index, content in enumerate((b"\xef\xbb\xbf{}", b"[]", b"\xff")):
        path = tmp_path / f"bad-{index}.json"
        path.write_bytes(content)
        with pytest.raises(builder.QualificationBuilderError):
            builder._read_json_object(path)


def test_strict_json_reader_rejects_duplicate_keys(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"status":"verified","status":"draft"}', encoding="utf-8")
    with pytest.raises(builder.QualificationBuilderError, match="duplicate"):
        builder._read_json_object(path)
