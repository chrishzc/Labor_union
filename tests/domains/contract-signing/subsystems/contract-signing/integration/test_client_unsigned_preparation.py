"""Current client PDF composition through typed ports; no SQL or NAS effects."""
from types import SimpleNamespace
import pytest
from api.dependencies.contract_external_signing import ContractExternalSigningApplication
from shared_kernel.identities import ActorContext, CorrelationId, IdempotencyKey
from subsystems.contract_signing.unsigned_contract_pdf import PreparedUnsignedContractPdf


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

def test_current_client_source_is_rendered_without_persisting_a_new_pdf_version():
    seen = []
    facade = SimpleNamespace(
        unsigned_repository=SimpleNamespace(load_current_pdf_for_source=lambda case, source: seen.append((case, source)) or None),
        unsigned_documents=SimpleNamespace(prepare=lambda command: seen.append(command.document_version_id) or PreparedUnsignedContractPdf(
            "CASE-1", 11, b"pdf", "application/pdf", "new-client.pdf", "test")),
    )
    documents = SimpleNamespace(prepare_external_document=lambda _command: (11, False))
    result = ContractExternalSigningApplication.prepare_client_unsigned(facade, "CASE-1", documents, ActorContext("admin:1"), IdempotencyKey("new:pdf"), CorrelationId("new:pdf"))
    assert seen == [("CASE-1", 11), 11]
    assert result["document_version_id"] == 11 and result["replayed"] is False

def test_missing_plan_rejection_is_a_typed_conflict():
    from subsystems.contract_signing.external_signing_contracts import ExternalSigningTypedError
    def reject(_command):
        raise ValueError("contract_external_signing_accepted_plan_required")
    with pytest.raises(ExternalSigningTypedError) as caught:
        ContractExternalSigningApplication.prepare_client_unsigned(SimpleNamespace(), "CASE-1", SimpleNamespace(prepare_external_document=reject), ActorContext("admin:1"), IdempotencyKey("signed:pdf"), CorrelationId("signed:pdf"))
    assert caught.value.category == "conflict"
    assert caught.value.code == "external_signing_accepted_plan_required"
