"""Reviewed knowledge publication and non-authoritative cited retrieval."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.dependencies.admin_auth import require_capability
from api.schemas.base import BaseResponse
from api.schemas.knowledge_retrieval import KnowledgeAnswerView, KnowledgeCommandBody, KnowledgeReceiptView
from infrastructure.mysql.knowledge_retrieval_repository import KnowledgeCommand, KnowledgeCommandError, apply_knowledge_command, query_published_knowledge
from subsystems.access.authentication_session import AdminPrincipal


router = APIRouter(prefix="/api/v1/knowledge", tags=["Knowledge Retrieval"])


@router.post("/sources", response_model=BaseResponse[KnowledgeReceiptView])
def ingest_source(body: KnowledgeCommandBody, request: Request, actor: AdminPrincipal = Depends(require_capability("knowledge.source.edit"))):
    return _command("ingest", body, request, actor)


@router.post("/{item_id}/review", response_model=BaseResponse[KnowledgeReceiptView])
def review_source(item_id: int, body: KnowledgeCommandBody, request: Request, actor: AdminPrincipal = Depends(require_capability("knowledge.source.review"))):
    return _command("review", body, request, actor, item_id)


@router.post("/{item_id}/publish", response_model=BaseResponse[KnowledgeReceiptView])
def publish_source(item_id: int, body: KnowledgeCommandBody, request: Request, actor: AdminPrincipal = Depends(require_capability("knowledge.source.publish"))):
    return _command("publish", body, request, actor, item_id)


@router.post("/{item_id}/retire", response_model=BaseResponse[KnowledgeReceiptView])
def retire_source(item_id: int, body: KnowledgeCommandBody, request: Request, actor: AdminPrincipal = Depends(require_capability("knowledge.source.publish"))):
    return _command("retire", body, request, actor, item_id)


@router.get("/answer", response_model=BaseResponse[KnowledgeAnswerView])
def answer(question: str = Query(min_length=1, max_length=500), _: AdminPrincipal = Depends(require_capability("knowledge.answer.query"))):
    result = query_published_knowledge(question)
    if result is None:
        raise HTTPException(status_code=503, detail="knowledge_answer_unsupported")
    return BaseResponse(data=KnowledgeAnswerView(**result))


def _command(action: str, body: KnowledgeCommandBody, request: Request, actor: AdminPrincipal, item_id: int | None = None):
    try:
        receipt = apply_knowledge_command(KnowledgeCommand(action=action, item_id=item_id, **body.model_dump()), actor)
    except KnowledgeCommandError as error:
        raise HTTPException(status_code=_status_for(error.code), detail=error.code) from error
    request.state.audit_action = f"knowledge.{action}"
    request.state.audit_resource_type = "knowledge_item"
    request.state.audit_resource_id = str(receipt["knowledge_item_id"])
    return BaseResponse(data=KnowledgeReceiptView(**receipt))


def _status_for(code: str) -> int:
    if code in {"knowledge_version_conflict", "knowledge_state_conflict", "knowledge_publisher_separation_required", "idempotency_conflict"}:
        return 409
    if code in {"knowledge_source_invalid", "knowledge_command_invalid"}:
        return 422
    return 404 if code == "knowledge_item_not_found" else 403
