from datetime import datetime
from contextlib import contextmanager
from pathlib import Path

import pytest

import subsystems.contract_signing.staff_contract_application as staff_signing
from shared_kernel.identities import CorrelationId, IdempotencyKey


class _Connection:
    def __init__(self) -> None:
        self.began = False
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def begin(self) -> None:
        self.began = True

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def test_staff_signed_return_discards_new_archive_when_transaction_fails(tmp_path, monkeypatch):
    connection = _Connection()
    application = staff_signing.StaffContractSigningApplication(
        lambda: connection, archive_root=tmp_path, now=lambda: datetime(2030, 1, 1)
    )
    monkeypatch.setattr(application, "_existing_signed_return_receipt", lambda _command: None)
    monkeypatch.setattr(staff_signing, "_staff_segment", lambda *_: {"plan_id": 3})
    monkeypatch.setattr(staff_signing, "_sent_staff_document", lambda *_: 4)
    monkeypatch.setattr(staff_signing, "_insert_signed_document", lambda *_: 5)
    monkeypatch.setattr(staff_signing, "_insert_signed_event", lambda *_: 6)
    monkeypatch.setattr(
        staff_signing,
        "_create_commitment_if_ready",
        lambda *_: (_ for _ in ()).throw(ValueError("stale_version")),
    )

    with pytest.raises(ValueError, match="stale_version"):
        application.record_signed_return(_command())

    assert connection.rolled_back is True
    assert connection.closed is True
    assert not (tmp_path / "CASE-1/staff/9/wp56-staff-signed-signed.xlsx").exists()


def test_staff_signed_return_rejects_same_key_with_different_signed_content(monkeypatch):
    application = staff_signing.StaffContractSigningApplication(
        lambda: _ReplayConnection(), archive_root=Path("unused"), now=lambda: datetime(2030, 1, 1)
    )
    monkeypatch.setattr(staff_signing, "archive_contract_document", lambda *_args, **_kwargs: pytest.fail("archive must not run on idempotency conflict"))

    with pytest.raises(ValueError, match="contract_signature_idempotency_conflict"):
        application.record_signed_return(_command())


class _ReplayConnection:
    @contextmanager
    def cursor(self):
        yield _ReplayCursor()

    def close(self) -> None:
        pass


class _ReplayCursor:
    def execute(self, _statement, _parameters=()) -> None:
        pass

    def fetchone(self):
        return {
            "document_version_id": 7,
            "id": 8,
            "line_delivery_task_id": None,
            "sha256": "different-content-digest",
        }


def _command() -> staff_signing.RecordStaffSignedReturnCommand:
    return staff_signing.RecordStaffSignedReturnCommand(
        "CASE-1", 9, b"signed-content", "signed.xlsx", "application/octet-stream",
        "wp56-test", IdempotencyKey("wp56-staff-signed"), CorrelationId("wp56-staff-signed"), 4,
    )
