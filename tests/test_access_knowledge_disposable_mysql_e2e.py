"""Durable business flow for temporary grants and reviewed cited knowledge."""

from datetime import datetime, timedelta
import os
from uuid import uuid4

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
            run_identity = uuid4().hex[:12]
            usernames = {
                "system": f"knowledge_system_{run_identity}",
                "editor": f"knowledge_editor_{run_identity}",
                "reviewer": f"knowledge_reviewer_{run_identity}",
            }
            cursor.executemany(
                "INSERT INTO admin_users (username,password_hash,display_name,role) VALUES (%s,%s,%s,%s)",
                [(usernames["system"], "unused", "系統管理員", "system_admin"), (usernames["editor"], "unused", "內容編輯", "line_agent"), (usernames["reviewer"], "unused", "內容覆核", "line_agent")],
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


def _grant(actor: AdminPrincipal, target_id: int, capability: str, version: int, key: str):
    return apply_capability_grant(CapabilityGrantCommand(target_id, capability, "grant", version, "兩週代理補助政策作業", key, f"corr-{key}", datetime.now() + timedelta(days=14)), actor)


def test_temporary_grant_then_separate_review_publication_and_cited_answer():
    ids = _seed_admin_users()
    run_identity = uuid4().hex
    system = _admin(ids["system"], "system", {"system.administration"})
    _seed_active_session(ids["editor"])
    _grant(system, ids["editor"], "knowledge.source.edit", 0, f"grant-editor-{run_identity}")
    assert _session_is_revoked(ids["editor"])
    _grant(system, ids["reviewer"], "knowledge.source.review", 0, f"grant-review-{run_identity}")
    _grant(system, ids["reviewer"], "knowledge.source.publish", 1, f"grant-publish-{run_identity}")
    editor = _admin(ids["editor"], "editor", {"knowledge.source.edit"})
    reviewer = _admin(ids["reviewer"], "reviewer", {"knowledge.source.review", "knowledge.source.publish"})
    source_uri = f"https://gov.example/subsidy-2026/{run_identity}"

    draft = apply_knowledge_command(KnowledgeCommand("ingest", 0, "轉錄最新補助公告", f"knowledge-ingest-{run_identity}", f"corr-knowledge-{run_identity}-1", source_uri=source_uri, source_trust_tier="government_source", title=f"2026 補助資格 {run_identity}", content="補助資格需由行政以正式證明文件確認。"), editor)
    reviewed = apply_knowledge_command(KnowledgeCommand("review", 1, "覆核來源與適用日期", f"knowledge-review-{run_identity}", f"corr-knowledge-{run_identity}-2", item_id=draft["knowledge_item_id"]), reviewer)
    published = apply_knowledge_command(KnowledgeCommand("publish", 2, "核准對外說明", f"knowledge-publish-{run_identity}", f"corr-knowledge-{run_identity}-3", item_id=draft["knowledge_item_id"]), reviewer)
    answer = query_published_knowledge("補助資格")

    assert reviewed["state"] == "reviewed"
    assert published["state"] == "published"
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
            cursor.execute("INSERT INTO admin_sessions (admin_user_id,session_token_hash,expires_at) VALUES (%s,%s,DATE_ADD(UTC_TIMESTAMP(), INTERVAL 1 DAY))", (admin_user_id, session_token_hash))
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
