"""
File: test_nas_test_bundle.py
Description: 驗證 LINE Worker 零副作用啟動檢查、MySQL TLS 設定、來源打包過濾與純 NAS DB Compose 邊界。
"""
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest
import yaml

from scripts import package_windows_runtime, run_line_worker

ROOT = Path(__file__).resolve().parents[7]


def test_line_check_never_enters_a_work_cycle(monkeypatch):
    client = Mock()
    client.run_line_cycle.side_effect = AssertionError("LINE work must not run")
    monkeypatch.setattr(run_line_worker, "PrivateOperationsClient", lambda _: client)
    monkeypatch.setattr(run_line_worker, "discard_database_credentials", lambda: None)
    monkeypatch.setattr(sys, "argv", ["run_line_worker", "--check"])
    assert run_line_worker.main() == 0
    client.check.assert_called_once_with()
    client.run_line_cycle.assert_not_called()


def test_line_check_auth_failure_does_not_process_work(monkeypatch):
    from infrastructure.http.private_operations_client import PrivateOperationError

    client = Mock()
    client.check.side_effect = PrivateOperationError("denied", retryable=False)
    monkeypatch.setattr(run_line_worker, "PrivateOperationsClient", lambda _: client)
    monkeypatch.setattr(run_line_worker, "discard_database_credentials", lambda: None)
    monkeypatch.setattr(sys, "argv", ["run_line_worker", "--check"])
    assert run_line_worker.main() == 2
    client.run_line_cycle.assert_not_called()


def test_server_tls_without_client_key_and_partial_mtls_rejected(monkeypatch):
    from infrastructure.mysql.mysql_adapter import _database_config_from_environment

    monkeypatch.setenv("DB_SSL_MODE", "verify_identity")
    monkeypatch.setenv("DB_SSL_CA", "synthetic-ca.pem")
    monkeypatch.setenv("DB_SSL_CERT", "")
    monkeypatch.setenv("DB_SSL_KEY", "")
    assert _database_config_from_environment()["ssl"] == {
        "ca": "synthetic-ca.pem",
        "check_hostname": True,
    }
    monkeypatch.setenv("DB_SSL_CERT", "synthetic-client.pem")
    with pytest.raises(RuntimeError, match="both"):
        _database_config_from_environment()


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        "api/.env.local",
        "config/credentials.json",
        "config/service_account_nas.json",
        "db/local.sqlite",
        "line/token.json",
        "ui_react/node_modules/dep/index.js",
    ],
)
def test_build_context_does_not_admit_local_credentials_or_data(name):
    assert not package_windows_runtime.include_source(name)


def test_nas_compose_is_database_only():
    compose = yaml.safe_load((ROOT / "deployment/nas/compose.yaml").read_text(encoding="utf-8"))
    assert set(compose["services"]) == {"db"}
    db_service = compose["services"]["db"]
    assert "mysql:" in db_service["image"]
    assert "no-new-privileges:true" in db_service["security_opt"]
    assert any("mysql-data:/var/lib/mysql" in str(v) for v in db_service["volumes"])
    assert "default-character-set=utf8mb4" in (
        ROOT / "deployment/nas/mysql-client.cnf"
    ).read_text(encoding="utf-8")
