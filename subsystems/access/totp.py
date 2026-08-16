"""
File: totp.py
Description: 提供 RFC 6238 TOTP、seed 加密與 recovery code 的純安全規則。
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken


TOTP_TIME_STEP_SECONDS = 30
TOTP_DIGITS = 6
TOTP_SECRET_BYTES = 20
TOTP_ALLOWED_DRIFT_STEPS = 1
RECOVERY_CODE_COUNT = 10
RECOVERY_CODE_LENGTH = 10


class TotpError(ValueError):
    """Raised when a TOTP input or configured key cannot be used safely."""


class TotpSecretUnavailableError(RuntimeError):
    """Raised when the configured keyring cannot decrypt an enrolled factor."""


@dataclass(frozen=True, slots=True)
class EncryptedTotpSecret:
    ciphertext: str
    key_version: str


@dataclass(frozen=True, slots=True)
class TotpVerification:
    matched_step: int


class TotpSecretCipher:
    """Encrypts factor seeds with an application-owned, versioned Fernet keyring."""

    def __init__(self, keyring: Mapping[str, str], active_key_version: str) -> None:
        if not active_key_version or active_key_version not in keyring:
            raise TotpError("TOTP active encryption key is unavailable")
        try:
            self._keys = {
                version: Fernet(value.encode("ascii"))
                for version, value in keyring.items()
                if version and value
            }
        except (TypeError, ValueError) as error:
            raise TotpError("TOTP encryption key format is invalid") from error
        if active_key_version not in self._keys:
            raise TotpError("TOTP active encryption key is unavailable")
        self._active_key_version = active_key_version

    def encrypt(self, secret: str) -> EncryptedTotpSecret:
        normalized = normalize_totp_secret(secret)
        ciphertext = self._keys[self._active_key_version].encrypt(
            normalized.encode("ascii")
        )
        return EncryptedTotpSecret(
            ciphertext=ciphertext.decode("ascii"), key_version=self._active_key_version
        )

    def decrypt(self, encrypted: EncryptedTotpSecret) -> str:
        key = self._keys.get(encrypted.key_version)
        if key is None:
            raise TotpSecretUnavailableError("TOTP encryption key version is unavailable")
        try:
            return normalize_totp_secret(key.decrypt(encrypted.ciphertext.encode("ascii")).decode("ascii"))
        except (InvalidToken, UnicodeError, TotpError) as error:
            raise TotpSecretUnavailableError("TOTP factor secret is unavailable") from error


def totp_cipher_from_environment() -> TotpSecretCipher:
    """Load a versioned Fernet keyring and reject an absent or malformed setting."""
    raw_keyring = os.getenv("ACCESS_CONTROL_TOTP_KEYRING", "").strip()
    active_version = os.getenv("ACCESS_CONTROL_TOTP_ACTIVE_KEY_VERSION", "").strip()
    if not raw_keyring or not active_version:
        raise TotpError("TOTP encryption keyring is unavailable")
    keyring: dict[str, str] = {}
    for item in raw_keyring.split(","):
        version, separator, key = item.strip().partition(":")
        if not separator or not version or not key or version in keyring:
            raise TotpError("TOTP encryption keyring format is invalid")
        keyring[version] = key
    return TotpSecretCipher(keyring, active_version)


def generate_totp_secret() -> str:
    """Return a random base32 seed suitable for standard authenticator applications."""
    return base64.b32encode(os.urandom(TOTP_SECRET_BYTES)).decode("ascii").rstrip("=")


def normalize_totp_secret(secret: str) -> str:
    normalized = "".join(str(secret).strip().upper().split())
    if not normalized or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for character in normalized):
        raise TotpError("TOTP secret is invalid")
    try:
        base64.b32decode(_padded_base32(normalized), casefold=True)
    except (ValueError, binascii.Error) as error:
        raise TotpError("TOTP secret is invalid") from error
    return normalized


def provisioning_uri(*, secret: str, account_name: str, issuer: str) -> str:
    normalized_secret = normalize_totp_secret(secret)
    normalized_account = account_name.strip()
    normalized_issuer = issuer.strip()
    if not normalized_account or not normalized_issuer:
        raise TotpError("TOTP account and issuer are required")
    label = quote(f"{normalized_issuer}:{normalized_account}", safe="")
    return (
        f"otpauth://totp/{label}?secret={normalized_secret}&issuer="
        f"{quote(normalized_issuer, safe='')}&algorithm=SHA1&digits={TOTP_DIGITS}"
        f"&period={TOTP_TIME_STEP_SECONDS}"
    )


def verify_totp(
    *, secret: str, code: str, now: datetime, allowed_drift_steps: int = TOTP_ALLOWED_DRIFT_STEPS
) -> TotpVerification | None:
    if allowed_drift_steps < 0:
        raise TotpError("TOTP drift window is invalid")
    normalized_secret = normalize_totp_secret(secret)
    normalized_code = str(code).strip()
    if len(normalized_code) != TOTP_DIGITS or not normalized_code.isascii() or not normalized_code.isdigit():
        return None
    step = totp_step(now)
    for candidate_step in range(step - allowed_drift_steps, step + allowed_drift_steps + 1):
        if candidate_step < 0:
            continue
        candidate = _totp_code(normalized_secret, candidate_step)
        if hmac.compare_digest(candidate, normalized_code):
            return TotpVerification(matched_step=candidate_step)
    return None


def totp_step(now: datetime) -> int:
    if now.tzinfo is None:
        raise TotpError("TOTP clock must be timezone-aware")
    return int(now.astimezone(timezone.utc).timestamp()) // TOTP_TIME_STEP_SECONDS


def generate_recovery_codes() -> tuple[str, ...]:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return tuple(
        "".join(alphabet[byte % len(alphabet)] for byte in os.urandom(RECOVERY_CODE_LENGTH))
        for _ in range(RECOVERY_CODE_COUNT)
    )


def hash_recovery_code(code: str) -> str:
    normalized = _normalize_recovery_code(code)
    salt = os.urandom(16)
    derived = hashlib.scrypt(normalized.encode("ascii"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$16384$8$1$" + base64.urlsafe_b64encode(salt).decode("ascii") + "$" + base64.urlsafe_b64encode(derived).decode("ascii")


def verify_recovery_code(code: str, encoded_hash: str) -> bool:
    try:
        algorithm, n, r, p, salt_b64, expected_b64 = encoded_hash.split("$", 5)
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(expected_b64.encode("ascii"))
        actual = hashlib.scrypt(
            _normalize_recovery_code(code).encode("ascii"), salt=salt,
            n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, binascii.Error):
        return False


def _totp_code(secret: str, step: int) -> str:
    key = base64.b32decode(_padded_base32(secret), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % (10**TOTP_DIGITS)).zfill(TOTP_DIGITS)


def _padded_base32(secret: str) -> str:
    return secret + "=" * (-len(secret) % 8)


def _normalize_recovery_code(code: str) -> str:
    normalized = "".join(str(code).strip().upper().split("-"))
    if len(normalized) != RECOVERY_CODE_LENGTH or not normalized.isalnum() or not normalized.isascii():
        raise TotpError("Recovery code is invalid")
    return normalized
