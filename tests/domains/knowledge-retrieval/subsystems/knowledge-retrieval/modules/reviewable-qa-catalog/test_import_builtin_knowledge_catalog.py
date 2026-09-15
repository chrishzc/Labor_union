from argparse import Namespace
import json
from pathlib import Path

import pytest

from api.dependencies.line_ai_qa_catalog import load_line_ai_qa_catalog
from shared_kernel.identities import ActorContext
from subsystems.knowledge_retrieval.qa_catalog_import import build_qa_import_commands
from scripts import import_builtin_knowledge_catalog as operator


ROOT = Path(__file__).resolve().parents[7]


def _target(rows=()):
    return {
        "database_name": "union_production_test",
        "server": "mysql-test-01",
        "actor_id": 7,
        "actor_username": "operator",
        "rows": tuple(rows),
    }


def test_production_dry_run_plans_all_missing_bundled_questions(monkeypatch) -> None:
    monkeypatch.setitem(operator.DB_CONFIG, "database", "union_production_test")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DB_HOST", "mysql-test.internal")
    monkeypatch.setattr(operator, "_read_target", lambda *_: _target())

    plan, _ = operator._build_plan("union_production_test", "operator")

    assert plan["environment"] == "production"
    assert plan["catalog_count"] == 54
    assert plan["enabled_count"] == 40
    assert plan["actor_id"] == 7
    assert plan["missing_count"] == 54
    assert plan["publish_candidate_count"] == 40
    assert plan["preserved_modified_count"] == 0


def test_plan_preserves_modified_item_and_only_publishes_pristine_enabled_v1(
    monkeypatch,
) -> None:
    items = load_line_ai_qa_catalog()
    commands = build_qa_import_commands(
        items, ActorContext("7"), "test-import", "test-import"
    )
    enabled = next(item for item in items if item.enabled)
    exact = next(command for command in commands if command.source_identity.endswith(enabled.id))
    modified = next(command for command in commands if command.source_identity != exact.source_identity)
    rows = (
        {
            "id": 11,
            "source_identity": exact.source_identity,
            "state": "draft",
            "version": 1,
            "content": exact.content,
            "content_digest": "exact",
        },
        {
            "id": 12,
            "source_identity": modified.source_identity,
            "state": "draft",
            "version": 2,
            "content": '{"answer":"人工修訂"}',
            "content_digest": "modified",
        },
    )
    monkeypatch.setitem(operator.DB_CONFIG, "database", "union_production_test")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DB_HOST", "mysql-test.internal")
    monkeypatch.setattr(operator, "_read_target", lambda *_: _target(rows))

    plan, _ = operator._build_plan("union_production_test", "operator")

    assert plan["preserved_modified_source_identities"] == [modified.source_identity]
    assert exact.source_identity in plan["publish_candidate_source_identities"]
    assert modified.source_identity not in plan["publish_candidate_source_identities"]


def test_apply_uses_the_same_owner_import_as_the_ui(monkeypatch) -> None:
    captured = {}

    def import_catalog(actor, import_key, correlation_id):
        captured.update(
            actor=actor,
            import_key=import_key,
            correlation_id=correlation_id,
        )
        return {
            "catalog_count": 54,
            "imported_count": 54,
            "skipped_existing_count": 0,
            "published_count": 40,
            "index_job_id": 88,
        }

    monkeypatch.setattr(operator, "import_builtin_knowledge_catalog", import_catalog)
    monkeypatch.setattr(operator, "_read_target", lambda *_: _target())
    arguments = Namespace(
        target_database="union_production_test",
        actor_username="operator",
    )
    plan = {"environment": "production", "catalog_sha256": "source-digest"}

    receipt = operator._apply(arguments, plan, _target())

    assert captured["actor"] == ActorContext("7")
    assert captured["import_key"] == "builtin-line-common-qa-production-v1"
    assert captured["correlation_id"] == "builtin-line-common-qa-production-v1"
    assert receipt["imported_count"] == 54
    assert receipt["skipped_existing_count"] == 0
    assert receipt["published_count"] == 40
    assert receipt["index_job_id"] == 88


def test_apply_rejects_a_plan_when_target_state_changed(tmp_path) -> None:
    plan_path = tmp_path / "plan.json"
    original = {
        "operation": "import_builtin_knowledge_catalog",
        "environment": "production",
        "target_database": "union_production_test",
        "target_server": "mysql-test-01",
        "actor_id": 7,
        "actor_username": "operator",
        "catalog_sha256": "source-digest",
        "target_state_fingerprint": "before",
    }
    plan_path.write_text(json.dumps(original), encoding="utf-8")
    changed = {**original, "target_state_fingerprint": "after"}

    with pytest.raises(ValueError, match="target_state_fingerprint"):
        operator._read_plan(plan_path, changed)


def test_runtime_rejects_target_different_from_configured_database(monkeypatch) -> None:
    monkeypatch.setitem(operator.DB_CONFIG, "database", "actual_database")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DB_HOST", "mysql-test.internal")

    with pytest.raises(ValueError, match="exactly match"):
        operator._require_runtime("wrong_database")


def test_cloud_runtime_image_includes_only_the_bundled_catalog_document() -> None:
    rules = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()

    assert "!document/" in rules
    assert "document/*" in rules
    assert "!document/line/" in rules
    assert "document/line/*" in rules
    assert "!document/line/AI客服QA題庫.jsonl" in rules
