"""Verified LINE actor feedback command and typed readback."""

import os

from fastapi import APIRouter, HTTPException

from api.dependencies.line_identity import get_liff_token_verifier
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
from infrastructure.mysql.line_unit_of_work import open_line_unit_of_work
from domains.line.identities import LineUserId
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.line.feedback_application import FeedbackConflictError
from subsystems.line.feedback_contracts import FeedbackOutcome, RecordLineFeedback
from subsystems.line.identity_management_contracts import LineIdentityCurrentFactQuery


router = APIRouter(prefix="/api/v1/line/feedback", tags=["LINE Feedback"])


@router.post("/preview", response_model=BaseResponse[LineFeedbackPreviewView])
def preview_feedback(payload: RecordLineFeedbackRequest):
    """Zero-write feedback preview bound to the verified actor and current binding."""
    line_user_id, binding_version = _verified_bound_actor(payload)
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
    line_user_id, binding_version = _verified_bound_actor(payload)
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
    line_user_id, _ = _verified_bound_actor(payload)
    result = get_line_feedback_application().query(
        line_user_id.value,
        payload.source_response_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="line_feedback_not_found")
    return BaseResponse(data=_readback_view(result))


def _feedback_command(payload: RecordLineFeedbackRequest, actor_id: str, binding_version: int):
    return RecordLineFeedback(
        actor_id=actor_id,
        source_response_id=payload.source_response_id,
        outcome=FeedbackOutcome(payload.outcome),
        binding_version=binding_version,
        response_revision=payload.response_revision,
        catalog_revision=payload.catalog_revision,
        rule_revision=payload.rule_revision,
        idempotency_key=IdempotencyKey(payload.idempotency_key),
        correlation_id=CorrelationId(payload.correlation_id),
    )


def _verified_bound_actor(payload: RecordLineFeedbackRequest | LineFeedbackQueryRequest):
    token = payload.line_id_token.strip()
    if token:
        try:
            line_user_id = get_liff_token_verifier().verify(token).line_user_id
        except InvalidLiffTokenError as error:
            raise HTTPException(status_code=401, detail="liff_token_invalid") from error
        except LiffVerificationUnavailableError as error:
            raise HTTPException(status_code=503, detail="liff_verification_unavailable") from error
    elif _development_identity_fallback_enabled() and payload.development_line_user_id.strip():
        line_user_id = LineUserId(payload.development_line_user_id.strip())
    else:
        raise HTTPException(status_code=401, detail="liff_token_required")

    with open_line_unit_of_work() as unit_of_work:
        fact = unit_of_work.identity_management.current_fact(LineIdentityCurrentFactQuery(line_user_id))
    if fact.root_version is None or not fact.owner_projections:
        raise HTTPException(status_code=403, detail="line_feedback_binding_not_current")
    return line_user_id, fact.root_version


def _development_identity_fallback_enabled() -> bool:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    access_profile = os.getenv("ACCESS_CONTROL_PROFILE", "").strip().lower()
    required = os.getenv("LIFF_REQUIRE_ID_TOKEN", "true").strip().lower()
    return access_profile == "local_bypass" and app_env in {"development", "dev", "local", "test"} and required in {
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
