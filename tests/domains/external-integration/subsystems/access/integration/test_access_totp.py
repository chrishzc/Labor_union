"""
File: test_access_totp.py
Description: 驗證 TOTP seed、加密、RFC 向量與 recovery code 的安全規則。
"""

from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet

from subsystems.access.totp import (
    EncryptedTotpSecret,
    TotpError,
    TotpSecretCipher,
    TotpSecretUnavailableError,
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_code,
    provisioning_uri,
    verify_recovery_code,
    verify_totp,
)


RFC6238_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


def test_totp_matches_rfc6238_sha1_vector() -> None:
    verification = verify_totp(
        secret=RFC6238_SECRET,
        code="287082",
        now=datetime.fromtimestamp(59, tz=timezone.utc),
    )

    assert verification is not None
    assert verification.matched_step == 1


def test_totp_accepts_only_one_adjacent_time_step() -> None:
    now = datetime.fromtimestamp(59, tz=timezone.utc)

    assert verify_totp(secret=RFC6238_SECRET, code="755224", now=now) is not None
    assert verify_totp(secret=RFC6238_SECRET, code="969429", now=now) is None
    assert verify_totp(secret=RFC6238_SECRET, code="000000", now=now) is None


def test_totp_cipher_round_trip_and_wrong_key_fail_closed() -> None:
    key = Fernet.generate_key().decode("ascii")
    cipher = TotpSecretCipher({"v1": key}, "v1")
    encrypted = cipher.encrypt(RFC6238_SECRET)

    assert encrypted.key_version == "v1"
    assert encrypted.ciphertext != RFC6238_SECRET
    assert cipher.decrypt(encrypted) == RFC6238_SECRET

    wrong_cipher = TotpSecretCipher({"v2": Fernet.generate_key().decode("ascii")}, "v2")
    with pytest.raises(TotpSecretUnavailableError):
        wrong_cipher.decrypt(EncryptedTotpSecret(encrypted.ciphertext, "v2"))


def test_provisioning_uri_and_recovery_codes_do_not_persist_plaintext() -> None:
    secret = generate_totp_secret()
    uri = provisioning_uri(secret=secret, account_name="root", issuer="Labor Union")
    code = generate_recovery_codes()[0]
    encoded = hash_recovery_code(code)

    assert uri.startswith("otpauth://totp/")
    assert "issuer=Labor%20Union" in uri
    assert code not in encoded
    assert verify_recovery_code(code, encoded)
    assert not verify_recovery_code("AAAAAAAAAA", encoded)


def test_totp_rejects_naive_clock_and_invalid_recovery_code() -> None:
    with pytest.raises(TotpError):
        verify_totp(secret=RFC6238_SECRET, code="287082", now=datetime(1970, 1, 1))
    with pytest.raises(TotpError):
        hash_recovery_code("short")
