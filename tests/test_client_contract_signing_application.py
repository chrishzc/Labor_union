from datetime import datetime
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

import subsystems.contract_signing.client_contract_application as client_signing
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


def test_client_signed_return_rolls_back_the_entire_transaction_when_completion_fails(monkeypatch):
    connection = _Connection()
    application = _application(connection)
    monkeypatch.setattr(application, "_existing_signed_return_receipt", lambda _command: None)
    _stub_signed_return_writes(monkeypatch, completion=lambda *_: (_ for _ in ()).throw(ValueError("stale_version")))

    with pytest.raises(ValueError, match="stale_version"):
        application.record_signed_return(_command())

    assert connection.began is True
    assert connection.committed is False
    assert connection.rolled_back is True
    assert connection.closed is True


def test_client_signed_return_discards_new_archive_when_transaction_fails(tmp_path, monkeypatch):
    connection = _Connection()
    application = client_signing.ClientContractSigningApplication(
        lambda: connection, archive_root=tmp_path, now=lambda: datetime(2030, 1, 1)
    )
    monkeypatch.setattr(application, "_existing_signed_return_receipt", lambda _command: None)
    monkeypatch.setattr(client_signing, "_client_contract_facts", lambda *_: {"matching_plan_id": 3})
    monkeypatch.setattr(client_signing, "_sent_client_document", lambda *_: 4)
    monkeypatch.setattr(client_signing, "_insert_signed_document", lambda *_: 5)
    monkeypatch.setattr(client_signing, "_insert_signed_event", lambda *_: 6)
    monkeypatch.setattr(client_signing, "_complete_contract_in_transaction", lambda *_: (_ for _ in ()).throw(ValueError("stale_version")))

    with pytest.raises(ValueError, match="stale_version"):
        application.record_signed_return(_command())

    assert not (tmp_path / "CASE-1/client/wp56-client-signed-signed.xlsx").exists()


def test_client_signed_return_completes_contract_before_the_only_commit(monkeypatch):
    connection = _Connection()
    application = _application(connection)
    monkeypatch.setattr(application, "_existing_signed_return_receipt", lambda _command: None)
    completion_identities: list[str] = []
    _stub_signed_return_writes(
        monkeypatch,
        completion=lambda _connection, _command, identity: completion_identities.append(identity),
    )
    monkeypatch.setattr(client_signing, "_append_command_outcome", lambda *_: None)

    receipt = application.record_signed_return(_command())

    assert receipt.contract_completed is True
    assert receipt.contract_identity == "client-contract:signed-digest"
    assert completion_identities == ["client-contract:signed-digest"]
    assert connection.committed is True
    assert connection.rolled_back is False


def test_client_signed_return_replays_before_archiving_a_second_document(monkeypatch):
    connection = _Connection()
    application = _application(connection)
    existing = client_signing.ClientContractWorkflowReceipt(7, 8, None, "identity", True)
    monkeypatch.setattr(application, "_existing_signed_return_receipt", lambda _command: existing)
    monkeypatch.setattr(client_signing, "archive_contract_document", lambda *_args, **_kwargs: pytest.fail("archive must not run on replay"))

    assert application.record_signed_return(_command()) is existing
    assert connection.began is False
    assert connection.closed is False


def test_client_signed_return_rejects_same_key_with_different_signed_content(monkeypatch):
    application = client_signing.ClientContractSigningApplication(
        lambda: _ReplayConnection(), archive_root=Path("unused"), now=lambda: datetime(2030, 1, 1)
    )
    monkeypatch.setattr(client_signing, "archive_contract_document", lambda *_args, **_kwargs: pytest.fail("archive must not run on idempotency conflict"))

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
            "contract_identity": "identity",
            "sha256": "different-content-digest",
            "contract_completed": True,
        }


def _application(connection: _Connection) -> client_signing.ClientContractSigningApplication:
    return client_signing.ClientContractSigningApplication(
        lambda: connection,
        archive_root=Path("unused"),
        now=lambda: datetime(2030, 1, 1),
    )


def _command() -> client_signing.RecordClientSignedReturnCommand:
    return client_signing.RecordClientSignedReturnCommand(
        "CASE-1", b"signed-content", "signed.xlsx", "application/octet-stream",
        "wp56-test", IdempotencyKey("wp56-client-signed"), CorrelationId("wp56-client-signed"), 4,
    )


def _stub_signed_return_writes(monkeypatch, completion) -> None:
    monkeypatch.setattr(client_signing, "archive_contract_document", lambda *_args, **_kwargs: SimpleNamespace(storage_key="case/signed.xlsx", sha256="signed-digest", file_size=42))
    monkeypatch.setattr(client_signing, "_client_contract_facts", lambda *_: {"matching_plan_id": 3})
    monkeypatch.setattr(client_signing, "_sent_client_document", lambda *_: 4)
    monkeypatch.setattr(client_signing, "_insert_signed_document", lambda *_: 5)
    monkeypatch.setattr(client_signing, "_insert_signed_event", lambda *_: 6)
    monkeypatch.setattr(client_signing, "_complete_contract_in_transaction", completion)
