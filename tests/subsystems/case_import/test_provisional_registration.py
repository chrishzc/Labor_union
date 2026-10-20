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
                    assert connection.record["application_version"] == args[4]
                    connection.record.update(client_id=args[0], beclass_record_id=args[1],
                        approved_by_actor=args[2], application_version=args[4] + 1)
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
