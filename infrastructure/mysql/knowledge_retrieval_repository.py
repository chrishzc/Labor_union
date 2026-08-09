"""MySQL persistence and cited retrieval for reviewed knowledge items."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any, Literal

from domains.knowledge_retrieval.publication import KnowledgeState, KnowledgeTransitionError, next_knowledge_state, require_separate_publisher, require_separate_reviewer
from infrastructure.mysql.mysql_adapter import get_connection
from subsystems.access.authentication_session import AdminPrincipal, has_required_capability


KnowledgeAction = Literal["ingest", "review", "publish", "retire"]


class KnowledgeCommandError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class KnowledgeCommand:
    action: KnowledgeAction
    expected_version: int
    reason: str
    idempotency_key: str
    correlation_id: str
    item_id: int | None = None
    source_uri: str | None = None
    source_trust_tier: str | None = None
    title: str | None = None
    content: str | None = None


def apply_knowledge_command(command: KnowledgeCommand, actor: AdminPrincipal) -> dict[str, Any]:
    _validate_command(command, actor)
    connection = get_connection()
    try:
        connection.begin()
        with connection.cursor() as cursor:
            receipt = _apply(cursor, command, int(actor.id))
        connection.commit()
        return receipt
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def query_published_knowledge(question: str) -> dict[str, Any] | None:
    normalized_question = question.strip()
    if not normalized_question:
        return None
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id,source_uri,title,content,content_digest,version,published_at
                FROM knowledge_items
                WHERE state='published' AND (title LIKE %s OR content LIKE %s)
                ORDER BY published_at DESC, id DESC LIMIT 3
                """,
                (f"%{normalized_question}%", f"%{normalized_question}%"),
            )
            rows = list(cursor.fetchall())
    finally:
        connection.close()
    return _answer(rows)


def _validate_command(command: KnowledgeCommand, actor: AdminPrincipal) -> None:
    if actor.id is None or command.expected_version < 0:
        raise KnowledgeCommandError("knowledge_command_invalid")
    required_capability = {
        "ingest": "knowledge.source.edit",
        "review": "knowledge.source.review",
        "publish": "knowledge.source.publish",
        "retire": "knowledge.source.publish",
    }[command.action]
    if not has_required_capability(actor, required_capability):
        raise KnowledgeCommandError("insufficient_capability")
    if not command.reason.strip() or not command.idempotency_key.strip() or not command.correlation_id.strip():
        raise KnowledgeCommandError("knowledge_command_invalid")
    if command.action == "ingest":
        if command.expected_version != 0:
            raise KnowledgeCommandError("knowledge_version_conflict")
        if not all((command.source_uri, command.source_trust_tier, command.title, command.content)):
            raise KnowledgeCommandError("knowledge_source_invalid")
        return
    if command.item_id is None or command.item_id <= 0:
        raise KnowledgeCommandError("knowledge_command_invalid")


def _apply(cursor: Any, command: KnowledgeCommand, actor_id: int) -> dict[str, Any]:
    replay = _existing_receipt(cursor, command)
    if replay is not None:
        return replay
    if command.action == "ingest":
        return _ingest(cursor, command, actor_id)
    item = _locked_item(cursor, command)
    return _transition(cursor, command, actor_id, item)


def _existing_receipt(cursor: Any, command: KnowledgeCommand) -> dict[str, Any] | None:
    cursor.execute("SELECT command_fingerprint,receipt_json FROM knowledge_apply_receipts WHERE idempotency_key=%s FOR UPDATE", (command.idempotency_key,))
    row = cursor.fetchone()
    if row is None:
        return None
    if row["command_fingerprint"] != _fingerprint(command):
        raise KnowledgeCommandError("idempotency_conflict")
    return json.loads(row["receipt_json"])


def _ingest(cursor: Any, command: KnowledgeCommand, actor_id: int) -> dict[str, Any]:
    digest = hashlib.sha256(command.content.encode("utf-8")).hexdigest()
    cursor.execute(
        "INSERT INTO knowledge_items (source_uri,source_trust_tier,title,content,content_digest,created_by_admin_user_id) VALUES (%s,%s,%s,%s,%s,%s)",
        (command.source_uri, command.source_trust_tier, command.title.strip(), command.content.strip(), digest, actor_id),
    )
    item_id = int(cursor.lastrowid)
    cursor.execute("UPDATE knowledge_items SET version=1 WHERE id=%s", (item_id,))
    item = {"id": item_id, "version": 0, "state": KnowledgeState.DRAFT.value, "created_by_admin_user_id": actor_id, "source_uri": command.source_uri, "content_digest": digest}
    return _persist_transition(cursor, command, actor_id, item, 1)


def _locked_item(cursor: Any, command: KnowledgeCommand) -> dict[str, Any]:
    cursor.execute("SELECT * FROM knowledge_items WHERE id=%s FOR UPDATE", (command.item_id,))
    item = cursor.fetchone()
    if item is None:
        raise KnowledgeCommandError("knowledge_item_not_found")
    if int(item["version"]) != command.expected_version:
        raise KnowledgeCommandError("knowledge_version_conflict")
    return item


def _transition(cursor: Any, command: KnowledgeCommand, actor_id: int, item: dict[str, Any]) -> dict[str, Any]:
    try:
        next_state = next_knowledge_state(KnowledgeState(item["state"]), command.action)
        if next_state is KnowledgeState.REVIEWED:
            require_separate_reviewer(int(item["created_by_admin_user_id"]), actor_id)
        if next_state is KnowledgeState.PUBLISHED:
            require_separate_publisher(int(item["created_by_admin_user_id"]), actor_id)
    except KnowledgeTransitionError as error:
        raise KnowledgeCommandError(str(error)) from error
    updates = _transition_updates(next_state, actor_id, command.reason)
    cursor.execute(f"UPDATE knowledge_items SET state=%s,version=version+1,{updates[0]} WHERE id=%s", (next_state.value, *updates[1], item["id"]))
    item["state"] = next_state.value
    return _persist_transition(cursor, command, actor_id, item, int(item["version"]) + 1)


def _transition_updates(state: KnowledgeState, actor_id: int, reason: str) -> tuple[str, tuple[object, ...]]:
    if state is KnowledgeState.REVIEWED:
        return "reviewed_by_admin_user_id=%s,review_reason=%s", (actor_id, reason.strip())
    if state is KnowledgeState.PUBLISHED:
        return "published_by_admin_user_id=%s,publication_reason=%s,published_at=UTC_TIMESTAMP()", (actor_id, reason.strip())
    return "retired_by_admin_user_id=%s,retired_reason=%s,retired_at=UTC_TIMESTAMP()", (actor_id, reason.strip())


def _persist_transition(cursor: Any, command: KnowledgeCommand, actor_id: int, item: dict[str, Any], after_version: int) -> dict[str, Any]:
    before_version = after_version - 1
    item_id = int(item["id"])
    snapshot = {"knowledge_item_id": item_id, "state": item["state"], "version": after_version, "source_uri": item["source_uri"], "content_digest": item["content_digest"]}
    cursor.execute("INSERT INTO knowledge_item_events (knowledge_item_id,actor_admin_user_id,event_type,before_version,after_version,reason,idempotency_key,correlation_id,snapshot_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)", (item_id, actor_id, _event_type(command.action), before_version, after_version, command.reason.strip(), command.idempotency_key, command.correlation_id, json.dumps(snapshot, ensure_ascii=False)))
    cursor.execute("INSERT INTO knowledge_apply_receipts (idempotency_key,command_fingerprint,receipt_json) VALUES (%s,%s,%s)", (command.idempotency_key, _fingerprint(command), json.dumps(snapshot, ensure_ascii=False)))
    return snapshot


def _event_type(action: KnowledgeAction) -> str:
    return {"ingest": "ingested", "review": "reviewed", "publish": "published", "retire": "retired"}[action]


def _answer(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    citations = [{"knowledge_item_id": row["id"], "source_uri": row["source_uri"], "content_digest": row["content_digest"], "version": row["version"], "published_at": row["published_at"]} for row in rows]
    answer = "\n\n".join(f"{row['title']}：{row['content'][:600]}" for row in rows)
    return {"answer": answer, "citations": citations, "authoritative": False}


def _fingerprint(command: KnowledgeCommand) -> str:
    payload = {"action": command.action, "expected_version": command.expected_version, "reason": command.reason.strip(), "item_id": command.item_id, "source_uri": command.source_uri, "source_trust_tier": command.source_trust_tier, "title": command.title, "content": command.content, "correlation_id": command.correlation_id}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
