"""
File: service_before_replacement.py
Description: 暴露服務前換人 authenticated Query、Preview、Apply typed API。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from pymysql.err import IntegrityError, OperationalError

from infrastructure.mysql.service_before_replacement_loader import (
    ServiceBeforeReplacementSourceUnavailable,
)

from api.dependencies.admin_auth import (
    admin_actor_context,
    require_historical_order_review_remediator,
)
from api.dependencies.service_before_replacement import (
    ServiceBeforeReplacementApplication,
    get_service_before_replacement_application,
)
from api.schemas.service_before_replacement import (
    ServiceBeforeReplacementApplyBody,
    ServiceBeforeReplacementApplyView,
    ServiceBeforeReplacementPreviewBody,
    ServiceBeforeReplacementPreviewView,
    ServiceBeforeReplacementQueryView,
    ServiceBeforeReplacementResponse,
)
from api.schemas.errors import GlobalTypedErrorResponseView
from domains.scheduling.service_before_replacement import (
    ReplacementOutcome,
    ReplacementScenario,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.fingerprints import PreviewFingerprint, fingerprint_payload
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.access.authentication_session import AdminPrincipal
from subsystems.scheduling.service_before_replacement_workflow import (
    ApplyServiceBeforeReplacement,
    ReplacementApplyResult,
    ReplacementApplyStatus,
    ServiceBeforeReplacementPreviewRequest,
    ServiceBeforeReplacementQueryRequest,
    ServiceBeforeReplacementWorkflowError,
)


router = APIRouter(prefix="/api/v1/orders", tags=["Orders"])
_ERROR_RESPONSES = {
    status: {"model": GlobalTypedErrorResponseView}
    for status in (400, 401, 403, 404, 409, 422, 500, 503)
}
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
_CasePath = Annotated[
    str,
    Path(min_length=1, max_length=50, pattern=r"^[^\s]+$"),
]


@router.get(
    "/{case_no}/service-before-replacement",
    response_model=ServiceBeforeReplacementResponse[ServiceBeforeReplacementQueryView],
    responses=_ERROR_RESPONSES,
)
def query_service_before_replacement(
    case_no: _CasePath,
    scenario: str | None = None,
    correlation_id: _CorrelationHeader = "service-before-replacement-query",
    principal: AdminPrincipal = Depends(require_historical_order_review_remediator),
    application: ServiceBeforeReplacementApplication = Depends(
        get_service_before_replacement_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    if scenario is None:
        # A case can have several RPRE scenarios; guessing one would expose the
        # wrong owner roots. Keep Query fail-closed until the caller supplies it.
        raise _http_error(
            503,
            TypedError(
                ErrorCategory.UNAVAILABLE,
                "replacement_scenario_required",
                "服務前換人 Query 需要明確 scenario；目前未授權自動推定。",
                correlation,
            ),
        )
    return _call(
        lambda: _query_payload(
            application.query(
                ServiceBeforeReplacementQueryRequest(
                    case_no,
                    ReplacementScenario(scenario),
                    correlation,
                )
            )
        ),
        "成功取得服務前換人根事實",
        correlation,
    )


@router.post(
    "/{case_no}/service-before-replacement/preview",
    response_model=ServiceBeforeReplacementResponse[ServiceBeforeReplacementPreviewView],
    responses=_ERROR_RESPONSES,
)
def preview_service_before_replacement(
    body: ServiceBeforeReplacementPreviewBody,
    case_no: _CasePath,
    correlation_id: _CorrelationHeader,
    principal: AdminPrincipal = Depends(require_historical_order_review_remediator),
    application: ServiceBeforeReplacementApplication = Depends(
        get_service_before_replacement_application
    ),
):
    del principal
    correlation = CorrelationId(correlation_id)
    request = ServiceBeforeReplacementPreviewRequest(
        case_no,
        ReplacementScenario(body.scenario),
        correlation,
        body.reason,
        tuple(body.evidence),
    )
    return _call(
        lambda: _preview_payload(application.preview(request), body),
        "成功產生服務前換人 Preview",
        correlation,
    )


@router.post(
    "/{case_no}/service-before-replacement/apply",
    response_model=ServiceBeforeReplacementResponse[ServiceBeforeReplacementApplyView],
    responses=_ERROR_RESPONSES,
)
def apply_service_before_replacement(
    body: ServiceBeforeReplacementApplyBody,
    case_no: _CasePath,
    idempotency_key: _IdempotencyHeader,
    correlation_id: _CorrelationHeader,
    principal: AdminPrincipal = Depends(require_historical_order_review_remediator),
    application: ServiceBeforeReplacementApplication = Depends(
        get_service_before_replacement_application
    ),
):
    correlation = CorrelationId(correlation_id)
    command = ApplyServiceBeforeReplacement(
        case_no=case_no,
        scenario=ReplacementScenario(body.scenario),
        expected_generation_version=ExpectedVersion(body.expected_generation_version),
        expected_event_version=ExpectedVersion(body.expected_event_version),
        expected_aggregate_version=ExpectedVersion(body.expected_aggregate_version),
        prior_generation_identity=body.prior_generation_identity,
        prior_event_identity=body.prior_event_identity,
        prior_aggregate_identity=body.prior_aggregate_identity,
        preview_fingerprint=PreviewFingerprint(body.preview_fingerprint),
        idempotency_key=IdempotencyKey(idempotency_key),
        actor=_server_actor(principal),
        reason=body.reason,
        evidence=tuple(body.evidence),
        correlation_id=correlation,
    )
    return _call(
        lambda: _apply_payload(application, command),
        "成功提交服務前換人 successor",
        correlation,
    )


def _server_actor(principal: AdminPrincipal) -> ActorContext:
    actor = admin_actor_context(principal) if hasattr(principal, "id") else None
    actor_id = "admin:development" if actor is None else actor.actor_id
    return ActorContext(actor_id, ("orders.historical_review.remediate",))


def _query_payload(query):
    actual_dates = tuple(query.actual_service_dates)
    referral = bool(actual_dates)
    prior_generation_identity = _first(query, "prior_generation_identity")
    prior_event_identity = _first(query, "prior_event_identity")
    if not referral and not query.blockers:
        if (
            not isinstance(prior_generation_identity, str)
            or not prior_generation_identity.strip()
            or not isinstance(prior_event_identity, str)
            or not prior_event_identity.strip()
        ):
            raise ServiceBeforeReplacementSourceUnavailable("replacement_prior_event_unavailable")
    outcome = (
        ReplacementOutcome.SUBSTITUTION_REFERRAL.value
        if actual_dates
        else ("ready" if not query.blockers else ReplacementOutcome.BLOCKED.value)
    )
    return {
        "case_no": query.case_no,
        "scenario": query.scenario.value,
        "outcome": outcome,
        "actual_service_day_count": query.actual_service_day_count,
        "actual_service_dates": list(actual_dates),
        "actual_service_proof": _proof_payload(query.actual_service_proof),
        "prior_generation_identity": prior_generation_identity,
        "prior_event_identity": prior_event_identity,
        "prior_aggregate_identity": query.prior_aggregate_identity,
        "generation_version": query.generation_version,
        "event_version": query.event_version,
        "aggregate_version": query.aggregate_version,
        "impacted_roots": [] if referral else [_root_payload(item) for item in _sorted_roots(query.impacted_roots)],
        "retained_roots": [] if referral else [_root_payload(item) for item in _sorted_roots(query.retained_roots)],
        "root_delta": None if referral else _delta_payload(query.root_delta),
        "candidate_pool_reuse_proof": None if referral else _reuse_payload(query.candidate_pool_reuse_proof),
        "successor_round": None if referral else _successor_payload(query.successor_round),
        "resume_step": query.resume_step.value,
        "blockers": list(query.blockers),
    }


def _preview_payload(candidate, body: ServiceBeforeReplacementPreviewBody | None = None):
    reason_evidence = getattr(candidate, "reason_evidence", None)
    reason = "" if reason_evidence is None else reason_evidence.reason
    evidence = [] if reason_evidence is None else list(reason_evidence.evidence_references)
    root_delta = _delta_payload(candidate.root_delta) if candidate.can_apply else None
    referral = candidate.outcome is ReplacementOutcome.SUBSTITUTION_REFERRAL
    return {
        "case_no": candidate.case_no,
        "scenario": candidate.scenario.value,
        "outcome": candidate.outcome.value,
        "actual_service_day_count": len(candidate.actual_service_dates),
        "actual_service_dates": list(candidate.actual_service_dates),
        "actual_service_proof": _proof_payload(candidate.actual_service_proof),
        "prior_generation_identity": candidate.prior_generation_identity,
        "prior_event_identity": candidate.prior_event_identity,
        "prior_aggregate_identity": candidate.prior_aggregate_identity,
        "generation_version": candidate.expected_generation_version,
        "event_version": candidate.expected_event_version,
        "aggregate_version": candidate.expected_aggregate_version,
        "impacted_roots": [] if referral else [_root_payload(item) for item in _sorted_roots(candidate.superseded_roots)],
        "retained_roots": [] if referral else [_root_payload(item) for item in _sorted_roots(candidate.retained_roots)],
        "root_delta": None if referral else root_delta,
        "candidate_pool_reuse_proof": None if referral else _reuse_payload(candidate.candidate_pool_reuse_proof),
        "successor_round": None if referral else _successor_payload(candidate.successor_round_fact),
        "resume_step": candidate.resume_step.value,
        "blockers": list(candidate.blockers),
        "replacement_generation_identity": candidate.replacement_generation_identity,
        "replacement_event_identity": candidate.replacement_event_identity,
        "successor_round_identity": candidate.successor_round_identity,
        "expected_generation_version": candidate.expected_generation_version,
        "resulting_generation_version": candidate.resulting_generation_version,
        "expected_event_version": candidate.expected_event_version,
        "resulting_event_version": candidate.resulting_event_version,
        "expected_aggregate_version": candidate.expected_aggregate_version,
        "resulting_aggregate_version": candidate.resulting_aggregate_version,
        "superseded_roots": [] if referral else [_root_payload(item) for item in _sorted_roots(candidate.superseded_roots)],
        "created_roots": [] if referral else [_root_payload(item) for item in _sorted_roots(candidate.created_roots)],
        "preview_fingerprint": candidate.fingerprint.value,
        "reason": reason,
        "evidence": evidence,
        "projection_kind": candidate.projection_kind.value,
    }


def _apply_payload(application, command):
    result = application.apply(command)
    if not isinstance(result, ReplacementApplyResult):
        raise RuntimeError("replacement_apply_result_invalid")
    if result.status not in (ReplacementApplyStatus.APPLIED, ReplacementApplyStatus.REPLAYED):
        if result.error is not None:
            raise ServiceBeforeReplacementWorkflowError(
                _normalize_error(result.error, command.correlation_id)
            )
        if result.status is ReplacementApplyStatus.OUTCOME_UNKNOWN:
            raise ServiceBeforeReplacementWorkflowError(
                TypedError(
                    ErrorCategory.UNAVAILABLE,
                    "replacement_outcome_unknown",
                    "服務前換人提交結果無法對帳。",
                    command.correlation_id,
                    retryable=True,
                )
            )
        code = "replacement_actual_service_exists" if result.status is ReplacementApplyStatus.SUBSTITUTION_REFERRAL else "replacement_blocked"
        category = ErrorCategory.CONFLICT if result.status is ReplacementApplyStatus.SUBSTITUTION_REFERRAL else ErrorCategory.DOMAIN_BLOCKED
        raise ServiceBeforeReplacementWorkflowError(
            TypedError(category, code, "服務前換人目前不可執行。", command.correlation_id)
        )
    if result.receipt is None or result.readback is None or not result.readback.complete:
        raise ServiceBeforeReplacementWorkflowError(
            TypedError(ErrorCategory.UNAVAILABLE, "replacement_outcome_unknown", "服務前換人提交結果無法對帳。", command.correlation_id, retryable=True)
        )
    receipt = result.receipt
    readback = result.readback
    if (
        len(readback.root_set_digests) != 3
        or len(readback.root_set_counts) != 3
        or not readback.outbox_identity
    ):
        raise ServiceBeforeReplacementWorkflowError(
            TypedError(ErrorCategory.UNAVAILABLE, "replacement_outcome_unknown", "服務前換人提交結果無法對帳。", command.correlation_id, retryable=True)
        )
    return {
        "status": result.status.value,
        "receipt": _receipt_payload(receipt),
        "readback": _readback_payload(readback),
    }


def _proof_payload(proof):
    if proof is None:
        return None
    return {
        "case_no": proof.case_no,
        "service_dates": list(proof.service_dates),
        "source_identity": proof.source_identity,
        "source_version": proof.source_version,
        "fingerprint": proof.fingerprint.value,
    }


def _root_payload(root):
    return {
        "kind": root.kind.value,
        "root_id": root.root_id,
        "case_no": root.case_no,
        "current": root.current,
        "caregiver_bound": root.caregiver_bound,
    }


def _delta_payload(delta):
    if delta is None:
        return None
    return {
        "retained": [_root_payload(item) for item in _sorted_roots(delta.retained)],
        "superseded": [_root_payload(item) for item in _sorted_roots(delta.superseded)],
        "created": [_root_payload(item) for item in _sorted_roots(delta.created)],
    }


def _sorted_roots(roots):
    return tuple(sorted(roots, key=lambda item: item.root_id))


def _reuse_payload(proof):
    if proof is None:
        return None
    return {
        "pool_identity": proof.pool_identity,
        "round_identity": proof.round_identity,
        "coverage_version": proof.coverage_version,
        "availability_version": proof.availability_version,
        "willingness_version": proof.willingness_version,
        "fingerprint": proof.fingerprint.value,
        "same_round": proof.same_round,
        "coverage_valid": proof.coverage_valid,
        "availability_valid": proof.availability_valid,
        "willingness_valid": proof.willingness_valid,
        "fresh": proof.fresh,
        "accepted_candidate": proof.accepted_candidate,
        "case_no": proof.case_no,
        "successor_round_identity": proof.successor_round_identity,
        "generation_version": proof.generation_version,
        "event_version": proof.event_version,
        "candidate_identity": proof.candidate_identity,
    }


def _successor_payload(successor):
    if successor is None:
        return None
    fingerprint = getattr(successor, "fingerprint", None)
    if fingerprint is None:
        fingerprint = fingerprint_payload({
            "kind": "successor-round",
            "case_no": successor.case_no,
            "round_identity": successor.round_identity,
            "generation_identity": successor.generation_identity,
            "event_identity": successor.event_identity,
            "generation_version": successor.generation_version,
            "event_version": successor.event_version,
            "candidate_count": successor.candidate_count,
            "zero_candidate_disposition": successor.zero_candidate_disposition,
        })
    if isinstance(fingerprint, PreviewFingerprint):
        fingerprint = fingerprint.value
    return {
        "case_no": successor.case_no,
        "round_identity": successor.round_identity,
        "generation_identity": successor.generation_identity,
        "event_identity": successor.event_identity,
        "generation_version": successor.generation_version,
        "event_version": successor.event_version,
        "candidate_count": successor.candidate_count,
        "zero_candidate_disposition": successor.zero_candidate_disposition,
        "fingerprint": fingerprint,
    }


def _receipt_payload(receipt):
    return {
        "case_no": receipt.case_no,
        "receipt_identity": receipt.receipt_identity,
        "idempotency_key": receipt.idempotency_key.value,
        "command_fingerprint": receipt.command_fingerprint.value,
        "preview_fingerprint": receipt.preview_fingerprint.value,
        "replacement_generation_identity": receipt.replacement_generation_identity,
        "replacement_event_identity": receipt.replacement_event_identity,
        "successor_round_identity": receipt.successor_round_identity,
        "resulting_generation_version": receipt.resulting_generation_version,
        "resulting_event_version": receipt.resulting_event_version,
        "resulting_aggregate_version": receipt.resulting_aggregate_version,
        "outbox_identity": receipt.outbox_identity,
        "retained_root_ids": list(receipt.retained_root_ids),
        "superseded_root_ids": list(receipt.superseded_root_ids),
        "created_root_ids": list(receipt.created_root_ids),
        "retained_root_set_digest": receipt.retained_root_set_digest,
        "retained_root_count": receipt.retained_root_count,
        "superseded_root_set_digest": receipt.superseded_root_set_digest,
        "superseded_root_count": receipt.superseded_root_count,
        "created_root_set_digest": receipt.created_root_set_digest,
        "created_root_count": receipt.created_root_count,
        "matching_package_lineage_id": receipt.matching_package_lineage_id,
        "matching_event_id": receipt.matching_event_id,
    }


def _readback_payload(readback):
    return {
        "case_no": readback.case_no,
        "generation_identity": readback.generation_identity,
        "event_identity": readback.event_identity,
        "successor_round_identity": readback.successor_round_identity,
        "generation_version": readback.generation_version,
        "event_version": readback.event_version,
        "aggregate_version": readback.aggregate_version,
        "retained_root_ids": list(readback.retained_root_ids),
        "superseded_root_ids": list(readback.superseded_root_ids),
        "created_root_ids": list(readback.created_root_ids),
        "root_set_digests": list(readback.root_set_digests),
        "root_set_counts": list(readback.root_set_counts),
        "outbox_identity": readback.outbox_identity,
        "matching_package_lineage_id": readback.matching_package_lineage_id,
        "matching_event_id": readback.matching_event_id,
        "complete": readback.complete,
    }


def _first(value, name):
    return getattr(value, name, None)


def _call(operation, message: str, correlation: CorrelationId):
    try:
        return ServiceBeforeReplacementResponse(data=operation(), message=message)
    except ServiceBeforeReplacementWorkflowError as error:
        normalized = _normalize_error(error.error, error.error.correlation_id)
        raise _typed_http_error(normalized) from error
    except OperationalError as error:
        retryable = int(error.args[0]) in {1205, 1213} if error.args else False
        typed = TypedError(
            ErrorCategory.UNAVAILABLE if retryable else ErrorCategory.INTERNAL,
            "replacement_outcome_unknown" if retryable else "replacement_internal_error",
            "服務前換人暫時無法完成。" if retryable else "服務前換人失敗。",
            correlation,
            retryable=retryable,
        )
        raise _http_error(503 if retryable else 500, typed) from error
    except IntegrityError as error:
        typed = TypedError(ErrorCategory.CONFLICT, "replacement_version_conflict", "服務前換人與目前資料衝突，請重新查詢與 Preview。", correlation)
        raise _http_error(409, typed) from error
    except ServiceBeforeReplacementSourceUnavailable as error:
        typed = TypedError(
            ErrorCategory.UNAVAILABLE,
            "replacement_source_unavailable",
            "服務前換人根事實目前無法完整讀取。",
            correlation,
            domain_blockers=(error.code,),
            retryable=True,
        )
        raise _http_error(503, typed) from error
    except (TypeError, ValueError) as error:
        typed = TypedError(ErrorCategory.VALIDATION, "replacement_request_invalid", "服務前換人資料未通過驗證。", correlation)
        raise _http_error(422, typed) from error
    except RuntimeError as error:
        typed = TypedError(ErrorCategory.UNAVAILABLE, "replacement_outcome_unknown", "服務前換人結果無法確認。", correlation, retryable=True)
        raise _http_error(503, typed) from error


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


def _normalize_error(error: TypedError, correlation: CorrelationId) -> TypedError:
    """Translate internal workflow aliases to the §8.5 stable vocabulary."""
    mapping = {
        "actual_service_exists": "replacement_actual_service_exists",
        "actual_service_proof_unavailable": "replacement_service_proof_unavailable",
        "replacement_stale_version": "replacement_version_conflict",
        "replacement_idempotency_conflict": "replacement_idempotency_mismatch",
        "replacement_case_identity_mismatch": "replacement_identity_drift",
        "replacement_scenario_identity_mismatch": "replacement_identity_drift",
        "replacement_transaction_unknown": "replacement_outcome_unknown",
        "replacement_post_commit_readback_unknown": "replacement_outcome_unknown",
        "replacement_replay_readback_unknown": "replacement_outcome_unknown",
        "replacement_readback_unavailable": "replacement_outcome_unknown",
    }
    code = mapping.get(error.code, error.code)
    if code not in {
        "replacement_blocked",
        "replacement_actual_service_exists",
        "replacement_version_conflict",
        "replacement_identity_drift",
        "replacement_reason_evidence_drift",
        "replacement_preview_stale",
        "replacement_idempotency_mismatch",
        "replacement_request_invalid",
        "replacement_scenario_invalid",
        "replacement_scenario_required",
        "replacement_service_proof_unavailable",
        "replacement_source_unavailable",
        "replacement_facts_not_found",
        "replacement_outcome_unknown",
        "replacement_internal_error",
    }:
        code = (
            "replacement_blocked"
            if error.category is ErrorCategory.DOMAIN_BLOCKED
            else "replacement_outcome_unknown"
            if error.category is ErrorCategory.UNAVAILABLE
            else "replacement_version_conflict"
            if error.category is ErrorCategory.CONFLICT
            else "replacement_internal_error"
        )
    category = error.category
    if code == "replacement_actual_service_exists":
        category = ErrorCategory.CONFLICT
    if code in {"replacement_service_proof_unavailable", "replacement_outcome_unknown"}:
        category = ErrorCategory.UNAVAILABLE
    return TypedError(
        category,
        code,
        error.message,
        correlation,
        field_errors=error.field_errors,
        domain_blockers=error.domain_blockers,
        retryable=error.retryable or code == "replacement_outcome_unknown",
        current_version=error.current_version,
    )


def _http_error(status: int, error: TypedError) -> HTTPException:
    return HTTPException(status_code=status, detail={"error": _error_payload(error)})


def _error_payload(error: TypedError) -> dict[str, object]:
    return {
        "category": error.category.value,
        "code": error.code,
        "message": error.message,
        "field_errors": [
            {"field": item.field, "code": item.code, "message": item.message}
            for item in error.field_errors
        ],
        "domain_blockers": list(error.domain_blockers),
        "retryable": error.retryable,
        "correlation_id": error.correlation_id.value,
        "current_version": None if error.current_version is None else error.current_version.value,
    }


__all__ = ["router"]
