"""
File: historical_operational_baseline.py
Description: 暴露歷史 Orders 作業基準的 authenticated Query、Preview、Apply 與 fresh readback。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from pymysql.err import IntegrityError, OperationalError

from api.dependencies.admin_auth import (
    admin_actor_context,
    require_historical_order_review_remediator,
)
from api.dependencies.historical_operational_baseline import (
    HistoricalOperationalBaselineApplication,
    get_historical_operational_baseline_application,
)
from api.schemas.base import BaseResponse
from api.schemas.historical_operational_baseline import (
    HistoricalOperationalBaselineApplyBody,
    HistoricalOperationalBaselineApplyView,
    HistoricalOperationalBaselineIntentBody,
    HistoricalOperationalBaselinePreviewView,
    HistoricalOperationalBaselineQueryView,
)
from domains.orders.historical_operational_baseline import (
    HistoricalBaselineEvidenceMode,
    HistoricalOperationalBaselineRequest,
    project_historical_baseline_steps,
)
from infrastructure.mysql.historical_operational_baseline_repository import (
    canonical_historical_order_identity,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint
from shared_kernel.identities import CorrelationId, ExpectedVersion, IdempotencyKey
from shared_kernel.identities import ActorContext
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.orders.historical_operational_baseline_workflow import (
    ApplyHistoricalOperationalBaseline,
    HistoricalOperationalBaselineWorkflowError,
)


router = APIRouter(prefix="/api/v1/orders", tags=["Orders"])
_CorrelationHeader = Annotated[
    str,
    Header(alias="X-Correlation-ID", min_length=1, max_length=191),
]
_IdempotencyHeader = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=191,
        pattern=r"^[a-z0-9][a-z0-9._:-]{0,190}$",
    ),
]


@router.get(
    "/{case_no}/historical-operational-baseline",
    response_model=BaseResponse[HistoricalOperationalBaselineQueryView],
)
def query_historical_operational_baseline(
    case_no: str = Path(
        ...,
        min_length=1,
        max_length=50,
        pattern=r"^[^\s]+$",
    ),
    correlation_id: _CorrelationHeader = "historical-operational-baseline-query",
    principal: AdminPrincipal = Depends(require_historical_order_review_remediator),
    application: HistoricalOperationalBaselineApplication = Depends(
        get_historical_operational_baseline_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    identity = canonical_historical_order_identity(case_no)
    return _call(
        lambda: _query_payload(application.query(identity, correlation)),
        "成功載入歷史案件作業基準",
        correlation,
    )


@router.post(
    "/{case_no}/historical-operational-baseline/preview",
    response_model=BaseResponse[HistoricalOperationalBaselinePreviewView],
)
def preview_historical_operational_baseline(
    body: HistoricalOperationalBaselineIntentBody,
    case_no: str = Path(
        ...,
        min_length=1,
        max_length=50,
        pattern=r"^[^\s]+$",
    ),
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_historical_order_review_remediator),
    application: HistoricalOperationalBaselineApplication = Depends(
        get_historical_operational_baseline_application
    ),
):
    correlation = CorrelationId(correlation_id)
    identity = _bound_identity(case_no, body.order_identity, correlation)
    return _call(
        lambda: _preview_payload(
            application.preview(
                _request(identity, body),
                _orders_actor(principal),
                correlation,
            )
        ),
        "成功產生歷史案件作業基準 Preview",
        correlation,
    )


@router.post(
    "/{case_no}/historical-operational-baseline/apply",
    response_model=BaseResponse[HistoricalOperationalBaselineApplyView],
)
def apply_historical_operational_baseline(
    body: HistoricalOperationalBaselineApplyBody,
    case_no: str = Path(
        ...,
        min_length=1,
        max_length=50,
        pattern=r"^[^\s]+$",
    ),
    idempotency_key: _IdempotencyHeader = ...,
    correlation_id: _CorrelationHeader = ...,
    principal: AdminPrincipal = Depends(require_historical_order_review_remediator),
    application: HistoricalOperationalBaselineApplication = Depends(
        get_historical_operational_baseline_application
    ),
):
    correlation = CorrelationId(correlation_id)
    identity = _bound_identity(case_no, body.order_identity, correlation)
    command = ApplyHistoricalOperationalBaseline(
        identity,
        body.selected_step,
        ExpectedVersion(body.expected_orders_version),
        PreviewFingerprint(body.expected_baseline_binding_fingerprint),
        HistoricalBaselineEvidenceMode(body.evidence_mode),
        body.reason,
        body.evidence_reference,
        PreviewFingerprint(body.preview_fingerprint),
        IdempotencyKey(idempotency_key),
        _orders_actor(principal),
        correlation,
        body.document_kind,
        None if body.affected_steps is None else tuple(body.affected_steps),
    )
    return _call(
        lambda: _apply_payload(application, command),
        "成功提交歷史案件作業基準",
        correlation,
    )


def _request(identity, body):
    return HistoricalOperationalBaselineRequest(
        identity,
        body.selected_step,
        body.expected_orders_version,
        PreviewFingerprint(body.expected_baseline_binding_fingerprint),
        HistoricalBaselineEvidenceMode(body.evidence_mode),
        body.reason,
        body.evidence_reference,
        body.document_kind,
        None if body.affected_steps is None else tuple(body.affected_steps),
    )


def _orders_actor(principal: AdminPrincipal) -> ActorContext:
    actor = admin_actor_context(principal)
    return ActorContext(
        actor.actor_id,
        ("orders.historical_review.remediate",),
    )


def _bound_identity(
    case_no: str,
    order_identity: str,
    correlation: CorrelationId,
):
    identity = canonical_historical_order_identity(case_no)
    if order_identity != identity.order_identity:
        raise HTTPException(
            status_code=422,
            detail={
                "error": _error_payload(
                    TypedError(
                        ErrorCategory.VALIDATION,
                        "historical_operational_baseline_identity_mismatch",
                        "order identity 與案件不一致。",
                        correlation,
                    )
                )
            },
        )
    return identity


def _query_payload(query):
    facts = query.facts
    prior = facts.prior_baseline_lineage
    payload = {
        "order_identity": facts.identity.order_identity,
        "case_no": facts.identity.case_no,
        "historical_provenance": {
            "source_event_identity": facts.historical_provenance.source_event_identity,
            "source_version": facts.historical_provenance.source_version,
        },
        "current_orders_version": facts.current_orders_version,
        "baseline_binding_fingerprint": facts.current_owner_binding_fingerprint.value,
        "current_baseline": None,
        "allowed_steps": list(range(1, 12)),
        "evidence_modes": [
            "retained",
            "historical_evidence_unavailable_accepted",
        ],
    }
    if prior is not None:
        payload["current_baseline"] = {
            "baseline_event_identity": prior.event_identity,
            "selected_step": prior.selected_step,
            "resulting_orders_version": prior.resulting_orders_version,
            "resulting_owner_binding_fingerprint": prior.resulting_owner_binding_fingerprint.value,
            "step_projection": [
                {"step": item.step, "state": item.state.value}
                for item in project_historical_baseline_steps(prior.selected_step)
            ],
        }
    return payload


def _preview_payload(preview):
    candidate = preview.candidate
    return {
        "order_identity": candidate.identity.order_identity,
        "case_no": candidate.identity.case_no,
        "selected_step": candidate.selected_step,
        "expected_orders_version": preview.expected_orders_version.value,
        "expected_baseline_binding_fingerprint": candidate.current_owner_binding_fingerprint.value,
        "candidate_fingerprint": candidate.fingerprint.value,
        "preview_fingerprint": preview.fingerprint.value,
        "evidence_mode": candidate.evidence_mode.value,
        "prior_baseline_event_identity": (
            None
            if candidate.prior_baseline_lineage is None
            else candidate.prior_baseline_lineage.event_identity
        ),
        "step_projection": [
            {"step": item.step, "state": item.state.value}
            for item in candidate.step_projection
        ],
    }


def _apply_payload(application, command):
    receipt = application.apply(command)
    readback = application.query(command.identity, command.correlation_id)
    prior = readback.facts.prior_baseline_lineage
    exact_event = (
        prior is not None
        and prior.event_identity == receipt.baseline_event_identity
        and prior.identity == receipt.identity
        and prior.selected_step == receipt.selected_step
        and prior.resulting_orders_version == receipt.resulting_orders_version
        and prior.resulting_owner_binding_fingerprint
        == command.expected_owner_binding_fingerprint
    )
    replay_has_monotonic_successor = (
        receipt.replayed
        and prior is not None
        and prior.identity == receipt.identity
        and prior.selected_step >= receipt.selected_step
        and prior.resulting_orders_version >= receipt.resulting_orders_version
        and readback.facts.current_orders_version
        >= receipt.resulting_orders_version
    )
    if not (exact_event or replay_has_monotonic_successor):
        raise RuntimeError("historical_operational_baseline_readback_mismatch")
    return {
        "order_identity": receipt.identity.order_identity,
        "case_no": receipt.identity.case_no,
        "receipt": {
            "baseline_event_identity": receipt.baseline_event_identity,
            "receipt_identity": receipt.receipt_identity,
            "selected_step": receipt.selected_step,
            "resulting_orders_version": receipt.resulting_orders_version,
            "preview_fingerprint": receipt.preview_fingerprint.value,
            "command_fingerprint": receipt.command_fingerprint.value,
            "replayed": receipt.replayed,
        },
        "readback": _query_payload(readback),
    }


def _call(operation, message: str, correlation: CorrelationId):
    try:
        return BaseResponse(data=operation(), message=message)
    except HistoricalOperationalBaselineWorkflowError as error:
        raise _typed_http_error(error.error) from error
    except OperationalError as error:
        retryable = int(error.args[0]) in {1205, 1213} if error.args else False
        typed = TypedError(
            ErrorCategory.UNAVAILABLE if retryable else ErrorCategory.INTERNAL,
            (
                "historical_operational_baseline_unavailable"
                if retryable
                else "historical_operational_baseline_failed"
            ),
            (
                "歷史案件作業基準暫時無法完成。"
                if retryable
                else "歷史案件作業基準失敗。"
            ),
            correlation,
            retryable=retryable,
        )
        raise _http_error(503 if retryable else 500, typed) from error
    except IntegrityError as error:
        typed = TypedError(
            ErrorCategory.CONFLICT,
            "historical_operational_baseline_integrity_conflict",
            "歷史案件作業基準與目前資料衝突，請重新查詢與 Preview。",
            correlation,
        )
        raise _http_error(409, typed) from error
    except (TypeError, ValueError) as error:
        typed = TypedError(
            ErrorCategory.VALIDATION,
            str(error) or "historical_operational_baseline_invalid",
            "歷史案件作業基準資料未通過驗證。",
            correlation,
        )
        raise _http_error(422, typed) from error
    except RuntimeError as error:
        typed = TypedError(
            ErrorCategory.INTERNAL,
            str(error) or "historical_operational_baseline_readback_failed",
            "歷史案件作業基準已執行但 readback 無法確認。",
            correlation,
        )
        raise _http_error(500, typed) from error


def _typed_http_error(error: TypedError) -> HTTPException:
    status = {
        ErrorCategory.VALIDATION: 422,
        ErrorCategory.FORBIDDEN: 403,
        ErrorCategory.NOT_FOUND: 404,
        ErrorCategory.DOMAIN_BLOCKED: 409,
        ErrorCategory.CONFLICT: 409,
        ErrorCategory.IDEMPOTENCY_MISMATCH: 409,
        ErrorCategory.UNAVAILABLE: 503,
        ErrorCategory.INTERNAL: 500,
    }[error.category]
    return _http_error(status, error)


def _http_error(status: int, error: TypedError) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"error": _error_payload(error)},
    )


def _error_payload(error: TypedError) -> dict[str, object]:
    return {
        "category": error.category.value,
        "code": error.code,
        "message": error.message,
        "field_errors": [],
        "domain_blockers": list(error.domain_blockers),
        "retryable": error.retryable,
        "correlation_id": error.correlation_id.value,
        "current_version": (
            None if error.current_version is None else error.current_version.value
        ),
    }


__all__ = ["router"]
