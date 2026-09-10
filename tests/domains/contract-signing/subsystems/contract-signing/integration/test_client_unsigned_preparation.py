"""Client preparation reuses current accepted plans without creating commitments."""
from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from shared_kernel.identities import CorrelationId, IdempotencyKey
from subsystems.contract_signing import client_contract_application as module


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
    digest = module._sha256(module._canonical_json(facts).encode())
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
    assert "status='accepted' AND is_active=1 FOR UPDATE" in cursor.sql[0]
    assert len(archived) == (0 if replayed else 1)
