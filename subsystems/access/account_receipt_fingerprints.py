"""Keyed fingerprints for password-bearing account receipts."""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import os
import re

KEY_SETTING = "ACCESS_CONTROL_ACCOUNT_RECEIPT_HMAC_KEY"
PASSWORD_RECEIPT_FAMILIES = ("account-create", "account-password-reset")
LEGACY_FINGERPRINT = re.compile(r"[0-9a-f]{64}")
PROTECTED_FINGERPRINT = r"^h1[.][A-Za-z0-9_-]{43}$"

_UNPROTECTED_PASSWORD_RECEIPTS = """
FROM admin_command_receipts
WHERE command_family IN (%s, %s)
  AND (CHAR_LENGTH(request_fingerprint) <> 46
       OR NOT REGEXP_LIKE(request_fingerprint, %s, 'c')
       OR BINARY request_fingerprint <> BINARY preview_fingerprint)
"""


class AccountReceiptProtectionError(RuntimeError):
    """A password-bearing receipt cannot be used safely."""


def account_receipt_key(encoded: str | None = None) -> bytes:
    value = os.environ.get(KEY_SETTING, "") if encoded is None else encoded
    try:
        key = base64.b64decode(value, altchars=b"-_", validate=True)
    except (ValueError, binascii.Error):
        key = b""
    if len(key) != 32:
        raise AccountReceiptProtectionError("account_receipt_key_unavailable")
    return key


def protect_receipt_fingerprint(key: bytes, family: str, request_key: str, digest: str) -> str:
    # Including the command identity binds the digest to its original row.
    # Wrapping the existing digest permits conversion without the original password.
    canonical = json.dumps(
        ["access-account-receipt/h1", family, request_key, digest],
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")
    mac = hmac.digest(key, canonical, "sha256")
    return "h1." + base64.urlsafe_b64encode(mac).decode("ascii").rstrip("=")


def require_protected_account_receipts(cursor) -> None:
    cursor.execute(
        "SELECT 1 " + _UNPROTECTED_PASSWORD_RECEIPTS + " LIMIT 1",
        (*PASSWORD_RECEIPT_FAMILIES, PROTECTED_FINGERPRINT),
    )
    if cursor.fetchone() is not None:
        raise AccountReceiptProtectionError("account_receipt_conversion_required")


def unprotected_account_receipt_count(cursor) -> int:
    cursor.execute(
        "SELECT COUNT(*) AS count " + _UNPROTECTED_PASSWORD_RECEIPTS,
        (*PASSWORD_RECEIPT_FAMILIES, PROTECTED_FINGERPRINT),
    )
    row = cursor.fetchone()
    return int(row["count"] if isinstance(row, dict) else row[0])


def convert_account_receipt_fingerprints(cursor, key: bytes) -> int:
    """Convert in the caller's transaction, retaining row identity and result."""
    cursor.execute(
        "SELECT id, command_family, idempotency_key, request_fingerprint, preview_fingerprint "
        + _UNPROTECTED_PASSWORD_RECEIPTS + " ORDER BY id FOR UPDATE",
        (*PASSWORD_RECEIPT_FAMILIES, PROTECTED_FINGERPRINT),
    )
    rows = cursor.fetchall()
    for row in rows:
        previous = row["request_fingerprint"]
        if not LEGACY_FINGERPRINT.fullmatch(previous) or row["preview_fingerprint"] != previous:
            raise AccountReceiptProtectionError("account_receipt_fingerprint_invalid")
        fingerprint = protect_receipt_fingerprint(key, row["command_family"], row["idempotency_key"], previous)
        cursor.execute(
            "UPDATE admin_command_receipts SET request_fingerprint=%s, preview_fingerprint=%s WHERE id=%s",
            (fingerprint, fingerprint, row["id"]),
        )
    require_protected_account_receipts(cursor)
    return len(rows)
