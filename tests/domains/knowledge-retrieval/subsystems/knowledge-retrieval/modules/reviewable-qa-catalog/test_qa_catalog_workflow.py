from __future__ import annotations

import pytest

import api.dependencies.knowledge_retrieval as knowledge_dependencies
from api.dependencies.line_ai_qa_catalog import load_line_ai_qa_catalog
from api.dependencies.llm_configuration import _qa_id_from_source
from domains.knowledge_retrieval.qa_catalog import decode_governed_qa
from shared_kernel.identities import ActorContext
from subsystems.knowledge_retrieval.application import KnowledgeApplication
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


def test_all_29_source_questions_map_to_stable_governed_knowledge() -> None:
    source_items = load_line_ai_qa_catalog()
    commands = build_qa_import_commands(source_items, ActorContext("7"), "one-import", "qa-migration-test")

    assert len(source_items) == len(commands) == 29
    assert len({command.source_identity for command in commands}) == 29
    assert commands[0].source_identity == "line-common-qa:QA-001"
    mapped = decode_governed_qa(commands[0].content)
    assert mapped is not None
    assert (mapped.question, mapped.aliases, mapped.answer) == (source_items[0].question, source_items[0].aliases, source_items[0].answer)
    missing = decode_governed_qa(commands[2].content)
    assert missing is not None and missing.migration_status == "missing"
    with pytest.raises(ValueError, match="knowledge_qa_answer_required"):
        missing.require_publishable()


def test_reimport_skips_existing_managed_revision_without_overwrite() -> None:
    commands = build_qa_import_commands(load_line_ai_qa_catalog(), ActorContext("7"), "repeat-import", "qa-migration-test")
    edited_content = '{"schema":"line.common_qa.v1","answer":"人工編修後答案"}'
    repository = _Repository(({"id": 91, "source_identity": "line-common-qa:QA-001", "content": edited_content},))
    unit_of_work = _UnitOfWork(repository)

    imported, skipped = KnowledgeApplication(lambda: unit_of_work).import_missing(commands)

    assert len(imported) == 28
    assert skipped == (91,)
    assert repository.items["line-common-qa:QA-001"]["content"] == edited_content
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
    def __init__(self) -> None: self.commands = None
    def import_missing(self, commands): self.commands = tuple(commands)


def test_development_startup_seeds_all_bundled_questions_without_manual_import(monkeypatch) -> None:
    connection = _AdminConnection()
    application = _CatalogApplication()
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DEV_ROOT_USERNAME", "ROOT-ADMIN")
    monkeypatch.setattr(knowledge_dependencies, "get_connection", lambda: connection)
    monkeypatch.setattr(knowledge_dependencies, "get_knowledge_application", lambda: application)

    knowledge_dependencies.ensure_builtin_knowledge_catalog()

    assert connection.closed is True
    assert application.commands is not None and len(application.commands) == 29
    assert {command.actor.actor_id for command in application.commands} == {"7"}
    assert application.commands[0].idempotency_key.value.startswith("qa-import:")
    assert application.commands[0].correlation_id.value == "builtin-line-common-qa-v1"


def test_non_development_startup_does_not_seed_catalog(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(
        knowledge_dependencies,
        "get_connection",
        lambda: (_ for _ in ()).throw(AssertionError("production startup must not seed")),
    )

    knowledge_dependencies.ensure_builtin_knowledge_catalog()
