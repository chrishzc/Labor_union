"""Canonical LINE webhook HTTP boundary used by the mutually exclusive runtime mode."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi import HTTPException, Request

from api.dependencies.line_runtime import (
    get_line_webhook_intake,
    record_line_webhook_security_receipt,
)
from shared_kernel.identities import CorrelationId
from subsystems.line.webhook_intake import (
    InvalidLineWebhookPayloadError,
    InvalidLineWebhookSignatureError,
    webhook_request_fingerprint,
)
from subsystems.line.runtime_contracts import LineWebhookVerificationOutcome


async def canonical_line_webhook(request: Request) -> dict[str, object]:
    raw_body = await request.body()
    signature = request.headers.get("x-line-signature")
    correlation_id = CorrelationId(
        request.headers.get("x-correlation-id") or f"line-webhook:{uuid4()}"
    )
    fingerprint = webhook_request_fingerprint(raw_body)
    try:
        result = await asyncio.to_thread(
            get_line_webhook_intake().accept,
            raw_body,
            signature,
            correlation_id,
        )
    except InvalidLineWebhookSignatureError as error:
        await _record_receipt(
            fingerprint,
            bool(signature),
            LineWebhookVerificationOutcome.INVALID_SIGNATURE,
            0,
            correlation_id,
        )
        raise HTTPException(status_code=401, detail=str(error)) from error
    except InvalidLineWebhookPayloadError as error:
        await _record_receipt(
            fingerprint,
            bool(signature),
            LineWebhookVerificationOutcome.INVALID_PAYLOAD,
            0,
            correlation_id,
        )
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        await _record_receipt(
            fingerprint,
            bool(signature),
            LineWebhookVerificationOutcome.STORAGE_FAILED,
            0,
            correlation_id,
        )
        raise HTTPException(status_code=503, detail="LINE webhook storage unavailable") from error
    event_count = result.created_count + result.duplicate_count
    await _record_receipt(
        fingerprint,
        bool(signature),
        LineWebhookVerificationOutcome.VERIFIED,
        event_count,
        correlation_id,
    )
    return {
        "status": "ok",
        "created_events": result.created_count,
        "duplicate_events": result.duplicate_count,
    }


async def _record_receipt(fingerprint, signature_present, outcome, count, correlation_id):
    try:
        await asyncio.to_thread(
            record_line_webhook_security_receipt,
            fingerprint,
            signature_present,
            outcome,
            count,
            correlation_id.value,
        )
    except Exception as error:
        print(f"[LINE Webhook] Security receipt unavailable: {error}")


__all__ = ["canonical_line_webhook"]
