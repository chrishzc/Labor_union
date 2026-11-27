"""
File: test_registration_intake.py
Description: 驗證公開登記收件容器邊界與胎數閉鎖輸入之 422 拒收行為。
"""
import ast
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.registration_contracts import registration_intent
from api.registration_intake import app, get_staging, get_verifier
from api.schemas.line_identity import ProvisionalRegistrationPreviewRequest
from domains.case_import.provisional_registration import (
    ProvisionalRegistrationCandidate, build_provisional_registration_candidate,
)
from domains.line.identities import LineUserId
from subsystems.case_import.provisional_registration_types import (
    ProvisionalRegistrationConflictError, ProvisionalRegistrationStorageError,
)
from subsystems.case_import.registration_staging import StagedRegistration


REQUIRED_CARE_ANSWERS = {
    "哺乳方式：": "母乳",
    "洗澡水準備：": "不需另外準備",
    "5媽咪有無過敏體質：": "無",
    "特殊照護時應注意事項：": "無",
    "月子餐點調理喜好/飲食習慣：": "不用料理/訂月餐",
    "呈上題，若遇無法媒合到葷食服務人員時，是否可以接受蛋奶素服務人員？": "可接受",
    "可以接受中藥補品：□茶飲 □藥飲 □藥膳": "無法接受中藥補品",
    "2．餐飲含酒比例：": "無酒料理",
    "3．料理用油：(可接受種類)": "不適用",
    "餐點喜忌備註：": "無",
    "烹煮工具": "無上述設備",
    "透天服務樓層方式(會加收樓層費)": "大樓公寓無樓層問題",
    "提供服務人員轎車停車位": "有",
}


def test_non_citizen_intake_can_preview_without_sql_app_settings_or_pandas():
    source = """
import importlib.abc, sys
from types import SimpleNamespace
class BlockDependencies(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  if fullname.startswith(('infrastructure.mysql','pymysql','mysql','sqlalchemy','api.main','api.nas_apps','config.settings','pandas')):
   raise ModuleNotFoundError(fullname)
sys.meta_path.insert(0, BlockDependencies())
from fastapi.testclient import TestClient
from api.registration_intake import app, get_staging, get_verifier
from domains.line.identities import LineUserId
assert all('approve' not in route.path and 'reject' not in route.path for route in app.routes)
app.dependency_overrides[get_staging] = object
app.dependency_overrides[get_verifier] = lambda: SimpleNamespace(verify=lambda _: SimpleNamespace(line_user_id=LineUserId('U-synthetic')))
with TestClient(app) as client:
 response = client.post('/api/v1/line/identity/registration/preview', json={
  'line_id_token': 'synthetic-token', 'name': '測試申請', 'phone': '0900000000',
  'address': '測試地址', 'expected_date': '2026-11-20', 'service_days': 10,
  'email': 'test@example.com', 'birth_date': '1990-01-01', 'gender': '女', 'city': '新竹市',
  'registration_kind': 'non_citizen', 'service_start_date': '2026-11-20',
  'service_time': '08:30-12:30 (4小時)', 'residence_type': '電梯大樓',
  'delivery_type': '自然產', 'service_type': '連續服務', 'baby_info': '單胞胎', 'notes': '無',
  'survey_details': {
   **REQUIRED_CARE_ANSWERS,
   '特殊計費:胎數': '單胞胎', '服務時間內是否有其他寶寶': '無', '是否需要下廚：': '不需要下廚',
   '代購食材': '自行準備',
   '補助款退款:銀行代號+分行代號': '0000000', '銀行帳號': '0000000000',
  },
 })
 assert response.status_code == 200, response.status_code
 assert response.json()['data']['status'] == 'ready'
""".replace("REQUIRED_CARE_ANSWERS", repr(REQUIRED_CARE_ANSWERS))
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


def test_non_citizen_without_passbook_can_preview_apply_and_read_original_submission() -> None:
    submission_id = str(uuid4())
    saved: list[StagedRegistration] = []

    class Staging:
        def submit(self, candidate: ProvisionalRegistrationCandidate, key: str) -> StagedRegistration:
            assert key == submission_id
            assert candidate.line_user_id == "U-verified-synthetic"
            assert candidate.registration_kind == "non_citizen"
            survey = candidate.beclass_payload["survey_details"]
            assert isinstance(survey, dict)
            assert "passbook_image_id" not in survey["_liff_meta"]
            now = datetime.now(timezone.utc)
            snapshot = StagedRegistration(234, 1, "pending", now, now + timedelta(days=14),
                                          candidate.registration_kind, candidate)
            saved.append(snapshot)
            return snapshot

        def status_for_submission(self, line_user_id: str, key: str) -> StagedRegistration | None:
            assert (line_user_id, key) == ("U-verified-synthetic", submission_id)
            return saved[0] if saved else None

    app.dependency_overrides[get_staging] = Staging
    app.dependency_overrides[get_verifier] = _verified_test_verifier
    try:
        with TestClient(app) as client:
            base = "/api/v1/line/identity/registration"
            payload = _registration_payload("non_citizen")
            query = {"line_id_token": payload["line_id_token"], "submission_id": submission_id}
            preview = client.post(f"{base}/preview", json=payload)
            assert preview.status_code == 200, preview.text
            ready = preview.json()["data"]
            assert ready["status"] == "ready"
            assert client.post(f"{base}/status", json=query).json()["data"] == {"status": "not_received"}
            response = client.post(
                f"{base}/apply",
                json={**payload, "expected_binding_version": ready["expected_binding_version"],
                      "preview_fingerprint": ready["preview_fingerprint"]},
                headers={"Idempotency-Key": submission_id},
            )
            assert response.status_code == 200, response.text
            receipt = response.json()["data"]
            assert receipt["status"] == "pending" and receipt["identity_status"] == "pending_approval"
            assert receipt["registration_id"] == 234
            assert all(receipt[field] is None for field in ("client_id", "beclass_record_id", "case_no"))
            assert client.post(f"{base}/status", json=query).json()["data"] == receipt
            assert len(saved) == 1
    finally:
        app.dependency_overrides.clear()


def _verified_test_verifier() -> SimpleNamespace:
    return SimpleNamespace(verify=lambda _token: SimpleNamespace(line_user_id=LineUserId("U-verified-synthetic")))


def _registration_payload(kind: str | None) -> dict[str, object]:
    payload: dict[str, object] = {
        "line_id_token": "synthetic-token", "name": "合成申請", "phone": "0900000000",
        "address": "合成地址", "expected_date": "2026-11-20", "service_days": 10,
        "email": "test@example.com", "birth_date": "1990-01-01", "gender": "女", "city": "新竹市",
        "service_start_date": "2026-11-20", "service_time": "08:30-12:30 (4小時)",
        "residence_type": "電梯大樓", "delivery_type": "自然產", "service_type": "週休 1 日",
        "baby_info": "單胞胎", "notes": "無",
        "survey_details": {
            **REQUIRED_CARE_ANSWERS,
            "特殊計費:胎數": "單胞胎", "服務時間內是否有其他寶寶": "無", "是否需要下廚：": "不需要下廚",
            "代購食材": "自行準備", "補助款退款:銀行代號+分行代號": "0000000", "銀行帳號": "0000000000",
        },
    }
    if kind is not None:
        payload["registration_kind"] = kind
    return payload


@pytest.mark.parametrize(
    ("kind", "image_id"),
    [
        pytest.param(None, None, id="default-omitted"),
        pytest.param("subsidy", None, id="subsidy-omitted"),
        pytest.param(None, "pbk_missing", id="default-missing"),
        pytest.param("subsidy", "pbk_missing", id="subsidy-missing"),
        pytest.param(None, "pbk_foreign", id="default-foreign"),
        pytest.param("subsidy", "pbk_foreign", id="subsidy-foreign"),
        pytest.param("non_citizen", "pbk_missing", id="non-citizen-missing"),
        pytest.param("non_citizen", "pbk_foreign", id="non-citizen-foreign"),
    ],
)
def test_intake_rejects_missing_or_foreign_required_passbook(kind: str | None, image_id: str | None) -> None:
    staged_for_preview = False

    def get_passbook_image(image: str, *, line_user_id: str) -> tuple[dict[str, str], bytes] | None:
        owners = {"pbk_foreign": "U-another-synthetic"}
        if (staged_for_preview and line_user_id == "U-verified-synthetic") or owners.get(image) == line_user_id:
            return {"passbook_image_id": image}, b"image"
        return None

    app.dependency_overrides[get_staging] = lambda: SimpleNamespace(
        get_passbook_image=get_passbook_image, replay_submission=lambda _candidate, _key: None,
    )
    app.dependency_overrides[get_verifier] = _verified_test_verifier
    try:
        with TestClient(app) as client:
            payload = _registration_payload(kind)
            fingerprint = "a" * 64
            if image_id is not None:
                payload["passbook_image_id"] = image_id
                staged_for_preview = True
                preview = client.post("/api/v1/line/identity/registration/preview", json=payload)
                assert preview.status_code == 200
                fingerprint = preview.json()["data"]["preview_fingerprint"]
                staged_for_preview = False
            _assert_preview_and_apply_rejected(
                client, payload, "registration_input_invalid" if image_id is None else "passbook_image_missing",
                fingerprint=fingerprint,
            )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("concurrent", [False, True], ids=["persisted", "persisted-after-lookup"])
def test_apply_replays_original_receipt_after_passbook_cleanup(concurrent: bool) -> None:
    base = "/api/v1/line/identity/registration"
    key = str(uuid4())
    payload = {**_registration_payload("subsidy"), "passbook_image_id": "pbk_synthetic"}
    saved: StagedRegistration | None = None
    pending_image = True
    commit_after_lookup = False

    class Staging:
        def get_passbook_image(self, image_id: str, *, line_user_id: str) -> tuple[dict[str, str], bytes] | None:
            assert (image_id, line_user_id) == ("pbk_synthetic", "U-verified-synthetic")
            if not pending_image:
                assert concurrent, "Replay must not read the deleted image"
                return None
            return {"passbook_image_id": image_id}, b"image"

        def replay_submission(self, candidate: ProvisionalRegistrationCandidate, submission_id: str) -> StagedRegistration | None:
            nonlocal commit_after_lookup
            if commit_after_lookup:
                commit_after_lookup = False
                return None
            if submission_id != key or saved is None:
                return None
            assert saved.candidate is not None
            if candidate.payload_fingerprint != saved.candidate.payload_fingerprint:
                raise ProvisionalRegistrationConflictError("registration_active_application_conflict")
            return replace(saved, replayed=True)

        def submit(self, candidate: ProvisionalRegistrationCandidate, submission_id: str) -> StagedRegistration:
            nonlocal saved
            assert saved is None and submission_id == key
            now = datetime.now(timezone.utc)
            saved = StagedRegistration(234, 1, "pending", now, now + timedelta(days=14), "subsidy", candidate)
            return saved

    app.dependency_overrides[get_staging] = Staging
    app.dependency_overrides[get_verifier] = _verified_test_verifier
    try:
        with TestClient(app) as client:
            preview = client.post(f"{base}/preview", json=payload)
            assert preview.status_code == 200
            command = {**payload, "expected_binding_version": 0,
                       "preview_fingerprint": preview.json()["data"]["preview_fingerprint"]}
            headers = {"Idempotency-Key": key}
            first = client.post(f"{base}/apply", json=command, headers=headers)
            assert first.status_code == 200
            assert first.json()["data"]["registration_id"] == 234
            assert saved is not None
            saved = replace(saved, status="approved", client_id=345, beclass_record_id=456)
            pending_image = False
            commit_after_lookup = concurrent

            replay = client.post(f"{base}/apply", json=command, headers=headers)
            assert replay.status_code == 200
            assert replay.json()["data"]["registration_id"] == 234
            assert replay.json()["data"]["status"] == "approved"
            assert replay.json()["data"]["replayed"] is True

            stale = client.post(f"{base}/apply", json={**command, "expected_binding_version": 1}, headers=headers)
            assert stale.status_code == 409
            assert stale.json()["detail"]["error"]["code"] == "registration_preview_stale"

            edited_payload = {**payload, "name": "不同合成姓名"}
            pending_image = True
            edited_preview = client.post(f"{base}/preview", json=edited_payload)
            assert edited_preview.status_code == 200
            pending_image = False
            changed = client.post(f"{base}/apply", json={
                **edited_payload, "expected_binding_version": 0,
                "preview_fingerprint": edited_preview.json()["data"]["preview_fingerprint"],
            }, headers=headers)
            assert changed.status_code == 409
            assert changed.json()["detail"]["error"]["code"] == "registration_conflict"
    finally:
        app.dependency_overrides.clear()


def test_status_reports_store_failure_as_unconfirmed() -> None:
    def unavailable(_line_user_id: str, _submission_id: str) -> StagedRegistration | None:
        raise ProvisionalRegistrationStorageError("registration_redis_initialization_required")

    app.dependency_overrides[get_staging] = lambda: SimpleNamespace(status_for_submission=unavailable)
    app.dependency_overrides[get_verifier] = _verified_test_verifier
    try:
        with TestClient(app) as client:
            result = client.post("/api/v1/line/identity/registration/status", json={
                "line_id_token": "synthetic-token", "submission_id": str(uuid4()),
            })
            assert result.status_code == 503
            assert result.json()["detail"]["error"]["code"] == "registration_unavailable"
            assert "not_received" not in result.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("field", ["補助款退款:銀行代號+分行代號", "銀行帳號"])
@pytest.mark.parametrize("invalid", [None, " ", "invalid"], ids=["missing", "blank", "invalid"])
def test_non_citizen_without_passbook_still_rejects_invalid_bank_fields(field: str, invalid: str | None) -> None:
    app.dependency_overrides[get_staging] = object
    app.dependency_overrides[get_verifier] = _verified_test_verifier
    try:
        with TestClient(app) as client:
            payload = _registration_payload("non_citizen")
            survey = payload["survey_details"]
            assert isinstance(survey, dict)
            if invalid is None:
                del survey[field]
            else:
                survey[field] = invalid
            _assert_preview_and_apply_rejected(client, payload, "registration_input_invalid")
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("kind", ["subsidy", "non_citizen"])
@pytest.mark.parametrize("field", [*REQUIRED_CARE_ANSWERS, "服務時間內是否有其他寶寶"])
def test_new_intake_rejects_missing_or_blank_required_care_answers(kind: str, field: str) -> None:
    app.dependency_overrides[get_staging] = lambda: SimpleNamespace(replay_submission=lambda _candidate, _key: None)
    app.dependency_overrides[get_verifier] = _verified_test_verifier
    try:
        with TestClient(app) as client:
            payload = _registration_payload(kind)
            if kind == "subsidy":
                payload["passbook_image_id"] = "pbk_synthetic"
            survey = payload["survey_details"]
            assert isinstance(survey, dict)
            del survey[field]
            for answer in ({}, {field: "  "}):
                command = {**payload, "survey_details": {**survey, **answer}}
                fingerprint = "a" * 64
                if kind != "non_citizen" or field != "服務時間內是否有其他寶寶":
                    candidate = build_provisional_registration_candidate(registration_intent(
                        ProvisionalRegistrationPreviewRequest.model_validate(command), LineUserId("U-verified-synthetic"),
                    ))
                    fingerprint = candidate.payload_fingerprint.value
                _assert_preview_and_apply_rejected(
                    client, command, "registration_input_invalid", fingerprint=fingerprint,
                )
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("kind", ["subsidy", "non_citizen"])
def test_new_intake_rejects_conflicting_diet_and_cooking_answers(kind: str) -> None:
    app.dependency_overrides[get_staging] = object
    app.dependency_overrides[get_verifier] = _verified_test_verifier
    try:
        with TestClient(app) as client:
            payload = _registration_payload(kind)
            if kind == "subsidy":
                payload["passbook_image_id"] = "pbk_synthetic"
            survey = payload["survey_details"]
            assert isinstance(survey, dict)
            survey["月子餐點調理喜好/飲食習慣："] = "葷食"
            _assert_preview_and_apply_rejected(client, payload, "registration_input_invalid")
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("kind", ["subsidy", "non_citizen"])
def test_apply_can_replay_exact_original_receipt_with_historical_care_answers(kind: str) -> None:
    key = str(uuid4())
    payload = _registration_payload(kind)
    if kind == "subsidy":
        payload["passbook_image_id"] = "pbk_already_cleaned_up"
    survey = payload["survey_details"]
    assert isinstance(survey, dict)
    del survey["哺乳方式："]
    original = build_provisional_registration_candidate(registration_intent(
        ProvisionalRegistrationPreviewRequest.model_validate(payload), LineUserId("U-verified-synthetic"),
    ))
    now = datetime.now(timezone.utc)
    saved = StagedRegistration(234, 1, "pending", now, now + timedelta(days=14), original.registration_kind, original)

    def replay_submission(candidate: ProvisionalRegistrationCandidate, submission_id: str) -> StagedRegistration | None:
        if submission_id != key:
            return None
        assert candidate.line_user_id == original.line_user_id
        assert candidate.payload_fingerprint == original.payload_fingerprint
        return replace(saved, replayed=True)

    app.dependency_overrides[get_staging] = lambda: SimpleNamespace(replay_submission=replay_submission)
    app.dependency_overrides[get_verifier] = _verified_test_verifier
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/line/identity/registration/apply", json={
                **payload, "expected_binding_version": 0, "preview_fingerprint": original.payload_fingerprint.value,
            }, headers={"Idempotency-Key": key})
            assert response.status_code == 200, response.text
            assert response.json()["data"]["registration_id"] == 234
            assert response.json()["data"]["replayed"] is True
    finally:
        app.dependency_overrides.clear()


def _assert_preview_and_apply_rejected(
    client: TestClient, payload: dict[str, object], code: str, *, fingerprint: str = "a" * 64,
) -> None:
    base = "/api/v1/line/identity/registration"
    preview = client.post(f"{base}/preview", json=payload)
    assert preview.status_code == 422, preview.text
    detail = preview.json()["detail"]
    assert detail.get("error", detail)["code"] == code
    apply = client.post(
        f"{base}/apply",
        json={**payload, "expected_binding_version": 0, "preview_fingerprint": fingerprint},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert apply.status_code == 422, apply.text
    detail = apply.json()["detail"]
    assert detail.get("error", detail)["code"] == code


def test_preview_uses_verified_subject_and_never_opens_staging_or_sql():
    def read_only_get_passbook(image_id, *, line_user_id=None):
        assert image_id == "pbk_synthetic_preview"
        assert line_user_id == "U-verified-synthetic"
        return ({"passbook_image_id": image_id}, b"img")
    def no_write(*_args, **_kwargs):
        raise AssertionError("Preview is zero write")
    app.dependency_overrides[get_staging] = lambda: SimpleNamespace(
        get_passbook_image=read_only_get_passbook,
        submit=no_write,
        stage_passbook_image=no_write,
    )
    app.dependency_overrides[get_verifier] = lambda: SimpleNamespace(verify=lambda _: SimpleNamespace(line_user_id=LineUserId("U-verified-synthetic")))
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/line/identity/registration/preview", json={
                "line_id_token": "synthetic-token", "name": "合成申請", "phone": "0900000000",
                "address": "合成地址", "service_days": 10, "expected_date": "2026-11-20",
                "passbook_image_id": "pbk_synthetic_preview",
                "survey_details": {**REQUIRED_CARE_ANSWERS, "服務時間內是否有其他寶寶": "無",
                                   "特殊計費:胎數": "單胞胎", "代購食材": "自行準備"}})
            assert response.status_code == 200
            assert response.json()["data"]["expected_binding_version"] == 0
            bad = client.post("/api/v1/line/identity/registration/preview", json={
                "line_id_token": "synthetic-token", "name": "合成申請", "phone": "0900000000",
                "address": "合成地址", "service_days": 10, "expected_date": "2026-11-20",
                "passbook_image_id": "pbk_synthetic_preview",
                "survey_details": {**REQUIRED_CARE_ANSWERS, "服務時間內是否有其他寶寶": "無",
                                   "特殊計費:胎數": "第一胎", "代購食材": "自行準備"}})
            assert bad.status_code == 422
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
    config = yaml.safe_load(Path("docker-compose.yml").read_text(encoding="utf-8"))
    intake = config["services"]["registration-intake"]
    assert intake["environment"]["APP_ENV"] == "production"
    assert intake["environment"]["REGISTRATION_REDIS_HOST"] == "registration-redis"
    assert intake["secrets"] == ["registration_intake_password"]
    assert not any(key.startswith(("DB_", "MYSQL")) for key in intake["environment"])
    assert all(config["networks"][key].get("internal") is True for key in intake["networks"])
    loopback = config["services"]["registration-loopback"]
    assert loopback["read_only"] is True
    assert loopback["cap_drop"] == ["ALL"]
    assert not loopback.get("secrets")
    assert not any(key.startswith(("DB_", "MYSQL")) for key in loopback.get("environment", ()))
    assert set(loopback["networks"]) == {"registration-ingress", "registration-loopback-host"}
    for service_name in ("registration-redis", "registration-intake", "registration-loopback", "registration-token-verifier"):
        for binding in config["services"][service_name].get("ports", ()):
            assert str(binding).startswith("127.0.0.1:")
    image_source = Path("deploy/registration/Dockerfile").read_text(encoding="utf-8")
    assert "COPY infrastructure/mysql" not in image_source
    assert "COPY api/main.py" not in image_source


def test_registration_deployment_multipart_proxy_and_minimal_redis_acl():
    reqs = Path("deploy/registration/requirements.txt").read_text(encoding="utf-8")
    assert any(line.strip().startswith("python-multipart==") for line in reqs.splitlines())

    proxy = Path("deploy/registration/proxy-location.conf").read_text(encoding="utf-8")
    assert "location = /api/v1/line/identity/registration/passbook" in proxy
    assert "client_max_body_size 6m;" in proxy
    assert "client_max_body_size 300k;" in proxy

    acl_script = Path("deploy/registration/redis-entrypoint.sh").read_text(encoding="utf-8")
    intake_line = next(line for line in acl_script.splitlines() if line.startswith("user registration-intake "))
    assert "+pexpireat" in intake_line
    assert "%RW~registration:passbook:meta:*" in intake_line
    assert "%RW~registration:passbook:data:*" in intake_line
    assert "%RW~registration:*" not in intake_line
    assert "registration:decision:*" not in intake_line
    assert "+del" not in intake_line
    assert "+persist" not in intake_line
    assert "+zrevrange" not in intake_line
    assert "+zremrangebyrank" not in intake_line
    assert "+expire" not in intake_line

    admin_line = next(line for line in acl_script.splitlines() if line.startswith("user registration-admin "))
    assert "+zrevrange" in admin_line
    assert "+zremrangebyrank" in admin_line
    assert "+expire" in admin_line
    assert "%RW~registration:*" in admin_line


def test_passbook_upload_size_limits_magic_bytes_and_cross_user_isolation():
    staged_images = {}

    class _Staging:
        def stage_passbook_image(self, *, line_user_id, filename, mime_type, content):
            image_id = f"pbk_{len(staged_images) + 1:08d}"
            staged_images[image_id] = ({"passbook_image_id": image_id, "line_user_id": line_user_id,
                                        "filename": filename, "mime_type": mime_type, "size_bytes": len(content)}, content)
            return staged_images[image_id][0]

        def get_passbook_image(self, image_id, *, line_user_id=None):
            entry = staged_images.get(image_id)
            if not entry:
                return None
            meta, content = entry
            if line_user_id is not None and meta["line_user_id"] != line_user_id:
                return None
            return meta, content

    current_user = {"id": "U-owner-A"}
    app.dependency_overrides[get_staging] = lambda: _Staging()
    app.dependency_overrides[get_verifier] = lambda: SimpleNamespace(
        verify=lambda _: SimpleNamespace(line_user_id=LineUserId(current_user["id"]))
    )
    png_header = b"\x89PNG\r\n\x1a\n"
    try:
        with TestClient(app) as client:
            near_limit = png_header + b"0" * (5 * 1024 * 1024 - len(png_header) - 64)
            ok = client.post(
                "/api/v1/line/identity/registration/passbook",
                data={"line_id_token": "synthetic-token"},
                files={"file": ("passbook.png", near_limit, "image/png")},
            )
            assert ok.status_code == 200
            image_id = ok.json()["data"]["passbook_image_id"]

            oversized = png_header + b"0" * (5 * 1024 * 1024 + 1)
            too_big = client.post(
                "/api/v1/line/identity/registration/passbook",
                data={"line_id_token": "synthetic-token"},
                files={"file": ("too_big.png", oversized, "image/png")},
            )
            assert too_big.status_code in {413, 422}

            invalid_magic = client.post(
                "/api/v1/line/identity/registration/passbook",
                data={"line_id_token": "synthetic-token"},
                files={"file": ("fake.jpg", b"<svg>not-an-image</svg>", "image/jpeg")},
            )
            assert invalid_magic.status_code == 422

            # Other registration endpoints keep the tighter 300 KB body limit.
            oversized_preview = client.post(
                "/api/v1/line/identity/registration/preview",
                content=b"{" + b" " * (301 * 1024) + b"}",
                headers={"Content-Type": "application/json"},
            )
            assert oversized_preview.status_code == 413

            # Another LINE user cannot bind User A's passbook image.
            current_user["id"] = "U-other-B"
            cross_user = client.post(
                "/api/v1/line/identity/registration/preview",
                json={
                    "line_id_token": "synthetic-token", "name": "跨帳號測試", "phone": "0900000000",
                    "address": "合成地址", "service_days": 10, "expected_date": "2026-11-20",
                    "passbook_image_id": image_id,
                    "survey_details": {**REQUIRED_CARE_ANSWERS, "服務時間內是否有其他寶寶": "無",
                                       "特殊計費:胎數": "單胞胎", "代購食材": "自行準備"},
                },
            )
            assert cross_user.status_code == 422
            assert cross_user.json()["detail"]["error"]["code"] == "passbook_image_missing"
    finally:
        app.dependency_overrides.clear()


def test_redis_passbook_atomic_stage_ttl_sync_and_fail_closed_recovery():
    import json
    from infrastructure.redis.registration_staging_repository import RedisRegistrationStagingRepository, _STAGE_PASSBOOK, _SUBMIT, _DECIDE, _COMPLETE
    from shared_kernel.fingerprints import PreviewFingerprint
    from shared_kernel.identities import CorrelationId
    from subsystems.case_import.provisional_registration_types import ProvisionalRegistrationStorageError
    from subsystems.case_import.registration_staging import RegistrationApprovalReceipt, RegistrationReviewApplication

    # 1. Verify Redis repository passes passbook keys to atomic Lua scripts.
    eval_calls = []

    class _FakeRedis:
        def __init__(self):
            self.kv = {"registration:ready": "1", "registration:counter": "2"}

        def get(self, key):
            return self.kv.get(key)

        def eval(self, script, numkeys, *keys_and_args):
            keys = list(keys_and_args[:numkeys])
            args = list(keys_and_args[numkeys:])
            eval_calls.append((script, keys, args))
            if script is _STAGE_PASSBOOK:
                self.kv[keys[0]] = args[0]
                self.kv[keys[1]] = args[1]
                return ["staged"]
            if script is _SUBMIT:
                return ["created", "2"]
            if script is _DECIDE:
                return ["approving"]
            if script is _COMPLETE:
                return ["approved"]
            return ["ok"]

    fake = _FakeRedis()
    repo = RedisRegistrationStagingRepository(fake, now_ms=lambda: 1_700_000_000_000)
    staged_meta = repo.stage_passbook_image(line_user_id="U-1", filename="p.png", mime_type="image/png", content=b"\x89PNG\r\n\x1a\n123")
    image_id = staged_meta["passbook_image_id"]
    assert eval_calls[-1][0] is _STAGE_PASSBOOK
    assert f"registration:passbook:meta:{image_id}" in eval_calls[-1][1]
    assert f"registration:passbook:data:{image_id}" in eval_calls[-1][1]

    fake.kv["registration:meta:2"] = json.dumps({
        "registration_id": 2, "subject": staged_meta["subject"],
        "fingerprint": "a" * 64, "submitted_ms": 1_700_000_000_000,
        "expires_ms": 1_700_000_100_000, "registration_kind": "citizen_registration",
    })
    fake.kv["registration:content:2"] = json.dumps({
        "client": {"line_user_id": "U-1", "passbook_image_id": image_id},
        "beclass": {"survey_details": {"_liff_meta": {"passbook_image_id": image_id}}},
    })
    assert f"registration:passbook:meta:{image_id}" in repo._passbook_keys_for_registration(2)

    # 2. Verify fail-closed approval when passbook is missing or archiver fails, and idempotent recovery.
    class _WorkflowStaging:
        def __init__(self, has_image=True):
            self.status = "pending"
            self.has_image = has_image
            self.deleted = False
            self.completed = False
            self.archived = False
            self.receipt: RegistrationApprovalReceipt | None = None
            self.candidate: ProvisionalRegistrationCandidate | None = ProvisionalRegistrationCandidate(
                "U-1",
                {"line_user_id": "U-1", "passbook_image_id": image_id},
                {"survey_details": {"_liff_meta": {"registration_kind": "non_citizen", "passbook_image_id": image_id}}},
                PreviewFingerprint("a" * 64),
            )

        def _snap(self) -> StagedRegistration:
            receipt = self.receipt
            return StagedRegistration(
                2, 1 if self.status == "pending" else 2, self.status,
                datetime.now(timezone.utc), datetime.now(timezone.utc),
                "non_citizen", self.candidate, "op-1", "admin-1",
                case_no=receipt["case_no"] if receipt else None,
                approved_at_utc=datetime.fromisoformat(receipt["approved_at_utc"]) if receipt else None,
            )

        def claim_approval(self, registration_id, expected_version, actor):
            self.status = "approving"
            return self._snap()

        def get(self, registration_id):
            return self._snap()

        def processing_ids(self, *, limit=100):
            return (2,) if self.status == "approving" else ()

        def get_passbook_image(self, req_id):
            return ({"filename": "p.png", "mime_type": "image/png"}, b"img") if self.has_image else None

        def delete_passbook_image(self, req_id: str) -> None:
            assert req_id == image_id
            assert self.completed and self.candidate is None
            self.deleted = True

        def complete(self, registration_id: int, operation_id: str, receipt: RegistrationApprovalReceipt) -> StagedRegistration:
            assert (registration_id, operation_id) == (2, "op-1")
            assert self.archived
            self.receipt = receipt
            self.candidate = None
            self.completed = True
            self.status = "approved"
            return self._snap()

    class _Formal:
        def __init__(self):
            self.create_calls = 0
            self.receipt: RegistrationApprovalReceipt | None = None

        def approve_staged_registration(self, snapshot: StagedRegistration, correlation_id: CorrelationId) -> RegistrationApprovalReceipt:
            assert (snapshot.registration_id, snapshot.operation_id) == (2, "op-1")
            self.create_calls += 1
            self.receipt = {"client_id": 501, "beclass_record_id": 601, "case_no": "A115001",
                            "approved_at_utc": datetime.now(timezone.utc).isoformat()}
            return self.receipt

        def registration_approval_receipt(self, registration_id: int, operation_id: str) -> RegistrationApprovalReceipt | None:
            assert (registration_id, operation_id) == (2, "op-1")
            return self.receipt

    # Missing passbook image -> must fail closed and NOT mark approved.
    missing_staging = _WorkflowStaging(has_image=False)
    app_missing = RegistrationReviewApplication(missing_staging, _Formal(), passbook_archiver=lambda **_: None)
    with pytest.raises(ProvisionalRegistrationStorageError, match="registration_passbook_image_missing"):
        app_missing.approve_registration(2, 1, "admin-1", CorrelationId("corr-1"))
    assert missing_staging.status == "approving"
    assert not missing_staging.completed

    # Archiver failure (NAS down) -> preserves approving & temp image; retry via recover() succeeds without duplicate client.
    flaky_staging = _WorkflowStaging(has_image=True)
    formal = _Formal()
    should_fail = {"flag": True}

    def _archiver(**_kwargs):
        if should_fail["flag"]:
            raise ProvisionalRegistrationStorageError("controlled_file_storage_unavailable")
        assert not flaky_staging.completed and not flaky_staging.deleted
        assert flaky_staging.candidate is not None
        flaky_staging.archived = True

    app_flaky = RegistrationReviewApplication(flaky_staging, formal, passbook_archiver=_archiver)
    with pytest.raises(ProvisionalRegistrationStorageError, match="controlled_file_storage_unavailable"):
        app_flaky.approve_registration(2, 1, "admin-1", CorrelationId("corr-2"))
    assert flaky_staging.status == "approving"
    assert not flaky_staging.completed
    assert not flaky_staging.deleted
    assert formal.create_calls == 1
    interrupted = app_flaky.registration_application(2)
    assert interrupted.status == "approving" and interrupted.case_no == "A115001"
    assert interrupted.approved_at_utc is not None and interrupted.candidate is None
    assert flaky_staging.candidate is not None

    should_fail["flag"] = False
    recovery = app_flaky.recover()
    assert (recovery.recovered, recovery.failed) == (1, 0)
    assert flaky_staging.status == "approved"
    assert flaky_staging.completed
    assert flaky_staging.deleted
    approved = app_flaky.registration_application(2)
    assert approved.status == "approved" and approved.candidate is None
    assert (approved.case_no, approved.approved_at_utc) == (interrupted.case_no, interrupted.approved_at_utc)
    assert formal.create_calls == 1


def test_redis_acl_covers_every_command_used_by_staging_and_maintenance() -> None:
    import ast
    from pathlib import Path
    import re

    root = Path(__file__).resolve().parents[7]
    entrypoint = (root / "deploy" / "registration" / "redis-entrypoint.sh").read_text(encoding="utf-8")
    users: dict[str, set[str]] = {}
    for line in entrypoint.splitlines():
        if line.startswith("user "):
            parts = line.split()
            users[parts[1]] = {token[1:].lower() for token in parts if token.startswith("+")}

    assert {"registration-admin", "registration-intake"}.issubset(users)
    admin_acl = users["registration-admin"]
    intake_acl = users["registration-intake"]

    redis_name_map = {"delete": "del"}
    used_commands: set[str] = set()
    for rel_path in (
        "infrastructure/redis/registration_staging_repository.py",
        "infrastructure/redis/registration_maintenance.py",
        "infrastructure/redis/staff_profile_change_staging.py",
    ):
        source = (root / rel_path).read_text(encoding="utf-8")
        for match in re.findall(r"""redis\.call\(\s*['"]([a-zA-Z]+)['"]""", source):
            used_commands.add(match.lower())
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "_call" and node.args and isinstance(node.args[0], ast.Constant):
                    if isinstance(node.args[0].value, str):
                        cmd = node.args[0].value.lower()
                        used_commands.add(redis_name_map.get(cmd, cmd))
                elif (
                    isinstance(node.func.value, ast.Attribute)
                    and node.func.value.attr == "_client"
                    and isinstance(node.func.value.value, ast.Name)
                    and node.func.value.value.id == "self"
                ):
                    cmd = node.func.attr.lower()
                    if cmd not in {"register_script", "pipeline"}:
                        used_commands.add(redis_name_map.get(cmd, cmd))

    # pexpireat is only used by intake paths (_STAGE_PASSBOOK / _SUBMIT); admin reads/persists/deletes.
    missing_admin = (used_commands - {"pexpireat"}) - admin_acl
    assert missing_admin == set(), f"registration-admin ACL 缺少必要 Redis 指令: {sorted(missing_admin)}"

    required_intake = {"ping", "get", "set", "incr", "zadd", "pexpireat", "exists", "eval"}
    assert required_intake - intake_acl == set()
    forbidden = {"flushall", "flushdb", "config", "acl", "keys", "scan", "shutdown", "module", "replicaof", "slaveof"}
    assert admin_acl.isdisjoint(forbidden)
    assert intake_acl.isdisjoint(forbidden | {"del", "persist", "zrem", "zrange", "zrevrange", "zrangebyscore", "zremrangebyrank", "expire", "dbsize", "info", "bgrewriteaof"})
