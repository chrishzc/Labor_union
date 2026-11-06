"""Real in-memory workbook reconstruction and source-owner ports; no SQL or Office."""

from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
from io import BytesIO
import json
from types import SimpleNamespace
from xml.dom.minidom import parseString
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook
import pytest

from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.contract_signing.render_source_snapshot import (
    RenderSourceRequest, RenderSourceWorkflow, canonical_json, canonical_xlsx,
    create_render_snapshot, rebuild_render_snapshot, _decode,
)
from subsystems.contract_signing.unsigned_contract_pdf import UnsignedContractPdfError


@pytest.fixture
def template(tmp_path):
    path = tmp_path / "contract.xlsx"
    workbook = Workbook()
    workbook.active["A1"] = "original"
    workbook.save(path)
    mapping = tmp_path / "contract.json"
    mapping.write_text(json.dumps({"id": "contract_client_copy", "param_mappings": {
        "A1": {"db_key": "name", "status": "approved", "requiredness": "required"},
    }}), encoding="utf-8")
    return SimpleNamespace(template_key="contract_client_copy", template_filename=path.name,
        template_path=path, mapping_path=mapping,
        template_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        mapping_sha256=hashlib.sha256(mapping.read_bytes()).hexdigest())


def request(scope="client_contract", key="source:first"):
    return RenderSourceRequest("CASE-1", scope, None if scope == "client_contract" else 71,
        ActorContext("admin:1"), IdempotencyKey(key), CorrelationId("source:test"))


def source(template, req=None, facts_sha="a" * 64):
    req = req or request()
    return {**req.identity, "matching_plan_id": 17, "template_key": template.template_key,
        "template_sha256": template.template_sha256, "mapping_sha256": template.mapping_sha256,
        "facts_snapshot_sha256": facts_sha}


def stored_row(identity, snapshot):
    return {**identity, "render_source_kind": "render_snapshot", "media_asset_id": None,
        "render_source_snapshot": snapshot.payload, "render_source_snapshot_sha256": snapshot.snapshot_sha256,
        "render_source_sha256": snapshot.source_sha256, "render_source_size_bytes": snapshot.source_size_bytes}


class Repository:
    def __init__(self): self.versions, self.receipts, self.events = [], {}, []
    def find_preparation(self, command): return self.receipts.get(command.idempotency_key.value)
    def find_matching_source(self, identity, snapshot):
        if self.versions and self.versions[-1]["render_source_snapshot_sha256"] == snapshot.snapshot_sha256:
            return self.versions[-1]["id"]
        return None
    def append_source(self, command, identity, snapshot):
        self.events.append("append_source")
        self.versions.append({**stored_row(identity, snapshot), "id": 101 + len(self.versions),
            "version_number": 1 + len(self.versions),
            "replaces_document_version_id": None if not self.versions else self.versions[-1]["id"]})
        return self.versions[-1]["id"]
    def save_preparation(self, command, document_id):
        self.events.append("receipt")
        self.receipts[command.idempotency_key.value] = {"request": command.receipt_identity, "document_version_id": document_id}


@pytest.mark.parametrize("scope", ["client_contract", "staff_segment"])
def test_fresh_real_source_version_then_same_key_replay_and_changed_facts_new_version(template, scope):
    if scope == "staff_segment":
        template.template_key = "contract_staff_service"
        mapping = json.loads(template.mapping_path.read_text())
        mapping["id"] = template.template_key
        template.mapping_path.write_text(json.dumps(mapping), encoding="utf-8")
        template.mapping_sha256 = hashlib.sha256(template.mapping_path.read_bytes()).hexdigest()
    repository = Repository()
    workflow = RenderSourceWorkflow(repository)
    facts = {"name": "First", "amount": Decimal("100.25"), "date": date(2026, 11, 6)}
    def load():
        return 17, template, facts, hashlib.sha256(canonical_json({"name": facts["name"]}).encode()).hexdigest()
    original = request(scope)
    assert workflow.prepare(original, load) == (101, False)
    frozen = deepcopy(repository.versions[0])
    assert frozen["media_asset_id"] is None and frozen["render_source_kind"] == "render_snapshot"
    assert frozen["document_scope"] == scope and frozen["matching_plan_id"] == 17
    def forbidden(): pytest.fail("same-key replay must use the saved version without reading live facts")
    assert workflow.prepare(original, forbidden) == (101, True)
    facts["name"] = "Changed"
    assert workflow.prepare(replace(original, idempotency_key=IdempotencyKey("source:changed")), load) == (102, False)
    assert repository.versions[1]["replaces_document_version_id"] == 101
    assert repository.versions[0] == frozen
    assert load_workbook(BytesIO(rebuild_render_snapshot(frozen, template))).active["A1"].value == "First"
    assert load_workbook(BytesIO(rebuild_render_snapshot(repository.versions[1], template))).active["A1"].value == "Changed"
    assert repository.events == ["append_source", "receipt", "append_source", "receipt"]


def test_same_key_different_target_is_rejected_without_new_source_or_receipt(template):
    repository = Repository()
    workflow = RenderSourceWorkflow(repository)
    original = request()
    loader = lambda: (17, template, {"name": "name"}, "a" * 64)
    workflow.prepare(original, loader)
    with pytest.raises(UnsignedContractPdfError) as captured:
        workflow.prepare(replace(original, document_scope="staff_segment", matching_segment_id=71), loader)
    assert captured.value.code == "contract_unsigned_source_idempotency_conflict"
    assert len(repository.versions) == len(repository.receipts) == 1


def test_same_key_different_authenticated_actor_cannot_replay_another_operators_result(template):
    repository = Repository()
    workflow = RenderSourceWorkflow(repository)
    command = request()
    workflow.prepare(command, lambda: (17, template, {"name": "name"}, "a" * 64))
    def forbidden(): pytest.fail("actor conflict must be rejected before loading fresh facts")
    with pytest.raises(UnsignedContractPdfError) as captured:
        workflow.prepare(replace(command, actor=ActorContext("admin:2")), forbidden)
    assert captured.value.code == "contract_unsigned_source_idempotency_conflict"
    assert len(repository.versions) == len(repository.receipts) == 1


def test_source_template_must_belong_to_the_requested_contract_scope(template):
    repository = Repository()
    with pytest.raises(UnsignedContractPdfError) as captured:
        RenderSourceWorkflow(repository).prepare(request("staff_segment"), lambda: (17, template, {"name": "name"}, "a" * 64))
    assert captured.value.code == "contract_render_snapshot_template_scope_mismatch"
    assert repository.versions == [] and repository.receipts == {}


def test_prepare_and_send_cannot_share_one_key_for_different_operations(template):
    repository = Repository()
    workflow = RenderSourceWorkflow(repository)
    original = request()
    loader = lambda: (17, template, {"name": "name"}, "a" * 64)
    workflow.prepare(original, loader)
    with pytest.raises(UnsignedContractPdfError) as captured:
        workflow.prepare(replace(original, operation="send"), loader)
    assert captured.value.code == "contract_unsigned_source_idempotency_conflict"
    assert len(repository.versions) == len(repository.receipts) == 1


def test_snapshot_preserves_complete_render_input_types_without_document_bytes(template):
    facts = {"name": "name", "date": date(2026, 11, 6), "datetime": datetime(2026, 11, 6, tzinfo=timezone.utc),
        "decimal": Decimal("123.450"), "int": 7, "float": 0.25, "bool": True,
        "none": None, "list": ["a", 1], "tuple": ("b", 2), "dict": {"nested": Decimal("0.1")}}
    snapshot = create_render_snapshot(source(template), facts, template)
    value = json.loads(snapshot.payload)
    assert {_key: _decode(item) for _key, item in value["facts"].items()} == facts
    assert "base64" not in snapshot.payload and "PK" not in snapshot.payload
    first = rebuild_render_snapshot(stored_row(source(template), snapshot), template)
    assert first == rebuild_render_snapshot(stored_row(source(template), snapshot), template)
    assert hashlib.sha256(first).hexdigest() == snapshot.source_sha256


def test_canonical_zip_clocks_are_deterministic_and_qname_namespace_stays_bound():
    def workbook_bytes(year):
        workbook = Workbook()
        workbook.active["A1"] = "unchanged"
        workbook.properties.created = workbook.properties.modified = datetime(year, 1, 1)
        output = BytesIO(); workbook.save(output)
        return output.getvalue()
    first, second = canonical_xlsx(workbook_bytes(2020)), canonical_xlsx(workbook_bytes(2024))
    assert first == second
    with ZipFile(BytesIO(first)) as archive:
        assert archive.namelist() == sorted(archive.namelist())
        assert {entry.date_time for entry in archive.infolist()} == {(1980, 1, 1, 0, 0, 0)}
        document = parseString(archive.read("docProps/core.xml"))
        for element in document.getElementsByTagNameNS("http://purl.org/dc/terms/", "created"):
            prefix = element.getAttributeNS("http://www.w3.org/2001/XMLSchema-instance", "type").split(":")[0]
            ancestor = element
            while ancestor is not None and not ancestor.hasAttribute("xmlns:" + prefix):
                ancestor = ancestor.parentNode
                if ancestor is not None and not hasattr(ancestor, "hasAttribute"): ancestor = None
            assert ancestor is not None
            assert ancestor.getAttribute("xmlns:" + prefix) == "http://purl.org/dc/terms/"
            assert element.firstChild.data == "1980-01-01T00:00:00Z"
    assert load_workbook(BytesIO(first)).active["A1"].value == "unchanged"


@pytest.mark.parametrize("field", ["render_source_sha256", "render_source_snapshot_sha256", "render_source_size_bytes", "case_no", "matching_plan_id"])
def test_reconstruction_rejects_drift_in_original_root_snapshot_or_expected_bytes(template, field):
    identity = source(template)
    row = stored_row(identity, create_render_snapshot(identity, {"name": "name"}, template))
    row[field] = (row[field] + 1 if type(row[field]) is int else "different")
    with pytest.raises(UnsignedContractPdfError): rebuild_render_snapshot(row, template)


@pytest.mark.parametrize("filename", ["template_path", "mapping_path"])
def test_template_or_mapping_drift_never_reuses_new_live_facts(template, filename):
    identity = source(template)
    row = stored_row(identity, create_render_snapshot(identity, {"name": "old"}, template))
    getattr(template, filename).write_bytes(b"changed")
    with pytest.raises(UnsignedContractPdfError) as captured: rebuild_render_snapshot(row, template)
    assert captured.value.code == "contract_render_snapshot_template_stale"


@pytest.mark.parametrize("change", ["unknown_schema", "unknown_type", "unbound_root", "bool_plan", "extra_key"])
def test_closed_snapshot_payload_cannot_be_replaced_with_another_contract(template, change):
    identity = source(template)
    snapshot = create_render_snapshot(identity, {"name": "name"}, template)
    value = json.loads(snapshot.payload)
    if change == "unknown_schema": value["schema"] = "other"
    elif change == "unknown_type": value["facts"]["name"]["type"] = "bytes"
    elif change == "unbound_root": value["source"]["document_target_key"] = "staff-segment:9"
    elif change == "bool_plan": value["source"]["matching_plan_id"] = True
    else: value["file_bytes"] = "not-metadata"
    row = stored_row(identity, snapshot)
    row["render_source_snapshot"] = canonical_json(value)
    row["render_source_snapshot_sha256"] = hashlib.sha256(row["render_source_snapshot"].encode()).hexdigest()
    with pytest.raises(UnsignedContractPdfError): rebuild_render_snapshot(row, template)


@pytest.mark.parametrize("field", ["template_path", "mapping_path"])
def test_missing_template_or_mapping_is_typed_unavailable_without_live_fact_fallback(template, field):
    identity = source(template)
    row = stored_row(identity, create_render_snapshot(identity, {"name": "frozen"}, template))
    getattr(template, field).unlink()
    with pytest.raises(UnsignedContractPdfError) as captured: rebuild_render_snapshot(row, template)
    assert captured.value.code == "contract_render_snapshot_template_unavailable"
    assert captured.value.retryable and captured.value.category == "unavailable"
    assert str(getattr(template, field)) not in str(captured.value)


def test_unreadable_template_is_typed_unavailable(template, monkeypatch):
    from pathlib import Path
    identity = source(template)
    row = stored_row(identity, create_render_snapshot(identity, {"name": "frozen"}, template))
    original = Path.read_bytes
    def read(path):
        if path == template.template_path: raise PermissionError("private template path")
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", read)
    with pytest.raises(UnsignedContractPdfError) as captured: rebuild_render_snapshot(row, template)
    assert captured.value.code == "contract_render_snapshot_template_unavailable" and captured.value.retryable
    assert "private template path" not in str(captured.value)


def test_invalid_rebuilt_xlsx_zip_is_a_closed_owner_failure(template, monkeypatch):
    from subsystems.contract_signing import render_source_snapshot as module
    monkeypatch.setattr(module, "render_contract_template", lambda **_: b"invalid zip")
    with pytest.raises(UnsignedContractPdfError) as captured:
        create_render_snapshot(source(template), {"name": "frozen"}, template)
    assert captured.value.code == "contract_render_snapshot_content_invalid" and not captured.value.retryable


@pytest.mark.parametrize("change", [None, "actor", "version", "case", "fingerprint"])
def test_source_preparation_receipt_reuses_original_fingerprint_validator(change):
    from infrastructure.db.contract_unsigned_pdf_repository import _source_preparation_receipt
    from subsystems.contract_signing.command_receipts import _fingerprint
    value = {"request": request().receipt_identity, "document_version_id": 101}
    row = {"command_kind": "prepare_unsigned_source", "case_no": "CASE-1", "document_version_id": 101,
        "result_snapshot": deepcopy(value), "command_fingerprint": _fingerprint("prepare_unsigned_source", "CASE-1", value)}
    if change is None:
        assert _source_preparation_receipt(row) == value
        return
    if change == "actor": row["result_snapshot"]["request"]["actor_id"] = "admin:2"
    elif change == "version": row["document_version_id"] = 102
    elif change == "case": row["case_no"] = "OTHER"
    else: row["command_fingerprint"] = "b" * 64
    with pytest.raises(UnsignedContractPdfError) as captured: _source_preparation_receipt(row)
    assert captured.value.code == "contract_unsigned_source_receipt_invalid"


@pytest.mark.parametrize("scope", ["client", "staff"])
@pytest.mark.parametrize("delivery_failure", [False, True])
def test_original_sender_uses_real_snapshot_lineage_and_one_uow_without_unsigned_archive(template, monkeypatch, scope, delivery_failure):
    from subsystems.contract_signing import client_contract_application as client_module, staff_contract_application as staff_module
    from subsystems.contract_signing.line_delivery import ContractLineBinding
    module = client_module if scope == "client" else staff_module
    template.template_key = "contract_client_copy" if scope == "client" else "contract_staff_service"
    mapping = json.loads(template.mapping_path.read_text()); mapping["id"] = template.template_key
    template.mapping_path.write_text(json.dumps(mapping), encoding="utf-8")
    template.mapping_sha256 = hashlib.sha256(template.mapping_path.read_bytes()).hexdigest()
    repository, tasks, links = Repository(), [], []
    class Connection:
        commits = rollbacks = 0
        def begin(self): self.saved = (deepcopy(repository.versions), deepcopy(repository.receipts))
        def commit(self): self.commits += 1
        def rollback(self):
            self.rollbacks += 1
            repository.versions[:] = self.saved[0]
            repository.receipts.clear(); repository.receipts.update(self.saved[1])
            tasks.clear(); links.clear()
        def close(self): pass
    connection = Connection()
    class Delivery:
        def enqueue(self, command):
            tasks.append(command)
            if delivery_failure: raise RuntimeError("durable task registration failed")
            return SimpleNamespace(task_id=SimpleNamespace(value=91))
    monkeypatch.setattr(module, "_line_binding", lambda *_: ContractLineBinding("U" + "a" * 32,
        "bound", "customer" if scope == "client" else "staff", "3" if scope == "client" else "9"))
    monkeypatch.setattr(module, "_insert_access_grant", lambda _conn, _command, document_id, *_args, **_kwargs: (links.append(("grant", document_id)) or 81, "opaque-access-token"))
    monkeypatch.setattr(module, "_insert_sent_event", lambda _conn, _command, _facts, document_id, *_args: links.append(("event", document_id)) or 92)
    monkeypatch.setattr(module, "_append_command_outcome", lambda _conn, _command, _kind, document_id, *_args: links.append(("receipt", document_id)))
    if scope == "client":
        monkeypatch.setattr(module, "_client_contract_facts", lambda *_: {"matching_plan_id": 17, "client_id": 3})
        app = module.ClientContractSigningApplication(lambda: connection, archive_root=template.template_path.parent,
            now=lambda: datetime(2026, 11, 6, tzinfo=timezone.utc), template_facts_loader=lambda *_: {"name": "client"},
            render_source_repository_factory=lambda _: repository, line_delivery_repository_factory=lambda _: Delivery())
        command = module.SendClientContractCommand("CASE-1", "admin:1", IdempotencyKey("source:send"), CorrelationId("source:send"), "https://example.test/contracts")
    else:
        monkeypatch.setattr(module, "_staff_segment", lambda *_: {"id": 71, "plan_id": 17, "staff_id": 9})
        monkeypatch.setattr(module, "_staff_template_facts", lambda *_: {"name": "staff"})
        app = module.StaffContractSigningApplication(lambda: connection, archive_root=template.template_path.parent,
            now=lambda: datetime(2026, 11, 6, tzinfo=timezone.utc),
            render_source_repository_factory=lambda _: repository, line_delivery_repository_factory=lambda _: Delivery())
        command = module.SendStaffContractCommand("CASE-1", 71, "admin:1", IdempotencyKey("source:send"), CorrelationId("source:send"), "https://example.test/contracts")
    monkeypatch.setattr(app, "_archive", lambda *_: pytest.fail("unsigned sender must not archive bytes"))
    if delivery_failure:
        with pytest.raises(RuntimeError, match="durable task registration"):
            app._persist_sent_contract(command, template)
        assert connection.commits == 0 and connection.rollbacks == 1
        assert repository.versions == [] and repository.receipts == {} and tasks == links == []
    else:
        receipt = app._persist_sent_contract(command, template)
        assert receipt.document_version_id == 101 and receipt.line_delivery_task_id == 91
        assert connection.commits == 1 and connection.rollbacks == 0
        assert links == [("grant", 101), ("event", 101), ("receipt", 101)]
        assert len(tasks) == 1 and repository.versions[0]["media_asset_id"] is None
        assert repository.receipts["source:send"]["request"]["operation"] == "send"
