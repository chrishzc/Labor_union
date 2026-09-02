"""MySQL SSOT for reviewed knowledge, durable jobs, and answer receipts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pymysql.err import IntegrityError

from domains.knowledge_retrieval.knowledge import (
    KnowledgeAnswer,
    KnowledgeItemStatus,
    source_digest,
    transition_item_status,
)
from domains.knowledge_retrieval.publication import (
    require_separate_publisher,
    require_separate_reviewer,
)
from domains.line.canonical_payload import canonical_line_payload_json
from domains.line.delivery import LineDeliveryRequest, LineMessageKind, LineRecipient, LineRecipientType
from domains.line.identities import LineUserId
from infrastructure.mysql.line_delivery_task_repository import MySqlLineDeliveryTaskRepository
from infrastructure.mysql.line_repository_support import database_utc, mysql_error_code
from infrastructure.mysql.mysql_adapter import get_connection
from shared_kernel.identities import (
    ActorContext,
    CorrelationId,
    ExpectedVersion,
    IdempotencyKey,
)
from subsystems.access.authentication_session import (
    AdminPrincipal,
    has_required_capability,
)
from subsystems.knowledge_retrieval.contracts import (
    IngestKnowledgeSourceCommand,
    PublishKnowledgeItemCommand,
    RetireKnowledgeItemCommand,
    ReviewKnowledgeItemCommand,
)


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


def apply_knowledge_command(
    command: KnowledgeCommand,
    actor: AdminPrincipal,
) -> dict[str, Any]:
    del command, actor
    raise KnowledgeCommandError("knowledge_legacy_writer_retired")


def query_published_knowledge(question: str) -> dict[str, Any] | None:
    normalized_question = question.strip()
    if not normalized_question:
        return None
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id,source_uri,title,content,content_digest,version,"
                "published_at FROM knowledge_items WHERE state='published' "
                "AND (title LIKE %s OR content LIKE %s) "
                "ORDER BY published_at DESC,id DESC LIMIT 3",
                (
                    f"%{normalized_question}%",
                    f"%{normalized_question}%",
                ),
            )
            rows = list(cursor.fetchall() or ())
    finally:
        connection.close()
    return _answer(rows)


def _answer(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    citations = [
        {
            "knowledge_item_id": row["id"],
            "source_uri": row["source_uri"],
            "content_digest": row["content_digest"],
            "version": row["version"],
            "published_at": row["published_at"],
        }
        for row in rows
    ]
    answer = "\n\n".join(
        f"{row['title']}：{row['content'][:600]}" for row in rows
    )
    return {"answer": answer, "citations": citations, "authoritative": False}


def _validate_compatibility_command(
    command: KnowledgeCommand,
    actor: AdminPrincipal,
) -> None:
    if actor.id is None or command.expected_version < 0:
        raise KnowledgeCommandError("knowledge_command_invalid")
    capabilities = {
        "ingest": ("knowledge.source.edit", "knowledge.manage"),
        "review": ("knowledge.source.review", "knowledge.manage"),
        "publish": ("knowledge.source.publish", "knowledge.publish"),
        "retire": ("knowledge.source.publish", "knowledge.publish"),
    }[command.action]
    if not any(has_required_capability(actor, item) for item in capabilities):
        raise KnowledgeCommandError("insufficient_capability")
    if not all((command.reason.strip(), command.idempotency_key.strip(), command.correlation_id.strip())):
        raise KnowledgeCommandError("knowledge_command_invalid")
    if command.action == "ingest":
        if command.expected_version != 0:
            raise KnowledgeCommandError("knowledge_version_conflict")
        if not all((command.source_uri, command.source_trust_tier, command.title, command.content)):
            raise KnowledgeCommandError("knowledge_source_invalid")
        return
    if command.item_id is None or command.item_id < 1:
        raise KnowledgeCommandError("knowledge_command_invalid")


def _apply_compatibility_command(repository, command, actor_id: int):
    actor = ActorContext(str(actor_id))
    key = IdempotencyKey(command.idempotency_key)
    correlation = CorrelationId(command.correlation_id)
    if command.action == "ingest":
        item_id, _ = repository.ingest(
            IngestKnowledgeSourceCommand(
                command.source_uri,
                command.source_trust_tier,
                command.title,
                command.content,
                command.source_uri,
                actor,
                key,
                correlation,
            )
        )
        return _compatibility_receipt(item_id, "draft", 1)
    command_type = {
        "review": ReviewKnowledgeItemCommand,
        "publish": PublishKnowledgeItemCommand,
        "retire": RetireKnowledgeItemCommand,
    }[command.action]
    typed_command = command_type(
        command.item_id,
        ExpectedVersion(command.expected_version),
        actor,
        command.reason,
        key,
        correlation,
    )
    version = getattr(repository, command.action)(typed_command)
    state = {"review": "reviewed", "publish": "published", "retire": "retired"}[
        command.action
    ]
    return _compatibility_receipt(command.item_id, state, version)


def _compatibility_receipt(item_id: int, state: str, version: int):
    return {
        "knowledge_item_id": item_id,
        "state": state,
        "version": version,
    }


class MySqlKnowledgeRetrievalRepository:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._delivery_tasks = MySqlLineDeliveryTaskRepository(connection)

    # A knowledge root and its first immutable version must never commit separately.
    def ingest(self, command):
        digest = source_digest(command.content)
        actor_id = _admin_actor_id(command.actor.actor_id)
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO knowledge_items "
                    "(source_identity,source_uri,source_trust_tier,title,content,"
                    "content_digest,state,version,created_by_admin_user_id) "
                    "VALUES (%s,%s,%s,%s,%s,%s,'draft',1,%s)",
                    (
                        command.source_identity, command.source_uri,
                        command.source_trust_tier, command.title,
                        command.content, digest, actor_id,
                    ),
                )
                item_id = int(cursor.lastrowid)
                cursor.execute(_INSERT_VERSION, (
                    item_id, 1, command.content, digest, "ingested", actor_id,
                    None, command.idempotency_key.value,
                ))
                _insert_governance_event(
                    cursor, command, item_id, actor_id, "ingested", 0, 1,
                    "draft", digest,
                )
            return item_id, True
        except IntegrityError as error:
            if mysql_error_code(error) != 1062:
                raise
            existing_id = self._existing_ingest(command.source_identity, digest)
            if existing_id is not None:
                return existing_id, False
            return self._revise_existing(command, digest, actor_id), True

    def review(self, command) -> int:
        return self._transition(command, KnowledgeItemStatus.REVIEWED, "reviewed")

    def publish(self, command) -> int:
        version = self._transition(command, KnowledgeItemStatus.PUBLISHED, "published")
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE knowledge_indexes SET index_status='stale' WHERE index_status='ready'"
            )
        return version

    def retire(self, command) -> int:
        version = self._transition(command, KnowledgeItemStatus.RETIRED, "retired")
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE knowledge_indexes SET index_status='stale' WHERE index_status='ready'"
            )
        return version

    def request_index_build(self, actor_id: str, idempotency_key: str) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT COALESCE(MAX(index_version),0)+1 AS version FROM knowledge_indexes FOR UPDATE")
            version = int(cursor.fetchone()["version"])
            cursor.execute(
                "INSERT INTO knowledge_indexes (index_version,index_status) VALUES (%s,'requested')",
                (version,),
            )
            cursor.execute(
                "INSERT INTO knowledge_jobs (job_type,target_index_version,idempotency_key,created_by_actor_id) "
                "VALUES ('index_build',%s,%s,%s)",
                (version, idempotency_key, actor_id),
            )
            return int(cursor.lastrowid)

    # Request and durable job are one root-fact transaction to prevent orphan work.
    def create_answer_request(self, command):
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO knowledge_answer_requests "
                    "(question,requester_line_user_id,idempotency_key,correlation_id) VALUES (%s,%s,%s,%s)",
                    (command.question, command.requester_line_user_id,
                     command.idempotency_key.value, command.correlation_id.value),
                )
                request_id = int(cursor.lastrowid)
                cursor.execute(
                    "INSERT INTO knowledge_jobs "
                    "(job_type,answer_request_id,question,idempotency_key,created_by_actor_id) "
                    "VALUES ('answer',%s,%s,%s,'system:knowledge-request')",
                    (request_id, command.question, f"knowledge-answer-job:{request_id}"),
                )
            return request_id, True
        except IntegrityError as error:
            if mysql_error_code(error) != 1062:
                raise
            return self._existing_answer_request(command.idempotency_key.value), False

    # The job lease and related request/index projection must move together.
    def claim_next_job(self, worker_id: str):
        now = datetime.now(timezone.utc)
        with self._connection.cursor() as cursor:
            cursor.execute(_CLAIM_JOB, (database_utc(now), database_utc(now)))
            row = cursor.fetchone()
            if row is None:
                return None
            cursor.execute(
                "UPDATE knowledge_jobs SET processing_status='processing',attempt_count=attempt_count+1,"
                "lease_owner=%s,lease_expires_at_utc=%s WHERE id=%s",
                (worker_id, database_utc(now + timedelta(seconds=60)), row["id"]),
            )
            if row["job_type"] == "index_build":
                cursor.execute(
                    "UPDATE knowledge_indexes SET index_status='building' WHERE index_version=%s",
                    (row["target_index_version"],),
                )
            if row["answer_request_id"] is not None:
                cursor.execute(
                    "UPDATE knowledge_answer_requests SET request_status='processing' WHERE id=%s",
                    (row["answer_request_id"],),
                )
        return dict(row)

    def published_items(self):
        with self._connection.cursor() as cursor:
            cursor.execute(_PUBLISHED_ITEMS)
            rows = cursor.fetchall() or ()
        return tuple(dict(row) for row in rows)

    def ready_index_version(self):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT MAX(index_version) AS version FROM knowledge_indexes WHERE index_status='ready'"
            )
            row = cursor.fetchone()
        return None if not row or row["version"] is None else int(row["version"])

    def complete_index(self, job_id: int, index_version: int, content_set_digest: str):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "UPDATE knowledge_indexes SET index_status='ready',content_set_digest=%s,"
                "built_at_utc=CURRENT_TIMESTAMP(6) "
                "WHERE index_version=%s AND index_status IN ('requested','building')",
                (content_set_digest, index_version),
            )
            self._complete_job(cursor, job_id)

    # Receipt, citations, LINE task, request, and job completion are one atomic outcome.
    def complete_answer(self, job_id: int, request_id: int, answer: KnowledgeAnswer):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT requester_line_user_id,correlation_id FROM knowledge_answer_requests "
                "WHERE id=%s FOR UPDATE",
                (request_id,),
            )
            request = cursor.fetchone()
            cursor.execute(
                "INSERT INTO knowledge_answer_receipts "
                "(answer_request_id,answer_text,index_version,authoritative) VALUES (%s,%s,%s,FALSE)",
                (request_id, answer.answer, answer.index_version),
            )
            receipt_id = int(cursor.lastrowid)
            self._insert_citations(cursor, receipt_id, answer)
            task_id = self._enqueue_answer_delivery(request_id, request, answer)
            cursor.execute(
                "UPDATE knowledge_answer_receipts SET line_delivery_task_id=%s WHERE id=%s",
                (task_id, receipt_id),
            )
            cursor.execute(
                "UPDATE knowledge_answer_requests SET request_status='answered',"
                "completed_at_utc=CURRENT_TIMESTAMP(6) WHERE id=%s",
                (request_id,),
            )
            self._complete_job(cursor, job_id)
        return task_id

    # Unsupported is a completed, non-answer outcome with an explicit human fallback.
    def complete_unsupported(self, job_id: int, request_id: int):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT requester_line_user_id,correlation_id FROM knowledge_answer_requests "
                "WHERE id=%s FOR UPDATE",
                (request_id,),
            )
            request = cursor.fetchone()
            task_id = self._enqueue_unsupported_delivery(request_id, request)
            cursor.execute(
                "UPDATE knowledge_answer_requests SET request_status='unsupported',"
                "completed_at_utc=CURRENT_TIMESTAMP(6) WHERE id=%s",
                (request_id,),
            )
            self._complete_job(cursor, job_id)
        return task_id

    def fail_job(self, job_id: int, error_code: str, retryable: bool):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT attempt_count,max_attempts,answer_request_id FROM knowledge_jobs WHERE id=%s FOR UPDATE", (job_id,))
            row = cursor.fetchone()
            retry = retryable and int(row["attempt_count"]) < int(row["max_attempts"])
            status = "retry_pending" if retry else "failed"
            cursor.execute(
                "UPDATE knowledge_jobs SET processing_status=%s,last_error_code=%s,"
                "lease_owner=NULL,lease_expires_at_utc=NULL,available_at_utc=%s WHERE id=%s",
                (status, error_code, database_utc(datetime.now(timezone.utc) + timedelta(seconds=30)), job_id),
            )
            if row["answer_request_id"] and not retry:
                cursor.execute("UPDATE knowledge_answer_requests SET request_status='failed' WHERE id=%s", (row["answer_request_id"],))

    def list_items(self, limit: int, lifecycle_status: str | None = None):
        return self._rows(_LIST_ITEMS, (lifecycle_status, lifecycle_status, limit))

    def get_item(self, item_id: int):
        rows = self._rows(_GET_ITEM, (item_id,))
        return rows[0] if rows else None

    def list_jobs(self, limit: int, processing_status: str | None = None):
        return self._rows(_LIST_JOBS, (processing_status, processing_status, limit))

    def list_indexes(self, limit: int):
        return self._rows(_LIST_INDEXES, (limit,))

    def get_answer_request(self, request_id: int):
        rows = self._rows(_GET_ANSWER_REQUEST, (request_id,))
        if not rows:
            return None
        result = rows[0]
        if result.get("authoritative") is not None:
            result["authoritative"] = bool(result["authoritative"])
        result["citations"] = self._rows(_GET_ANSWER_SOURCES, (request_id,))
        return result

    # A manual retry is a new durable job so its idempotency identity remains immutable.
    def retry_job(self, job_id: int, actor_id: str, idempotency_key: str) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT id FROM knowledge_jobs WHERE idempotency_key=%s", (idempotency_key,))
            existing = cursor.fetchone()
            if existing:
                return int(existing["id"])
            cursor.execute("SELECT * FROM knowledge_jobs WHERE id=%s FOR UPDATE", (job_id,))
            source = cursor.fetchone()
            if source is None:
                raise LookupError("knowledge_job_not_found")
            if source["processing_status"] != "failed":
                raise RuntimeError("knowledge_job_state_conflict")
            cursor.execute(_INSERT_RETRY_JOB, _retry_job_values(source, actor_id, idempotency_key))
            retry_id = int(cursor.lastrowid)
            self._reset_retry_projection(cursor, source)
        return retry_id

    def _reset_retry_projection(self, cursor, source) -> None:
        if source["answer_request_id"] is not None:
            cursor.execute(
                "UPDATE knowledge_answer_requests SET request_status='pending',completed_at_utc=NULL WHERE id=%s",
                (source["answer_request_id"],),
            )
        if source["target_index_version"] is not None:
            cursor.execute(
                "UPDATE knowledge_indexes SET index_status='requested' WHERE index_version=%s",
                (source["target_index_version"],),
            )

    def next_due_at(self):
        rows = self._rows("SELECT MIN(available_at_utc) AS due_at FROM knowledge_jobs WHERE processing_status IN ('pending','retry_pending')")
        return rows[0]["due_at"] if rows and rows[0]["due_at"] else None

    # Version CAS, append-only event, and current projection cannot be split safely.
    def _transition(self, command, target, event_type):
        with self._connection.cursor() as cursor:
            cursor.execute(_LOCK_ITEM, (command.item_id,))
            item = cursor.fetchone()
            if item is None:
                raise LookupError("knowledge_item_not_found")
            if int(item["version"]) != command.expected_version.value:
                raise RuntimeError("knowledge_item_version_conflict")
            transition_item_status(KnowledgeItemStatus(item["state"]), target)
            actor_id = _admin_actor_id(command.actor.actor_id)
            _enforce_actor_separation(item, target, actor_id)
            next_version = command.expected_version.value + 1
            cursor.execute(_CURRENT_CONTENT, (command.item_id, command.expected_version.value))
            version = cursor.fetchone()
            cursor.execute(_INSERT_VERSION, (
                command.item_id, next_version, version["content"], version["source_digest"],
                event_type, actor_id, command.reason, command.idempotency_key.value,
            ))
            update_sql, update_values = _transition_projection_update(
                target, actor_id, command.reason,
            )
            cursor.execute(
                f"UPDATE knowledge_items SET state=%s,version=%s,{update_sql} "
                "WHERE id=%s AND version=%s",
                (
                    target.value, next_version, *update_values,
                    command.item_id, command.expected_version.value,
                ),
            )
            _insert_governance_event(
                cursor, command, command.item_id, actor_id, event_type,
                command.expected_version.value, next_version, target.value,
                version["source_digest"],
            )
        return next_version

    def _insert_citations(self, cursor, receipt_id, answer):
        for order, citation in enumerate(answer.citations, start=1):
            cursor.execute(
                "INSERT INTO knowledge_answer_sources "
                "(answer_receipt_id,source_identity,source_version,safe_excerpt,citation_order) "
                "VALUES (%s,%s,%s,%s,%s)",
                (receipt_id, citation.source_identity, citation.source_version, citation.safe_excerpt, order),
            )

    def _enqueue_answer_delivery(self, request_id, request, answer):
        line_user_id = request["requester_line_user_id"]
        if not line_user_id:
            return None
        citations = "\n".join(f"來源：{item.source_identity} v{item.source_version}" for item in answer.citations)
        payload = canonical_line_payload_json({"type": "text", "text": f"{answer.answer}\n\n{citations}\n\n此內容僅供參考，非正式決策。"})
        delivery = LineDeliveryRequest(
            LineRecipient(LineRecipientType.USER, LineUserId(str(line_user_id))),
            LineMessageKind.TEXT, payload, datetime.now(timezone.utc),
            IdempotencyKey(f"knowledge-answer-delivery:{request_id}"),
            CorrelationId(str(request["correlation_id"])),
            "knowledge_answer_request", str(request_id),
        )
        return self._delivery_tasks.enqueue(delivery).task_id.value

    def _enqueue_unsupported_delivery(self, request_id, request):
        line_user_id = request["requester_line_user_id"]
        if not line_user_id:
            return None
        payload = canonical_line_payload_json(
            {
                "type": "text",
                "text": "目前沒有可引用的已核准答案，請聯絡工會人員協助確認。",
            }
        )
        delivery = LineDeliveryRequest(
            LineRecipient(LineRecipientType.USER, LineUserId(str(line_user_id))),
            LineMessageKind.TEXT,
            payload,
            datetime.now(timezone.utc),
            IdempotencyKey(f"knowledge-unsupported-delivery:{request_id}"),
            CorrelationId(str(request["correlation_id"])),
            "knowledge_answer_request",
            str(request_id),
        )
        return self._delivery_tasks.enqueue(delivery).task_id.value

    def _complete_job(self, cursor, job_id):
        cursor.execute(
            "UPDATE knowledge_jobs SET processing_status='completed',lease_owner=NULL,"
            "lease_expires_at_utc=NULL,completed_at_utc=CURRENT_TIMESTAMP(6) WHERE id=%s",
            (job_id,),
        )

    def _existing_ingest(self, identity, digest):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id,content_digest FROM knowledge_items WHERE source_identity=%s",
                (identity,),
            )
            row = cursor.fetchone()
        if row is None or row["content_digest"] != digest:
            return None
        return int(row["id"])

    # New source version and index staleness are one consistency boundary.
    def _revise_existing(self, command, digest, actor_id):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id,version FROM knowledge_items "
                "WHERE source_identity=%s FOR UPDATE",
                (command.source_identity,),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("knowledge_source_conflict")
            before_version = int(row["version"])
            next_version = before_version + 1
            cursor.execute(_INSERT_VERSION, (
                row["id"], next_version, command.content, digest, "ingested",
                actor_id, None, command.idempotency_key.value,
            ))
            cursor.execute(
                "UPDATE knowledge_items SET title=%s,content=%s,content_digest=%s,"
                "source_uri=%s,source_trust_tier=%s,state='draft',version=%s,"
                "reviewed_by_admin_user_id=NULL,published_by_admin_user_id=NULL,"
                "review_reason=NULL,publication_reason=NULL,published_at=NULL "
                "WHERE id=%s",
                (
                    command.title, command.content, digest, command.source_uri,
                    command.source_trust_tier, next_version, row["id"],
                ),
            )
            _insert_governance_event(
                cursor, command, int(row["id"]), actor_id, "ingested",
                before_version, next_version, "draft", digest,
            )
            cursor.execute("UPDATE knowledge_indexes SET index_status='stale' WHERE index_status='ready'")
        return int(row["id"])

    def _existing_answer_request(self, key):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT id FROM knowledge_answer_requests WHERE idempotency_key=%s", (key,))
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("knowledge_answer_idempotency_conflict")
        return int(row["id"])

    def _rows(self, sql, parameters=()):
        with self._connection.cursor() as cursor:
            cursor.execute(sql, parameters)
            return tuple(dict(row) for row in (cursor.fetchall() or ()))


class MySqlKnowledgeQuestionIntakeAdapter:
    """Narrow cross-domain port used inside the canonical LINE event transaction."""

    def __init__(self, connection) -> None:
        self._repository = MySqlKnowledgeRetrievalRepository(connection)

    def create_answer_request(self, command):
        return self._repository.create_answer_request(command)


def _admin_actor_id(actor_id: str) -> int:
    try:
        value = int(actor_id)
    except (TypeError, ValueError) as error:
        raise ValueError("knowledge_admin_identity_required") from error
    if value < 1:
        raise ValueError("knowledge_admin_identity_required")
    return value


def _enforce_actor_separation(item, target, actor_id: int) -> None:
    creator_id = int(item["created_by_admin_user_id"])
    if target is KnowledgeItemStatus.REVIEWED:
        require_separate_reviewer(creator_id, actor_id)
    if target is KnowledgeItemStatus.PUBLISHED:
        require_separate_publisher(creator_id, actor_id)


def _transition_projection_update(target, actor_id: int, reason: str):
    if target is KnowledgeItemStatus.REVIEWED:
        return "reviewed_by_admin_user_id=%s,review_reason=%s", (actor_id, reason)
    if target is KnowledgeItemStatus.PUBLISHED:
        return (
            "published_by_admin_user_id=%s,publication_reason=%s,"
            "published_at=UTC_TIMESTAMP()",
            (actor_id, reason),
        )
    return (
        "retired_by_admin_user_id=%s,retired_reason=%s,retired_at=UTC_TIMESTAMP()",
        (actor_id, reason),
    )


def _insert_governance_event(
    cursor,
    command,
    item_id: int,
    actor_id: int,
    event_type: str,
    before_version: int,
    after_version: int,
    state: str,
    digest: str,
) -> None:
    snapshot = {
        "knowledge_item_id": item_id,
        "state": state,
        "version": after_version,
        "source_identity": command.source_identity
        if hasattr(command, "source_identity") else None,
        "content_digest": digest,
    }
    receipt_json = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
    cursor.execute(
        "INSERT INTO knowledge_item_events "
        "(knowledge_item_id,actor_admin_user_id,event_type,before_version,"
        "after_version,reason,idempotency_key,correlation_id,snapshot_json) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            item_id, actor_id, event_type, before_version, after_version,
            command.reason if hasattr(command, "reason") else "knowledge source ingested",
            command.idempotency_key.value, command.correlation_id.value, receipt_json,
        ),
    )
    fingerprint = hashlib.sha256(
        repr(command).encode("utf-8")
    ).hexdigest()
    cursor.execute(
        "INSERT INTO knowledge_apply_receipts "
        "(idempotency_key,command_fingerprint,receipt_json) VALUES (%s,%s,%s)",
        (command.idempotency_key.value, fingerprint, receipt_json),
    )


_INSERT_VERSION = """INSERT INTO knowledge_item_versions
(item_id,item_version,content,source_digest,event_type,actor_admin_user_id,reason,idempotency_key)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"""
_LOCK_ITEM = """SELECT id,state,version,created_by_admin_user_id,
reviewed_by_admin_user_id FROM knowledge_items WHERE id=%s FOR UPDATE"""
_CURRENT_CONTENT = "SELECT content,source_digest FROM knowledge_item_versions WHERE item_id=%s AND item_version=%s"
_CLAIM_JOB = """SELECT * FROM knowledge_jobs WHERE processing_status IN ('pending','retry_pending')
AND available_at_utc<=%s AND (lease_expires_at_utc IS NULL OR lease_expires_at_utc<=%s)
ORDER BY available_at_utc,id LIMIT 1 FOR UPDATE SKIP LOCKED"""
_PUBLISHED_ITEMS = """SELECT i.source_identity,i.title,i.version AS source_version,
v.content,i.content_digest AS source_digest,i.source_uri FROM knowledge_items i
JOIN knowledge_item_versions v ON v.item_id=i.id AND v.item_version=i.version
WHERE i.state='published'
ORDER BY i.id"""
_LIST_ITEMS = """SELECT id,source_identity,source_trust_tier,title,
state AS lifecycle_status,version AS current_version,
content_digest AS source_digest,source_uri,updated_at AS updated_at_utc
FROM knowledge_items WHERE (%s IS NULL OR state=%s)
ORDER BY updated_at DESC,id DESC LIMIT %s"""
_GET_ITEM = """SELECT i.id,i.source_identity,i.source_trust_tier,i.title,
i.state AS lifecycle_status,i.version AS current_version,
i.content_digest AS source_digest,i.source_uri,i.updated_at AS updated_at_utc,
v.content FROM knowledge_items i
JOIN knowledge_item_versions v ON v.item_id=i.id AND v.item_version=i.version
WHERE i.id=%s"""
_LIST_JOBS = """SELECT id,job_type,processing_status,answer_request_id,target_index_version,
attempt_count,max_attempts,last_error_code,created_at_utc,completed_at_utc FROM knowledge_jobs
WHERE (%s IS NULL OR processing_status=%s) ORDER BY created_at_utc DESC,id DESC LIMIT %s"""
_LIST_INDEXES = """SELECT index_version,index_status,content_set_digest,built_at_utc,created_at_utc
FROM knowledge_indexes ORDER BY index_version DESC LIMIT %s"""
_GET_ANSWER_REQUEST = """SELECT q.id,q.question,q.request_status,q.correlation_id,q.created_at_utc,
q.completed_at_utc,r.answer_text,r.index_version,r.authoritative,r.line_delivery_task_id,r.answered_at_utc
FROM knowledge_answer_requests q LEFT JOIN knowledge_answer_receipts r ON r.answer_request_id=q.id
WHERE q.id=%s"""
_GET_ANSWER_SOURCES = """SELECT s.source_identity,s.source_version,s.safe_excerpt,s.citation_order
FROM knowledge_answer_sources s JOIN knowledge_answer_receipts r ON r.id=s.answer_receipt_id
WHERE r.answer_request_id=%s ORDER BY s.citation_order"""
_INSERT_RETRY_JOB = """INSERT INTO knowledge_jobs
(job_type,answer_request_id,target_index_version,question,idempotency_key,created_by_actor_id)
VALUES (%s,%s,%s,%s,%s,%s)"""


def _retry_job_values(source, actor_id, idempotency_key):
    return (
        source["job_type"], source["answer_request_id"], source["target_index_version"],
        source["question"], idempotency_key, actor_id,
    )


__all__ = [
    "MySqlKnowledgeQuestionIntakeAdapter",
    "MySqlKnowledgeRetrievalRepository",
]
