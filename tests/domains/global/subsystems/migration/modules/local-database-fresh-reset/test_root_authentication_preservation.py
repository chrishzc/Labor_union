"""Reset must retain root credentials without exposing or replacing MFA secrets."""
import json
import secrets

import pytest
from cryptography.fernet import Fernet

from scripts import reset_root_authentication as preservation
from subsystems.access.totp import TotpSecretCipher, generate_totp_secret


def test_encrypted_backup_roundtrip_and_target_binding(monkeypatch, tmp_path):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ACCESS_CONTROL_TOTP_KEYRING", "v1:" + key)
    monkeypatch.setenv("ACCESS_CONTROL_TOTP_ACTIVE_KEY_VERSION", "v1")
    seed = generate_totp_secret()
    encrypted = TotpSecretCipher({"v1": key}, "v1").encrypt(seed)
    snapshot = {table: [] for table in preservation.TABLES}
    password_hash = secrets.token_urlsafe(24)
    snapshot["admin_users"] = [{"password_hash": password_hash}]
    snapshot["admin_totp_factors"] = [{"factor_state": "active", "seed_ciphertext": encrypted.ciphertext, "encryption_key_version": "v1"}]
    config = {"host": "127.0.0.1", "port": 3306, "database": "lu_test_root"}
    path = tmp_path / "root.encrypted.json"
    result = preservation.save_root_authentication(snapshot, config, path)
    assert result["status"] == "encrypted_and_verified"
    assert preservation.load_root_authentication(path, config) == snapshot
    for sensitive in (seed, password_hash, encrypted.ciphertext, key):
        assert sensitive not in path.read_text() and sensitive not in json.dumps(result)
    with pytest.raises(preservation.RootPreservationError, match="another target"):
        preservation.load_root_authentication(path, {**config, "database": "union_db"})
    envelope = json.loads(path.read_text())
    envelope["ciphertext"] = envelope["ciphertext"][:-5] + "AAAAA"
    path.write_text(json.dumps(envelope))
    with pytest.raises(preservation.RootPreservationError):
        preservation.load_root_authentication(path, config)


def test_missing_key_refuses_backup_without_writing_secret(monkeypatch, tmp_path):
    monkeypatch.delenv("ACCESS_CONTROL_TOTP_KEYRING", raising=False)
    snapshot = {table: [] for table in preservation.TABLES}
    snapshot["admin_users"] = [{"id": 1}]
    path = tmp_path / "root.json"
    with pytest.raises(preservation.RootPreservationError, match="keyring"):
        preservation.save_root_authentication(snapshot, {}, path)
    assert not path.exists()
