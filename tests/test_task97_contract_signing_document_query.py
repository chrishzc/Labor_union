"""Task 97 focused contract for the typed Contract Signing download query."""

from types import SimpleNamespace

from api.routes import contract_signing as route
from subsystems.contract_signing.document_query import (
    ContractSigningDocumentDownload,
    ContractSigningDocument,
    ContractSigningDocumentQueryApplication,
    ContractSigningStaffSegment,
    ContractSigningStatus,
)


class _Repository:
    def __init__(self, document):
        self.document = document
        self.calls = []

    def find_document_for_download(self, case_no, document_version_id):
        self.calls.append((case_no, document_version_id))
        return self.document


def test_contract_signing_document_query_is_bounded_and_typed():
    document = ContractSigningDocumentDownload(
        case_no="CASE-1",
        document_version_id=7,
        storage_key="CASE-1/client/7.pdf",
        sha256="a" * 64,
        mime_type="application/pdf",
        original_filename="signed.pdf",
    )
    repository = _Repository(document)
    application = ContractSigningDocumentQueryApplication(repository)

    assert application.find_document_for_download("CASE-1", 7) == document
    assert repository.calls == [("CASE-1", 7)]


def test_contract_signing_document_query_does_not_expose_missing_row_as_raw_data():
    repository = _Repository(None)
    application = ContractSigningDocumentQueryApplication(repository)

    assert application.find_document_for_download("CASE-1", 7) is None


def test_contract_signing_status_route_uses_typed_query_application():
    status = ContractSigningStatus(
        case_no="CASE-1",
        staff_segments=(ContractSigningStaffSegment(4, 9, True, False),),
        commitment_id=11,
        client_document_sent=True,
        client_signed_received=False,
        contract_identity="contract-1",
        documents=(
            ContractSigningDocument(
                document_version_id=7,
                scope="client_contract",
                role="template_generated",
                target_key="client",
                version_number=1,
                template_key="client-v1",
                template_sha256=None,
                mapping_sha256=None,
                archive_sha256="a" * 64,
                mime_type="application/pdf",
                file_size=3,
            ),
        ),
    )
    application = SimpleNamespace(query_status=lambda case_no: status)

    response = route.query_contract_signing(
        case_no="CASE-1", principal=SimpleNamespace(), application=application
    )

    assert response.data.case_no == "CASE-1"
    assert response.data.staff_segments[0].segment_id == 4
    assert response.data.documents[0].document_version_id == 7
