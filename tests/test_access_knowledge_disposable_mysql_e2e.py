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
