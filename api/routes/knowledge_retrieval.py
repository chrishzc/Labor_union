"""Capability-protected knowledge review, publication, indexing, and query APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from api.dependencies.admin_auth import (
    require_knowledge_manager,
    require_knowledge_publisher,
    require_knowledge_reader,
    require_knowledge_reindexer,
)
from api.dependencies.knowledge_retrieval import get_knowledge_application
from api.schemas.knowledge_retrieval import (
    KnowledgeIngestBody,
    KnowledgeQuestionBody,
    KnowledgeTransitionBody,
)
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.knowledge_retrieval.contracts import (
    AskKnowledgeQuestionCommand,
    IngestKnowledgeSourceCommand,
    PublishKnowledgeItemCommand,
    ReviewKnowledgeItemCommand,
)

router = APIRouter(prefix="/api/v1/knowledge", tags=["Knowledge Retrieval"])


@router.get("/items")
def list_knowledge_items(
    limit: int = Query(100, ge=1, le=500),
    _=Depends(require_knowledge_reader),
):
    return list(get_knowledge_application().list_items(limit))


@router.get("/jobs")
def list_knowledge_jobs(
    limit: int = Query(100, ge=1, le=500),
    _=Depends(require_knowledge_reader),
):
    return list(get_knowledge_application().list_jobs(limit))


@router.post("/items")
def ingest_knowledge_item(
    body: KnowledgeIngestBody,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    correlation_id: str = Header(..., alias="X-Correlation-ID"),
    principal=Depends(require_knowledge_manager),
):
    result = _call_knowledge(lambda: get_knowledge_application().ingest(
        IngestKnowledgeSourceCommand(
            body.source_identity, body.title, body.content, body.source_uri,
            _actor(principal), IdempotencyKey(idempotency_key), CorrelationId(correlation_id),
        )
    ))
    return {"item_id": result[0], "created": result[1]}


@router.post("/items/{item_id}/review")
def review_knowledge_item(
    item_id: int,
    body: KnowledgeTransitionBody,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    correlation_id: str = Header(..., alias="X-Correlation-ID"),
    principal=Depends(require_knowledge_manager),
):
    command = _transition_command(
        ReviewKnowledgeItemCommand, item_id, body, idempotency_key, correlation_id, principal
    )
    return {"item_id": item_id, "version": _call_knowledge(lambda: get_knowledge_application().review(command))}


@router.post("/items/{item_id}/publish")
def publish_knowledge_item(
    item_id: int,
    body: KnowledgeTransitionBody,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    correlation_id: str = Header(..., alias="X-Correlation-ID"),
    principal=Depends(require_knowledge_publisher),
):
    command = _transition_command(
        PublishKnowledgeItemCommand, item_id, body, idempotency_key, correlation_id, principal
    )
    return {"item_id": item_id, "version": _call_knowledge(lambda: get_knowledge_application().publish(command))}


@router.post("/indexes")
def request_knowledge_index(
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    principal=Depends(require_knowledge_reindexer),
):
    job_id = _call_knowledge(lambda: get_knowledge_application().request_index_build(
        _actor(principal).actor_id, idempotency_key
    ))
    return {"job_id": job_id, "status": "pending"}


@router.post("/questions")
def ask_knowledge_question(
    body: KnowledgeQuestionBody,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    correlation_id: str = Header(..., alias="X-Correlation-ID"),
    _=Depends(require_knowledge_reader),
):
    request_id, created = _call_knowledge(lambda: get_knowledge_application().ask(
        AskKnowledgeQuestionCommand(
            body.question, None, IdempotencyKey(idempotency_key), CorrelationId(correlation_id)
        )
    ))
    return {"request_id": request_id, "created": created, "status": "pending"}


def _actor(principal):
    return ActorContext(f"admin:{principal.username}")


def _transition_command(command_type, item_id, body, key, correlation, principal):
    return command_type(
        item_id, ExpectedVersion(body.expected_version), _actor(principal), body.reason,
        IdempotencyKey(key), CorrelationId(correlation),
    )


def _call_knowledge(command):
    try:
        return command()
    except LookupError as error:
        raise HTTPException(404, {"code": str(error)}) from error
    except RuntimeError as error:
        raise HTTPException(409, {"code": str(error)}) from error
    except ValueError as error:
        raise HTTPException(422, {"code": str(error)}) from error


__all__ = ["router"]
