"""Authenticated readback routes for persisted historical-baseline projection."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from pymysql.err import InterfaceError, OperationalError

from api.dependencies.admin_auth import require_historical_order_review_remediator
from api.dependencies.historical_baseline_projector import (
    HistoricalBaselineProjectorQueryApplication,
    get_historical_baseline_projector_query_application,
)
from api.schemas.base import BaseResponse
from api.schemas.historical_baseline_projector import (
    HistoricalBaselineProjectorReadModelView,
)
from infrastructure.mysql.historical_baseline_projector_read_model import (
    HistoricalBaselineProjectorQueryError,
)
from shared_kernel.errors import ErrorCategory, TypedError
from shared_kernel.identities import CorrelationId
from subsystems.access.authentication_session import AdminPrincipal


router = APIRouter(prefix="/api/v1/orders", tags=["Orders"])
_RETRYABLE_MYSQL_CODES = frozenset({1205, 1213, 2003, 2006, 2013})
_CorrelationHeader = Annotated[
    str | None,
    Header(alias="X-Correlation-ID", min_length=1, max_length=191),
]


@router.get(
    "/{case_no}/historical-baseline-projector",
    response_model=BaseResponse[HistoricalBaselineProjectorReadModelView],
)
def query_latest_historical_baseline_projection(
    case_no: str = Path(..., min_length=1, max_length=50, pattern=r"^[^\s]+$"),
    correlation_header: _CorrelationHeader = None,
    principal: AdminPrincipal = Depends(require_historical_order_review_remediator),
    application: HistoricalBaselineProjectorQueryApplication = Depends(
        get_historical_baseline_projector_query_application
    ),
):
    del principal
    correlation = CorrelationId(
        correlation_header or f"historical-baseline-projector:{case_no}"
    )
    return _query(
        lambda: application.query_latest_by_case(case_no),
        correlation,
        "成功載入案件最新的歷史基線投影",
    )


@router.get(
    "/historical-baseline-projector/deliveries/{delivery_identity}",
    response_model=BaseResponse[HistoricalBaselineProjectorReadModelView],
)
def query_historical_baseline_projection_delivery(
    delivery_identity: str = Path(..., pattern=r"^[0-9a-f]{64}$"),
    correlation_header: _CorrelationHeader = None,
    principal: AdminPrincipal = Depends(require_historical_order_review_remediator),
    application: HistoricalBaselineProjectorQueryApplication = Depends(
        get_historical_baseline_projector_query_application
    ),
):
    del principal
    correlation = CorrelationId(
        correlation_header or f"historical-baseline-delivery:{delivery_identity}"
    )
    return _query(
        lambda: application.query_by_delivery_identity(delivery_identity),
        correlation,
        "成功載入歷史基線 projector delivery",
    )


def _query(operation, correlation: CorrelationId, message: str):
    try:
        result = operation()
        if result is None:
            raise _http_error(
                404,
                TypedError(
                    ErrorCategory.NOT_FOUND,
                    "historical_baseline_projection_not_found",
                    "找不到歷史基線 projector readback。",
                    correlation,
                ),
            )
        model, reconciliation = result
        return BaseResponse(
            data=_read_model_payload(model, reconciliation),
            message=message,
        )
    except HTTPException:
        raise
    except HistoricalBaselineProjectorQueryError as error:
        raise _http_error(
            503,
            TypedError(
                ErrorCategory.UNAVAILABLE,
                error.code,
                "歷史基線 projector readback 無法完成一致性驗證。",
                correlation,
                retryable=False,
            ),
        ) from error
    except (OperationalError, InterfaceError) as error:
        retryable = bool(error.args) and error.args[0] in _RETRYABLE_MYSQL_CODES
        raise _http_error(
            503 if retryable else 500,
            TypedError(
                ErrorCategory.UNAVAILABLE if retryable else ErrorCategory.INTERNAL,
                (
                    "historical_baseline_projection_unavailable"
                    if retryable
                    else "historical_baseline_projection_failed"
                ),
                "歷史基線 projector readback 暫時無法使用。",
                correlation,
                retryable=retryable,
            ),
            headers={"Retry-After": "1"} if retryable else None,
        ) from error


def _read_model_payload(model, reconciliation):
    return {
        "delivery": _delivery_payload(model.delivery),
        "receipt": None if model.receipt is None else _receipt_payload(model.receipt),
        "active_memberships": [
            {
                "membership_identity": item.membership_identity.value,
                "set_ordinal": item.set_ordinal,
                "occurrence_identity": item.occurrence_identity.value,
            }
            for item in model.active_memberships
        ],
        "post_commit_readback": (
            None
            if model.post_commit_readback is None
            else _readback_payload(model.post_commit_readback)
        ),
        "current_alert": (
            None if model.current_alert is None else _alert_payload(model.current_alert)
        ),
        "reconciliation": {
            "status": reconciliation.status,
            "delivery_identity": reconciliation.delivery_identity,
            "projector_receipt_identity": reconciliation.projector_receipt_identity,
            "reason_code": reconciliation.reason_code,
            "referral": reconciliation.referral,
        },
    }


def _delivery_payload(delivery):
    return {
        "delivery_identity": delivery.delivery_identity,
        "source_trigger_identity": delivery.source_trigger_identity,
        "payload_digest": delivery.payload_digest.value,
        "source_kind": delivery.source_kind,
        "source_domain": delivery.source_domain,
        "source_event_identity": delivery.source_event_identity,
        "source_version": delivery.source_version,
        "partition_key": delivery.partition_key,
        "projection_sequence": delivery.projection_sequence,
        "projector_receipt_identity": delivery.projector_receipt_identity,
        "status": delivery.status.value,
        "attempt_count": delivery.attempt_count,
        "max_attempts": delivery.max_attempts,
        "next_attempt_at": delivery.next_attempt_at,
        "lease_expires_at": delivery.lease_expires_at,
        "last_error_code": delivery.last_error_code,
    }


def _receipt_payload(receipt):
    return {
        "projector_receipt_identity": receipt.projector_receipt_identity,
        "source_trigger_identity": receipt.source_trigger_identity,
        "source_trigger_version": receipt.source_trigger_version,
        "payload_digest": receipt.payload_digest.value,
        "idempotency_key": receipt.idempotency_key,
        "case_no": receipt.case_no,
        "order_identity": receipt.order_identity,
        "catalog_identity": receipt.catalog_identity.value,
        "catalog_version": receipt.catalog_version,
        "whole_vector_fingerprint": receipt.whole_vector_fingerprint.value,
        "whole_vector_count": receipt.whole_vector_count,
        "emitted_occurrence_set_digest": receipt.emitted_occurrence_set_digest.value,
        "emitted_occurrence_set_count": receipt.emitted_occurrence_set_count,
        "active_membership_set_digest": receipt.active_membership_set_digest.value,
        "active_membership_set_count": receipt.active_membership_set_count,
        "umbrella_identity": receipt.umbrella_identity.value,
        "projection_sequence": receipt.projection_sequence,
        "current_alert_fingerprint": receipt.current_alert_fingerprint.value,
        "expected_readback_digest": receipt.expected_readback_digest.value,
        "result_state": receipt.result_state,
    }


def _readback_payload(readback):
    return {
        "readback_identity": readback.readback_identity.value,
        "readback_attempt": readback.readback_attempt,
        "expected_readback_digest": readback.expected_readback_digest.value,
        "actual_readback_digest": _fingerprint_value(readback.actual_readback_digest),
        "emitted_occurrence_set_digest": _fingerprint_value(
            readback.emitted_occurrence_set_digest
        ),
        "emitted_occurrence_set_count": readback.emitted_occurrence_set_count,
        "active_membership_set_digest": _fingerprint_value(
            readback.active_membership_set_digest
        ),
        "active_membership_set_count": readback.active_membership_set_count,
        "state_event_set_digest": _fingerprint_value(readback.state_event_set_digest),
        "successor_set_digest": _fingerprint_value(readback.successor_set_digest),
        "workflow_event_set_digest": _fingerprint_value(
            readback.workflow_event_set_digest
        ),
        "current_alert_fingerprint": _fingerprint_value(
            readback.current_alert_fingerprint
        ),
        "result": readback.result,
        "error_code": readback.error_code,
    }


def _alert_payload(alert):
    return {
        "fingerprint": alert.fingerprint.value,
        "definition_code": alert.definition_code,
        "definition_version": alert.definition_version,
        "source_domain": alert.source_domain,
        "source_identity": alert.source_identity.value,
        "source_version": alert.source_version,
        "predicate_active": alert.predicate_active,
        "workflow_status": alert.workflow_status,
        "workflow_version": alert.workflow_version,
        "projection_version": alert.projection_version,
        "display": {
            "case_no": alert.display.case_no,
            "earliest_blocked_step": alert.display.earliest_blocked_step,
            "active_count": alert.display.active_count,
            "repair_referrals": [
                {
                    "step": item.step,
                    "contract_id": item.contract_id,
                    "owner_domain": item.owner_domain,
                    "repair_target": item.repair_target,
                    "repair_capability": item.repair_capability,
                }
                for item in alert.display.repair_referrals
            ],
            "projection_fingerprint": alert.display.projection_fingerprint.value,
        },
    }


def _fingerprint_value(value):
    return None if value is None else value.value


def _http_error(
    status: int,
    error: TypedError,
    *,
    headers: dict[str, str] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status,
        headers=headers,
        detail={
            "error": {
                "category": error.category.value,
                "code": error.code,
                "message": error.message,
                "field_errors": [],
                "domain_blockers": list(error.domain_blockers),
                "retryable": error.retryable,
                "correlation_id": error.correlation_id.value,
                "current_version": (
                    None
                    if error.current_version is None
                    else error.current_version.value
                ),
            }
        },
    )


__all__ = ["router"]
