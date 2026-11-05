"""Public registration ASGI process: LINE verification + dedicated Redis only.

Deploy this module independently. It does not import api.main, app settings,
MySQL repositories, SQL pools, delivery outboxes or internal approval routes.
"""
from __future__ import annotations

from functools import lru_cache
import os
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from api.error_contracts import typed_http_error
from api.registration_contracts import registration_intent
from api.schemas.base import BaseResponse
from api.schemas.line_identity import ProvisionalRegistrationPreviewRequest, ProvisionalRegistrationRequest
from domains.case_import.provisional_registration import (
    ProvisionalRegistrationDomainError, build_provisional_registration_candidate,
)
from infrastructure.line.liff_token_verifier import (
    InvalidLiffTokenError, LiffVerificationUnavailableError, LineLoginTokenVerifier,
)
from infrastructure.line.registration_token_verifier import registration_token_verifier
from infrastructure.redis.registration_connection import registration_redis_client
from infrastructure.redis.registration_staging_repository import RedisRegistrationStagingRepository
from subsystems.case_import.provisional_registration_types import (
    ProvisionalRegistrationConflictError, ProvisionalRegistrationStorageError,
)


app = FastAPI(title="Registration intake", docs_url=None, redoc_url=None, openapi_url=None)


@app.middleware("http")
async def bounded_body(request: Request, call_next):
    # Streaming limit also covers chunked requests without trusting Content-Length.
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 300 * 1024:
            return JSONResponse(status_code=413, content={"detail": {"code": "registration_payload_too_large"}})
    request._body = bytes(body)
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def invalid_request(request, error):
    # FastAPI's default validation response echoes input (including questionnaire accounts).
    return JSONResponse(status_code=422, content={"detail": {"code": "registration_input_invalid",
                        "message": "申請資料未通過驗證，請確認欄位。"}})


@lru_cache(maxsize=1)
def get_staging():
    try:
        return RedisRegistrationStagingRepository(registration_redis_client(role="intake"))
    except (OSError, ValueError, RuntimeError):
        raise typed_http_error(503, "unavailable", "registration_storage_not_configured",
                              "申請暫存服務尚未完成設定。", uuid4().hex) from None


@lru_cache(maxsize=1)
def get_verifier():
    try:
        return registration_token_verifier()
    except ValueError:
        raise typed_http_error(503, "unavailable", "registration_verification_not_configured",
                              "LINE 驗證尚未完成設定。", uuid4().hex) from None


def _verified_subject(payload, verifier):
    try:
        return verifier.verify(payload.line_id_token).line_user_id
    except InvalidLiffTokenError:
        raise typed_http_error(401, "forbidden", "liff_token_invalid", "請重新登入 LINE 後送出。", uuid4().hex) from None
    except LiffVerificationUnavailableError:
        raise typed_http_error(503, "unavailable", "liff_verification_unavailable", "LINE 驗證暫時無法使用。", uuid4().hex, retryable=True) from None


def _candidate(payload, verifier):
    subject = _verified_subject(payload, verifier)
    try:
        return build_provisional_registration_candidate(registration_intent(payload, subject))
    except (ProvisionalRegistrationDomainError, ValueError):
        raise typed_http_error(422, "validation", "registration_input_invalid", "申請資料未通過驗證。", uuid4().hex) from None


def _translate(operation):
    try:
        return operation()
    except ProvisionalRegistrationConflictError:
        raise typed_http_error(409, "conflict", "registration_conflict", "申請狀態已變更或已有待審申請，請查詢原申請。", uuid4().hex) from None
    except ProvisionalRegistrationStorageError:
        raise typed_http_error(503, "unavailable", "registration_unavailable", "申請暫存服務無法使用；請保留原申請識別查詢結果。", uuid4().hex, retryable=True) from None


def _result(snapshot):
    return {"registration_id": snapshot.registration_id, "client_id": snapshot.client_id,
            "beclass_record_id": snapshot.beclass_record_id, "case_no": snapshot.case_no,
            "client_name": "", "replayed": snapshot.replayed,
            "identity_status": "pending_approval" if snapshot.status == "pending" else snapshot.status,
            "status": snapshot.status, "submitted_at_utc": snapshot.submitted_at_utc.isoformat(),
            "expires_at_utc": snapshot.expires_at_utc.isoformat()}


@app.post("/api/v1/line/identity/registration/preview")
def preview(payload: ProvisionalRegistrationPreviewRequest, verifier=Depends(get_verifier)):
    candidate = _candidate(payload, verifier)
    return BaseResponse(data={"status": "ready", "expected_binding_version": 0,
        "payload_fingerprint": candidate.payload_fingerprint.value,
        "preview_fingerprint": candidate.payload_fingerprint.value})


@app.post("/api/v1/line/identity/registration/apply")
def submit(payload: ProvisionalRegistrationRequest, submission_id: str = Header(alias="Idempotency-Key"),
           staging=Depends(get_staging), verifier=Depends(get_verifier)):
    candidate = _candidate(payload, verifier)
    if payload.expected_binding_version != 0 or payload.preview_fingerprint != candidate.payload_fingerprint.value:
        raise typed_http_error(409, "conflict", "registration_preview_stale", "申請內容已變更，請重新確認。", uuid4().hex)
    return BaseResponse(data=_translate(lambda: _result(staging.submit(candidate, submission_id))))


class StatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line_id_token: str = Field(min_length=1, max_length=4096)
    submission_id: str = Field(min_length=36, max_length=36)


@app.post("/api/v1/line/identity/registration/status")
def status(payload: StatusRequest, staging=Depends(get_staging), verifier=Depends(get_verifier)):
    subject = _verified_subject(payload, verifier)
    def query():
        snapshot = staging.status_for_submission(subject.value, payload.submission_id)
        if snapshot is None:
            return {"status": "not_received"}
        return _result(snapshot)
    return BaseResponse(data=_translate(query))


@app.get("/health")
def health():
    return {"status": "ok"}
