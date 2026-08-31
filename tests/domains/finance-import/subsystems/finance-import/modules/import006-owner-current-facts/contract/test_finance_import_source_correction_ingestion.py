from domains.finance_import.anomaly_remediation import FinanceImportSourceCorrectionIntent
from domains.finance_import.ingestion import FinanceWorkbookIngestionReceipt
from shared_kernel.identities import ActorContext, IdempotencyKey
from subsystems.finance_import import ingestion


class _Cursor:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _Connection:
    def __init__(self):
        self.cursor_value = _Cursor()

    def cursor(self):
        return self.cursor_value


def _intent() -> FinanceImportSourceCorrectionIntent:
    return FinanceImportSourceCorrectionIntent(
        "finance-import-batch:7",
        3,
        "human confirmed source correction",
        "evidence-7",
    )


def _receipt() -> FinanceWorkbookIngestionReceipt:
    return FinanceWorkbookIngestionReceipt(
        "finance-import-batch:8",
        "a" * 64,
        2,
        2,
        0,
    )


def test_corrected_source_lineage_is_appended_before_receipt_in_same_connection(monkeypatch) -> None:
    connection = _Connection()
    captured = {}
    monkeypatch.setattr(ingestion, "_find_replay", lambda *_args: None)
    monkeypatch.setattr(ingestion, "load_finance_identity_maps", lambda *_args: {})
    monkeypatch.setattr(ingestion, "stage_finance_rows", lambda *_args: {"batch_id": 8, "staged_rows": []})
    monkeypatch.setattr(ingestion, "_persist_ingestion", lambda *_args: _receipt())
    monkeypatch.setattr(
        ingestion,
        "_append_source_correction_lineage",
        lambda received_connection, receipt, source_correction, actor: captured.update(
            connection=received_connection,
            receipt=receipt,
            source_correction=source_correction,
            actor=actor,
        ) or "finance-import-source-correction:19",
    )
    saved = []
    monkeypatch.setattr(ingestion, "_save_receipt", lambda cursor, *args: saved.append(cursor))

    result = ingestion._ingest_or_replay(
        connection,
        {"normalized_rows": []},
        "a" * 64,
        "b" * 64,
        IdempotencyKey("ingest-correction"),
        ActorContext("operator-7"),
        ingestion._IngestionProgress(),
        _intent(),
    )

    assert result == _receipt()
    assert captured == {
        "connection": connection,
        "receipt": _receipt(),
        "source_correction": _intent(),
        "actor": ActorContext("operator-7"),
    }
    assert saved == [connection.cursor_value]


def test_legacy_ingestion_call_does_not_attempt_source_correction_lineage(monkeypatch) -> None:
    connection = _Connection()
    appended = []
    monkeypatch.setattr(ingestion, "_find_replay", lambda *_args: None)
    monkeypatch.setattr(ingestion, "load_finance_identity_maps", lambda *_args: {})
    monkeypatch.setattr(ingestion, "stage_finance_rows", lambda *_args: {"batch_id": 8, "staged_rows": []})
    monkeypatch.setattr(ingestion, "_persist_ingestion", lambda *_args: _receipt())
    monkeypatch.setattr(ingestion, "_append_source_correction_lineage", lambda *_args: appended.append(True))
    monkeypatch.setattr(ingestion, "_save_receipt", lambda *_args: None)

    ingestion._ingest_or_replay(
        connection,
        {"normalized_rows": []},
        "a" * 64,
        "b" * 64,
        IdempotencyKey("legacy-ingest"),
        ActorContext("operator-7"),
        ingestion._IngestionProgress(),
        None,
    )

    assert appended == []


def test_source_correction_intent_is_part_of_idempotency_fingerprint() -> None:
    actor = ActorContext("operator-7")
    source_digest = "a" * 64
    assert ingestion._command_fingerprint(source_digest, actor) == ingestion.fingerprint_payload(
        {"source_content_digest": source_digest, "actor_id": actor.actor_id}
    ).value
    assert ingestion._command_fingerprint(source_digest, actor) != ingestion._command_fingerprint(
        source_digest, actor, _intent()
    )
