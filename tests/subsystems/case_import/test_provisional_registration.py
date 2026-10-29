"""Focused coverage for the shared provisional registration ID owner."""

from __future__ import annotations

import pytest

from domains.case_import.provisional_registration import (
    ProvisionalRegistrationDomainError,
    ProvisionalRegistrationIntent,
    build_provisional_registration_candidate,
)


def _intent(*, id_number: str | None) -> ProvisionalRegistrationIntent:
    return ProvisionalRegistrationIntent(
        line_user_id="U-id-format-smoke",
        name="測試申請人",
        phone="0912345678",
        expected_date="2026-10-01",
        service_days=1,
        address="測試地址",
        gender=None,
        email=None,
        birth_date=None,
        tel=None,
        ext=None,
        city=None,
        zip_code=None,
        id_number=id_number,
        liff_config_revision=None,
        survey_details={},
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" o123456782 ", "O123456782"),
        ("ｏ１２３４５６７８２", "O123456782"),
        (None, None),
        ("   ", None),
    ],
)
def test_shared_candidate_normalizes_nonempty_ids_and_keeps_optional_empty_values(
    value: str | None,
    expected: str | None,
) -> None:
    candidate = build_provisional_registration_candidate(_intent(id_number=value))

    assert candidate.beclass_payload["survey_details"]["身分證字號"] == expected


def test_shared_candidate_does_not_add_checksum_or_second_digit_limits() -> None:
    candidate = build_provisional_registration_candidate(_intent(id_number="O000000000"))

    assert candidate.beclass_payload["survey_details"]["身分證字號"] == "O000000000"


def _non_citizen_intent(**changes):
    from dataclasses import replace
    values = dict(
        registration_kind="non_citizen", gender="女", email="synthetic@example.test",
        city="新竹縣", birth_date="1990-01-01", service_start_date="2026-11-01",
        service_time="8小時 08:00-17:00", residence_type="公寓", delivery_type="自然產",
        notes="無", line_id="無", service_type="連續服務", baby_info="合成測試資料",
        survey_details={"服務時間內是否有其他寶寶": "無", "是否需要下廚": "需要下廚",
                        "補助款退款:銀行代號+分行代號": "0000000", "銀行帳號": "000000000000"},
    )
    values.update(changes)
    return replace(_intent(id_number=None), **values)


def test_non_citizen_candidate_keeps_merged_fields_and_refund_account_without_issuing_case():
    candidate = build_provisional_registration_candidate(_non_citizen_intent())
    assert candidate.registration_kind == "non_citizen"
    assert candidate.client_payload["identity_status"] == "非市民"
    assert candidate.client_payload["service_time"] == "8小時 08:00-17:00"
    assert candidate.beclass_payload["survey_details"]["銀行帳號"] == "000000000000"
    assert "case_no" not in candidate.client_payload
    assert build_provisional_registration_candidate(_intent(id_number=None)).registration_kind == "subsidy"


@pytest.mark.parametrize("field", ["gender", "email", "city", "service_start_date", "service_time",
                                   "residence_type", "delivery_type", "service_type", "baby_info", "birth_date", "notes", "line_id"])
def test_non_citizen_hcm_and_beclass_required_fields_are_enforced_by_owner(field):
    with pytest.raises(ProvisionalRegistrationDomainError):
        build_provisional_registration_candidate(_non_citizen_intent(**{field: None}))


@pytest.mark.parametrize("field", ["服務時間內是否有其他寶寶", "是否需要下廚", "補助款退款:銀行代號+分行代號", "銀行帳號"])
def test_non_citizen_keeps_original_survey_required_fields(field):
    intent = _non_citizen_intent()
    survey = dict(intent.survey_details)
    survey.pop(field)
    from dataclasses import replace
    with pytest.raises(ProvisionalRegistrationDomainError):
        build_provisional_registration_candidate(replace(intent, survey_details=survey))


def test_non_citizen_accepts_the_existing_liff_cooking_question_name():
    from dataclasses import replace
    intent = _non_citizen_intent()
    survey = dict(intent.survey_details)
    survey['是否需要下廚：'] = survey.pop('是否需要下廚')
    assert build_provisional_registration_candidate(replace(intent, survey_details=survey)).registration_kind == 'non_citizen'


def test_registration_validation_is_not_misreported_as_expired_identity_flow():
    from fastapi import HTTPException
    from api.routes.line_identity import _translate_identity_errors
    def invalid():
        build_provisional_registration_candidate(_non_citizen_intent(service_time=None))
    with pytest.raises(HTTPException) as caught:
        _translate_identity_errors(invalid)
    assert caught.value.status_code == 422
    assert caught.value.detail['code'] == 'provisional_registration_invalid_root_facts'


def test_non_citizen_merged_snapshot_round_trips_before_approval():
    from infrastructure.mysql.provisional_registration_repository import _application_snapshot, _candidate_snapshot
    candidate = build_provisional_registration_candidate(_non_citizen_intent())
    snapshot = _application_snapshot(dict(
        id=42, application_version=1, application_payload=_candidate_snapshot(candidate),
        payload_fingerprint=candidate.payload_fingerprint.value, line_user_id=candidate.line_user_id,
        client_id=None, beclass_record_id=None, approved_by_actor=None,
    ))
    assert snapshot.candidate == candidate
    assert snapshot.case_no is None and snapshot.approved_at_utc is None


def test_non_citizen_number_uses_taipei_approval_year_and_annual_sequence():
    from datetime import datetime, timezone
    from domains.case_import.non_citizen_registration import non_citizen_case_number
    before = datetime(2026, 12, 31, 15, 59, tzinfo=timezone.utc)
    after = datetime(2026, 12, 31, 16, 0, tzinfo=timezone.utc)
    assert non_citizen_case_number(before, 1) == "A115001"
    assert non_citizen_case_number(before, 2) == "A115002"
    assert non_citizen_case_number(after, 1) == "A116001"


def test_non_citizen_intake_reuses_typed_case_import_with_approval_time():
    from datetime import datetime, timezone
    from subsystems.case_import.non_citizen_registration_application import non_citizen_case_intent
    candidate = build_provisional_registration_candidate(_non_citizen_intent())
    intent = non_citizen_case_intent(candidate, "A115001", datetime(2026, 10, 29, tzinfo=timezone.utc), 42, set())
    values = {item.name: item.value for item in intent.client_attributes}
    assert values["case_no"] == "A115001" and values["identity_status"] == "非市民"
    assert values["created_at"] == datetime(2026, 10, 29, 8)
    assert intent.order.requires_cooking is True and intent.provisional_registration_id == 42
    assert intent.bootstrap.client_payment_terms.deposit_service_days == 5


@pytest.mark.parametrize("value", ["O12345678", "O12345678X", "1234567890"])
def test_shared_candidate_rejects_nonempty_ids_outside_database_shape(value: str) -> None:
    with pytest.raises(ProvisionalRegistrationDomainError, match="id_number is invalid"):
        build_provisional_registration_candidate(_intent(id_number=value))


class _ApplicationConnection:
    """Transactional state oracle for registration; not a MySQL engine substitute."""
    def __init__(self):
        from copy import deepcopy
        self.copy = deepcopy
        self.record = None
        self.clients = []
        self.beclass = []
        self.statements = []
        self.fail_after_client = False
        self.commits = self.rollbacks = 0

    def cursor(self):
        connection = self
        class Cursor:
            rowcount = 0
            lastrowid = 0
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def execute(self, sql, args=()):
                connection.statements.append((sql, args))
                self.rowcount = 0
                if sql.startswith("INSERT IGNORE INTO provisional_client_registrations"):
                    if connection.record is None:
                        self.rowcount = 1
                        connection.record = dict(id=5, line_user_id=args[0], payload_fingerprint=args[2],
                            application_payload=args[3], application_version=1, client_id=None,
                            beclass_record_id=None, approved_by_actor=None)
                elif sql.startswith("INSERT INTO clients"):
                    connection.clients.append(args)
                    self.lastrowid = 17
                elif sql.startswith("INSERT INTO beclass_records"):
                    if connection.fail_after_client:
                        raise RuntimeError("simulated downstream failure")
                    connection.beclass.append(args)
                    self.lastrowid = 23
                elif sql.startswith("UPDATE provisional_client_registrations SET client_id"):
                    assert connection.record["application_version"] == args[-1]
                    connection.record.update(client_id=args[0], beclass_record_id=args[1],
                        approved_by_actor=args[2], application_version=args[-1] + 1)
                    self.rowcount = 1
                elif not sql.startswith("SELECT "):
                    raise AssertionError(f"unexpected registration write: {sql}")
            def fetchone(self): return connection.copy(connection.record)
        return Cursor()

    def begin(self):
        self.before = self.copy((self.record, self.clients, self.beclass))
    def commit(self): self.commits += 1
    def rollback(self):
        self.record, self.clients, self.beclass = self.copy(self.before)
        self.rollbacks += 1


def _pending_repository(connection):
    from infrastructure.mysql.provisional_registration_repository import MySqlProvisionalRegistrationRepository
    from unittest.mock import Mock
    repository = MySqlProvisionalRegistrationRepository(connection)
    repository._delivery_tasks = Mock()
    return repository


def test_demand_submission_and_replay_never_create_client_or_business_rows():
    connection = _ApplicationConnection()
    repository = _pending_repository(connection)
    candidate = build_provisional_registration_candidate(_intent(id_number=None))
    first = repository.apply(candidate)
    replay = repository.apply(candidate)
    assert first.client_id is None and first.beclass_record_id is None
    assert not first.replayed and replay.replayed
    assert connection.clients == connection.beclass == []
    assert connection.record["approved_by_actor"] is None
    assert not any(sql.startswith(("INSERT INTO clients", "INSERT INTO orders", "UPDATE clients"))
                   for sql, _ in connection.statements)


def test_approval_creates_roots_once_and_legacy_receipt_replay_is_preserved():
    connection = _ApplicationConnection()
    repository = _pending_repository(connection)
    candidate = build_provisional_registration_candidate(_intent(id_number=None))
    repository.apply(candidate)
    first = repository.approve(5, 1, "admin:7")
    replay = repository.approve(5, 1, "admin:8")
    assert first.client_id == replay.client_id == 17
    assert first.beclass_record_id == replay.beclass_record_id == 23
    assert replay.replayed and not replay.worker_wakeup_required
    assert len(connection.clients) == len(connection.beclass) == 1
    assert connection.record["approved_by_actor"] == "admin:7"
    assert connection.record["application_version"] == 2
    # Pre-upgrade completed receipts have no saved application; external replay
    # must return their original root IDs without replacing any data.
    connection.record["application_payload"] = None
    legacy = repository.apply(candidate)
    assert legacy.client_id == 17 and legacy.replayed
    assert len(connection.clients) == 1


def test_stale_approval_and_tampered_snapshot_cannot_create_roots():
    from infrastructure.mysql.provisional_registration_repository import ProvisionalRegistrationStorageError
    from subsystems.case_import.provisional_registration_types import ProvisionalRegistrationConflictError
    connection = _ApplicationConnection()
    repository = _pending_repository(connection)
    repository.apply(build_provisional_registration_candidate(_intent(id_number=None)))
    with pytest.raises(ProvisionalRegistrationConflictError, match="stale"):
        repository.approve(5, 2, "admin:7")
    connection.record["application_payload"] = '{"client":{},"beclass":{}}'
    with pytest.raises(ProvisionalRegistrationStorageError, match="payload_mismatch"):
        repository.approve(5, 1, "admin:7")
    assert connection.clients == connection.beclass == []


def test_failure_after_client_insert_rolls_back_entire_approval():
    from infrastructure.mysql.provisional_registration_repository import ProvisionalRegistrationMySqlUnitOfWork
    connection = _ApplicationConnection()
    repository = _pending_repository(connection)
    repository.apply(build_provisional_registration_candidate(_intent(id_number=None)))
    connection.fail_after_client = True
    with pytest.raises(RuntimeError, match="downstream"):
        with ProvisionalRegistrationMySqlUnitOfWork(connection) as uow:
            repository.approve(5, 1, "admin:7")
            uow.commit()
    assert connection.clients == connection.beclass == []
    assert connection.record["client_id"] is None and connection.record["application_version"] == 1
    assert connection.rollbacks == 1 and connection.commits == 0
