"""Verified LINE actor feedback command and typed readback."""

import os

from fastapi import APIRouter, HTTPException

from api.dependencies.line_identity import get_liff_token_verifier
from api.error_contracts import typed_http_error
from api.dependencies.line_runtime import get_line_feedback_application
from api.schemas.base import BaseResponse
from api.schemas.line_feedback import (
    LineFeedbackPreviewView,
    LineFeedbackQueryRequest,
    LineFeedbackReadbackView,
    LineFeedbackReceiptView,
    LineFeedbackRootView,
    RecordLineFeedbackRequest,
)
from infrastructure.line.liff_token_verifier import InvalidLiffTokenError, LiffVerificationUnavailableError
from infrastructure.mysql.knowledge_retrieval_unit_of_work import open_knowledge_retrieval_unit_of_work
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from domains.line.identities import LineUserId
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.feedback_application import FeedbackConflictError
from subsystems.line.feedback_contracts import (
    KNOWLEDGE_LIFF_RESULT_PREFIX,
    FeedbackOutcome,
    RecordLineFeedback,
)
from subsystems.line.identity_management_contracts import LineIdentityCurrentFactQuery


router = APIRouter(prefix="/api/v1/line/feedback", tags=["LINE Feedback"])
_KNOWLEDGE_RESPONSE_PREFIX = "knowledge-answer-receipt:"


@router.post("/preview", response_model=BaseResponse[LineFeedbackPreviewView])
def preview_feedback(payload: RecordLineFeedbackRequest):
    """Preview feedback for the verified actor without writing."""
    _reject_retired_liff_feedback(payload.source_response_id)
    line_user_id, binding_version = _verified_feedback_actor(payload)
    command = _feedback_command(payload, line_user_id.value, binding_version)
    result = get_line_feedback_application().preview(command)
    return BaseResponse(
        data=LineFeedbackPreviewView(
            source_response_id=result.source_response_id,
            outcome=result.outcome.value,
            command_fingerprint=result.command_fingerprint.value,
            apply_ready=result.apply_ready,
        )
    )


@router.post("", response_model=BaseResponse[LineFeedbackReceiptView])
def record_feedback(payload: RecordLineFeedbackRequest):
    _reject_retired_liff_feedback(payload.source_response_id)
    line_user_id, binding_version = _verified_feedback_actor(payload)
    try:
        result = get_line_feedback_application().apply(
            _feedback_command(payload, line_user_id.value, binding_version)
        )
    except FeedbackConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    receipt = result.receipt
    return BaseResponse(
        data=LineFeedbackReceiptView(
            source_response_id=receipt.source_response_id,
            outcome=receipt.outcome.value,
            command_fingerprint=receipt.command_fingerprint.value,
            ticket_id=receipt.ticket_id,
            replayed=receipt.replayed,
        )
    )


@router.post("/query", response_model=BaseResponse[LineFeedbackReadbackView])
def query_feedback(payload: LineFeedbackQueryRequest):
    """Read back only the verified actor's immutable feedback root and receipt."""
    line_user_id, binding_version = _verified_feedback_actor(payload)
    if binding_version == 0:
        _knowledge_feedback_source(payload.source_response_id, line_user_id.value, inline_only=True)
    result = get_line_feedback_application().query(
        line_user_id.value,
        payload.source_response_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="line_feedback_not_found")
    return BaseResponse(data=_readback_view(result))


def _reject_retired_liff_feedback(source_response_id: str) -> None:
    if source_response_id.startswith(KNOWLEDGE_LIFF_RESULT_PREFIX):
        raise typed_http_error(
            410, "validation", "line_service_help_retired",
            "此問答回饋已停用。請回到 LINE 官方帳號聊天室。", "line-service-help:retired",
        )


def _feedback_command(payload: RecordLineFeedbackRequest, actor_id: str, binding_version: int):
    source = _knowledge_feedback_source(
        payload.source_response_id, actor_id, inline_only=binding_version == 0,
    )
    catalog_revision = payload.catalog_revision
    if source is not None:
        context, catalog_revision = source
        if (
            payload.response_revision != context.response_revision
            or payload.catalog_revision != catalog_revision
            or payload.rule_revision != context.rule_revision
        ):
            raise HTTPException(status_code=409, detail="line_feedback_source_version_conflict")
    elif catalog_revision is None:
        raise HTTPException(status_code=422, detail="line_feedback_catalog_revision_required")
    return RecordLineFeedback(
        actor_id=actor_id,
        source_response_id=payload.source_response_id,
        outcome=FeedbackOutcome(payload.outcome),
        binding_version=binding_version,
        response_revision=payload.response_revision,
        catalog_revision=catalog_revision,
        rule_revision=payload.rule_revision,
        idempotency_key=IdempotencyKey(payload.idempotency_key),
        correlation_id=CorrelationId(payload.correlation_id),
    )


def _knowledge_feedback_source(source_response_id: str, actor_id: str, *, inline_only: bool = False):
    prefix, separator, raw_id = source_response_id.partition(":")
    prefix += separator
    if prefix not in (_KNOWLEDGE_RESPONSE_PREFIX, KNOWLEDGE_LIFF_RESULT_PREFIX):
        return None
    try:
        record_id = int(raw_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail="line_feedback_source_invalid") from error
    if not 1 <= record_id < 2**64 or str(record_id) != raw_id:
        raise HTTPException(status_code=422, detail="line_feedback_source_invalid")
    with open_knowledge_retrieval_unit_of_work() as unit_of_work:
        if prefix == KNOWLEDGE_LIFF_RESULT_PREFIX:
            context = unit_of_work.knowledge.inline_result_feedback_context(record_id, actor_id)
            if context is None:
                raise HTTPException(status_code=404, detail="line_feedback_source_unavailable")
            return context, None
        context = unit_of_work.knowledge.feedback_context(record_id, actor_id)
        catalog_revision = (
            None
            if context is None
            else unit_of_work.answer_receipt_catalog_revision(record_id)
        )
    if (
        context is None
        or context.source_response_id != source_response_id
        or catalog_revision is None
        or (inline_only and context.line_delivery_task_id is not None)
    ):
        raise HTTPException(status_code=404, detail="line_feedback_source_unavailable")
    return context, catalog_revision


def _verified_feedback_actor(
    payload: RecordLineFeedbackRequest | LineFeedbackQueryRequest,
) -> tuple[LineUserId, int]:
    token = payload.line_id_token.strip()
    if token:
        try:
            line_user_id = get_liff_token_verifier().verify(token).line_user_id
        except InvalidLiffTokenError as error:
            raise HTTPException(status_code=401, detail="liff_token_invalid") from error
        except LiffVerificationUnavailableError as error:
            raise HTTPException(status_code=503, detail="liff_verification_unavailable") from error
    elif (
        not payload.source_response_id.startswith(KNOWLEDGE_LIFF_RESULT_PREFIX)
        and _development_identity_fallback_enabled()
        and payload.development_line_user_id.strip()
    ):
        line_user_id = LineUserId(payload.development_line_user_id.strip())
    else:
        raise HTTPException(status_code=401, detail="liff_token_required")

    with open_line_unit_of_work() as unit_of_work:
        fact = unit_of_work.identity_management.current_fact(LineIdentityCurrentFactQuery(line_user_id))
    if fact.root_version is not None and fact.owner_projections:
        return line_user_id, fact.root_version
    if token and payload.source_response_id.startswith((_KNOWLEDGE_RESPONSE_PREFIX, KNOWLEDGE_LIFF_RESULT_PREFIX)):
        return line_user_id, 0
    raise HTTPException(status_code=403, detail="line_feedback_binding_not_current")


def _development_identity_fallback_enabled() -> bool:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    access_profile = os.getenv("ACCESS_CONTROL_PROFILE", "").strip().lower()
    required = os.getenv("LIFF_REQUIRE_ID_TOKEN", "true").strip().lower()
    return access_profile == "local_auth" and app_env in {"development", "dev", "local", "test"} and required in {
        "0", "false", "no", "off"
    }


def _readback_view(result) -> LineFeedbackReadbackView:
    root = result.root
    return LineFeedbackReadbackView(
        root=LineFeedbackRootView(
            actor_id=_canonical_actor(root.actor_id),
            source_response_id=root.source_response_id,
            outcome=root.outcome.value,
            binding_version=root.binding_version,
            response_revision=root.response_revision,
            catalog_revision=root.catalog_revision,
            rule_revision=root.rule_revision,
            command_fingerprint=root.command_fingerprint.value,
            ticket_id=root.ticket_id,
            idempotency_key=root.idempotency_key.value,
            correlation_id=root.correlation_id.value,
            occurred_at=root.occurred_at.isoformat(),
        ),
        receipt=LineFeedbackReceiptView(
            source_response_id=result.receipt.source_response_id,
            outcome=result.receipt.outcome.value,
            command_fingerprint=result.receipt.command_fingerprint.value,
            ticket_id=result.receipt.ticket_id,
            replayed=result.receipt.replayed,
        ),
    )


def _canonical_actor(value: str) -> str:
    return str(value or "").strip()

__all__ = ["router"]
