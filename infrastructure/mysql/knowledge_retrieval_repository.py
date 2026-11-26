"""MySQL SSOT for published knowledge, durable jobs, and answer receipts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pymysql.err import IntegrityError

from domains.knowledge_retrieval.knowledge import (
    KnowledgeAnswer,
    KnowledgeAnswerUnsupported,
    KnowledgeItemStatus,
    source_digest,
    transition_item_status,
)
from domains.knowledge_retrieval.qa_catalog import (
    QA_SOURCE_PREFIX, decode_governed_qa, format_line_faq_reply, line_faq_reply_fits,
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
from subsystems.line.feedback_contracts import (
    KNOWLEDGE_LIFF_RESULT_PREFIX,
    KnowledgeAnswerFeedbackContext,
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
                f"SELECT snapshot.id,snapshot.source_uri,snapshot.title,snapshot.content,"
                f"snapshot.source_digest AS content_digest,snapshot.source_version AS version,"
                f"snapshot.published_at FROM ({_PUBLISHED_SNAPSHOT}) snapshot "
                "WHERE snapshot.title LIKE %s OR snapshot.content LIKE %s "
                "ORDER BY snapshot.published_at DESC,snapshot.id DESC LIMIT 3",
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
    if not all((command.idempotency_key.strip(), command.correlation_id.strip())):
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
        governed_qa = decode_governed_qa(command.content)
        if governed_qa is not None:
            if command.source_identity != governed_qa.source_identity:
                raise ValueError("knowledge_qa_identity_mismatch")
        elif command.source_identity.startswith(QA_SOURCE_PREFIX):
            raise ValueError("knowledge_qa_content_invalid")
        actor_id = _admin_actor_id(command.actor.actor_id)
        with self._connection.cursor() as cursor:
            receipt = _claim_governance_receipt(cursor, command)
            if receipt is not None:
                return int(receipt["knowledge_item_id"]), bool(receipt.get("created", True))
            if command.expected_version is not None:
                return self._revise_existing(command, digest, actor_id)
            try:
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
            except IntegrityError as error:
                if mysql_error_code(error) != 1062:
                    raise
                return self._revise_existing(command, digest, actor_id)

            item_id = int(cursor.lastrowid)
            cursor.execute(_INSERT_VERSION, (
                item_id, 1, command.content, digest, "ingested", actor_id,
                None, command.idempotency_key.value, command.title,
                command.source_uri, command.source_trust_tier,
            ))
            _insert_governance_event(
                cursor, command, item_id, actor_id, "ingested", 0, 1,
                "draft", digest,
            )
        return item_id, True

    def review(self, command) -> int:
        """Preserved internal compatibility; current UI publishes drafts directly."""
        return self._transition(command, KnowledgeItemStatus.REVIEWED, "reviewed")

    def publish(self, command) -> int:
        return self._transition(command, KnowledgeItemStatus.PUBLISHED, "published")

    def retire(self, command) -> int:
        return self._transition(command, KnowledgeItemStatus.RETIRED, "retired")

    def request_index_build(self, actor_id: str, idempotency_key: str) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id,created_by_actor_id,job_type FROM knowledge_jobs WHERE idempotency_key=%s",
                (idempotency_key,),
            )
            job = cursor.fetchone()
            if job is not None:
                if job["job_type"] != "index_build" or job["created_by_actor_id"] != actor_id:
                    raise RuntimeError("knowledge_idempotency_conflict")
                return int(job["id"])
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

    # LIFF renders the answer in-page, so the existing request/receipt roots are
    # committed without creating a LINE delivery task or an answer worker job.
    def record_inline_answer(self, command, answer: KnowledgeAnswer) -> int:
        if not command.requester_line_user_id:
            raise ValueError("knowledge_inline_answer_actor_required")
        self._require_published_citations(answer)
        try:
            with self._connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO knowledge_answer_requests "
                    "(question,requester_line_user_id,idempotency_key,correlation_id,"
                    "request_status,completed_at_utc) "
                    "VALUES (%s,%s,%s,%s,'answered',CURRENT_TIMESTAMP(6))",
                    (
                        command.question,
                        command.requester_line_user_id,
                        command.idempotency_key.value,
                        command.correlation_id.value,
                    ),
                )
                request_id = int(cursor.lastrowid)
                cursor.execute(
                    "INSERT INTO knowledge_answer_receipts "
                    "(answer_request_id,answer_text,index_version,authoritative) "
                    "VALUES (%s,%s,%s,FALSE)",
                    (request_id, answer.answer, answer.index_version),
                )
                receipt_id = int(cursor.lastrowid)
                self._insert_citations(cursor, receipt_id, answer)
            return receipt_id
        except IntegrityError as error:
            if mysql_error_code(error) != 1062:
                raise
            return self._existing_inline_answer_receipt(command, answer)

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

    def published_faq_by_id(self, qa_id: str, *, predecessor=False):
        query = self._faq_publication_query(predecessor)
        return self._rows(
            f"{query} AND {_FAQ_ID_ORDER}=%s",
            (QA_SOURCE_PREFIX + qa_id,),
        )

    def published_faq_page(self, cursor: str | None, limit: int, *, predecessor=False):
        query = self._faq_publication_query(predecessor)
        after = "" if cursor is None else f" AND {_FAQ_ID_ORDER}>%s"
        args = () if cursor is None else (QA_SOURCE_PREFIX + cursor,)
        return self._rows(
            f"{query}{after} ORDER BY {_FAQ_ID_ORDER} LIMIT %s",
            (*args, limit),
        )

    def published_faq_by_alias(self, text: str, *, predecessor=False):
        query = self._faq_publication_query(predecessor)
        return self._rows(
            f"{query} AND ("
            f"BINARY TRIM(JSON_UNQUOTE(JSON_EXTRACT({_FAQ_PAYLOAD},'$.question')))=BINARY %s "
            f"OR JSON_CONTAINS({_FAQ_PAYLOAD},JSON_QUOTE(%s),'$.aliases'))",
            (text, text),
        )

    def faq_by_legacy_text(self, text: str):
        self._require_faq_backfill()
        return self._rows(
            f"{_FAQ_SNAPSHOT} WHERE {_IS_FAQ} "
            "AND JSON_CONTAINS(i.faq_legacy_aliases,JSON_QUOTE(%s))",
            (text,),
        )

    def predecessor_faq_identity_exists(self, qa_id: str) -> bool:
        rows = self._rows(
            f"SELECT i.id FROM knowledge_items i WHERE {_FAQ_ID_ORDER}=%s",
            (QA_SOURCE_PREFIX + qa_id,),
        )
        return bool(rows)

    def _faq_publication_query(self, predecessor: bool) -> str:
        if predecessor:
            return _PREDECESSOR_PUBLISHED_FAQ
        self._require_faq_backfill()
        return _PUBLISHED_FAQ

    def _require_faq_backfill(self) -> None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                f"SELECT i.id FROM knowledge_items i WHERE {_IS_FAQ} "
                "AND i.published_version IS NULL AND (i.state='published' OR ("
                "i.state IN ('draft','reviewed') AND (SELECT v.event_type FROM knowledge_item_versions v "
                "WHERE v.item_id=i.id AND v.event_type IN ('published','retired') "
                "ORDER BY v.item_version DESC LIMIT 1)='published')) LIMIT 1"
            )
            if cursor.fetchone() is not None:
                raise RuntimeError("knowledge_faq_backfill_required")

    def published_source_versions(self, source_identities: tuple[str, ...], *, lock=False):
        if not source_identities:
            return set()
        marks = ",".join("%s" for _ in source_identities)
        rows = self._rows(
            f"SELECT i.source_identity,v.item_version FROM knowledge_items i "
            f"JOIN knowledge_item_versions v ON v.item_id=i.id AND v.item_version=({_ACTIVE_VERSION}) "
            f"AND v.event_type='published' WHERE i.source_identity IN ({marks})" + (" FOR SHARE" if lock else ""),
            source_identities,
        )
        return {(row["source_identity"], int(row["item_version"])) for row in rows}

    def ready_index_version(self):
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT MAX(index_version) AS version FROM knowledge_indexes WHERE index_status='ready'"
            )
            row = cursor.fetchone()
        return None if not row or row["version"] is None else int(row["version"])

    def recent_conversation_history(self, answer_request_id: int, limit: int = 3) -> tuple[dict[str, str], ...]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT requester_line_user_id FROM knowledge_answer_requests WHERE id=%s",
                (answer_request_id,),
            )
            row = cursor.fetchone()
            if not row or not row["requester_line_user_id"]:
                return ()
            user_id = row["requester_line_user_id"]
            cursor.execute(
                "SELECT req.question, r.answer_text "
                "FROM knowledge_answer_receipts r "
                "JOIN knowledge_answer_requests req ON r.answer_request_id = req.id "
                "WHERE req.requester_line_user_id=%s AND req.id != %s "
                "ORDER BY r.id DESC LIMIT %s",
                (user_id, answer_request_id, limit),
            )
            history_rows = cursor.fetchall() or ()
            return tuple(
                {"question": str(h["question"]), "answer": str(h["answer_text"])}
                for h in reversed(history_rows)
            )

    def feedback_context(
        self,
        answer_receipt_id: int,
        actor_id: str,
    ) -> KnowledgeAnswerFeedbackContext | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT receipt.id,receipt.line_delivery_task_id FROM knowledge_answer_receipts receipt "
                "JOIN knowledge_answer_requests request "
                "ON request.id=receipt.answer_request_id "
                "LEFT JOIN line_delivery_tasks task ON task.id=receipt.line_delivery_task_id "
                "WHERE receipt.id=%s AND request.requester_line_user_id=%s "
                "AND request.request_status='answered' "
                "AND (receipt.line_delivery_task_id IS NULL OR task.processing_status='sent')",
                (answer_receipt_id, actor_id),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return KnowledgeAnswerFeedbackContext(
            source_response_id=f"knowledge-answer-receipt:{int(row['id'])}",
            response_revision=1,
            rule_revision=None,
            line_delivery_task_id=row["line_delivery_task_id"],
        )

    def inline_result_feedback_context(
        self,
        request_id: int,
        actor_id: str,
    ) -> KnowledgeAnswerFeedbackContext | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT requester_line_user_id FROM knowledge_answer_requests "
                "WHERE id=%s AND requester_line_user_id=%s "
                "AND SUBSTR(idempotency_key,1,LENGTH('liff-knowledge-answer:'))='liff-knowledge-answer:' "
                "AND request_status IN ('unsupported','failed')",
                (request_id, actor_id),
            )
            row = cursor.fetchone()
        if row is None or row["requester_line_user_id"] != actor_id:
            return None
        return KnowledgeAnswerFeedbackContext(
            source_response_id=f"{KNOWLEDGE_LIFF_RESULT_PREFIX}{request_id}",
            response_revision=1,
            rule_revision=None,
        )

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
        self._require_published_citations(answer)
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
            task_id = self._enqueue_answer_delivery(request_id, receipt_id, request, answer)
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

    def find_by_source_identity(self, source_identity: str):
        rows = self._rows(_GET_ITEM_BY_SOURCE_IDENTITY, (source_identity,))
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

    def list_answer_requests(self, limit: int, request_status: str | None = None):
        return self._rows(
            _LIST_ANSWER_REQUESTS,
            (request_status, request_status, limit),
        )

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
        try:
            with self._connection.cursor() as cursor:
                receipt = _claim_governance_receipt(cursor, command)
                if receipt is not None:
                    return int(receipt["version"])
                cursor.execute(_LOCK_ITEM, (command.item_id,))
                item = cursor.fetchone()
                if item is None:
                    raise LookupError("knowledge_item_not_found")
                if int(item["version"]) != command.expected_version.value:
                    raise RuntimeError("knowledge_item_version_conflict")
                governed_qa = decode_governed_qa(item["content"])
                current_state = KnowledgeItemStatus(item["state"])
                published_version = item["published_version"]
                if governed_qa is not None and target is KnowledgeItemStatus.RETIRED:
                    # FAQ can still have an official version while the editing head is a draft.
                    current_state = (
                        KnowledgeItemStatus.PUBLISHED if published_version is not None
                        else KnowledgeItemStatus.DRAFT
                    )
                transition_item_status(current_state, target)
                if governed_qa is not None and target is KnowledgeItemStatus.PUBLISHED:
                    governed_qa.require_publishable()
                    if not line_faq_reply_fits(format_line_faq_reply(governed_qa.answer, governed_qa.source_ref)):
                        raise ValueError("knowledge_qa_line_reply_too_long")

                actor_id = _admin_actor_id(command.actor.actor_id)
                next_version = command.expected_version.value + 1
                cursor.execute(_INSERT_VERSION, (
                    command.item_id, next_version, item["content"], item["source_digest"],
                    event_type, actor_id, command.reason, command.idempotency_key.value,
                    item["title"], item["source_uri"], item["source_trust_tier"],
                ))
                if target is KnowledgeItemStatus.PUBLISHED:
                    published_version = next_version if governed_qa is not None else None
                elif target is KnowledgeItemStatus.RETIRED:
                    published_version = None
                update_sql, update_values = _transition_projection_update(
                    target, actor_id, command.reason,
                )
                cursor.execute(
                    f"UPDATE knowledge_items SET state=%s,version=%s,published_version=%s,{update_sql} "
                    "WHERE id=%s AND version=%s",
                    (
                        target.value, next_version, published_version, *update_values,
                        command.item_id, command.expected_version.value,
                    ),
                )
                _insert_governance_event(
                    cursor, command, command.item_id, actor_id, event_type,
                    command.expected_version.value, next_version, target.value,
                    item["source_digest"],
                )
                if target in (KnowledgeItemStatus.PUBLISHED, KnowledgeItemStatus.RETIRED):
                    cursor.execute(_STALE_INDEXES)
        except IntegrityError as error:
            if mysql_error_code(error) == 1062:
                raise RuntimeError("knowledge_idempotency_conflict") from error
            raise
        return next_version

    def _require_published_citations(self, answer: KnowledgeAnswer) -> None:
        cited = {(citation.source_identity, citation.source_version) for citation in answer.citations}
        source_identities = tuple(sorted({identity for identity, _ in cited}))
        if not cited <= self.published_source_versions(source_identities, lock=True):
            raise KnowledgeAnswerUnsupported("knowledge_answer_unsupported")

    def _insert_citations(self, cursor, receipt_id, answer):
        for order, citation in enumerate(answer.citations, start=1):
            cursor.execute(
                "INSERT INTO knowledge_answer_sources "
                "(answer_receipt_id,source_identity,source_version,safe_excerpt,citation_order) "
                "VALUES (%s,%s,%s,%s,%s)",
                (receipt_id, citation.source_identity, citation.source_version, citation.safe_excerpt, order),
            )

    def _enqueue_answer_delivery(self, request_id, receipt_id, request, answer):
        line_user_id = request["requester_line_user_id"]
        if not line_user_id:
            return None
        payload = canonical_line_payload_json({
            "type": "text",
            "text": _public_line_answer_text(answer.answer),
            "quickReply": {
                "items": [
                    {
                        "type": "action",
                        "action": {
                            "type": "postback",
                            "label": "👍 有幫助",
                            "data": f"feedback:knowledge:{receipt_id}:resolved",
                            "displayText": "有幫助",
                        },
                    },
                    {
                        "type": "action",
                        "action": {
                            "type": "postback",
                            "label": "👎 未解決",
                            "data": f"feedback:knowledge:{receipt_id}:unresolved",
                            "displayText": "未解決",
                        },
                    },
                ]
            },
        })
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
        payload = canonical_line_payload_json(_unsupported_faq_payload())
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

    def _revise_existing(self, command, digest, actor_id) -> tuple[int, bool]:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT id,source_identity,version,content_digest FROM knowledge_items "
                "WHERE source_identity=%s FOR UPDATE",
                (command.source_identity,),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("knowledge_source_conflict")

            before_version = int(row["version"])
            governed_qa = command.source_identity.startswith(QA_SOURCE_PREFIX)
            if governed_qa and row["source_identity"] != command.source_identity:
                raise RuntimeError("knowledge_source_conflict")
            if command.expected_version is not None:
                if command.expected_version.value != before_version:
                    raise RuntimeError("knowledge_item_version_conflict")
            elif row["content_digest"] == digest:
                _finish_governance_receipt(cursor, command, {
                    "knowledge_item_id": int(row["id"]),
                    "version": before_version,
                    "created": False,
                })
                return int(row["id"]), False
            elif governed_qa:
                raise RuntimeError("knowledge_item_version_conflict")

            next_version = before_version + 1
            cursor.execute(_INSERT_VERSION, (
                row["id"], next_version, command.content, digest, "ingested",
                actor_id, None, command.idempotency_key.value, command.title,
                command.source_uri, command.source_trust_tier,
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
            if not governed_qa:
                cursor.execute(_STALE_INDEXES)
        return int(row["id"]), True

    def _existing_answer_request(self, key):
        with self._connection.cursor() as cursor:
            cursor.execute("SELECT id FROM knowledge_answer_requests WHERE idempotency_key=%s", (key,))
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("knowledge_answer_idempotency_conflict")
        return int(row["id"])

    def _existing_inline_answer_receipt(self, command, answer: KnowledgeAnswer) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(
                "SELECT request.id AS request_id,request.question,"
                "request.requester_line_user_id,request.correlation_id,"
                "request.request_status,receipt.id AS receipt_id,receipt.answer_text,"
                "receipt.index_version,receipt.line_delivery_task_id "
                "FROM knowledge_answer_requests request "
                "LEFT JOIN knowledge_answer_receipts receipt "
                "ON receipt.answer_request_id=request.id "
                "WHERE request.idempotency_key=%s",
                (command.idempotency_key.value,),
            )
            row = cursor.fetchone()
            if row is None:
                raise RuntimeError("knowledge_answer_idempotency_conflict")
            expected = (
                command.question,
                command.requester_line_user_id,
                command.correlation_id.value,
                "answered",
                answer.answer,
                answer.index_version,
                None,
            )
            actual = (
                str(row["question"]),
                str(row["requester_line_user_id"]),
                str(row["correlation_id"]),
                str(row["request_status"]),
                None if row["answer_text"] is None else str(row["answer_text"]),
                None if row["index_version"] is None else int(row["index_version"]),
                row["line_delivery_task_id"],
            )
            if actual != expected or row["receipt_id"] is None:
                raise RuntimeError("knowledge_answer_idempotency_conflict")
            cursor.execute(
                "SELECT source_identity,source_version,safe_excerpt,citation_order "
                "FROM knowledge_answer_sources WHERE answer_receipt_id=%s "
                "ORDER BY citation_order",
                (row["receipt_id"],),
            )
            citation_rows = tuple(cursor.fetchall() or ())
        actual_citations = tuple(
            (
                str(item["source_identity"]),
                int(item["source_version"]),
                str(item["safe_excerpt"]),
                int(item["citation_order"]),
            )
            for item in citation_rows
        )
        expected_citations = tuple(
            (
                citation.source_identity,
                citation.source_version,
                citation.safe_excerpt,
                order,
            )
            for order, citation in enumerate(answer.citations, start=1)
        )
        if actual_citations != expected_citations:
            raise RuntimeError("knowledge_answer_idempotency_conflict")
        return int(row["receipt_id"])

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

    def feedback_context(
        self,
        answer_receipt_id: int,
        actor_id: str,
    ) -> KnowledgeAnswerFeedbackContext | None:
        return self._repository.feedback_context(answer_receipt_id, actor_id)


def _admin_actor_id(actor_id: str) -> int:
    try:
        value = int(actor_id)
    except (TypeError, ValueError) as error:
        raise ValueError("knowledge_admin_identity_required") from error
    if value < 1:
        raise ValueError("knowledge_admin_identity_required")
    return value


def _public_line_answer_text(answer: str) -> str:
    text = answer.strip()
    prefix = "原始回答為"
    if text.startswith(prefix):
        public_text = text[len(prefix):].lstrip("：: ")
        if public_text:
            return public_text
    return text


def _unsupported_faq_payload() -> dict[str, Any]:
    topics = ("服務流程", "收費與補助", "查詢服務進度", "修改登記資料", "其他問題")
    return {
        "type": "text",
        "text": "請從下方常見問答選擇主題，或換一種方式輸入您的問題。",
        "quickReply": {
            "items": [
                {
                    "type": "action",
                    "action": {"type": "message", "label": topic, "text": topic},
                }
                for topic in topics
            ]
        },
    }


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
    _finish_governance_receipt(cursor, command, snapshot)


def _command_fingerprint(command) -> str:
    canonical = replace(command, correlation_id=CorrelationId(command.idempotency_key.value))
    return hashlib.sha256(repr(canonical).encode("utf-8")).hexdigest()


def _claim_governance_receipt(cursor, command) -> dict | None:
    key = command.idempotency_key.value
    fingerprint = _command_fingerprint(command)
    try:
        cursor.execute(
            "INSERT INTO knowledge_apply_receipts "
            "(idempotency_key,command_fingerprint,receipt_json) VALUES (%s,%s,'{}')",
            (key, fingerprint),
        )
        return None
    except IntegrityError as error:
        if mysql_error_code(error) != 1062:
            raise

    cursor.execute(
        "SELECT command_fingerprint,receipt_json FROM knowledge_apply_receipts "
        "WHERE idempotency_key=%s FOR SHARE",
        (key,),
    )
    row = cursor.fetchone()
    original = repr(command)
    compatible = {fingerprint, hashlib.sha256(original.encode("utf-8")).hexdigest()}
    if isinstance(command, IngestKnowledgeSourceCommand) and command.expected_version is None:
        legacy = original.removesuffix(", expected_version=None)") + ")"
        compatible.add(hashlib.sha256(legacy.encode("utf-8")).hexdigest())
    if row["command_fingerprint"] not in compatible:
        raise RuntimeError("knowledge_idempotency_conflict")
    return json.loads(row["receipt_json"])


def _finish_governance_receipt(cursor, command, snapshot: dict) -> None:
    cursor.execute(
        "UPDATE knowledge_apply_receipts SET receipt_json=%s WHERE idempotency_key=%s",
        (json.dumps(snapshot, ensure_ascii=False, sort_keys=True), command.idempotency_key.value),
    )


_INSERT_VERSION = """INSERT INTO knowledge_item_versions
(item_id,item_version,content,source_digest,event_type,actor_admin_user_id,reason,idempotency_key,
title,source_uri,source_trust_tier)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
_LOCK_ITEM = """SELECT i.id,i.state,i.version,i.published_version,v.content,v.source_digest,
COALESCE(v.title,i.title) AS title,COALESCE(v.source_uri,i.source_uri) AS source_uri,
COALESCE(v.source_trust_tier,i.source_trust_tier) AS source_trust_tier
FROM knowledge_items i JOIN knowledge_item_versions v
ON v.item_id=i.id AND v.item_version=i.version WHERE i.id=%s FOR UPDATE"""
_STALE_INDEXES = "UPDATE knowledge_indexes SET index_status='stale' WHERE index_status='ready'"
_CLAIM_JOB = """SELECT * FROM knowledge_jobs WHERE processing_status IN ('pending','retry_pending')
AND available_at_utc<=%s AND (lease_expires_at_utc IS NULL OR lease_expires_at_utc<=%s)
ORDER BY available_at_utc,id LIMIT 1 FOR UPDATE SKIP LOCKED"""
_IS_FAQ = f"LEFT(i.source_identity,{len(QA_SOURCE_PREFIX)})=BINARY '{QA_SOURCE_PREFIX}'"
_ACTIVE_VERSION = f"""CASE WHEN {_IS_FAQ} THEN i.published_version
WHEN i.state='published' THEN i.version END"""
_FAQ_PAYLOAD = "IF(JSON_VALID(v.content),v.content,'{}')"
_PUBLISHED_SNAPSHOT = f"""SELECT i.id,i.source_identity,
COALESCE(v.title,CASE WHEN {_IS_FAQ}
  THEN JSON_UNQUOTE(JSON_EXTRACT({_FAQ_PAYLOAD},'$.question')) ELSE i.title END) AS title,
v.item_version AS source_version,v.content,v.source_digest,
COALESCE(v.source_uri,CASE WHEN {_IS_FAQ}
  THEN JSON_UNQUOTE(JSON_EXTRACT({_FAQ_PAYLOAD},'$.source_ref')) ELSE i.source_uri END) AS source_uri,
v.recorded_at_utc AS published_at
FROM knowledge_items i JOIN knowledge_item_versions v
ON v.item_id=i.id AND v.item_version=({_ACTIVE_VERSION}) AND v.event_type='published'"""
_PUBLISHED_ITEMS = _PUBLISHED_SNAPSHOT + " ORDER BY i.id"
_FAQ_SNAPSHOT = """SELECT i.source_identity,i.published_version AS source_version,v.content,v.source_uri,
CASE WHEN i.faq_legacy_category_version=i.published_version THEN i.faq_legacy_category_id END AS legacy_category_id
FROM knowledge_items i LEFT JOIN knowledge_item_versions v
ON v.item_id=i.id AND v.item_version=i.published_version AND v.event_type='published'"""
_PUBLISHED_FAQ = f"{_FAQ_SNAPSHOT} WHERE {_IS_FAQ} AND i.published_version IS NOT NULL"
_FAQ_ID_ORDER = "i.source_identity COLLATE utf8mb4_bin"
_PREDECESSOR_PUBLISHED_FAQ = f"""
SELECT i.source_identity,v.item_version AS source_version,v.content,
    CASE WHEN i.version=v.item_version THEN i.source_uri END AS source_uri
FROM knowledge_items i
JOIN knowledge_item_versions v ON v.item_id=i.id AND v.item_version=(
    SELECT previous.item_version FROM knowledge_item_versions previous
    WHERE previous.item_id=i.id AND previous.event_type IN ('published','retired')
    ORDER BY previous.item_version DESC LIMIT 1
)
WHERE {_IS_FAQ} AND i.state<>'retired' AND v.event_type='published'
"""
_LIST_ITEMS = """SELECT i.id,i.source_identity,i.source_trust_tier,i.title,
i.state AS lifecycle_status,i.version AS current_version,i.published_version,
i.content_digest AS source_digest,i.source_uri,i.updated_at AS updated_at_utc,
v.content
FROM knowledge_items i
JOIN knowledge_item_versions v ON v.item_id=i.id AND v.item_version=i.version
WHERE (%s IS NULL OR i.state=%s)
ORDER BY i.updated_at DESC,i.id DESC LIMIT %s"""
_GET_ITEM = """SELECT i.id,i.source_identity,i.source_trust_tier,i.title,
i.state AS lifecycle_status,i.version AS current_version,i.published_version,
i.content_digest AS source_digest,i.source_uri,i.updated_at AS updated_at_utc,
v.content FROM knowledge_items i
JOIN knowledge_item_versions v ON v.item_id=i.id AND v.item_version=i.version
WHERE i.id=%s"""
_GET_ITEM_BY_SOURCE_IDENTITY = """SELECT i.id,i.source_identity,i.source_trust_tier,
i.title,i.state AS lifecycle_status,i.version AS current_version,i.published_version,
i.content_digest AS source_digest,i.source_uri,i.updated_at AS updated_at_utc,
v.content FROM knowledge_items i
JOIN knowledge_item_versions v ON v.item_id=i.id AND v.item_version=i.version
WHERE i.source_identity=%s"""
_LIST_JOBS = """SELECT id,job_type,processing_status,answer_request_id,target_index_version,
attempt_count,max_attempts,last_error_code,created_at_utc,completed_at_utc FROM knowledge_jobs
WHERE (%s IS NULL OR processing_status=%s) ORDER BY created_at_utc DESC,id DESC LIMIT %s"""
_LIST_INDEXES = """SELECT index_version,index_status,content_set_digest,built_at_utc,created_at_utc
FROM knowledge_indexes ORDER BY index_version DESC LIMIT %s"""
_GET_ANSWER_REQUEST = """SELECT q.id,q.question,q.request_status,q.correlation_id,q.created_at_utc,
q.completed_at_utc,r.answer_text,r.index_version,r.authoritative,r.line_delivery_task_id,r.answered_at_utc
FROM knowledge_answer_requests q LEFT JOIN knowledge_answer_receipts r ON r.answer_request_id=q.id
WHERE q.id=%s"""
_LIST_ANSWER_REQUESTS = f"""SELECT q.id,q.question,q.request_status,
q.created_at_utc,q.completed_at_utc,r.answer_text,r.index_version,
(SELECT s.source_identity FROM knowledge_answer_sources s
 WHERE s.answer_receipt_id=r.id ORDER BY s.citation_order LIMIT 1) AS source_identity,
(SELECT s.source_version FROM knowledge_answer_sources s
 WHERE s.answer_receipt_id=r.id ORDER BY s.citation_order LIMIT 1) AS source_version,
(SELECT JSON_UNQUOTE(JSON_EXTRACT(e.facts_snapshot,'$.outcome'))
 FROM line_notification_source_events e
 WHERE e.source_domain='line_feedback'
 AND e.source_aggregate_type='line_feedback'
 AND JSON_UNQUOTE(JSON_EXTRACT(e.facts_snapshot,'$.actor_id'))=q.requester_line_user_id
 AND JSON_UNQUOTE(JSON_EXTRACT(e.facts_snapshot,'$.source_response_id'))=CASE
   WHEN r.id IS NOT NULL THEN CONCAT('knowledge-answer-receipt:',CAST(r.id AS CHAR))
   WHEN q.request_status IN ('unsupported','failed')
   AND SUBSTR(q.idempotency_key,1,LENGTH('liff-knowledge-answer:'))='liff-knowledge-answer:'
   THEN CONCAT('{KNOWLEDGE_LIFF_RESULT_PREFIX}',CAST(q.id AS CHAR))
 END
 ORDER BY e.occurred_at_utc DESC,e.id DESC LIMIT 1) AS feedback_outcome,
(SELECT j.last_error_code FROM knowledge_jobs j
 WHERE j.answer_request_id=q.id ORDER BY j.id DESC LIMIT 1) AS failure_code
FROM knowledge_answer_requests q
LEFT JOIN knowledge_answer_receipts r ON r.answer_request_id=q.id
WHERE (%s IS NULL OR q.request_status=%s)
ORDER BY q.created_at_utc DESC,q.id DESC LIMIT %s"""
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
