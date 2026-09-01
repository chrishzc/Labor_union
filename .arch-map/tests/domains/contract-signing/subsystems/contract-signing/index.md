subsystem: contract-signing
parent_domain: contract-signing
architecture: ../../../../../domains/contract-signing/subsystems/contract-signing/index.md
test_root: tests/domains/contract-signing/subsystems/contract-signing/
integration_root: tests/domains/contract-signing/subsystems/contract-signing/integration/
fixtures_root: tests/fixtures/

modules:
  staff-contract-application:
    layout_status: custom_current
    test_root: tests/test_staff_contract_signing_application.py

# Routing notes
Owner-local coverage includes external-signing domain/contracts/workflow, legacy manual recovery, final-document Q/P/A and preview token, Contract Signing API/download routes, contract renderer/LibreOffice adapter, unsigned-PDF application/storage/persistence/repository, external-signing repository, borrowed staff-completion adapter, and the Contract Signing-specific historical-baseline owner adapter.

# Deferred / higher-boundary
- `tests/test_contract_external_signing_schema_contract.py` — migration/release/schema contract and repo-relative `Path(__file__)` consumer; keep at the release/schema boundary.
- `tests/test_task97_contract_signing_document_query.py` — protected Task97 verification; keep at its Task97 boundary.
- `tests/integration/test_contract_unsigned_pdf_mysql_adapter.py` — explicitly targets the approved 1005 candidate database; keep at candidate-DB qualification boundary.
- `tests/test_contract_completion_workflow.py` — direct SUT is Orders Contract Completion, not Contract Signing.
- `tests/test_contract_context_router.py` — direct SUT is the separate `contract_integration` source boundary, which is not modeled here.

# Flat-test audit
After the direct `domains.contract_signing`, `subsystems.contract_signing`, Contract Signing API/adapter and owner-specific infrastructure searches, no additional high-confidence Contract Signing owner-local flat tests remain outside the documented Task97, release/schema, candidate-DB, Orders, `contract_integration`, or true cross-owner boundaries. Admit future cases by direct SUT/current ownership rather than filename alone.
