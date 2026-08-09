"""Public verified BreezySign intake and capability-protected evidence APIs."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from api.dependencies.admin_auth import (
    require_contract_evidence_manager,
    require_contract_evidence_reader,
)
from api.dependencies.contract_integration import (
    breezysign_signature_header,
    get_contract_webhook_application,
)
from api.schemas.contract_integration import ContractMappingBody
from infrastructure.mysql.contract_integration_unit_of_work import (
    open_contract_integration_unit_of_work,
)
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.contract_integration.application import ContractSignatureInvalid
from subsystems.contract_integration.contracts import (
    MapContractEvidenceCommand,
    ReceiveContractWebhookCommand,
)

public_router = APIRouter(tags=["Contract Integration"])
admin_router = APIRouter(prefix="/api/v1/contract-integration", tags=["Contract Integration"])


@public_router.post("/webhook/breezysign")
# The complete provider HTTP boundary stays visible for security review.
async def receive_breezysign_webhook(
    request: Request,
    correlation_id: str = Header("breezysign-webhook", alias="X-Correlation-ID"),
):
    raw_body = await request.body()
    if len(raw_body) > 1024 * 1024:
        raise HTTPException(413, {"code": "external_payload_too_large"})
    try:
        header_name = breezysign_signature_header()
        application = get_contract_webhook_application()
        result = await asyncio.to_thread(
            application.receive,
            ReceiveContractWebhookCommand(
                "breezysign",
                raw_body,
                request.headers.get(header_name),
                datetime.now(timezone.utc),
                CorrelationId(correlation_id),
            ),
        )
    except ContractSignatureInvalid as error:
        raise HTTPException(401, {"code": str(error), "receipt_id": error.receipt_id}) from error
    except RuntimeError as error:
        _raise_runtime_error(error)
    except ValueError as error:
        raise HTTPException(422, {"code": str(error)}) from error
    return {"status": result.outcome.value, "receipt_id": result.receipt_id, "inbox_id": result.inbox_id}


@admin_router.get("/evidence")
def list_contract_evidence(
    limit: int = Query(100, ge=1, le=500),
    provider_contract_id: str | None = Query(default=None, max_length=191),
    processing_status: str | None = Query(default=None, max_length=32),
    cursor: int | None = Query(default=None, gt=0),
    _=Depends(require_contract_evidence_reader),
):
    with open_contract_integration_unit_of_work() as unit_of_work:
        evidence = unit_of_work.contracts.list_evidence(
            limit,
            provider_contract_id=provider_contract_id,
            processing_status=processing_status,
            before_inbox_id=cursor,
        )
        unit_of_work.commit()
    items = [_evidence_payload(item) for item in evidence]
    return {
        "items": items,
        "next_cursor": items[-1]["inbox_id"] if len(items) == limit else None,
    }


@admin_router.post("/mappings")
# FastAPI needs the full mutation contract here for OpenAPI and audit middleware.
def map_contract_evidence(
    body: ContractMappingBody,
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    correlation_id: str = Header(..., alias="X-Correlation-ID"),
    principal=Depends(require_contract_evidence_manager),
):
    command = MapContractEvidenceCommand(
        body.provider,
        body.provider_contract_id,
        body.internal_contract_identity,
        body.expected_version,
        ActorContext(f"admin:{principal.username}"),
        body.reason,
        IdempotencyKey(idempotency_key),
        CorrelationId(correlation_id),
    )
    try:
        with open_contract_integration_unit_of_work() as unit_of_work:
            version = unit_of_work.contracts.map_contract(command)
            unit_of_work.commit()
    except RuntimeError as error:
        raise HTTPException(409, {"code": str(error)}) from error
    request.state.audit_action = "contract.evidence.map"
    request.state.audit_resource_type = "external_contract"
    request.state.audit_resource_id = body.provider_contract_id
    request.state.audit_details = {"reason": body.reason}
    return {"provider_contract_id": body.provider_contract_id, "version": version}


def _raise_runtime_error(error: RuntimeError) -> None:
    code = str(error)
    if code == "external_event_payload_conflict":
        raise HTTPException(409, {"code": code}) from error
    if "BREEZYSIGN_" in code:
        raise HTTPException(503, {"code": "contract_provider_not_configured"}) from error
    raise error


def _evidence_payload(evidence):
    event = evidence.event
    return {
        "inbox_id": evidence.inbox_id,
        "provider": event.provider,
        "provider_contract_id": event.provider_contract_id,
        "provider_event_id": event.provider_event_id,
        "event_type": event.event_type,
        "contract_status": event.contract_status.value,
        "provider_occurred_at": event.occurred_at,
        "internal_contract_identity": evidence.internal_contract_identity,
        "mapping_version": evidence.mapping_version,
        "processing_status": evidence.processing_status,
        "processing_attempts": evidence.processing_attempts,
        "last_error_code": evidence.last_error_code,
        "orders_contract_completion_path": (
            f"/api/v1/orders/{evidence.internal_contract_identity}/contract-completion"
            if evidence.internal_contract_identity else None
        ),
    }


__all__ = ["admin_router", "public_router"]
