"""Durable business flow for temporary grants and reviewed cited knowledge."""

from datetime import datetime, timedelta
import os

import pytest

from infrastructure.mysql.admin_capability_grant_repository import CapabilityGrantCommand, apply_capability_grant
from infrastructure.mysql.knowledge_retrieval_repository import KnowledgeCommand, apply_knowledge_command, query_published_knowledge
from subsystems.access.authentication_session import AdminPrincipal


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


def _admin(user_id: int, username: str, capabilities: set[str]) -> AdminPrincipal:
    return AdminPrincipal(user_id, username, username, "line_agent", capabilities=frozenset(capabilities))


def _seed_admin_users():
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM admin_users")
            cursor.executemany(
                "INSERT INTO admin_users (username,password_hash,display_name,role) VALUES (%s,%s,%s,%s)",
                [("system", "unused", "系統管理員", "system_admin"), ("editor", "unused", "內容編輯", "line_agent"), ("reviewer", "unused", "內容覆核", "line_agent")],
            )
            cursor.execute("SELECT id,username FROM admin_users ORDER BY id")
            return {row["username"]: int(row["id"]) for row in cursor.fetchall()}
    finally:
        connection.commit()
        connection.close()


def _grant(actor: AdminPrincipal, target_id: int, capability: str, version: int, key: str):
    return apply_capability_grant(CapabilityGrantCommand(target_id, capability, "grant", version, "兩週代理補助政策作業", key, f"corr-{key}", datetime.now() + timedelta(days=14)), actor)


def test_temporary_grant_then_separate_review_publication_and_cited_answer():
    ids = _seed_admin_users()
    system = _admin(ids["system"], "system", {"system.administration"})
    _seed_active_session(ids["editor"])
    _grant(system, ids["editor"], "knowledge.source.edit", 0, "grant-editor")
    assert _session_is_revoked(ids["editor"])
    _grant(system, ids["reviewer"], "knowledge.source.review", 0, "grant-review")
    _grant(system, ids["reviewer"], "knowledge.source.publish", 1, "grant-publish")
    editor = _admin(ids["editor"], "editor", {"knowledge.source.edit"})
    reviewer = _admin(ids["reviewer"], "reviewer", {"knowledge.source.review", "knowledge.source.publish"})

    draft = apply_knowledge_command(KnowledgeCommand("ingest", 0, "轉錄最新補助公告", "knowledge-ingest-1", "corr-knowledge-1", source_uri="https://gov.example/subsidy-2026", source_trust_tier="government_source", title="2026 補助資格", content="補助資格需由行政以正式證明文件確認。"), editor)
    reviewed = apply_knowledge_command(KnowledgeCommand("review", 1, "覆核來源與適用日期", "knowledge-review-1", "corr-knowledge-2", item_id=draft["knowledge_item_id"]), reviewer)
    published = apply_knowledge_command(KnowledgeCommand("publish", 2, "核准對外說明", "knowledge-publish-1", "corr-knowledge-3", item_id=draft["knowledge_item_id"]), reviewer)
    answer = query_published_knowledge("補助資格")

    assert reviewed["state"] == "reviewed"
    assert published["state"] == "published"
    assert answer is not None
    assert answer["authoritative"] is False
    assert answer["citations"][0]["source_uri"] == "https://gov.example/subsidy-2026"
    assert answer["citations"][0]["version"] == 3


def _seed_active_session(admin_user_id: int) -> None:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO admin_sessions (admin_user_id,session_token_hash,expires_at) VALUES (%s,%s,DATE_ADD(UTC_TIMESTAMP(), INTERVAL 1 DAY))", (admin_user_id, "a" * 64))
        connection.commit()
    finally:
        connection.close()


def _session_is_revoked(admin_user_id: int) -> bool:
    from infrastructure.mysql.mysql_adapter import get_connection

    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT revoked_at FROM admin_sessions WHERE admin_user_id=%s", (admin_user_id,))
            return cursor.fetchone()["revoked_at"] is not None
    finally:
        connection.close()
