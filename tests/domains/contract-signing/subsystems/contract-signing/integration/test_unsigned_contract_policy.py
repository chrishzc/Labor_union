"""Current unsigned-draft policy through pure ports/AST, without executing SQL."""

import ast
import inspect
from types import SimpleNamespace

import pytest

from api.dependencies.contract_external_signing import ContractExternalSigningApplication
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.contract_signing.client_contract_application import ClientContractSigningApplication
from subsystems.contract_signing.staff_contract_application import StaffContractSigningApplication
from subsystems.contract_signing.unsigned_contract_pdf import (
    PreparedUnsignedContractPdf,
)


@pytest.mark.parametrize("scope", ["client", "staff"])
@pytest.mark.parametrize("historical_pdf", [False, True])
def test_http_composition_reuses_real_source_and_never_calls_retired_pdf_persistence(scope, historical_pdf):
    seen = []
    def source(_command):
        seen.append("source")
        return (11, True) if scope == "client" else SimpleNamespace(source_document_version_id=11, replayed=True)
    def current(case_no, source_id):
        seen.append((case_no, source_id))
        return SimpleNamespace(document_version_id=12, filename="old.pdf", mime_type="application/pdf", size_bytes=3) if historical_pdf else None
    def prepare(command):
        seen.append("render")
        assert command.document_version_id == 11
        return PreparedUnsignedContractPdf("CASE-1", 11, b"pdf", "application/pdf", "dynamic.pdf", "test")
    def forbidden(*_args, **_kwargs):
        pytest.fail("unsigned PDF must not be stored through retired CFS purpose")
    documents = SimpleNamespace(prepare_external_document=source)
    application = SimpleNamespace(
        staff_documents=documents,
        unsigned_repository=SimpleNamespace(load_current_pdf_for_source=current),
        unsigned_documents=SimpleNamespace(prepare=prepare),
        unsigned_persistence=SimpleNamespace(prepare_and_persist=forbidden),
    )
    args = (ActorContext("admin:1"), IdempotencyKey("draft:prepare"), CorrelationId("draft:prepare"))
    if scope == "client":
        result = ContractExternalSigningApplication.prepare_client_unsigned(application, "CASE-1", documents, *args)
    else:
        result = ContractExternalSigningApplication.prepare_staff_unsigned(application, "CASE-1", 71, *args)
    assert result["document_version_id"] == (12 if historical_pdf else 11)
    assert result["replayed"] is True
    assert seen == ["source", ("CASE-1", 11)] + ([] if historical_pdf else ["render"])


@pytest.mark.parametrize("owner", [ClientContractSigningApplication, StaffContractSigningApplication])
def test_real_source_entry_uses_snapshot_owner_without_archiving_draft_bytes(owner):
    # Inspect the real owner method; do not run its SQL, even through a fake cursor.
    import textwrap
    method = ast.parse(textwrap.dedent(inspect.getsource(owner.prepare_external_document)))
    calls = [node for node in ast.walk(method) if isinstance(node, ast.Call)]
    names = {node.func.id if isinstance(node.func, ast.Name) else node.func.attr
             for node in calls if isinstance(node.func, (ast.Name, ast.Attribute))}
    assert "RenderSourceWorkflow" in names
    assert not {"_archive", "_insert_generated_document", "render_contract_template"} & names


@pytest.mark.parametrize("owner", [ClientContractSigningApplication, StaffContractSigningApplication])
def test_current_sender_reuses_snapshot_owner_and_original_delivery_without_archiving_unsigned_bytes(owner):
    import textwrap
    method = ast.parse(textwrap.dedent(inspect.getsource(owner._persist_sent_contract)))
    calls = [node for node in ast.walk(method) if isinstance(node, ast.Call)]
    names = {node.func.id if isinstance(node.func, ast.Name) else node.func.attr
             for node in calls if isinstance(node.func, (ast.Name, ast.Attribute))}
    assert {"RenderSourceWorkflow", "_insert_access_grant", "enqueue", "_insert_sent_event", "_append_command_outcome"} <= names
    assert not {"_archive", "_insert_generated_document", "render_contract_template"} & names


def test_current_summary_reads_truthful_dynamic_metadata_with_original_authenticated_actor_per_request():
    seen = []
    def metadata(query):
        seen.append((query.document_version_id, query.actor.actor_id))
        return SimpleNamespace(document_version_id=query.document_version_id, filename="dynamic.pdf", mime_type="application/pdf", size_bytes=42)
    application = SimpleNamespace(unsigned_documents=SimpleNamespace(metadata=metadata))
    facts = SimpleNamespace(case_no="CASE-1", client_document_version_id=101,
        staff_targets=(SimpleNamespace(matching_segment_id=71, document_version_id=102),))
    actor = ActorContext("admin:7")
    for _ in range(2):
        rows = ContractExternalSigningApplication._unsigned_documents(application, facts, actor)
        assert {row["document_version_id"] for row in rows} == {101, 102}
        assert {row["size_bytes"] for row in rows} == {42}
        assert all("render_source_snapshot" not in row and "object_reference" not in row for row in rows)
    assert seen == [(101, "admin:7"), (102, "admin:7"), (101, "admin:7"), (102, "admin:7")]
