"""Capability-protected knowledge review, publication, indexing, and query APIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

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
    RetireKnowledgeItemCommand,
    ReviewKnowledgeItemCommand,
)

router = APIRouter(prefix="/api/v1/knowledge", tags=["Knowledge Retrieval"])


@router.get("/items")
def list_knowledge_items(
    limit: int = Query(100, ge=1, le=500),
    lifecycle_status: str | None = Query(default=None, max_length=32),
    _=Depends(require_knowledge_reader),
):
    return list(get_knowledge_application().list_items(limit, lifecycle_status))


@router.get("/items/{item_id}")
def get_knowledge_item(item_id: int, _=Depends(require_knowledge_reader)):
    result = get_knowledge_application().get_item(item_id)
    if result is None:
        raise HTTPException(404, {"code": "knowledge_item_not_found"})
    return result


@router.get("/jobs")
def list_knowledge_jobs(
    limit: int = Query(100, ge=1, le=500),
    processing_status: str | None = Query(default=None, max_length=32),
    _=Depends(require_knowledge_reader),
):
    return list(get_knowledge_application().list_jobs(limit, processing_status))


@router.get("/indexes")
def list_knowledge_indexes(
    limit: int = Query(100, ge=1, le=500),
    _=Depends(require_knowledge_reader),
):
    return list(get_knowledge_application().list_indexes(limit))


@router.get("/questions/{request_id}")
def get_knowledge_answer(request_id: int, _=Depends(require_knowledge_reader)):
    result = get_knowledge_application().get_answer_request(request_id)
    if result is None:
        raise HTTPException(404, {"code": "knowledge_answer_request_not_found"})
    return result


@router.post("/items")
def ingest_knowledge_item(
    body: KnowledgeIngestBody,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    correlation_id: str = Header(..., alias="X-Correlation-ID"),
    principal=Depends(require_knowledge_manager),
):
    result = _call_knowledge(lambda: get_knowledge_application().ingest(
        IngestKnowledgeSourceCommand(
            body.source_identity, body.source_trust_tier, body.title,
            body.content, body.source_uri,
            _actor(principal), IdempotencyKey(idempotency_key), CorrelationId(correlation_id),
        )
    ))
    _set_knowledge_audit(request, "ingest", "knowledge_item", result[0])
    return {"item_id": result[0], "created": result[1]}


@router.post("/items/{item_id}/review")
def review_knowledge_item(
    item_id: int,
    body: KnowledgeTransitionBody,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    correlation_id: str = Header(..., alias="X-Correlation-ID"),
    principal=Depends(require_knowledge_manager),
):
    command = _transition_command(
        ReviewKnowledgeItemCommand, item_id, body, idempotency_key, correlation_id, principal
    )
    version = _call_knowledge(lambda: get_knowledge_application().review(command))
    _set_knowledge_audit(request, "review", "knowledge_item", item_id, body.reason)
    return {"item_id": item_id, "version": version}


@router.post("/items/{item_id}/publish")
def publish_knowledge_item(
    item_id: int,
    body: KnowledgeTransitionBody,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    correlation_id: str = Header(..., alias="X-Correlation-ID"),
    principal=Depends(require_knowledge_publisher),
):
    command = _transition_command(
        PublishKnowledgeItemCommand, item_id, body, idempotency_key, correlation_id, principal
    )
    version = _call_knowledge(lambda: get_knowledge_application().publish(command))
    _set_knowledge_audit(request, "publish", "knowledge_item", item_id, body.reason)
    return {"item_id": item_id, "version": version}


@router.post("/items/{item_id}/retire")
def retire_knowledge_item(
    item_id: int,
    body: KnowledgeTransitionBody,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    correlation_id: str = Header(..., alias="X-Correlation-ID"),
    principal=Depends(require_knowledge_publisher),
):
    command = _transition_command(
        RetireKnowledgeItemCommand, item_id, body, idempotency_key, correlation_id, principal
    )
    version = _call_knowledge(lambda: get_knowledge_application().retire(command))
    _set_knowledge_audit(request, "retire", "knowledge_item", item_id, body.reason)
    return {"item_id": item_id, "version": version}


@router.post("/indexes")
def request_knowledge_index(
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    principal=Depends(require_knowledge_reindexer),
):
    job_id = _call_knowledge(lambda: get_knowledge_application().request_index_build(
        _actor(principal).actor_id, idempotency_key
    ))
    _set_knowledge_audit(request, "index", "knowledge_job", job_id)
    return {"job_id": job_id, "status": "pending"}


@router.post("/questions")
def ask_knowledge_question(
    body: KnowledgeQuestionBody,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    correlation_id: str = Header(..., alias="X-Correlation-ID"),
    _=Depends(require_knowledge_reader),
):
    request_id, created = _call_knowledge(lambda: get_knowledge_application().ask(
        AskKnowledgeQuestionCommand(
            body.question, None, IdempotencyKey(idempotency_key), CorrelationId(correlation_id)
        )
    ))
    _set_knowledge_audit(request, "question", "knowledge_answer_request", request_id)
    return {"request_id": request_id, "created": created, "status": "pending"}


@router.post("/jobs/{job_id}/retry")
def retry_knowledge_job(
    job_id: int,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    principal=Depends(require_knowledge_reindexer),
):
    retry_id = _call_knowledge(lambda: get_knowledge_application().retry_job(
        job_id, _actor(principal).actor_id, idempotency_key
    ))
    _set_knowledge_audit(request, "retry", "knowledge_job", retry_id)
    return {"job_id": retry_id, "status": "pending"}


def _actor(principal):
    if principal.id is None:
        raise HTTPException(403, {"code": "admin_identity_required"})
    return ActorContext(str(principal.id))


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


def _set_knowledge_audit(
    request: Request,
    action: str,
    resource_type: str,
    resource_id: int,
    reason: str | None = None,
) -> None:
    request.state.audit_action = f"knowledge.{action}"
    request.state.audit_resource_type = resource_type
    request.state.audit_resource_id = str(resource_id)
    if reason:
        request.state.audit_details = {"reason": reason}


__all__ = ["router"]
