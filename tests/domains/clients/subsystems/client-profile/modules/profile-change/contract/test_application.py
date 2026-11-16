"""Owner-local contract tests for administrative Client profile maintenance."""

from contextlib import AbstractContextManager

import pytest

from domains.clients.profile import ClientProfileValidationError, validate_changes


def test_admin_due_date_and_reject_reason_validation():
    assert validate_changes({'due_month': '2026-10-15', 'reject_reason': '  服務地區不符  '}) == {
        'due_month': '2026-10-15', 'reject_reason': '服務地區不符',
    }
    for invalid in ('2026-02-30', '2026/10/15', 'not-a-date'):
        with pytest.raises(ClientProfileValidationError, match='profile_due_month_invalid'):
            validate_changes({'due_month': invalid})


@pytest.mark.parametrize('service_type', ['連續服務', '週休1日', '每週依需求排班，含週末服務'])
def test_admin_service_type_repair_uses_existing_profile_writer(service_type):
    repository = _Repository()
    repository.profile.update(phone=None, service_type=None)
    application = _application(repository)
    changes = {'phone': '0912345678', 'service_type': service_type}
    preview = application.preview_admin('CASE-001', changes, ExpectedVersion(0))
    assert preview.requested == {'phone': '0912345678', 'service_type': service_type}
    receipt = application.apply_admin('CASE-001', changes, ExpectedVersion(0), ActorContext('admin:9'),
                                      '修正進件欄位', preview.preview_fingerprint, IdempotencyKey('hcm-profile-repair'),
                                      CorrelationId('hcm-profile-repair'))
    assert receipt.readback.values['phone'] == '0912345678'
    assert receipt.readback.values['service_type'] == service_type
    assert application.query_admin('CASE-001').values['service_type'] == service_type


def test_service_type_free_text_respects_existing_storage_capacity():
    assert validate_changes({'service_type': '  週休1日  '}) == {'service_type': '週休1日'}
    assert validate_changes({'service_type': '字' * 100}) == {'service_type': '字' * 100}
    with pytest.raises(ClientProfileValidationError, match='profile_value_too_long:service_type'):
        validate_changes({'service_type': '字' * 101})
    with pytest.raises(ClientProfileValidationError, match='profile_value_cannot_be_empty:service_type'):
        validate_changes({'service_type': '   '})
from shared_kernel.identities import ActorContext, CorrelationId, ExpectedVersion, IdempotencyKey
from subsystems.client_profile.application import ClientProfileApplication
from subsystems.client_profile.contracts import (
    ClientProfileRequestConflictError,
    ClientProfileStaleError,
)


@pytest.mark.parametrize("phone,expected", [
    ("0912-345-678", "0912345678"),
    ("(02) 2345-6789", "0223456789"),
    ("03-2345678", "032345678"),
    ("+886-2-2345-6789", "0223456789"),
])
def test_mobile_and_landline_use_existing_profile_preview_apply_readback(phone, expected):
    repository = _Repository()
    application = _application(repository)
    changes = {"phone": phone}
    preview = application.preview_admin("CASE-001", changes, ExpectedVersion(0))
    assert preview.requested == {"phone": expected}
    receipt = application.apply_admin(
        "CASE-001", changes, ExpectedVersion(0), ActorContext("admin"), "更新聯絡電話",
        preview.preview_fingerprint, IdempotencyKey("phone-format"), CorrelationId("phone-format"),
    )
    assert receipt.readback.values["phone"] == expected
    assert application.query_admin("CASE-001").values["phone"] == expected


@pytest.mark.parametrize("phone", ["123", "02234567", "09123456789", "0912abc345678", "02-23456789#123"])
def test_phone_validation_rejects_invalid_values_without_discarding_letters_or_extensions(phone):
    with pytest.raises(ClientProfileValidationError):
        validate_changes({"phone": phone})


def test_admin_email_repair_uses_profile_version_receipt():
    repository = _Repository()
    repository.profile["email"] = None
    application = _application(repository)
    changes = {"email": "  corrected@example.com  "}
    preview = application.preview_admin("CASE-001", changes, ExpectedVersion(0))
    assert preview.before == {"email": ""}
    assert preview.requested == {"email": "corrected@example.com"}
    receipt = application.apply_admin(
        "CASE-001", changes, ExpectedVersion(0), ActorContext("admin:9"),
        "補登 HCM email", preview.preview_fingerprint, IdempotencyKey("hcm-email-repair"),
        CorrelationId("hcm-email-repair"),
    )
    assert receipt.readback.values["email"] == "corrected@example.com"
    assert receipt.resulting_version == 1
    for invalid in ("wrong", "a b@example.com", "user@domain"):
        with pytest.raises(ClientProfileValidationError, match="profile_email_invalid"):
            application.preview_admin("CASE-001", {"email": invalid}, ExpectedVersion(1))


class _Uow(AbstractContextManager):
    def __init__(self, repository):
        self.client_profiles = repository
        self.commit_count = 0
        self.rollback_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        if exception_type is not None:
            self.rollback_count += 1
        return False

    def commit(self):
        self.commit_count += 1


class _Repository:
    def load_email_fill_target(self, case_no, *, for_update=False):
        row = self.load_profile_by_case_no(case_no, for_update=for_update)
        return None if row is None else {field: row.get(field) for field in ("client_id", "client_profile_version", "email")}
    def __init__(self):
        self.profile = {
            "client_id": 7, "client_profile_version": 0, "name": "王小明", "gender": "女",
            "phone": "0912345678", "city": "新竹市", "address": "新竹市東區一號",
            "residence_type": "電梯大樓", "delivery_type": "自然產", "baby_info": "初生兒", "notes": "無",
        }
        self.admin_receipts = {}
        self.admin_claims = {}

    def load_profile(self, client_id, *, for_update=False):
        return dict(self.profile) if client_id == 7 else None

    def load_profile_by_case_no(self, case_no, *, for_update=False):
        return dict(self.profile) if case_no == "CASE-001" else None

    def claim_admin_command(self, **kwargs):
        key = kwargs["idempotency_key"]
        fingerprint = kwargs["command_fingerprint"]
        if key in self.admin_claims and self.admin_claims[key] != fingerprint:
            raise ValueError("idempotency_mismatch")
        self.admin_claims[key] = fingerprint

    def find_admin_receipt(self, key, *, for_update=False):
        return self.admin_receipts.get(key)

    def apply_admin_change(self, **kwargs):
        assert kwargs["expected_version"] == self.profile["client_profile_version"]
        self.profile.update(kwargs["requested"])
        self.profile["client_profile_version"] += 1
        return self.profile["client_profile_version"]

    def save_admin_receipt(self, **kwargs):
        self.admin_receipts[kwargs["idempotency_key"]] = {
            "actor_id": kwargs["actor_id"], "reason": kwargs["reason"],
            "command_fingerprint": kwargs["command_fingerprint"],
            "preview_fingerprint": kwargs["preview_fingerprint"],
            "result": dict(kwargs["result"]),
        }


@pytest.mark.parametrize("existing", [None, "", "  "])
def test_hcm_fill_changes_only_empty_email_and_version_without_owning_a_commit(existing):
    repository = _Repository()
    repository.profile["email"] = existing
    before = dict(repository.profile)
    application = ClientProfileApplication(lambda: (_ for _ in ()).throw(AssertionError("no nested UoW")))
    assert application.fill_hcm_email_in_current_uow(repository, "CASE-001", "  hcm@example.com  ",
        source_identity="synthetic-workbook:row:1", actor=ActorContext("import-client-hcm"),
        correlation_id=CorrelationId("synthetic-fill")) is True
    assert repository.profile == {**before, "email": "hcm@example.com", "client_profile_version": 1}
    assert len(repository.admin_receipts) == 1
    assert next(iter(repository.admin_receipts.values()))["result"]["changed_fields"] == ["email"]
    assert application.fill_hcm_email_in_current_uow(repository, "CASE-001", "another@example.com",
        source_identity="another-workbook:row:1", actor=ActorContext("import-client-hcm"),
        correlation_id=CorrelationId("synthetic-fill-again")) is False
    assert repository.profile == {**before, "email": "hcm@example.com", "client_profile_version": 1}


@pytest.mark.parametrize("existing,source", [("manual@example.com", "new@example.com"),
    ("manual@example.com", "invalid"), (None, None), (None, "  ")])
def test_hcm_fill_skips_nonempty_target_or_empty_source_without_receipts(existing, source):
    repository = _Repository()
    repository.profile["email"] = existing
    before = dict(repository.profile)
    assert ClientProfileApplication.fill_hcm_email_in_current_uow(repository, "CASE-001", source,
        source_identity="synthetic-workbook:row:1", actor=ActorContext("import-client-hcm"),
        correlation_id=CorrelationId("synthetic-no-fill")) is False
    assert repository.profile == before
    assert not repository.admin_receipts and not repository.admin_claims


def test_hcm_fill_rejects_invalid_source_and_maps_version_conflict(monkeypatch):
    repository = _Repository()
    repository.profile["email"] = None
    arguments = dict(source_identity="synthetic-workbook:row:1", actor=ActorContext("import-client-hcm"),
                     correlation_id=CorrelationId("synthetic-conflict"))
    with pytest.raises(ClientProfileValidationError, match="profile_email_invalid"):
        ClientProfileApplication.fill_hcm_email_in_current_uow(repository, "CASE-001", "invalid", **arguments)
    monkeypatch.setattr(repository, "apply_admin_change", lambda **_: (_ for _ in ()).throw(RuntimeError("client_profile_version_stale")))
    with pytest.raises(ClientProfileStaleError, match="client_profile_version_stale"):
        ClientProfileApplication.fill_hcm_email_in_current_uow(repository, "CASE-001", "hcm@example.com", **arguments)
    assert repository.profile["email"] is None and not repository.admin_receipts


def _application(repository):
    return ClientProfileApplication(
        lambda: _Uow(repository),
    )


@pytest.mark.parametrize("field,value", [
    ("name", "合成測試姓名"), ("phone", "0999000000"),
    ("address", "合成測試地址"), ("notes", "合成測試註記"),
])
def test_admin_can_save_one_profile_field_when_every_other_profile_field_is_missing(field, value):
    repository = _Repository()
    for profile_field in ("name", "gender", "phone", "city", "address", "residence_type", "delivery_type", "baby_info", "notes"):
        repository.profile[profile_field] = None
    application = _application(repository)
    preview = application.preview_admin("CASE-001", {field: value}, ExpectedVersion(0))
    application.apply_admin("CASE-001", {field: value}, ExpectedVersion(0), ActorContext("admin"),
        "補正單一主檔欄位", preview.preview_fingerprint, IdempotencyKey(f"profile-partial-{field}"), CorrelationId("profile-partial"))
    assert application.query_admin("CASE-001").values[field] == value
    assert all(repository.profile[other] is None for other in
        ("name", "gender", "phone", "city", "address", "residence_type", "delivery_type", "baby_info", "notes") if other != field)


@pytest.mark.parametrize("field,value", [
    ("name", "合成測試姓名"), ("phone", "0999000000"),
    ("address", "合成測試地址"), ("notes", "合成測試註記"),
])
def test_admin_can_save_one_profile_field_when_every_other_profile_field_is_missing(field, value):
    repository = _Repository()
    for profile_field in ("name", "gender", "phone", "city", "address", "residence_type", "delivery_type", "baby_info", "notes"):
        repository.profile[profile_field] = None
    application = _application(repository)
    preview = application.preview_admin("CASE-001", {field: value}, ExpectedVersion(0))
    application.apply_admin("CASE-001", {field: value}, ExpectedVersion(0), ActorContext("admin"),
        "補正單一主檔欄位", preview.preview_fingerprint, IdempotencyKey(f"profile-partial-{field}"), CorrelationId("profile-partial"))
    assert application.query_admin("CASE-001").values[field] == value
    assert all(repository.profile[other] is None for other in
        ("name", "gender", "phone", "city", "address", "residence_type", "delivery_type", "baby_info", "notes") if other != field)


def test_profile_validation_is_closed_and_accepts_free_text_city():
    assert validate_changes({"name": " 王小美 ", "city": " 東區 "}) == {"city": "東區", "name": "王小美"}
    assert validate_changes({"city": "區" * 20}) == {"city": "區" * 20}
    with pytest.raises(ClientProfileValidationError):
        validate_changes({"line_user_id": "other"})
    with pytest.raises(ClientProfileValidationError):
        validate_changes({"phone": "123"})
    for value, code in (("   ", "profile_value_cannot_be_empty"),
                        (None, "profile_value_must_be_text"),
                        ("區" * 21, "profile_value_too_long")):
        with pytest.raises(ClientProfileValidationError) as raised:
            validate_changes({"city": value})
        assert raised.value.code == code


def test_admin_notes_can_be_edited_and_cleared():
    repository = _Repository()
    repository.profile["admin_notes"] = "原行政註記"
    application = _application(repository)
    for version, value, expected in ((0, "更新行政註記", "更新行政註記"), (1, None, "")):
        changes = {"admin_notes": value}
        preview = application.preview_admin("CASE-001", changes, ExpectedVersion(version))
        application.apply_admin(
            "CASE-001", changes, ExpectedVersion(version), ActorContext("admin"),
            "", preview.preview_fingerprint, IdempotencyKey(f"admin-notes-{version}"),
            CorrelationId(f"admin-notes-{version}"),
        )
        assert application.query_admin("CASE-001").values["admin_notes"] == expected


@pytest.mark.parametrize("identity", ["補助市民", "原住民"])
def test_identity_reclassification_rechecks_service_start_and_reprices(identity, monkeypatch):
    repository = _Repository()
    repository.profile.update(identity_status=identity, order_status="訂單成立", actual_start_date=None)
    calls = []
    monkeypatch.setattr(repository, "prepare_identity_change",
        lambda case, client_id, *, lock: calls.append(lock) or "pricing", raising=False)
    monkeypatch.setattr(repository, "apply_identity_pricing",
        lambda pricing, **kwargs: calls.append(pricing), raising=False)
    application = _application(repository)
    changes = {"identity_status": "一般市民"}
    preview = application.preview_admin("CASE-001", changes, ExpectedVersion(0))
    repository.profile["actual_start_date"] = "2026-11-11"
    with pytest.raises(ClientProfileRequestConflictError, match="profile_identity_change_unavailable"):
        application.apply_admin(
            "CASE-001", changes, ExpectedVersion(0), ActorContext("admin"), "",
            preview.preview_fingerprint, IdempotencyKey("started"), CorrelationId("started"),
        )
    assert repository.profile["identity_status"] == identity
    assert calls == [False]
    repository.profile["actual_start_date"] = None
    application.apply_admin(
        "CASE-001", changes, ExpectedVersion(0), ActorContext("admin"), "",
        preview.preview_fingerprint, IdempotencyKey("unstarted"), CorrelationId("unstarted"),
    )
    assert repository.profile["identity_status"] == "一般市民"
    assert calls == [False, True, "pricing"]


@pytest.mark.parametrize("city", ["東區", "新竹市香山區", "123"])
def test_admin_can_preview_apply_and_read_back_free_text_city(city):
    repository = _Repository()
    application = _application(repository)
    preview = application.preview_admin("CASE-001", {"city": city}, ExpectedVersion(0))
    assert preview.requested == {"city": city}
    assert repository.profile["city"] == "新竹市"
    receipt = application.apply_admin(
        "CASE-001", {"city": city}, ExpectedVersion(0), ActorContext("admin"),
        "補正行政區", preview.preview_fingerprint,
        IdempotencyKey("profile-city"), CorrelationId("profile-city"),
    )
    assert receipt.readback.values["city"] == city
    assert application.query_admin("CASE-001").values["city"] == city


def test_admin_can_save_due_date_and_reason():
    repository = _Repository()
    repository.profile.update({'due_month': None, 'reject_reason': None})
    application = _application(repository)
    changes = {'due_month': '2026-10-15', 'reject_reason': '服務地區不符'}
    preview = application.preview_admin('CASE-001', changes, ExpectedVersion(0))
    assert preview.before == {'due_month': '', 'reject_reason': ''}
    assert repository.profile['due_month'] is None
    actor = ActorContext('admin:9', ('data_browser.write',))
    receipt = application.apply_admin('CASE-001', changes, ExpectedVersion(0), actor, '補齊匯入資料',
                                      preview.preview_fingerprint, IdempotencyKey('admin-missing-fields'),
                                      CorrelationId('admin-missing-fields-corr'))
    assert all(receipt.readback.values[field] == value for field, value in changes.items())
    assert all(application.query_admin('CASE-001').values[field] == value for field, value in changes.items())


@pytest.mark.parametrize("note", ["", "   ", "人工核對"])
def test_admin_profile_change_uses_case_identity_and_exact_idempotent_replay(note):
    repository = _Repository()
    application = _application(repository)
    preview = application.preview_admin(
        "CASE-001", {"name": "王小美"}, ExpectedVersion(0)
    )
    actor = ActorContext("admin:9", ("data_browser.write",))
    receipt = application.apply_admin(
        "CASE-001", {"name": "王小美"}, ExpectedVersion(0), actor, note,
        preview.preview_fingerprint, IdempotencyKey("admin-profile-1"), CorrelationId("admin-profile-corr-1"),
    )
    assert receipt.resulting_version == 1
    assert receipt.readback.values["name"] == "王小美"
    replay = application.apply_admin(
        "CASE-001", {"name": "王小美"}, ExpectedVersion(0), actor, note,
        preview.preview_fingerprint, IdempotencyKey("admin-profile-1"), CorrelationId("admin-profile-corr-1"),
    )
    assert replay.replayed is True
    assert repository.admin_receipts["admin-profile-1"]["reason"] == note.strip()
    assert repository.admin_receipts["admin-profile-1"]["actor_id"] == actor.actor_id
    assert repository.profile["client_profile_version"] == 1
    with pytest.raises((ClientProfileRequestConflictError, ValueError)):
        application.apply_admin(
            "CASE-001", {"name": "另一人"}, ExpectedVersion(0), actor, note,
            preview.preview_fingerprint, IdempotencyKey("admin-profile-1"), CorrelationId("admin-profile-corr-2"),
        )


def test_admin_notes_are_optional_without_relaxing_profile_field_limits():
    from pydantic import ValidationError
    from api.schemas.client_registry import ClientProfileAdminApplyRequest
    body = dict(changes={'name': '王小美'}, expected_version=0, preview_fingerprint='a' * 64)
    assert ClientProfileAdminApplyRequest(**body).reason == ''
    assert ClientProfileAdminApplyRequest(**body, reason='').reason == ''
    with pytest.raises(ValidationError):
        ClientProfileAdminApplyRequest(**body, reason='字' * 501)
