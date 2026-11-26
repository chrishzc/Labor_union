"""Durable business flow for equal-access sessions and reviewed cited knowledge."""

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from infrastructure.mysql.knowledge_retrieval_repository import query_published_knowledge
from infrastructure.mysql.knowledge_retrieval_unit_of_work import open_knowledge_retrieval_unit_of_work
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.knowledge_retrieval.application import KnowledgeApplication
from subsystems.knowledge_retrieval.contracts import (
    IngestKnowledgeSourceCommand,
    PublishKnowledgeItemCommand,
    ReviewKnowledgeItemCommand,
)


DATABASE = os.getenv("LABOR_UNION_TEST_MYSQL_DATABASE")
pytestmark = pytest.mark.skipif(not DATABASE, reason="requires explicitly configured disposable MySQL")


@pytest.fixture(autouse=True)
def _use_disposable_database(monkeypatch):
    from infrastructure.mysql import mysql_adapter

    monkeypatch.setattr(mysql_adapter, "DB_CONFIG", {
        "host": os.environ["LABOR_UNION_TEST_MYSQL_HOST"],
        "port": int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        "user": os.environ["LABOR_UNION_TEST_MYSQL_USER"],
        "password": os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
        "database": DATABASE,
        "charset": "utf8mb4",
    })


def _seed_admin_users():
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            run_identity = uuid4().hex[:12]
            usernames = {
                "author": f"knowledge_author_{run_identity}",
                "reviewer": f"knowledge_reviewer_{run_identity}",
            }
            cursor.executemany(
                "INSERT INTO admin_users (username,password_hash,display_name,role) VALUES (%s,%s,%s,%s)",
                [(usernames["author"], "unused", "內容作者", "line_agent"), (usernames["reviewer"], "unused", "內容覆核", "line_agent")],
            )
            placeholders = ",".join(["%s"] * len(usernames))
            cursor.execute(
                f"SELECT id,username FROM admin_users WHERE username IN ({placeholders})",
                tuple(usernames.values()),
            )
            ids_by_username = {row["username"]: int(row["id"]) for row in cursor.fetchall()}
            return {role: ids_by_username[username] for role, username in usernames.items()}
    finally:
        connection.commit()
        connection.close()


def test_equal_enabled_users_review_publish_and_retrieve_cited_knowledge():
    ids = _seed_admin_users()
    run_identity = uuid4().hex
    _seed_active_session(ids["author"])
    assert _session_is_active(ids["author"])
    application = KnowledgeApplication(open_knowledge_retrieval_unit_of_work)
    author = ActorContext(str(ids["author"]))
    reviewer = ActorContext(str(ids["reviewer"]))
    source_uri = f"https://gov.example/subsidy-2026/{run_identity}"

    draft_id, created = application.ingest(IngestKnowledgeSourceCommand(
        source_identity=f"knowledge:subsidy-2026:{run_identity}",
        source_trust_tier="government_source",
        title=f"2026 補助資格 {run_identity}",
        content="補助資格需由行政以正式證明文件確認。",
        source_uri=source_uri,
        actor=author,
        idempotency_key=IdempotencyKey(f"knowledge-ingest-{run_identity}"),
        correlation_id=CorrelationId(f"corr-knowledge-{run_identity}-1"),
    ))
    assert created is True
    reviewed_version = application.review(ReviewKnowledgeItemCommand(
        item_id=draft_id,
        expected_version=ExpectedVersion(1),
        actor=reviewer,
        reason="覆核來源與適用日期",
        idempotency_key=IdempotencyKey(f"knowledge-review-{run_identity}"),
        correlation_id=CorrelationId(f"corr-knowledge-{run_identity}-2"),
    ))
    published_version = application.publish(PublishKnowledgeItemCommand(
        item_id=draft_id,
        expected_version=ExpectedVersion(2),
        actor=reviewer,
        reason="核准對外說明",
        idempotency_key=IdempotencyKey(f"knowledge-publish-{run_identity}"),
        correlation_id=CorrelationId(f"corr-knowledge-{run_identity}-3"),
    ))
    answer = query_published_knowledge("補助資格")

    assert reviewed_version == 2
    assert published_version == 3
    item = application.get_item(draft_id)
    assert item is not None
    assert item["lifecycle_status"] == "published"
    assert item["current_version"] == 3
    assert item["source_uri"] == source_uri
    assert answer is not None
    assert answer["authoritative"] is False
    assert answer["citations"][0]["source_uri"] == source_uri
    assert answer["citations"][0]["version"] == 3


def _seed_active_session(admin_user_id: int) -> None:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            session_token_hash = uuid4().hex + uuid4().hex
            cursor.execute(
                """INSERT INTO admin_sessions (
                    admin_user_id,session_token_hash,expires_at,absolute_expires_at,last_seen_at
                ) VALUES (%s,%s,DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 30 MINUTE),
                    DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 8 HOUR),UTC_TIMESTAMP(6))""",
                (admin_user_id, session_token_hash),
            )
        connection.commit()
    finally:
        connection.close()


def _session_is_active(admin_user_id: int) -> bool:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT revoked_at,expires_at FROM admin_sessions WHERE admin_user_id=%s",
                (admin_user_id,),
            )
            row = cursor.fetchone()
            return row["revoked_at"] is None and row["expires_at"] > datetime.now(timezone.utc).replace(tzinfo=None)
    finally:
        connection.close()


def test_faq_04_mysql_publication_and_receipt_rollback(monkeypatch):
    from domains.knowledge_retrieval.qa_catalog import GovernedQaContent, encode_governed_qa
    from infrastructure.mysql.knowledge_retrieval_unit_of_work import KnowledgeRetrievalMySqlUnitOfWork
    from infrastructure.mysql.mysql_adapter import get_connection
    from subsystems.knowledge_retrieval.faq_catalog import PublishedFaqCatalog

    actors = _seed_admin_users()
    actor = ActorContext(str(actors["author"]))
    reviewer = ActorContext(str(actors["reviewer"]))
    qa_id = "CI-" + uuid4().hex[:16].upper()

    def key(operation):
        return IdempotencyKey(f"{qa_id}:{operation}")

    def save(answer, expected_version):
        content = GovernedQaContent(
            qa_id=qa_id, category="服務流程", category_id="service_flow", tag="合成",
            question=f"測試題 {qa_id}？", aliases=("合成別名",), answer=answer, source_ref=f"source-{answer}-{qa_id}",
        )
        return app.ingest(IngestKnowledgeSourceCommand(
            content.source_identity, "internal_policy", content.question, encode_governed_qa(content),
            content.source_ref, actor, key(f"draft-{answer}"), CorrelationId(f"{qa_id}:draft"),
            ExpectedVersion(expected_version) if expected_version is not None else None,
        ))[0]

    def publish(version, attempt):
        return PublishKnowledgeItemCommand(
            item_id, ExpectedVersion(version), reviewer, "合成發布", key(attempt),
            CorrelationId(f"{qa_id}:publish"),
        )

    app = KnowledgeApplication(open_knowledge_retrieval_unit_of_work)
    catalog = PublishedFaqCatalog(open_knowledge_retrieval_unit_of_work)
    item_id = save("A", None)
    first = publish(1, "publish-A")
    first_version, index_job = app.publish_and_request_index(first)
    assert app.publish_and_request_index(first) == (first_version, index_job)
    assert save("B", first_version) == item_id
    second = publish(first_version + 1, "publish-B")
    assert catalog.get(qa_id).answer == "A"
    assert catalog.get(qa_id).source_uri == f"source-A-{qa_id}"

    original_commit = KnowledgeRetrievalMySqlUnitOfWork.commit

    def fail_after_writes(unit):
        with unit._connection.cursor() as cursor:
            cursor.execute("SELECT published_version FROM knowledge_items WHERE id=%s", (item_id,))
            assert cursor.fetchone()["published_version"] == first_version + 2
            cursor.execute("SELECT COUNT(*) AS n FROM knowledge_apply_receipts WHERE idempotency_key=%s", (second.idempotency_key.value,))
            assert cursor.fetchone()["n"] == 1
        raise RuntimeError("synthetic failure after official pointer and receipt")

    monkeypatch.setattr(KnowledgeRetrievalMySqlUnitOfWork, "commit", fail_after_writes)
    with pytest.raises(RuntimeError, match="synthetic failure after official pointer and receipt"):
        app.publish_and_request_index(second)

    assert catalog.get(qa_id).answer == "A"
    with get_connection() as fresh:
        with fresh.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS n FROM knowledge_apply_receipts WHERE idempotency_key=%s", (second.idempotency_key.value,))
            assert cursor.fetchone()["n"] == 0
            cursor.execute("SELECT COUNT(*) AS n FROM knowledge_item_versions WHERE item_id=%s AND item_version=%s", (item_id, first_version + 2))
            assert cursor.fetchone()["n"] == 0

    monkeypatch.setattr(KnowledgeRetrievalMySqlUnitOfWork, "commit", original_commit)
    assert app.publish_and_request_index(second)[0] == first_version + 2
    assert catalog.get(qa_id).answer == "B"


def test_faq_04_mysql_compatible_upgrade_rerun():
    from pathlib import Path

    from scripts.migrate_preserved_database_additive_schema import (
        DatabaseConfig, _canonical_artifact_descriptor, _schema_snapshot, local_additive_descriptor_state,
    )
    from scripts.reset_fake_database import split_sql

    root = Path(__file__).resolve().parents[1]
    sql = root / "db/schema_parts/1087_shared_line_faq.sql"
    descriptor = _canonical_artifact_descriptor(sql.name)
    config = DatabaseConfig(
        os.environ["LABOR_UNION_TEST_MYSQL_HOST"], int(os.environ["LABOR_UNION_TEST_MYSQL_PORT"]),
        os.environ["LABOR_UNION_TEST_MYSQL_USER"], os.environ["LABOR_UNION_TEST_MYSQL_PASSWORD"],
    )
    assert DATABASE.startswith("lu_test_faq_")
    assert config.host == "127.0.0.1"

    def migrate():
        before = _schema_snapshot(config, DATABASE)
        status = local_additive_descriptor_state(before, descriptor, sql.name)
        if status == "absent":
            with config.connect(DATABASE) as connection:
                with connection.cursor() as cursor:
                    for statement in split_sql(sql.read_text(encoding="utf-8")):
                        cursor.execute(statement)
        else:
            assert status == "exact"
        after = _schema_snapshot(config, DATABASE)
        assert local_additive_descriptor_state(after, descriptor, sql.name) == "exact"
        return status

    assert migrate() == "absent"
    assert migrate() == "exact"


def test_faq_04_mysql_legacy_audit_and_backfill_rerun():
    from domains.knowledge_retrieval.qa_catalog import GovernedQaContent, encode_governed_qa
    from infrastructure.mysql.mysql_adapter import get_connection
    from scripts.backfill_shared_line_faq import POLICY_LABELS, backfill
    from subsystems.knowledge_retrieval.faq_catalog import KnowledgeCatalogUnavailable, PublishedFaqCatalog
    from subsystems.line.capabilities import LineCapability

    actors = _seed_admin_users()
    actor = ActorContext(str(actors["author"]), (LineCapability.CONFIG_MANAGE.value,))
    reviewer = ActorContext(str(actors["reviewer"]))
    run = uuid4().hex[:12].upper()
    correlation = CorrelationId(f"legacy-faq-{run}")
    app = KnowledgeApplication(open_knowledge_retrieval_unit_of_work)
    catalog = PublishedFaqCatalog(open_knowledge_retrieval_unit_of_work)
    legacy = []
    item_ids = []

    for index, category in enumerate(("服務流程", "收費與補助")):
        qa_id = f"LEGACY-{run}-{index}"
        question = f"舊題 {qa_id}？"
        source_ref = f"original:{qa_id}"
        content = GovernedQaContent(qa_id, category, "合成", question, (), "正式 A", source_ref)
        legacy.append({"id": qa_id, "category": category, "question": question, "answer": "匯入來源內容", "enabled": True})
        item_id = app.ingest(IngestKnowledgeSourceCommand(
            content.source_identity, "internal_policy", question, encode_governed_qa(content),
            source_ref, actor, IdempotencyKey(f"{qa_id}:initial"), correlation,
        ))[0]
        item_ids.append(item_id)
        assert app.publish(PublishKnowledgeItemCommand(
            item_id, ExpectedVersion(1), reviewer, "正式 A", IdempotencyKey(f"{qa_id}:publish"), correlation,
        )) == 2
        revised = GovernedQaContent(qa_id, category, "合成", "只在草稿的題目", (), "草稿 B", f"revised:{qa_id}")
        app.ingest(IngestKnowledgeSourceCommand(
            content.source_identity, "internal_policy", revised.question, encode_governed_qa(revised),
            revised.source_ref, actor, IdempotencyKey(f"{qa_id}:revision"), correlation, ExpectedVersion(2),
        ))

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.executemany("UPDATE knowledge_items SET published_version=NULL WHERE id=%s", [(item_id,) for item_id in item_ids])
        connection.commit()

    with pytest.raises(KnowledgeCatalogUnavailable):
        catalog.page(None)

    def migration(reviewed, *, apply):
        with get_connection() as connection:
            return backfill(connection, legacy, reviewed, actor=actor, correlation_id=correlation, apply=apply)

    blocked = migration({}, apply=True)
    assert blocked["updated_items"] == 0
    assert {issue["code"] for issue in blocked["issues"]} == {"legacy_policy_unresolved"}
    reviewed = {"legacy_questions": {text: legacy[1]["id"] for text in POLICY_LABELS}}
    audit = migration(reviewed, apply=False)
    assert audit["issues"] == [] and audit["updated_items"] == 0 and audit["layout_revision"] == 0
    with pytest.raises(KnowledgeCatalogUnavailable):
        catalog.page(None)
    applied = migration(reviewed, apply=True)
    assert applied["issues"] == [] and applied["updated_items"] >= 2 and applied["layout_revision"] == 1
    for row in legacy:
        official = catalog.get(row["id"])
        assert official.answer == "正式 A" and official.source_version == 2
        assert catalog.match_legacy_text(row["question"]) == (official,)
    assert catalog.match_legacy_text(POLICY_LABELS[0])[0].qa_id == legacy[1]["id"]
    repeated = migration(reviewed, apply=True)
    assert repeated["issues"] == [] and repeated["updated_items"] == 0 and repeated["layout_revision"] == 1
