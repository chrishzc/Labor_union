from __future__ import annotations

import pytest

import api.dependencies.knowledge_retrieval as knowledge_dependencies
from api.dependencies.line_ai_qa_catalog import load_line_ai_qa_catalog
from api.dependencies.llm_configuration import _qa_id_from_source
from domains.knowledge_retrieval.qa_catalog import decode_governed_qa
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.knowledge_retrieval.application import KnowledgeApplication
from subsystems.knowledge_retrieval.contracts import (
    PublishKnowledgeItemCommand,
    RetireKnowledgeItemCommand,
)
from subsystems.knowledge_retrieval.qa_catalog_import import build_qa_import_commands


class _Repository:
    def __init__(self, existing=()) -> None:
        self.items = {item["source_identity"]: dict(item) for item in existing}
        self.ingested = []

    def find_by_source_identity(self, source_identity):
        return self.items.get(source_identity)

    def ingest(self, command):
        item_id = len(self.items) + 1
        self.items[command.source_identity] = {"id": item_id, "source_identity": command.source_identity, "content": command.content}
        self.ingested.append(command)
        return item_id, True


class _UnitOfWork:
    def __init__(self, repository) -> None:
        self.knowledge = repository
        self.commits = 0

    def __enter__(self): return self
    def __exit__(self, *_): return None
    def commit(self): self.commits += 1


class _LifecycleRepository:
    def __init__(self) -> None:
        self.actions = []

    def publish(self, command):
        self.actions.append(("publish", command.item_id))
        return command.expected_version.value + 1

    def retire(self, command):
        self.actions.append(("retire", command.item_id))
        return command.expected_version.value + 1

    def request_index_build(self, actor_id, idempotency_key):
        self.actions.append(("index", actor_id, idempotency_key))
        return 91


def test_all_54_source_questions_map_to_stable_governed_knowledge() -> None:
    source_items = load_line_ai_qa_catalog()
    commands = build_qa_import_commands(source_items, ActorContext("7"), "one-import", "qa-migration-test")

    assert len(source_items) == len(commands) == 54
    assert len({command.source_identity for command in commands}) == 54
    assert commands[0].source_identity == "line-common-qa:QA-001"
    assert source_items[-1].id == "QA-054"
    assert sum(item.status == "ready" for item in source_items) == 40
    assert any(item.status == "missing" for item in source_items)
    assert all(item.status in {"ready", "missing"} for item in source_items)
    mapped = decode_governed_qa(commands[0].content)
    assert mapped is not None
    assert (mapped.question, mapped.aliases, mapped.answer) == (source_items[0].question, source_items[0].aliases, source_items[0].answer)
    missing = decode_governed_qa(commands[2].content)
    assert missing is not None and missing.migration_status == "missing"
    with pytest.raises(ValueError, match="knowledge_qa_answer_required"):
        missing.require_publishable()
    social_welfare = next(item for item in source_items if item.id == "QA-025")
    assert social_welfare.category == "社福補助"
    assert "120 小時" in social_welfare.answer
    assert "40 小時" not in social_welfare.answer


def test_reimport_skips_existing_managed_revision_without_overwrite() -> None:
    commands = build_qa_import_commands(load_line_ai_qa_catalog(), ActorContext("7"), "repeat-import", "qa-migration-test")
    edited_content = '{"schema":"line.common_qa.v1","answer":"人工編修後答案"}'
    repository = _Repository(({"id": 91, "source_identity": "line-common-qa:QA-001", "content": edited_content},))
    unit_of_work = _UnitOfWork(repository)

    imported, skipped = KnowledgeApplication(lambda: unit_of_work).import_missing(commands)

    assert len(imported) == 53
    assert skipped == (91,)
    assert repository.items["line-common-qa:QA-001"]["content"] == edited_content
    assert unit_of_work.commits == 1


@pytest.mark.parametrize(
    ("method_name", "action", "command_type"),
    (
        ("publish_and_request_index", "publish", PublishKnowledgeItemCommand),
        ("retire_and_request_index", "retire", RetireKnowledgeItemCommand),
    ),
)
def test_lifecycle_action_atomically_requests_index_update(
    method_name, action, command_type
) -> None:
    repository = _LifecycleRepository()
    unit_of_work = _UnitOfWork(repository)
    command = command_type(
        41,
        ExpectedVersion(3),
        ActorContext("7"),
        "管理員變更題庫狀態",
        IdempotencyKey(f"qa-{action}-41"),
        CorrelationId(f"qa-{action}-41"),
    )

    result = getattr(KnowledgeApplication(lambda: unit_of_work), method_name)(command)

    assert result == (4, 91)
    assert repository.actions == [
        (action, 41),
        ("index", "7", f"qa-{action}-41:index"),
    ]
    assert unit_of_work.commits == 1


def test_semantic_readback_reports_managed_qa_identity() -> None:
    assert _qa_id_from_source("line-common-qa:QA-013") == "QA-013"


class _AdminCursor:
    def __enter__(self): return self
    def __exit__(self, *_): return None
    def execute(self, sql, parameters):
        assert "FROM admin_users" in sql
        assert parameters == ("root-admin",)
    def fetchone(self): return {"id": 7}


class _AdminConnection:
    def __init__(self) -> None: self.closed = False
    def cursor(self): return _AdminCursor()
    def close(self): self.closed = True


class _CatalogApplication:
    def __init__(self) -> None:
        self.commands = None
        self.publish_commands = None
    def import_missing(self, commands):
        self.commands = tuple(commands)
        return tuple(range(1, len(self.commands) + 1)), ()
    def list_items(self, limit):
        assert limit == 500
        return tuple({
            "id": index,
            "source_identity": command.source_identity,
            "lifecycle_status": "draft",
            "current_version": 1,
            "content": command.content,
        } for index, command in enumerate(self.commands, start=1))
    def publish_many_and_request_index(self, commands):
        self.publish_commands = tuple(commands)
        return tuple(2 for _ in self.publish_commands), 91


def test_development_startup_seeds_all_bundled_questions_without_manual_import(monkeypatch) -> None:
    connection = _AdminConnection()
    application = _CatalogApplication()
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DEV_ROOT_USERNAME", "ROOT-ADMIN")
    monkeypatch.setattr(knowledge_dependencies, "get_connection", lambda: connection)
    monkeypatch.setattr(knowledge_dependencies, "get_knowledge_application", lambda: application)

    knowledge_dependencies.ensure_builtin_knowledge_catalog()

    assert connection.closed is True
    assert application.commands is not None and len(application.commands) == 54
    assert {command.actor.actor_id for command in application.commands} == {"7"}
    assert application.commands[0].idempotency_key.value.startswith("qa-import:")
    assert application.commands[0].correlation_id.value == "builtin-line-common-qa-v1"
    assert application.publish_commands is not None
    assert len(application.publish_commands) == 40
    expected_enabled_ids = {
        index
        for index, item in enumerate(load_line_ai_qa_catalog(), start=1)
        if item.enabled
    }
    assert {command.item_id for command in application.publish_commands} == expected_enabled_ids


def test_non_development_startup_does_not_seed_catalog(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(
        knowledge_dependencies,
        "get_connection",
        lambda: (_ for _ in ()).throw(AssertionError("production startup must not seed")),
    )

    knowledge_dependencies.ensure_builtin_knowledge_catalog()
