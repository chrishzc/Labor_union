from __future__ import annotations

import hashlib
import json

import pytest

from scripts.migrate_order_lifecycle_control_facts import (
    _dataset_fingerprint,
    classify_legacy_rows,
    run_migration,
    validate_backup,
    validate_plan,
)


def test_classify_legacy_rows_bootstraps_only_cancelled_rows_with_reason():
    bootstrappable, review_required = classify_legacy_rows(
        [
            {
                "case_no": "115000002",
                "status": "訂單取消",
                "cancel_reason": None,
            },
            {
                "case_no": "115000001",
                "status": "訂單取消",
                "cancel_reason": " 客戶取消 ",
            },
        ]
    )

    assert [item["case_no"] for item in bootstrappable] == ["115000001"]
    assert review_required == ["115000002"]
    item = bootstrappable[0]
    assert item["reason"] == "客戶取消"
    assert item["idempotency_key"] == (
        "migration:legacy_status_bootstrap:115000001"
    )
    assert item["payload"]["cancellation_date"] is None
    assert item["payload"]["provenance"] == "legacy_status_bootstrap"
    assert item["payload_hash"] == hashlib.sha256(
        item["payload_json"].encode("utf-8")
    ).hexdigest()


def test_classification_rejects_non_cancelled_input():
    with pytest.raises(ValueError, match="unexpected non-cancelled row"):
        classify_legacy_rows(
            [
                {
                    "case_no": "115000001",
                    "status": "訂單成立",
                    "cancel_reason": "not eligible",
                }
            ]
        )


def test_dataset_fingerprint_is_stable_across_source_order():
    first, first_review = classify_legacy_rows(
        [
            {
                "case_no": "B",
                "status": "訂單取消",
                "cancel_reason": "reason-b",
            },
            {
                "case_no": "A",
                "status": "訂單取消",
                "cancel_reason": "",
            },
        ]
    )
    second, second_review = classify_legacy_rows(
        [
            {
                "case_no": "A",
                "status": "訂單取消",
                "cancel_reason": "",
            },
            {
                "case_no": "B",
                "status": "訂單取消",
                "cancel_reason": "reason-b",
            },
        ]
    )

    assert _dataset_fingerprint(first, first_review) == _dataset_fingerprint(
        second, second_review
    )


def test_validate_backup_requires_nonempty_file(tmp_path):
    empty = tmp_path / "empty.sql"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="empty"):
        validate_backup(str(empty), target_database="configured_db")

    backup = tmp_path / "backup.sql"
    backup.write_bytes(
        b"-- MySQL dump\n-- Current Database: `configured_db`\n"
    )
    result = validate_backup(str(backup), target_database="configured_db")
    assert result["size"] == backup.stat().st_size
    assert result["sha256"] == hashlib.sha256(backup.read_bytes()).hexdigest()
    assert result["target_database"] == "configured_db"


def test_validate_backup_rejects_wrong_database(tmp_path):
    backup = tmp_path / "backup.sql"
    backup.write_bytes(b"-- MySQL dump\n-- Current Database: `other_db`\n")
    with pytest.raises(ValueError, match="target database"):
        validate_backup(str(backup), target_database="configured_db")


def test_validate_plan_binds_database_server_and_fingerprints(tmp_path):
    plan = {
        "migration": "order_lifecycle_control_facts_v1",
        "mode": "dry-run",
        "database": "configured_db",
        "server": "db-host",
        "orders": 10,
        "cancelled": 2,
        "bootstrappable": 1,
        "review_required": 1,
        "dataset_fingerprint": "a" * 64,
        "schema_fingerprint": "b" * 64,
    }
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    assert validate_plan(
        str(path),
        target_database="configured_db",
        server="db-host",
    ) == plan

    plan["server"] = "another-host"
    path.write_text(json.dumps(plan), encoding="utf-8")
    with pytest.raises(ValueError, match="another migration target"):
        validate_plan(
            str(path),
            target_database="configured_db",
            server="db-host",
        )


def test_overlong_legacy_reason_is_review_required():
    bootstrappable, review_required = classify_legacy_rows(
        [
            {
                "case_no": "115000001",
                "status": "訂單取消",
                "cancel_reason": "x" * 501,
            }
        ]
    )
    assert bootstrappable == []
    assert review_required == ["115000001"]


def test_target_database_must_match_configuration(monkeypatch):
    monkeypatch.setitem(
        __import__(
            "scripts.migrate_order_lifecycle_control_facts",
            fromlist=["DB_CONFIG"],
        ).DB_CONFIG,
        "database",
        "configured_db",
    )
    with pytest.raises(ValueError, match="must exactly match"):
        run_migration(mode="dry-run", target_database="another_db")


def test_bootstrap_payload_is_canonical_json():
    bootstrappable, _ = classify_legacy_rows(
        [
            {
                "case_no": "115000001",
                "status": "訂單取消",
                "cancel_reason": "客戶取消",
            }
        ]
    )
    payload_json = bootstrappable[0]["payload_json"]
    assert json.loads(payload_json) == bootstrappable[0]["payload"]
    assert payload_json == json.dumps(
        bootstrappable[0]["payload"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
