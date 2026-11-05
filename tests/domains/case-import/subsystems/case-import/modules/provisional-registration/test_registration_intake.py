"""The public boundary has no SQL imports or approval endpoints, even on malformed input."""
import ast
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.registration_intake import app, get_staging, get_verifier
from domains.line.identities import LineUserId


def test_intake_import_closure_cannot_load_sql_or_app_settings():
    source = """
import importlib.abc, sys
class BlockSql(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  if fullname.startswith(('infrastructure.mysql','pymysql','mysql','sqlalchemy','api.main','api.nas_apps','config.settings')):
   raise AssertionError('SQL dependency crossed intake boundary')
sys.meta_path.insert(0,BlockSql())
import api.registration_intake
assert all('approve' not in r.path and 'reject' not in r.path for r in api.registration_intake.app.routes)
"""
    result = subprocess.run([sys.executable, "-B", "-c", source], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_intake_validation_does_not_echo_questionnaire_or_tokens():
    app.dependency_overrides[get_staging] = lambda: object()
    app.dependency_overrides[get_verifier] = lambda: object()
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/line/identity/registration/apply", json={"line_id_token": "synthetic-private-token",
                "refund_account_no": "synthetic-private-account"})
        assert response.status_code == 422
        assert "synthetic-private" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_preview_uses_verified_subject_and_never_opens_staging_or_sql():
    def no_storage():
        raise AssertionError("Preview is zero write and needs no staging connection")
    app.dependency_overrides[get_staging] = no_storage
    app.dependency_overrides[get_verifier] = lambda: SimpleNamespace(verify=lambda _: SimpleNamespace(line_user_id=LineUserId("U-verified-synthetic")))
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/line/identity/registration/preview", json={
                "line_id_token": "synthetic-token", "name": "合成申請", "phone": "0900000000",
                "address": "合成地址", "service_days": 10, "expected_date": "2026-11-20"})
        assert response.status_code == 200
        assert response.json()["data"]["expected_binding_version"] == 0
    finally:
        app.dependency_overrides.clear()


def test_old_public_registration_routes_cannot_reach_sql():
    from api.routes.line_identity import public_router
    assert not any("/registration/" in route.path for route in public_router.routes)
    tree = ast.parse(Path("line/line_bot.py").read_text(encoding="utf-8"))
    handler = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "line_register")
    assert len(handler.body) == 1 and isinstance(handler.body[0], ast.Raise)


def test_public_container_has_no_mysql_settings_or_network_egress():
    import yaml
    config = yaml.safe_load(Path("docker-compose.registration.yml").read_text(encoding="utf-8"))
    intake = config["services"]["registration-intake"]
    assert not any(key.startswith(("DB_", "MYSQL")) for key in intake["environment"])
    assert all(config["networks"][key].get("internal") is True for key in intake["networks"])
    assert "ports" not in config["services"]["registration-redis"]
    image_source = Path("deploy/registration/Dockerfile").read_text(encoding="utf-8")
    assert "COPY infrastructure/mysql" not in image_source
    assert "COPY api/main.py" not in image_source
