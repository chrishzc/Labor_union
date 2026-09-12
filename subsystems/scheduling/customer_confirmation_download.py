"""Short-lived bearer references for PDFs already selected by a confirmation package."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone


_LOCAL_SECRET = "local-only-matching-confirmation-download-v1"


def issue_resume_download_token(*, case_no: str, plan_id: int, staff_id: int, file_id: str, now: datetime) -> str:
    if now.tzinfo is None:
        raise ValueError("download token time must be timezone-aware")
    payload = {"case_no": case_no, "plan_id": plan_id, "staff_id": staff_id, "file_id": file_id,
               "exp": int((now + timedelta(days=7)).timestamp())}
    encoded = _encode(payload)
    signature = hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
    return f"mcf_{encoded}.{_urlsafe(signature)}"


def verify_resume_download_token(token: str, *, now: datetime) -> dict[str, object]:
    if not token.startswith("mcf_") or "." not in token[4:]:
        raise ValueError("confirmation download token is invalid")
    encoded, signature = token[4:].split(".", 1)
    expected = hmac.new(_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
    if not hmac.compare_digest(_urlsafe(expected), signature):
        raise ValueError("confirmation download token is invalid")
    try:
        payload = json.loads(_decode(encoded))
    except (ValueError, json.JSONDecodeError) as error:
        raise ValueError("confirmation download token is invalid") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("file_id"), str) or not isinstance(payload.get("exp"), int):
        raise ValueError("confirmation download token is invalid")
    if now.timestamp() > payload["exp"]:
        raise ValueError("confirmation download token has expired")
    return payload


def confirmation_download_url(token: str) -> str:
    base = (os.getenv("LINE_PUBLIC_BASE_URL", "").strip() or os.getenv("BASE_URL", "").strip()).rstrip("/")
    if not base.startswith("https://"):
        raise ValueError("customer confirmation requires an HTTPS LINE_PUBLIC_BASE_URL")
    return f"{base}/api/v1/matching-confirmation-files/{token}"


def _secret() -> bytes:
    configured = os.getenv("MATCHING_CONFIRMATION_DOWNLOAD_TOKEN_SECRET", "").strip()
    if configured:
        return configured.encode("utf-8")
    if os.getenv("APP_ENV", "development").strip().lower() == "development":
        return _LOCAL_SECRET.encode("utf-8")
    raise ValueError("MATCHING_CONFIRMATION_DOWNLOAD_TOKEN_SECRET is required outside development")


def _urlsafe(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _encode(value: dict[str, object]) -> str:
    return _urlsafe(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _decode(value: str) -> str:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode("utf-8")
