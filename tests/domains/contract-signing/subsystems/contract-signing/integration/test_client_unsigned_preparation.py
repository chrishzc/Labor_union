"""Client preparation reuses current accepted plans without creating commitments."""
from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.contract_signing import client_contract_application as module
from api.dependencies.contract_external_signing import ContractExternalSigningApplication
from shared_kernel.identities import ActorContext


class Cursor:
    def __init__(self, plan, existing): self.plan, self.existing, self.sql = plan, existing, []
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, args): self.sql.append(sql)
    def fetchall(self): return self.plan
    def fetchone(self): return self.existing


class Connection:
    def __init__(self, cursor): self.reader, self.commits, self.rollbacks = cursor, 0, 0
    def cursor(self): return self.reader
    def begin(self): pass
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1
    def close(self): pass


@pytest.mark.parametrize('replayed', [True, False])
def test_preparation_uses_stable_facts_and_never_requires_prior_commitment(monkeypatch, tmp_path, replayed):
    facts = {'case_no': 'CASE-1', 'service_days': 5}
    snapshot_facts = {
        **facts,
        "__pdf_presentation_version__": module.CONTRACT_PDF_PRESENTATION_VERSION,
    }
    digest = module._sha256(module._canonical_json(snapshot_facts).encode())
    cursor = Cursor([{'matching_plan_id': 17}], {'id': 8, 'facts_snapshot_sha256': digest} if replayed else None)
    connection = Connection(cursor)
    archived = []
    monkeypatch.setattr(module, 'load_approved_template', lambda key: SimpleNamespace(template_key=key, template_filename='client.xlsx', template_sha256='a'*64, mapping_sha256='b'*64))
    monkeypatch.setattr(module, 'render_contract_template', lambda **kwargs: b'xlsx')
    monkeypatch.setattr(module, '_insert_generated_document', lambda *args, **kwargs: 9)
    app = module.ClientContractSigningApplication(lambda: connection, archive_root=tmp_path,
        now=lambda: datetime(2026,9,10,tzinfo=timezone.utc), template_facts_loader=lambda *args: facts,
        archive_document=lambda content, **kwargs: archived.append(kwargs['storage_key']) or SimpleNamespace(storage_key=kwargs['storage_key']))
    command = module.PrepareExternalClientContractCommand('CASE-1','admin:1',IdempotencyKey('client:1'),CorrelationId('test:1'))
    assert app.prepare_external_document(command) == ((8,True) if replayed else (9,False))
    assert connection.commits == 1 and connection.rollbacks == 0
    assert not any('commitment' in sql for sql in cursor.sql)
    assert "plan.status='proposed'" in cursor.sql[0]
    assert "response.response_type='customer_decision'" in cursor.sql[0]
    assert "JOIN media_assets asset ON asset.id=d.media_asset_id" in cursor.sql[1]
    assert "asset.mime_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'" in cursor.sql[1]
    assert len(archived) == (0 if replayed else 1)
    if not replayed:
        assert archived == [
            f"CASE-1/client/external-{module._sha256(b'xlsx')[:24]}.xlsx"
        ]
        assert ":" not in archived[0]


def test_client_pdf_preparation_reuses_pdf_for_current_xlsx_source():
    class Documents:
        def prepare_external_document(self, _command):
            return 7, True

    existing = SimpleNamespace(
        document_version_id=8,
        filename="client.pdf",
        mime_type="application/pdf",
        size_bytes=1234,
    )
    facade = SimpleNamespace(
        unsigned_repository=SimpleNamespace(
            load_current_pdf_for_source=lambda case_no, source_id: existing
        ),
        unsigned_persistence=SimpleNamespace(
            prepare_and_persist=lambda _command: pytest.fail("must reuse current PDF")
        ),
    )

    result = ContractExternalSigningApplication.prepare_client_unsigned(
        facade,
        "CASE-1",
        Documents(),
        ActorContext("admin:1"),
        IdempotencyKey("client:reuse"),
        CorrelationId("test:reuse"),
    )

    assert result == {
        "document_version_id": 8,
        "filename": "client.pdf",
        "mime_type": "application/pdf",
        "size_bytes": 1234,
        "replayed": True,
    }
